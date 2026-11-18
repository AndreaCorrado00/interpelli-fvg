# Avviato dall'Utilita di pianificazione: aggiorna configurazione, cerca, invia, salva lo stato.
$Cartella = Split-Path -Parent $PSScriptRoot
Set-Location $Cartella
New-Item -ItemType Directory -Force -Path "log" | Out-Null
$Log = Join-Path $Cartella "log\ultimo.log"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm') ===" | Out-File $Log -Encoding utf8

# Configurazione e filtri si modificano su GitHub: prima di ogni controllo scarico le modifiche
git pull --rebase --autostash *>> $Log

& ".\.venv\Scripts\python.exe" -m interpelli *>> $Log
$esito = $LASTEXITCODE

# Salvo su GitHub l'elenco degli interpelli gia segnalati (per l'etichetta NUOVO)
git add stato/visti.json *>> $Log
git -c user.name="interpelli-bot" -c user.email="interpelli-bot@users.noreply.github.com" commit -m "Aggiorna interpelli gia segnalati" *>> $Log
git push *>> $Log

Copy-Item $Log (Join-Path $Cartella ("log\" + (Get-Date -Format "yyyy-MM-dd_HHmm") + ".log"))
Get-ChildItem "log\*.log" | Where-Object { $_.Name -ne "ultimo.log" } |
  Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 | Remove-Item -ErrorAction SilentlyContinue
exit $esito
