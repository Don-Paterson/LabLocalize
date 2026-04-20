###############################################################################
#  bootstrap.ps1  –  CCES Lab Localisation Bootstrap
#
#  Usage (run once per lab build / blueprint prep, elevated PS7 on A-GUI):
#
#      irm https://raw.githubusercontent.com/Don-Paterson/LabLocalize/main/bootstrap.ps1 | iex
#
#  What it does:
#    1. Ensures Python 3.x is available  (winget install if missing)
#    2. Installs Paramiko into the system Python
#    3. Pre-installs all required Windows language packs
#    4. Downloads lab_localize.py to C:\LabConfig\
#    5. Downloads lab_localize.cmd to C:\LabConfig\
#    6. Creates a desktop shortcut on the Public desktop
#       (visible to all users / all student logins)
#
###############################################################################

#Requires -RunAsAdministrator

$ErrorActionPreference = 'Stop'

# ── Config ───────────────────────────────────────────────────────────────────
$LabConfigDir = 'C:\LabConfig'
$RawBase      = 'https://raw.githubusercontent.com/Don-Paterson/LabLocalize/main'
$ScriptFile   = Join-Path $LabConfigDir 'lab_localize.py'
$CmdFile      = Join-Path $LabConfigDir 'lab_localize.cmd'
$ShortcutPath = Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Lab Localise.lnk'

# Language packs to pre-install (covers all locales in LOCALES catalogue)
# sv-SE was missing from the original LanguagePacks-install.txt – now included.
$LanguagePacks = @(
    'de-AT', 'fr-BE', 'bg-BG', 'hr-HR', 'el-CY', 'cs-CZ',
    'da-DK', 'et-EE', 'fi-FI', 'fr-FR', 'de-DE', 'el-GR',
    'hu-HU', 'en-IE', 'it-IT', 'lv-LV', 'lt-LT', 'lb-LU',
    'en-MT', 'nl-NL', 'nb-NO', 'pl-PL', 'pt-PT', 'ro-RO',
    'ru-RU', 'sk-SK', 'sl-SI', 'en-ZA', 'es-ES', 'sv-SE',
    'fr-CH', 'de-CH', 'tr-TR', 'en-GB', 'en-US'
)

function Write-Step([string]$msg) {
    Write-Host "`n  >> $msg" -ForegroundColor Cyan
}

function Write-OK([string]$msg) {
    Write-Host "     OK  $msg" -ForegroundColor Green
}

function Write-Warn([string]$msg) {
    Write-Host "     WARN  $msg" -ForegroundColor Yellow
}

# ── 1. Ensure LabConfig directory ────────────────────────────────────────────
Write-Step "Ensuring $LabConfigDir exists"
if (-not (Test-Path $LabConfigDir)) {
    New-Item -ItemType Directory -Path $LabConfigDir | Out-Null
}
Write-OK "$LabConfigDir ready"

# ── 2. Ensure Python is installed ────────────────────────────────────────────
Write-Step "Checking for Python"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "     Python not found – installing via winget ..." -ForegroundColor Yellow
    # --source winget is required where HTTPS Inspection is active (CCSA Lab 8A+)
    winget install --id Python.Python.3 --source winget --silent --accept-package-agreements --accept-source-agreements
    $env:PATH = [System.Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('PATH', 'User')
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Write-Host "     ERROR: Python install failed.  Install manually and re-run." -ForegroundColor Red
        exit 1
    }
}
$pyVer = & python --version 2>&1
Write-OK "Found: $pyVer"

# ── 3. Install Paramiko ───────────────────────────────────────────────────────
Write-Step "Installing / verifying Paramiko"
$piCmd = 'import paramiko; print(paramiko.__version__)'
$check = & python -c $piCmd 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "     Installing Paramiko ..." -ForegroundColor Yellow
    & python -m pip install paramiko --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "     ERROR: pip install paramiko failed." -ForegroundColor Red
        exit 1
    }
    $check = & python -c $piCmd 2>&1
}
Write-OK "Paramiko $check"

# ── 4. Install language packs ─────────────────────────────────────────────────
Write-Step "Installing Windows language packs (this may take a few minutes)"
$installed = (Get-InstalledLanguage).LanguageId
foreach ($lp in $LanguagePacks) {
    if ($installed -contains $lp) {
        Write-Host "     Skip  $lp  (already installed)" -ForegroundColor DarkGray
    } else {
        Write-Host "     Installing $lp ..." -ForegroundColor Yellow
        try {
            Install-Language $lp -ErrorAction Stop | Out-Null
            Write-OK "Installed $lp"
        } catch {
            Write-Warn "Could not install $lp : $_"
        }
    }
}

# ── 5. Download script files ──────────────────────────────────────────────────
Write-Step "Downloading lab_localize.py"
try {
    Invoke-WebRequest -Uri "$RawBase/lab_localize.py" -OutFile $ScriptFile -UseBasicParsing
    Write-OK "Saved to $ScriptFile"
} catch {
    Write-Host "     ERROR downloading lab_localize.py : $_" -ForegroundColor Red
    Write-Host "     Copy the file to $ScriptFile manually." -ForegroundColor Yellow
}

Write-Step "Downloading lab_localize.cmd"
try {
    Invoke-WebRequest -Uri "$RawBase/lab_localize.cmd" -OutFile $CmdFile -UseBasicParsing
    Write-OK "Saved to $CmdFile"
} catch {
    Write-Host "     ERROR downloading lab_localize.cmd : $_" -ForegroundColor Red
    Write-Host "     Copy the file to $CmdFile manually." -ForegroundColor Yellow
}

# ── 6. Desktop shortcut (Public desktop – all users) ─────────────────────────
Write-Step "Creating desktop shortcut"
try {
    $wsh     = New-Object -ComObject WScript.Shell
    $shortcut              = $wsh.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath   = $CmdFile
    $shortcut.WorkingDirectory = $LabConfigDir
    $shortcut.Description  = 'CCES Lab Localisation Tool'
    $shortcut.IconLocation = 'C:\Windows\System32\shell32.dll,22'
    $shortcut.Save()
    Write-OK "Shortcut: $ShortcutPath"
} catch {
    Write-Warn "Could not create shortcut: $_"
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host "`n  ════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Bootstrap complete." -ForegroundColor Green
Write-Host "  Students run:  Lab Localise  (desktop shortcut)" -ForegroundColor Green
Write-Host "  ════════════════════════════════════════════════════`n" -ForegroundColor Green
