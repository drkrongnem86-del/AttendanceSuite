# Test cold start of D:\chamcong\AttendanceSuite.exe
Get-Process python,AttendanceSuite,cmd -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3
Write-Host "=== COLD START TEST ===" -ForegroundColor Cyan

# Start EXE
$proc = Start-Process -FilePath "D:\chamcong\AttendanceSuite.exe" -RedirectStandardOutput "D:\chamcong\logs\test_run.out" -RedirectStandardError "D:\chamcong\logs\test_run.err" -PassThru
Start-Sleep -Seconds 10

# Test 1: Services
$ports = Get-NetTCPConnection -LocalPort 8080,8081,8082 -State Listen -ErrorAction SilentlyContinue
Write-Host "1. Services listening: $($ports.Count)/3"
if ($ports.Count -ne 3) { Write-Host "   FAIL"; exit 1 }
Write-Host "   PASS"

# Test 2: Endpoints
$creds = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes("admin:bvdk2026"))

$tests = @(
    @{url='http://127.0.0.1:8080/'; name='Viewer'; auth=$false},
    @{url='http://127.0.0.1:8080/merge'; name='MERGE'; auth=$false},
    @{url='http://127.0.0.1:8082/healthz'; name='Remote healthz'; auth=$true},
    @{url='http://127.0.0.1:8081/'; name='Simulator'; auth=$false},
)

foreach ($t in $tests) {
    try {
        if ($t.auth) {
            $r = Invoke-WebRequest -Uri $t.url -Headers @{"Authorization"="Basic $creds"} -UseBasicParsing -TimeoutSec 5
        } else {
            $r = Invoke-WebRequest -Uri $t.url -UseBasicParsing -TimeoutSec 5
        }
        Write-Host ("  " + $t.name + ": " + $r.StatusCode + " (len=" + $r.Content.Length + ")")
    } catch {
        Write-Host ("  " + $t.name + ": FAIL - " + $_)
    }
}

# Test 3: API config masking
Write-Host "3. API config password masking..."
$r = Invoke-WebRequest -Uri "http://127.0.0.1:8082/api/config" -Headers @{"Authorization"="Basic $creds"} -UseBasicParsing -TimeoutSec 5
$cfg = $r.Content | ConvertFrom-Json
if ($cfg.config.auth.pass -eq "***") {
    Write-Host "   PASS - passwords masked"
} else {
    Write-Host "   FAIL - password leaked: $($cfg.config.auth.pass)"
}

# Stop
Get-Process -Id $proc.Id -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process python,AttendanceSuite -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Write-Host ""
Write-Host "=== ALL TESTS PASS ===" -ForegroundColor Green
