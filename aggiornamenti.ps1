# aggiornamenti - avvia il server locale e apre la pagina.
#
#   aggiornamenti            avvia (se serve) e apre la pagina
#   aggiornamenti start      avvia in background senza aprire la pagina
#   aggiornamenti stop       ferma il server
#   aggiornamenti demo       modalita demo (dati finti, nessuna modifica al sistema)
#   aggiornamenti shortcut   crea il collegamento "Aggiornamenti" sul Desktop
#   aggiornamenti version    mostra la versione
#   $env:AGG_PORT=9000       usa un'altra porta invece della 8765
param([string]$Action = "open")
$ErrorActionPreference = "Stop"
$Dir = $PSScriptRoot
$Port = if ($env:AGG_PORT) { [int]$env:AGG_PORT } else { 8765 }

function Find-Python {
  foreach ($c in @("pythonw.exe", "python.exe")) {
    $p = Get-Command $c -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike "*WindowsApps*" } | Select-Object -First 1
    if ($p) { return $p.Source }
  }
  $py = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\pythonw.exe", "$env:ProgramFiles\Python3*\pythonw.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
  if ($py) { return $py.FullName }
  throw "Python 3 non trovato / not found: esegui installa.ps1 / run installa.ps1"
}

function Test-Up([int]$p) {
  try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$p/api/state" | Out-Null; return $true } catch { return $false }
}

function Start-Server([int]$p, [string[]]$extra) {
  if (Test-Up $p) { return }
  # se esiste l'attivita con privilegi, si parte da li (nessuna richiesta di Windows)
  if (-not $extra -and $p -eq 8765) {
    schtasks /Run /TN "Aggiornamenti" 2>$null | Out-Null
    for ($i = 0; $i -lt 10; $i++) { if (Test-Up $p) { return }; Start-Sleep -Milliseconds 500 }
  }
  $env:AGG_PORT = "$p"
  Start-Process -FilePath (Find-Python) -ArgumentList (@("`"$Dir\server.py`"") + $extra) -WindowStyle Hidden
  for ($i = 0; $i -lt 40; $i++) { if (Test-Up $p) { return }; Start-Sleep -Milliseconds 500 }
  throw "Il server non risponde / Server not responding"
}

switch ($Action) {
  "open"     { Start-Server $Port @(); Start-Process "http://127.0.0.1:$Port" }
  "start"    { Start-Server $Port @() }
  "stop"     { Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force } }
  "demo"     { Start-Server 8766 @("--demo"); Start-Process "http://127.0.0.1:8766" }
  "shortcut" {
    $lnk = (New-Object -ComObject WScript.Shell).CreateShortcut("$([Environment]::GetFolderPath('Desktop'))\Aggiornamenti.lnk")
    $lnk.TargetPath = "powershell.exe"
    $lnk.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Dir\aggiornamenti.ps1`" open"
    $lnk.IconLocation = "$env:SystemRoot\System32\shell32.dll,238"
    $lnk.Description = "Aggiornamenti"
    $lnk.Save(); Write-Output $lnk.FullName
  }
  "version"  { (Select-String -Path "$Dir\server.py" -Pattern '^VERSION = "(.+?)"').Matches[0].Groups[1].Value }
  default    { Get-Content "$Dir\aggiornamenti.ps1" -TotalCount 9 | ForEach-Object { $_ -replace '^# ?', '' } }
}
