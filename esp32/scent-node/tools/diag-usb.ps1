# Read-only USB/serial diagnostics for the ESP32's CP2102 (changes nothing).
# Run: Terminal > Run Task > "XRPod: diagnose ESP32 USB"
$ErrorActionPreference = 'Continue'
$port = 'COM3'

function Prop($id, $key) {
  (Get-PnpDeviceProperty -InstanceId $id -KeyName $key -ErrorAction SilentlyContinue).Data
}

Write-Host "`n== Silicon Labs CP210x devices (VID 10C4), including unplugged ghosts ==" -ForegroundColor Cyan
Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_10C4' } | ForEach-Object {
  [pscustomobject]@{
    Name          = $_.FriendlyName
    Present       = $_.Present
    Status        = $_.Status
    ProblemCode   = Prop $_.InstanceId 'DEVPKEY_Device_ProblemCode'
    DriverVersion = Prop $_.InstanceId 'DEVPKEY_Device_DriverVersion'
    DriverInf     = Prop $_.InstanceId 'DEVPKEY_Device_DriverInfPath'
    InstanceId    = $_.InstanceId
  }
} | Format-List

Write-Host "== Serial ports Windows reports ==" -ForegroundColor Cyan
[System.IO.Ports.SerialPort]::GetPortNames()
Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match '\(COM\d+\)' } |
  Select-Object Name, Status, ConfigManagerErrorCode, PNPDeviceID | Format-Table -AutoSize

Write-Host "== CP210x driver packages installed ==" -ForegroundColor Cyan
pnputil /enum-drivers 2>$null | Select-String -Context 1,5 'silabser|slabvcp'

Write-Host "== Open $port with .NET ==" -ForegroundColor Cyan
try {
  $p = New-Object System.IO.Ports.SerialPort $port, 115200
  $p.Open(); "OPEN OK"; $p.Close()
} catch { "OPEN FAILED: $($_.Exception.Message)" }

Write-Host "`n== esptool chip_id on $port ==" -ForegroundColor Cyan
$py = Join-Path $env:USERPROFILE '.platformio\penv\Scripts\python.exe'
$et = Join-Path $env:USERPROFILE '.platformio\packages\tool-esptoolpy\esptool.py'
if ((Test-Path $py) -and (Test-Path $et)) {
  & $py $et --port $port --baud 115200 chip_id 2>&1 | Select-Object -First 25
} else { "esptool not found" }

Write-Host "`n== Programs that often hold serial ports ==" -ForegroundColor Cyan
Get-Process -ErrorAction SilentlyContinue |
  Where-Object { $_.ProcessName -match 'arduino|putty|cura|serial|teraterm|esptool|cubeide|cubeprog|termite|realterm' } |
  Select-Object ProcessName, Id | Format-Table -AutoSize
Write-Host "`nDone." -ForegroundColor Green
