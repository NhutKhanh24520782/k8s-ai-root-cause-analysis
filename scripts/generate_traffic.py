"""
scripts/generate_traffic.py

Generates synthetic user traffic against the API Gateway to create realistic
baseline request throughput and enable fault injections to manifest real errors/latencies.

Usage:
    # Generate ~5 requests per second continuously
    python scripts/generate_traffic.py --rate 5 --gateway-url http://localhost:8000

    # Run for 300 seconds then stop
    python scripts/generate_traffic.py --rate 5 --duration 300
"""

import argparse
import json
import random
import sys
import time
import urllib.request
import urllib.error

ITEMS = ["Laptop", "Mouse", "Keyboard", "Monitor", "Headphones", "USB Drive"]

def send_request(url: str, method: str = "GET", data: dict = None) -> tuple:
    headers = {"User-Agent": "RCA-Traffic-Generator"}
    payload = None
    if data:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            duration = (time.perf_counter() - start) * 1000
            try:
                body = json.loads(resp.read().decode("utf-8"))
            except Exception:
                body = {}
            return resp.status, duration, body
    except urllib.error.HTTPError as e:
        duration = (time.perf_counter() - start) * 1000
        return e.code, duration, {}
    except Exception as e:
        return 0, 0.0, {}

def run_load(gateway_url: str, rate_rps: float, duration: int):
    base_url = gateway_url.rstrip("/")
    interval = 1.0 / max(0.1, rate_rps)
    end_time = (time.time() + duration) if duration > 0 else float("inf")

    print(f"[*] Starting synthetic traffic against {base_url} at {rate_rps} req/s...")
    print(f"[*] Driving /orders and /payments pipelines...")
    print(f"[*] Duration: {'Infinite' if duration <= 0 else f'{duration}s'}. Press Ctrl+C to stop.\n")

    sent = 0
    errors = 0

    while time.time() < end_time:
        # 1. Create Order
        item = random.choice(ITEMS)
        qty = random.randint(1, 5)
        status, lat, body = send_request(f"{base_url}/orders", method="POST", data={"item_name": item, "quantity": qty})

        sent += 1
        if status >= 500:
            errors += 1

        # 2. Process Payment for Order
        order_id = body.get("order_id") if isinstance(body, dict) else None
        if order_id:
            pay_status, pay_lat, _ = send_request(
                f"{base_url}/payments",
                method="POST",
                data={
                    "order_id": order_id,
                    "amount": round(random.uniform(10.0, 500.0), 2),
                    "currency": "USD",
                },
            )
            sent += 1
            if pay_status >= 500:
                errors += 1

        # Periodic log
        if sent % 20 == 0:
            err_pct = (errors / sent) * 100 if sent > 0 else 0
            print(f"[*] Sent: {sent:5d} reqs | 5xx Errors: {errors:4d} ({err_pct:5.1f}%) | Last Latency: {lat:6.1f}ms (HTTP {status})")

        time.sleep(interval)

    print(f"\n[OK] Traffic generation complete. Sent: {sent}, 5xx Errors: {errors}")

def main():
    parser = argparse.ArgumentParser(description="Synthetic traffic generator for microservices.")
    parser.add_argument("--gateway-url", default="http://localhost:8000", help="API Gateway URL")
    parser.add_argument("--rate", type=float, default=5.0, help="Requests per second")
    parser.add_argument("--duration", type=int, default=0, help="Run duration in seconds (0 for infinite)")
    args = parser.parse_args()

    try:
        run_load(args.gateway_url, args.rate, args.duration)
    except KeyboardInterrupt:
        print("\n[*] Stopped by user.")

if __name__ == "__main__":
    main()

