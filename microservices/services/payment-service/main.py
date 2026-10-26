
import os
import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


# ==========================================
# Database configuration
# ==========================================

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

# ==========================================
# Prometheus metrics
# ==========================================

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "handler", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "handler"],
)

HTTP_REQUESTS_IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "Number of HTTP requests currently being processed",
)

PAYMENT_ATTEMPTS = Counter(
    "payment_attempts_total",
    "Total payment attempts",
)

PAYMENT_FAILURES = Counter(
    "payment_failures_total",
    "Total failed payment attempts",
)

# ==========================================
# Application configuration
# ==========================================

SIMULATE_FAILURE = (
    os.getenv("SIMULATE_PAYMENT_FAILURE", "false").lower()
    in {"true", "1", "yes"}
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    last_error = None

    # Wait for PostgreSQL to become available.
    for _ in range(20):
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("""
                        CREATE TABLE IF NOT EXISTS payments (
                            id SERIAL PRIMARY KEY,
                            payment_id UUID NOT NULL UNIQUE,
                            order_id INTEGER NOT NULL CHECK (order_id > 0),
                            amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
                            currency VARCHAR(3) NOT NULL,
                            status VARCHAR(20) NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                    """)
                )

            last_error = None
            break

        except SQLAlchemyError as exc:
            last_error = exc
            time.sleep(2)

    if last_error:
        engine.dispose()
        raise RuntimeError(
            f"Cannot initialize Payment PostgreSQL: {last_error}"
        )

    yield
    engine.dispose()


app = FastAPI(
    title="Payment Service",
    lifespan=lifespan,
)


# ==========================================
# Request models
# ==========================================

class PaymentRequest(BaseModel):
    order_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)


# ==========================================
# Prometheus middleware
# ==========================================

@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    start_time = time.perf_counter()

    method = request.method
    handler = request.url.path
    status = "500"

    HTTP_REQUESTS_IN_FLIGHT.inc()

    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response

    finally:
        duration = time.perf_counter() - start_time

        # Prefer route templates to avoid high-cardinality labels.
        route = request.scope.get("route")
        if route is not None:
            handler = getattr(route, "path", handler)

        HTTP_REQUESTS.labels(
            method=method,
            handler=handler,
            status=status,
        ).inc()

        HTTP_REQUEST_DURATION.labels(
            method=method,
            handler=handler,
        ).observe(duration)

        HTTP_REQUESTS_IN_FLIGHT.dec()


# ==========================================
# Health and readiness
# ==========================================

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/ready")
def readiness():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "database": "connected",
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "database": "disconnected",
            },
        )


@app.get("/metrics")
def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# ==========================================
# Payment endpoints
# ==========================================

@app.post("/payments", status_code=201)
def create_payment(payment: PaymentRequest):
    PAYMENT_ATTEMPTS.inc()

    payment_id = uuid.uuid4()
    status = "failed" if SIMULATE_FAILURE else "succeeded"

    try:
        with engine.begin() as connection:
            row = connection.execute(
                text("""
                    INSERT INTO payments (
                        payment_id,
                        order_id,
                        amount,
                        currency,
                        status
                    )
                    VALUES (
                        :payment_id,
                        :order_id,
                        :amount,
                        :currency,
                        :status
                    )
                    RETURNING
                        id,
                        payment_id,
                        order_id,
                        amount,
                        currency,
                        status,
                        created_at
                """),
                {
                    "payment_id": payment_id,
                    "order_id": payment.order_id,
                    "amount": payment.amount,
                    "currency": payment.currency.upper(),
                    "status": status,
                },
            ).fetchone()

        result = dict(row._mapping)
        result["payment_id"] = str(result["payment_id"])
        result["amount"] = str(result["amount"])
        result["created_at"] = result["created_at"].isoformat()

        if SIMULATE_FAILURE:
            PAYMENT_FAILURES.inc()

            # The failed attempt remains recorded in the database.
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Simulated payment failure",
                    "payment": result,
                },
            )

        return result

    except HTTPException:
        raise

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Payment database unavailable",
        )


@app.get("/payments")
def list_payments():
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text("""
                    SELECT *
                    FROM payments
                    ORDER BY id
                """)
            ).fetchall()

        results = []

        for row in rows:
            item = dict(row._mapping)
            item["payment_id"] = str(item["payment_id"])
            item["amount"] = str(item["amount"])
            item["created_at"] = item["created_at"].isoformat()
            results.append(item)

        return results

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Payment database unavailable",
        )


@app.get("/payments/{payment_id}")
def get_payment(payment_id: uuid.UUID):
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text("""
                    SELECT *
                    FROM payments
                    WHERE payment_id = :payment_id
                """),
                {"payment_id": payment_id},
            ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Payment not found",
            )

        result = dict(row._mapping)
        result["payment_id"] = str(result["payment_id"])
        result["amount"] = str(result["amount"])
        result["created_at"] = result["created_at"].isoformat()

        return result

    except HTTPException:
        raise

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Payment database unavailable",
        )
