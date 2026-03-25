param(
  [string]$Host = "127.0.0.1",
  [int]$Port = 15000,
  [ValidateSet("tcp","udp")][string]$Protocol = "tcp",
  [int]$Count = 4,
  [int]$Retries = 0
)

$ErrorActionPreference = "Stop"

Write-Host "==> Starting simulator (background)"
$simArgs = @("--host", $Host, "--port", "$Port")
if ($Protocol -eq "udp") { $simArgs += "--udp" }

$sim = Start-Process -FilePath "python" -ArgumentList @("tools/sim_server.py") + $simArgs -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 1

try {
  Write-Host "==> CLI smoke test"
  $cli = @"
wr D0100 1
ww D0100 0x1234
br D0100L 1
bw D0100L 0x12
bitr M0201
bitw M0201 1
quit
"@
  $cli | python tools/interactive_cli.py

  Write-Host "==> Auto RW test (basic)"
  python tools/auto_rw_test.py --host $Host --port $Port --protocol $Protocol --count $Count --retries $Retries --log auto_basic.log

  Write-Host "==> Auto RW test (extended)"
  python tools/auto_rw_test.py --host $Host --port $Port --protocol $Protocol --count $Count --retries $Retries --include-extended --log auto_ext.log

  Write-Host "==> Done"
}
finally {
  if ($sim -and !$sim.HasExited) {
    Write-Host "==> Stopping simulator"
    Stop-Process -Id $sim.Id -Force
  }
}
