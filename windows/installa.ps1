# Installazione del monitoraggio interpelli su Windows.
# Lanciare con doppio clic su installa.bat (oppure: powershell -ExecutionPolicy Bypass -File installa.ps1)
$ErrorActionPreference = "Stop"
$Repo   = "https://github.com/AndreaCorrado00/interpelli-fvg.git"
$Cartella = Join-Path $env:USERPROFILE "interpelli-fvg"
$NomeAttivita = "Interpelli FVG"

function Passo($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Trova($nome) { return (Get-Command $nome -ErrorAction SilentlyContinue) }
function AggiornaPath {
  $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
}

Passo "1/6 Controllo Git"
if (-not (Trova git)) {
  Write-Host "Git non trovato: lo installo con winget..."
  winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
  AggiornaPath
}
git --version

Passo "2/6 Controllo Python"
$Py = $null
if (Trova py) { $Py = "py" } elseif (Trova python) { $Py = "python" }
if (-not $Py) {
  Write-Host "Python non trovato: lo installo con winget..."
  winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
  AggiornaPath
  if (Trova py) { $Py = "py" } else { $Py = "python" }
}
& $Py --version

Passo "3/6 Scarico il progetto in $Cartella"
if (Test-Path (Join-Path $Cartella ".git")) {
  git -C $Cartella pull --rebase --autostash
} else {
  Write-Host "Se compare una finestra di accesso a GitHub, accedi con il tuo account."
  git clone $Repo $Cartella
}

Passo "4/6 Preparo l'ambiente Python"
Set-Location $Cartella
if (-not (Test-Path ".venv")) { & $Py -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt

Passo "5/6 Credenziali Gmail per l'invio delle mail"
$utente = [Environment]::GetEnvironmentVariable("GMAIL_USER","User")
if (-not $utente) {
  $utente = Read-Host "Indirizzo Gmail da cui partono le mail"
  [Environment]::SetEnvironmentVariable("GMAIL_USER", $utente.Trim(), "User")
}
if (-not [Environment]::GetEnvironmentVariable("GMAIL_APP_PASSWORD","User")) {
  $sicura = Read-Host "Password per app di Gmail (16 lettere, non viene mostrata)" -AsSecureString
  $chiara = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sicura))
  [Environment]::SetEnvironmentVariable("GMAIL_APP_PASSWORD", ($chiara -replace "\s",""), "User")
}
Write-Host "Credenziali salvate per il tuo utente Windows."

Passo "6/6 Programmo i controlli alle 8:15 e alle 17:00"
$Esegui = Join-Path $Cartella "windows\esegui.ps1"
$Azione = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Esegui`""
$Orari = @( (New-ScheduledTaskTrigger -Daily -At 8:15am), (New-ScheduledTaskTrigger -Daily -At 5:00pm) )
# StartWhenAvailable: se il computer era spento all'ora prevista, il controllo parte appena si accende
$Opzioni = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $NomeAttivita -Action $Azione -Trigger $Orari -Settings $Opzioni `
  -Description "Controlla gli interpelli FVG e invia il riepilogo via mail" -Force | Out-Null
Write-Host "Attivita '$NomeAttivita' creata."

Passo "Prova: cerco gli interpelli adesso (nessuna mail inviata, ci vogliono alcuni minuti)"
$env:PYTHONUTF8 = "1"
& ".\.venv\Scripts\python.exe" -m interpelli --prova
$riepilogo = Join-Path $Cartella "riepilogo_andrea.html"
if (Test-Path $riepilogo) { Start-Process $riepilogo }

Write-Host ""
Write-Host "Installazione completata. Per inviare subito la mail vera: Utilita di pianificazione >" -ForegroundColor Green
Write-Host "'$NomeAttivita' > Esegui. Il log dell'ultimo controllo e' in $Cartella\log\ultimo.log" -ForegroundColor Green
Read-Host "Premi Invio per chiudere"
