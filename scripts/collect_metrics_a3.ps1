
param(
    [int]$IntervalSeconds = 5,
    [string]$FaultType = "normal",
    [string]$IncidentRunId = "baseline_local_001",
    [string]$OutputFile = ".\dataset\a3_metrics_timeseries.csv"
)

$ErrorActionPreference = "Stop"

if (-not [IO.Path]::IsPathRooted($OutputFile)) {
    $OutputFile = Join-Path (Split-Path $PSScriptRoot -Parent) $OutputFile
}

$OutputFile = [IO.Path]::GetFullPath($OutputFile)
$OutputDir = Split-Path $OutputFile -Parent
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$Services = @(
    @{ Name = "api-gateway"; Url = "http://localhost:8000/metrics"; Handler = "/orders"; Method = "POST" },
    @{ Name = "order-service"; Url = "http://localhost:8001/metrics"; Handler = "/orders"; Method = "POST" },
    @{ Name = "payment-service"; Url = "http://localhost:8002/metrics"; Handler = "/payments"; Method = "POST" }
)

$Columns = @(
    "timestamp", "incident_run_id", "fault_type", "data_source", "service",
    "request_rate_rps", "error_rate", "latency_avg_ms", "latency_p95_est_ms",
    "requests_total", "http_errors_total", "process_cpu_seconds_total",
    "process_memory_mb", "http_requests_in_flight", "payment_attempts_total",
    "pod_restart_count", "db_query_latency_p95_ms", "db_connection_count"
)

if (-not (Test-Path $OutputFile)) {
    ($Columns -join ",") | Set-Content -Path $OutputFile -Encoding utf8
}

function Get-Samples {
    param([string]$Text)

    $samples = [System.Collections.Generic.List[object]]::new()

    foreach ($line in ($Text -split '\r?\n')) {
        $line = $line.Trim()

        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
            continue
        }

        $m = [regex]::Match(
            $line,
            '^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{([^}]*)\})?\s+([0-9.eE+-]+)\s*$'
        )

        if (-not $m.Success) {
            continue
        }

        [double]$number = 0

        if (-not [double]::TryParse(
            $m.Groups[4].Value,
            [Globalization.NumberStyles]::Float,
            [Globalization.CultureInfo]::InvariantCulture,
            [ref]$number
        )) {
            continue
        }

        $labels = @{}
        $labelText = $m.Groups[3].Value

        if ($labelText) {
            foreach ($lm in [regex]::Matches($labelText, '(\w+)="([^"]*)"')) {
                $labels[$lm.Groups[1].Value] = $lm.Groups[2].Value
            }
        }

        $samples.Add([pscustomobject]@{
            Name = $m.Groups[1].Value
            Labels = $labels
            Value = $number
        })
    }

    return $samples.ToArray()
}

function Get-Sum {
    param(
        $Samples,
        [string]$Name,
        [string]$Handler = "",
        [string]$Method = ""
    )

    [double]$total = 0
    $found = $false

    foreach ($sample in $Samples) {
        if ($sample.Name -ne $Name) {
            continue
        }

        if ($Handler -and $sample.Labels["handler"] -ne $Handler) {
            continue
        }

        if ($Method -and $sample.Labels["method"] -ne $Method) {
            continue
        }

        $total += [double]$sample.Value
        $found = $true
    }

    if ($found) {
        return $total
    }

    return $null
}

function Get-P95 {
    param(
        $Samples,
        [string]$Handler,
        [string]$Method
    )

    $buckets = @($Samples | Where-Object {
        $_.Name -eq "http_request_duration_seconds_bucket" -and
        $_.Labels["handler"] -eq $Handler -and
        $_.Labels["method"] -eq $Method
    } | Sort-Object {
        if ($_.Labels["le"] -eq "+Inf") {
            [double]::PositiveInfinity
        } else {
            [double]$_.Labels["le"]
        }
    })

    if ($buckets.Count -eq 0) {
        return $null
    }

    $infinityBucket = $buckets |
        Where-Object { $_.Labels["le"] -eq "+Inf" } |
        Select-Object -First 1

    if ($null -eq $infinityBucket -or $infinityBucket.Value -le 0) {
        return $null
    }

    $target = $infinityBucket.Value * 0.95

    foreach ($bucket in $buckets) {
        if ($bucket.Value -ge $target) {
            if ($bucket.Labels["le"] -eq "+Inf") {
                return $null
            }

            return [math]::Round(([double]$bucket.Labels["le"]) * 1000, 3)
        }
    }

    return $null
}

$Previous = @{}

Write-Host "A3 metrics collector: every $IntervalSeconds seconds"
Write-Host "Output: $OutputFile"
Write-Host "Press Ctrl+C to stop."

while ($true) {
    foreach ($service in $Services) {
        try {
            $response = Invoke-WebRequest -Uri $service.Url -TimeoutSec 3
            $samples = @(Get-Samples -Text $response.Content)
            $now = [DateTime]::UtcNow
            $key = $service.Name

            $requests = @($samples | Where-Object {
                $_.Name -eq "http_requests_total" -and
                $_.Labels["handler"] -eq $service.Handler -and
                $_.Labels["method"] -eq $service.Method
            })

            $total = Get-Sum $samples "http_requests_total" $service.Handler $service.Method

            [double]$errors = 0

            foreach ($sample in $requests) {
                if ($sample.Labels["status"] -match '^5\d\d$') {
                    $errors += [double]$sample.Value
                }
            }

            $durationSum = Get-Sum $samples "http_request_duration_seconds_sum" $service.Handler $service.Method
            $durationCount = Get-Sum $samples "http_request_duration_seconds_count" $service.Handler $service.Method

            $memory = Get-Sum $samples "process_resident_memory_bytes"
            $cpu = Get-Sum $samples "process_cpu_seconds_total"
            $inFlight = Get-Sum $samples "http_requests_in_flight"
            $payments = Get-Sum $samples "payment_attempts_total"

            $rate = ""
            $errorRate = ""
            $latency = ""

            if ($null -ne $total -and $null -ne $durationSum -and $null -ne $durationCount) {
                if ($Previous.ContainsKey($key)) {
                    $old = $Previous[$key]
                    $elapsed = ($now - $old.Time).TotalSeconds

                    $deltaRequests = $total - $old.Total
                    $deltaErrors = $errors - $old.Errors
                    $deltaCount = $durationCount - $old.Count
                    $deltaSum = $durationSum - $old.Sum

                    if ($elapsed -gt 0 -and $deltaRequests -ge 0) {
                        $rate = [math]::Round($deltaRequests / $elapsed, 4)

                        if ($deltaRequests -gt 0) {
                            $errorRate = [math]::Round(($deltaErrors / $deltaRequests) * 100, 3)
                        } else {
                            $errorRate = 0
                        }
                    }

                    if ($deltaCount -gt 0 -and $deltaSum -ge 0) {
                        $latency = [math]::Round(($deltaSum / $deltaCount) * 1000, 3)
                    }
                }

                $Previous[$key] = @{
                    Time = $now
                    Total = $total
                    Errors = $errors
                    Sum = $durationSum
                    Count = $durationCount
                }
            }

            $memoryMB = ""
            $memorySample = $samples |
            Where-Object { $_.Name -eq "process_resident_memory_bytes" } |
            Select-Object -First 1

            if ($null -ne $memorySample) {
                $memoryMB = [math]::Round(([double]$memorySample.Value) / 1MB,3)
            }

            $row = [pscustomobject]@{
                timestamp = $now.ToString("o")
                incident_run_id = $IncidentRunId
                fault_type = $FaultType
                data_source = "local_prometheus_endpoint"
                service = $service.Name
                request_rate_rps = $rate
                error_rate = $errorRate
                latency_avg_ms = $latency
                latency_p95_est_ms = Get-P95 $samples $service.Handler $service.Method
                requests_total = $total
                http_errors_total = $errors
                process_cpu_seconds_total = $cpu
                process_memory_mb = $memoryMB
                http_requests_in_flight = $inFlight
                payment_attempts_total = $payments
                pod_restart_count = ""
                db_query_latency_p95_ms = ""
                db_connection_count = ""
            }

            $row | Select-Object $Columns |
                Export-Csv -Path $OutputFile -Append -NoTypeInformation -Encoding utf8

            Write-Host "$($service.Name): requests=$total rate=$rate error%=$errorRate latency_ms=$latency p95_ms=$($row.latency_p95_est_ms) memory_mb=$memoryMB cpu_seconds=$cpu"
        }
        catch {
            Write-Warning "$($service.Name): $($_.Exception.Message)"
        }
    }

    Start-Sleep -Seconds $IntervalSeconds
}
