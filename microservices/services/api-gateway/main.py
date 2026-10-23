import os
import time

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import (
    Counter,
    Histogram,
    generate_latest, 
    Gauge,
    CONTENT_TYPE_LATEST,
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

app = FastAPI(title="API Gateway")

ORDER_SERVICE_URL = os.getenv(
    "ORDER_SERVICE_URL",
    "http://order-service:8001",
)

PAYMENT_SERVICE_URL = os.getenv(
    "PAYMENT_SERVICE_URL",
    "http://payment-service:8002",
)



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


async def proxy_request(
    request: Request,
    service_url: str,
    path: str,
):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method=request.method,
                url=f"{service_url.rstrip('/')}/{path.lstrip('/')}",
                params=request.query_params,
                content=await request.body(),
                headers={
                    key: value
                    for key, value in request.headers.items()
                    if key.lower() not in {
                        "host",
                        "content-length",
                        "connection",
                    }
                },
            )

        return Response(
            content=response.content,
            status_code=response.status_code,
            headers={
                key: value
                for key, value in response.headers.items()
                if key.lower() not in {
                    "content-length",
                    "transfer-encoding",
                    "connection",
                }
            },
        )

    except httpx.RequestError:
        return JSONResponse(
            status_code=502,
            content={
                "detail": "Upstream service unavailable",
            },
        )


@app.api_route(
    "/orders",
    methods=["GET", "POST"],
)
@app.api_route(
    "/orders/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def orders(request: Request, path: str = ""):
    suffix = f"/{path}" if path else ""

    return await proxy_request(
        request,
        ORDER_SERVICE_URL,
        f"orders{suffix}",
    )


@app.api_route(
    "/payments",
    methods=["POST"],
)
@app.api_route(
    "/payments/{path:path}",
    methods=["POST"],
)
async def payments(request: Request, path: str = ""):
    suffix = f"/{path}" if path else ""

    return await proxy_request(
        request,
        PAYMENT_SERVICE_URL,
        f"payments{suffix}",
    )