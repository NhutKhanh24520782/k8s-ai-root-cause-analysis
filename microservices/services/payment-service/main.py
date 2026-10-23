import os
import time
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


app = FastAPI(title="Payment Service")

SIMULATE_FAILURE = (
    os.getenv("SIMULATE_PAYMENT_FAILURE", "false").lower()
    in {"true", "1", "yes"}
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

PAYMENT_FAILURES = Counter(
    "payment_failures_total",
    "Total failed payment attempts",
)


class PaymentRequest(BaseModel):
    order_id: int = Field(gt=0)
    amount: float = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


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


@app.get("/metrics")
def metrics():
    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.post("/payments", status_code=201)
def create_payment(payment: PaymentRequest):
    PAYMENT_ATTEMPTS.inc()

    if SIMULATE_FAILURE:
        PAYMENT_FAILURES.inc()

        raise HTTPException(
            status_code=503,
            detail="Simulated payment failure",
        )

    return {
        "payment_id": str(uuid.uuid4()),
        "order_id": payment.order_id,
        "amount": payment.amount,
        "currency": payment.currency.upper(),
        "status": "succeeded",
    }