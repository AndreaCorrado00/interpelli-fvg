# Avviato dall'Utilita di pianificazione: aggiorna configurazione, cerca, invia, salva lo stato.
$Cartella = Split-Path -Parent $PSScriptRoot
Set-Location $Cartella
New-Item -ItemType Directory -Force -Path "log" | Out-Null
$Log = Join-Path $Cartella "log\ultimo.log"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
function Scrivi($righe) { $righe | ForEach-Object { "$_" } | Out-File $Log -Append -Encoding utf8 }
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm') ===" | Out-File $Log -Encoding utf8

# Al risveglio del PC la rete arriva dopo qualche secondo: aspetto fino a 10 minuti
$rete = $false
for ($i = 0; $i -lt 60; $i++) {
  try { [System.Net.Dns]::GetHostEntry("github.com") | Out-Null; $rete = $true; break } catch { Start-Sleep -Seconds 10 }
}
if (-not $rete) { Scrivi "Rete non disponibile dopo 10 minuti: controllo rimandato al prossimo giro."; exit 1 }
Scrivi "Rete disponibile dopo $($i * 10) secondi."

# Configurazione e filtri si modificano su GitHub: prima di ogni controllo scarico le modifiche
Scrivi (git pull --rebase --autostash 2>&1)

# Python scrive direttamente su file (niente pipeline di PowerShell che possa bloccarsi)
$Out = Join-Path $Cartella "log\python.log"
$Err = Join-Path $Cartella "log\python_errori.log"
$p = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-u", "-m", "interpelli" `
  -NoNewWindow -PassThru -RedirectStandardOutput $Out -RedirectStandardError $Err
$null = $p.Handle   # necessario per leggere ExitCode a fine processo
$p | Wait-Process -Timeout 2400 -ErrorAction SilentlyContinue
if (-not $p.HasExited) { Scrivi "Controllo fermo da 40 minuti: interrotto."; $p | Stop-Process -Force }
$esito = $p.ExitCode
Scrivi (Get-Content $Out -Encoding utf8)
if ((Test-Path $Err) -and (Get-Item $Err).Length -gt 0) { Scrivi "--- errori ---"; Scrivi (Get-Content $Err -Encoding utf8) }
Scrivi "Fine controllo, esito $esito."

# Salvo su GitHub l'elenco degli interpelli gia segnalati (per l'etichetta NUOVO)
Scrivi (git add stato/visti.json 2>&1)
Scrivi (git -c user.name="interpelli-bot" -c user.email="interpelli-bot@users.noreply.github.com" commit -m "Aggiorna interpelli gia segnalati" 2>&1)
Scrivi (git push 2>&1)

Copy-Item $Log (Join-Path $Cartella ("log\" + (Get-Date -Format "yyyy-MM-dd_HHmm") + ".log"))
Get-ChildItem "log\*.log" | Where-Object { $_.Name -ne "ultimo.log" } |
  Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 | Remove-Item -ErrorAction SilentlyContinue
exit $esito
