
$ErrorActionPreference = "Continue"

$services = @(
    @{ Name = "api-gateway";   Port = 8000 },
    @{ Name = "order-service"; Port = 8001 },
    @{ Name = "payment-service"; Port = 8002 }
)

$failed = 0

Write-Host "`n========== MICROSERVICES SMOKE TEST ==========" -ForegroundColor Cyan

foreach ($service in $services) {
    $name = $service.Name
    $port = $service.Port
    $baseUrl = "http://localhost:$port"

    Write-Host "`n[$name] $baseUrl" -ForegroundColor Yellow

    # Test health endpoint
    try {
        $health = Invoke-WebRequest `
            -Uri "$baseUrl/health" `
            -Method Get `
            -TimeoutSec 5 `
            -UseBasicParsing

        if ($health.StatusCode -eq 200) {
            Write-Host "[PASS] GET /health -> $($health.StatusCode)" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] GET /health -> $($health.StatusCode)" -ForegroundColor Red
            $failed++
        }
    } catch {
        Write-Host "[FAIL] GET /health -> $($_.Exception.Message)" -ForegroundColor Red
        $failed++
    }

    # Test Prometheus metrics endpoint
    try {
        $metrics = Invoke-WebRequest `
            -Uri "$baseUrl/metrics" `
            -Method Get `
            -TimeoutSec 5 `
            -UseBasicParsing

        if ($metrics.StatusCode -eq 200 -and
            $metrics.Content -match "process_|python_|http_") {
            Write-Host "[PASS] GET /metrics -> Prometheus metrics found" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] GET /metrics -> No expected metrics found" -ForegroundColor Red
            $failed++
        }
    } catch {
        Write-Host "[FAIL] GET /metrics -> $($_.Exception.Message)" -ForegroundColor Red
        $failed++
    }
}

Write-Host "`n========== SUMMARY ==========" -ForegroundColor Cyan

if ($failed -eq 0) {
    Write-Host "ALL TESTS PASSED" -ForegroundColor Green
    exit 0
} else {
    Write-Host "$failed TEST(S) FAILED" -ForegroundColor Red
    exit 1
}
