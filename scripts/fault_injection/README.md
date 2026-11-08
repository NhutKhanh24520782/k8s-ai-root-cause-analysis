# Fault Injection Scripts — A3.1 (Đình Tân + Phước Thọ)

This directory contains automated scripts to inject controlled microservice faults for building the Root Cause Analysis dataset.

## Supported Fault Scenarios

| Fault Label | Target Component | Injection Method | Expected Symptoms |
|---|---|---|---|
| `normal` | Entire System | None (healthy baseline) | Low latency, 0 error rate, normal CPU/Memory |
| `cpu_stress` | `order-service` | stress-ng / CPU burn loop | Pod CPU spike (>80%), moderate latency increase |
| `payment_failure` | `payment-service` | Env `SIMULATE_PAYMENT_FAILURE=true` | 500 status codes, error rate jump |
| `db_slowness` | `order-service` | Env `SIMULATE_DB_DELAY=true` (+500ms) | p95 DB and order latency spike |
| `memory_leak` | `payment-service` | Env `SIMULATE_MEMORY_LEAK=true` | Resident memory growth over time |
| `network_latency` | Network link | `tc netem` or artificial delay | Gateway and cross-service p95 latency surge |

## Usage

### Individual Fault Injections:
```bash
# Inject payment failure
python scripts/fault_injection/inject_payment_failure.py
# Restore payment-service
python scripts/fault_injection/inject_payment_failure.py --restore

# Inject CPU stress
python scripts/fault_injection/inject_cpu_stress.py --service order-service --duration 300

# Inject DB slowness
python scripts/fault_injection/inject_db_slowness.py --delay-ms 500
# Restore DB latency
python scripts/fault_injection/inject_db_slowness.py --restore

# Inject memory leak
python scripts/fault_injection/inject_memory_leak.py --service payment-service --rate-mb 20
# Restore memory leak
python scripts/fault_injection/inject_memory_leak.py --restore --service payment-service

# Inject network latency
python scripts/fault_injection/inject_network_latency.py --service order-service --delay-ms 200
# Restore network latency
python scripts/fault_injection/inject_network_latency.py --restore --service order-service
```

### Complete Automated Cycle (Step 1 to 6 in PDF):
```bash
python scripts/fault_injection/run_collection_cycle.py --duration-per-fault 300 --baseline-wait 120
```
