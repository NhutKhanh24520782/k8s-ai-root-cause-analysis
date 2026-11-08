$ErrorActionPreference = "Stop"

$OutputFile = ".\dataset\metrics_timeseries_v2.csv"
$IntervalSeconds = 5

$Services = @(
    @{ Name = "api-gateway"; Url = "http://localhost:8000/metrics"; Handler = "/orders" },
    @{ Name = "order-service"; Url = "http://localhost:8001/metrics"; Handler = "/orders" },
    @{ Name = "payment-service"; Url = "http://localhost:8002/metrics"; Handler = "/payments" }
)

function Get-MetricValue {
    param(
        [string]$Metrics,
        [string]$MetricName,
        [string]$Handler = ""
    )

    foreach ($line in ($Metrics -split "`n")) {
        if ($line -match '^\s*#') {
            continue
        }

        if ($line -match '^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{([^}]*)\})?\s+([0-9.eE+-]+)\s*$') {
            $name = $Matches[1]
            $labels = $Matches[3]
            $value = $Matches[4]

            if ($name -ne $MetricName) {
                continue
            }

            if ($Handler -and $labels -notmatch ('handler="' + [regex]::Escape($Handler) + '"')) {
                continue
            }

            $number = 0.0

            if ([double]::TryParse(
                $value,
                [Globalization.NumberStyles]::Float,
                [Globalization.CultureInfo]::InvariantCulture,
                [ref]$number
            )) {
                return $number
            }
        }
    }

    return $null
}

$Previous = @{}

if (-not (Test-Path $OutputFile)) {
    "timestamp,service,process_memory_mb,http_requests_in_flight,requests_total,request_rate_rps,latency_avg_ms,payment_attempts_total" |
        Set-Content -Path $OutputFile -Encoding utf8
}

Write-Host "Collecting metrics every $IntervalSeconds seconds."
Write-Host "Output: $OutputFile"
Write-Host "Press Ctrl+C to stop."

while ($true) {
    foreach ($Service in $Services) {
        try {
            $Metrics = (Invoke-RestMethod -Uri $Service.Url -TimeoutSec 3) -join "`n"

            $Memory = Get-MetricValue $Metrics "process_resident_memory_bytes"
            $InFlight = Get-MetricValue $Metrics "http_requests_in_flight"
            $Total = Get-MetricValue $Metrics "http_requests_total" $Service.Handler
            $Sum = Get-MetricValue $Metrics "http_request_duration_seconds_sum" $Service.Handler
            $Count = Get-MetricValue $Metrics "http_request_duration_seconds_count" $Service.Handler
            $Payments = Get-MetricValue $Metrics "payment_attempts_total"

            $Now = [DateTime]::UtcNow
            $Key = $Service.Name

            $Rate = ""
            $Latency = ""

            if (
                $Previous.ContainsKey($Key) -and
                $null -ne $Total -and
                $null -ne $Sum -and
                $null -ne $Count
            ) {
                $Old = $Previous[$Key]
                $Elapsed = ($Now - $Old.Time).TotalSeconds
                $DeltaCount = $Count - $Old.Count
                $DeltaSum = $Sum - $Old.Sum
                $DeltaTotal = $Total - $Old.Total

                if ($Elapsed -gt 0 -and $DeltaCount -ge 0 -and $DeltaSum -ge 0 -and $DeltaTotal -ge 0) {
                    $Rate = [math]::Round($DeltaTotal / $Elapsed, 4)

                    if ($Count -gt 0) {
                        $Latency = [math]::Round(($Sum / $Count) * 1000, 3)
                    }
                }
            }

            if ($null -ne $Total -and $null -ne $Sum -and $null -ne $Count) {
                $Previous[$Key] = @{
                    Time = $Now
                    Total = $Total
                    Sum = $Sum
                    Count = $Count
                }
            }

            $MemoryMB = ""
            if ($null -ne $Memory) {
                $MemoryMB = [math]::Round($Memory / 1MB, 3)
            }

            $InFlightValue = ""
            if ($null -ne $InFlight) {
                $InFlightValue = $InFlight
            }

            $TotalValue = ""
            if ($null -ne $Total) {
                $TotalValue = $Total
            }

            $PaymentsValue = ""
            if ($null -ne $Payments) {
                $PaymentsValue = $Payments
            }

            $Row = [pscustomobject]@{
                timestamp = $Now.ToString("o")
                service = $Service.Name
                process_memory_mb = $MemoryMB
                http_requests_in_flight = $InFlightValue
                requests_total = $TotalValue
                request_rate_rps = $Rate
                latency_avg_ms = $Latency
                payment_attempts_total = $PaymentsValue
            }

            $Row | Export-Csv -Path $OutputFile -Append -NoTypeInformation -Encoding utf8

            Write-Host "$($Service.Name): total=$Total rate=$Rate rps latency=$Latency ms"
        }
        catch {
            Write-Warning "$($Service.Name): $($_.Exception.Message)"
        }
    }

    Start-Sleep -Seconds $IntervalSeconds
}
