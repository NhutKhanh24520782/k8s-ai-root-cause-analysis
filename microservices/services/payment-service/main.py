from asyncio.log import logger
import os
import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

import httpx

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

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

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

import random

SIMULATE_FAILURE = (
    os.getenv("SIMULATE_PAYMENT_FAILURE", "false").lower() in {"true", "1", "yes"}
    or os.getenv("FAULT_TYPE", "").lower() == "payment_failure"
)
FAULT_PROBABILITY = float(os.getenv("FAULT_PROBABILITY", "0.85"))

SIMULATE_MEMORY_LEAK = (
    os.getenv("SIMULATE_MEMORY_LEAK", "false").lower() in {"true", "1", "yes"}
    or os.getenv("FAULT_TYPE", "").lower() == "memory_leak"
)
MEMORY_LEAK_RATE_MB = int(os.getenv("MEMORY_LEAK_RATE_MB", "15"))
_LEAK_BUFFER = []

ORDER_SERVICE_URL = os.getenv(
    "ORDER_SERVICE_URL",
    "http://order-service:8001",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    last_error = None

    for _ in range(20):
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("""
                        CREATE TABLE IF NOT EXISTS payments (
                            id SERIAL PRIMARY KEY,
                            payment_id UUID NOT NULL UNIQUE,
                            order_id UUID NOT NULL,
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

class PaymentRequest(BaseModel):
    order_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)

class PaymentUpdate(BaseModel):
    order_id: uuid.UUID
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Za-z]{3}$",
    )
    status: str | None = Field(
        default=None,
        pattern=r"^(pending|succeeded|failed|cancelled)$",
    )

@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    start_time = time.perf_counter()

    if SIMULATE_MEMORY_LEAK:
        try:
            _LEAK_BUFFER.append(bytearray(1024 * 1024 * MEMORY_LEAK_RATE_MB))
        except MemoryError:
            pass

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

def serialize_payment(row):
    result = dict(row._mapping)

    if result.get("created_at"):
        result["created_at"] = (
            result["created_at"].isoformat()
        )

    return result

async def validate_order(order_id: uuid.UUID) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{ORDER_SERVICE_URL.rstrip('/')}/orders/{order_id}"
            )

        if response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Order not found",
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail="Unable to validate order",
            )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Order service unavailable",
        )

@app.post("/payments", status_code=201)
async def create_payment(payment: PaymentRequest):
    PAYMENT_ATTEMPTS.inc()

    if SIMULATE_FAILURE and random.random() < FAULT_PROBABILITY:
        raise HTTPException(
            status_code=500,
            detail="Simulated Payment Gateway Service Exception (500 Internal Error)",
        )

    await validate_order(payment.order_id)

    payment_id = uuid.uuid4()
    status = "succeeded"

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
                    RETURNING *
                """),
                {
                    **payment.model_dump(),
                    "payment_id": str(payment_id),
                    "order_id": str(payment.order_id),
                    "status": status,
                    "currency": payment.currency.upper(),
                },
            ).fetchone()

        return serialize_payment(row)

    except SQLAlchemyError:
        logger.exception("Failed to create payment")

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

        return [serialize_payment(row) for row in rows]

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

        return serialize_payment(row)

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Payment database unavailable",
        )

@app.delete(
    "/payments/{payment_id}",
    status_code=204,
)
def delete_payment(payment_id: uuid.UUID):
    try:
        with engine.begin() as connection:
            result = connection.execute(
                text("""
                    DELETE FROM payments
                    WHERE payment_id = :payment_id
                """),
                {"payment_id": payment_id},
            )

        if result.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Payment not found",
            )

        return Response(status_code=204)

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Payment database unavailable",
        )
