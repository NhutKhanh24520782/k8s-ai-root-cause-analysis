import os
import time
from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field
from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
    Gauge,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo bảng khi service khởi động.
    last_error = None

    for _ in range(20):
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("""
                        CREATE TABLE IF NOT EXISTS orders (
                            id SERIAL PRIMARY KEY,
                            order_id UUID NOT NULL UNIQUE,
                            item_name VARCHAR(200) NOT NULL,
                            quantity INTEGER NOT NULL
                                CHECK (quantity > 0),
                            status VARCHAR(30) NOT NULL
                                DEFAULT 'created',
                            created_at TIMESTAMPTZ NOT NULL
                                DEFAULT NOW()
                        )
                    """)
                )

            last_error = None
            break

        except SQLAlchemyError as exc:
            last_error = exc
            time.sleep(2)

    if last_error:
        raise RuntimeError(
            f"Cannot initialize PostgreSQL: {last_error}"
        )

    yield
    engine.dispose()


app = FastAPI(
    title="Order Service",
    lifespan=lifespan,
)


class OrderCreate(BaseModel):
    item_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(gt=0)


class OrderUpdate(BaseModel):
    item_name: str | None = Field(default=None, min_length=1)
    quantity: int | None = Field(default=None, gt=0)
    status: str | None = None


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
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


def serialize_order(row):
    result = dict(row._mapping)

    if result.get("created_at"):
        result["created_at"] = (
            result["created_at"].isoformat()
        )

    return result


@app.get("/orders")
def list_orders():
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT * FROM orders ORDER BY id")
            ).fetchall()

        return [serialize_order(row) for row in rows]

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )


@app.post("/orders", status_code=201)
def create_order(order: OrderCreate):
    order_id = uuid.uuid4()
    try:
        with engine.begin() as connection:
            row = connection.execute(
                text("""
                    INSERT INTO orders (order_id, item_name, quantity)
                    VALUES (:order_id, :item_name, :quantity)
                    RETURNING *
                """),
                {**order.model_dump(), "order_id": str(order_id)},
            ).fetchone()

            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Order not found",
                )

        return serialize_order(row)

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )


@app.get("/orders/{order_id}")
def get_order(order_id: uuid.UUID):
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text("""
                    SELECT * FROM orders
                    WHERE order_id = :order_id
                """),
                {"order_id": order_id},
            ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Order not found",
            )

        return serialize_order(row)

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )


@app.put("/orders/{order_id}")
def update_order(
    order_id: uuid.UUID,
    order: OrderUpdate,
):
    values = {
        key: value
        for key, value in order.model_dump().items()
        if value is not None
    }

    if not values:
        raise HTTPException(
            status_code=400,
            detail="No fields supplied",
        )

    assignments = ", ".join(
        f"{key} = :{key}" for key in values
    )
    values["order_id"] = order_id

    try:
        with engine.begin() as connection:
            row = connection.execute(
                text(f"""
                    UPDATE orders
                    SET {assignments}
                    WHERE order_id = :order_id
                    RETURNING *
                """),
                values,
            ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Order not found",
            )

        return serialize_order(row)

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )


@app.delete("/orders/{order_id}", status_code=204)
def delete_order(order_id: uuid.UUID):
    try:
        with engine.begin() as connection:
            result = connection.execute(
                text("""
                    DELETE FROM orders
                    WHERE order_id = :order_id
                """),
                {"order_id": order_id},
            )

        if result.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Order not found",
            )

        return Response(status_code=204)

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )