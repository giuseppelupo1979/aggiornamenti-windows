# Installazione: Python 3 (se manca), collegamento sul Desktop, apertura della pagina.
# Install: Python 3 (if missing), Desktop shortcut, opens the page.
$ErrorActionPreference = "Stop"
$Dir = $PSScriptRoot
$hasPy = Get-Command python.exe -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike "*WindowsApps*" }
if (-not $hasPy -and -not (Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue)) {
  Write-Output "Installo Python 3 / Installing Python 3..."
  winget install --id Python.Python.3.13 -e --source winget --scope user --silent --accept-source-agreements --accept-package-agreements --disable-interactivity
}
& "$Dir\aggiornamenti.ps1" shortcut | Out-Null
Write-Output "OK: collegamento Aggiornamenti sul Desktop / Desktop shortcut created"
& "$Dir\aggiornamenti.ps1" open
Write-Output "Pronto / Ready: http://127.0.0.1:8765"
Write-Output "Per aggiornamenti silenziosi attiva i privilegi di amministratore in fondo alla pagina."
Write-Output "For silent updates turn on administrator rights at the bottom of the page."
