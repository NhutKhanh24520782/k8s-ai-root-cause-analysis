"""
scripts/data_collection/traffic_generator.py

Continuous synthetic traffic generator for AIOps Prometheus metrics collection.
Sends simulated user traffic through the API Gateway (or directly to microservices)
so that Prometheus records realistic, dynamic metrics during baseline and fault injection periods.

Usage:
    # Run continuous traffic at 5 requests/sec for 300 seconds
    python scripts/data_collection/traffic_generator.py --rate 5 --duration 300

    # Target custom API gateway URL
    python scripts/data_collection/traffic_generator.py --gateway http://localhost:8000 --rate 10
"""

import argparse
import random
import sys
import time
import urllib.error
import urllib.request
import json

ITEMS = [
    "MacBook Pro 16",
    "iPhone 15 Pro",
    "Sony WH-1000XM5",
    "Mechanical Keyboard",
    "Gaming Mouse",
    "4K Monitor",
    "Running Shoes",
    "Smart Watch",
]


def send_traffic_step(gateway_url: str) -> bool:
    gateway_url = gateway_url.rstrip("/")
    item = random.choice(ITEMS)
    qty = random.randint(1, 4)

    # 1. Create Order
    order_data = json.dumps({"item_name": item, "quantity": qty}).encode("utf-8")
    order_req = urllib.request.Request(
        f"{gateway_url}/orders",
        data=order_data,
        headers={"Content-Type": "application/json", "User-Agent": "AIOps-TrafficGen/1.0"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(order_req, timeout=8) as resp:
            if resp.status not in (200, 201):
                return False
            order_res = json.loads(resp.read().decode("utf-8"))
            order_id = order_res.get("order_id")

        if not order_id:
            return False

        # 2. Process Payment for this order
        payment_amount = round(random.uniform(25.0, 450.0), 2)
        payment_data = json.dumps({
            "order_id": order_id,
            "amount": payment_amount,
            "currency": "USD",
        }).encode("utf-8")

        payment_req = urllib.request.Request(
            f"{gateway_url}/payments",
            data=payment_data,
            headers={"Content-Type": "application/json", "User-Agent": "AIOps-TrafficGen/1.0"},
            method="POST",
        )

        with urllib.request.urlopen(payment_req, timeout=8) as p_resp:
            return p_resp.status in (200, 201)

    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False


def run_traffic_generator(gateway_url: str, rate: float, duration: int):
    print("=" * 60)
    print("AIOps Traffic Generator Started")
    print(f"Target Gateway: {gateway_url}")
    print(f"Rate: {rate} req/s | Duration: {'Infinite' if duration <= 0 else f'{duration}s'}")
    print("=" * 60)

    interval = 1.0 / max(rate, 0.1)
    start_time = time.time()
    total_sent = 0
    success_count = 0
    fail_count = 0

    try:
        while True:
            if duration > 0 and (time.time() - start_time) >= duration:
                break

            ok = send_traffic_step(gateway_url)
            total_sent += 1
            if ok:
                success_count += 1
            else:
                fail_count += 1

            if total_sent % 10 == 0:
                elapsed = round(time.time() - start_time, 1)
                print(f"[TrafficGen] Elapsed: {elapsed}s | Sent: {total_sent} | Success: {success_count} | Errors: {fail_count}")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n[TrafficGen] Interrupted by user.")

    print(f"[TrafficGen] Finished. Total: {total_sent}, Success: {success_count}, Errors: {fail_count}")


def main():
    parser = argparse.ArgumentParser(description="Synthetic traffic generator for microservices.")
    parser.add_argument("--gateway", default="http://localhost:8000", help="API Gateway URL")
    parser.add_argument("--rate", type=float, default=5.0, help="Target requests per second")
    parser.add_argument("--duration", type=int, default=0, help="Duration in seconds (0 = run forever)")
    args = parser.parse_args()

    run_traffic_generator(args.gateway, args.rate, args.duration)


if __name__ == "__main__":
    main()
