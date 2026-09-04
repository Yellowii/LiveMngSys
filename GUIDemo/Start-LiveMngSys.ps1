param(
  [switch]$NoBrowser,
  [int]$GuiPort = 7000
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$launcher = Join-Path $root 'Start-LiveMngSys.ps1'

& $launcher -NoBrowser:$NoBrowser -GuiPort $GuiPort
exit $LASTEXITCODE
