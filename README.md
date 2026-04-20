# LabLocalize

**CCES R81.20 Lab Localisation Tool**  
Replaces the original TeraTerm-macro-based `Gaia-Settings.cmd` / `Gaia-settings.ps1` and `Windows-Localize.cmd` / `Windows-Localize.ps1` with a single Python script.

---

## What it does

One numbered menu.  Student picks a country.  The script:

1. Applies Windows timezone, locale, UI language, and keyboard to **A-GUI** (locally, via PowerShell subprocess)
2. SSH-configures **A-SMS** and **A-GW** in parallel via Paramiko:
   - `set timezone <continent> / <city>`
   - `dbset keyboard:mapping <layout>`
   - `save config`, `set user admin shell /etc/cli.sh`, `reboot`
3. Reboots A-GUI after a 15-second countdown

---

## Files

| File | Purpose |
|------|---------|
| `lab_localize.py` | Main script – all locale data embedded, no CSV files needed |
| `lab_localize.cmd` | Launcher – handles UAC elevation, calls Python |
| `bootstrap.ps1` | One-time blueprint prep – installs Python, Paramiko, language packs, downloads files, creates desktop shortcut |

---

## Blueprint prep (one-time, run on A-GUI image)

```powershell
# Elevated PowerShell 7 on A-GUI
irm https://raw.githubusercontent.com/Don-Paterson/LabLocalize/main/bootstrap.ps1 | iex
```

This installs Python (via winget `--source winget` for HTTPS-inspection environments), Paramiko, all Windows language packs, downloads the scripts to `C:\LabConfig\`, and creates a **Public desktop shortcut** visible to all student logins.

---

## Student usage

Double-click **Lab Localise** on the desktop.  
Select a number.  Press Y to confirm.  Done.

```
╔══════════════════════════════════════════════════════╗
║          CCES Lab Localisation Tool                  ║
║  Sets timezone + keyboard on A-GUI, A-SMS and A-GW  ║
╚══════════════════════════════════════════════════════╝

  ────────────────────────────────────────────────────────
  Select your country / locale:
  ────────────────────────────────────────────────────────

   1. Austria                         19. Norway
   2. Belgium                         20. Poland
  ...

  Enter number and press Enter: 3

  ════════════════════════════════════════════════════════
  Selected : Bulgaria
  Gaia TZ  : Europe / Sofia
  Gaia KB  : bg
  Win TZ   : FLE Standard Time
  Win Lang : bg-BG
  ════════════════════════════════════════════════════════

  Proceed? (Y/N): Y
```

---

## Dry-run mode

```cmd
python C:\LabConfig\lab_localize.py --dry-run
```

Prints every clish/PowerShell command that would be sent without making any changes.  Useful for verifying a new locale entry before committing to the blueprint.

---

## Adding locales

Edit the `LOCALES` list in `lab_localize.py`.  Each `Locale(...)` entry takes:

```python
Locale(
    country        = "Display name",   # shown in menu
    win_lang       = "xx-XX",          # BCP-47
    win_geoid      = 123,              # Windows GeoID
    win_input_tip  = "XXXX:XXXXXXXX",  # HKL:KLID
    win_tz         = "... Standard Time",
    gaia_continent = "Europe",         # Gaia clish continent
    gaia_city      = "CityName",       # must exist in Gaia's tz database
    gaia_kb        = "xx",             # Gaia dbset keyboard:mapping value
)
```

No CSV files to update.

---

## Topology

```
A-GUI  10.1.1.201   (runs this script)
A-SMS  10.1.1.101   (Gaia SSH target)
A-GW   10.1.1.1     (Gaia SSH target)
```

SSH credentials and host list are defined at the top of `lab_localize.py`.

---

## Compared to the original

| | Original | This |
|--|---------|------|
| Gaia config | TeraTerm macro per host (serial) | Paramiko SSH, parallel |
| Windows config | Separate PS1 script | Integrated, same run |
| Menu | Two separate menus (continent → city, then keyboard) | Single country menu |
| TeraTerm dependency | Required at fixed path | None |
| CSV files at runtime | Required | None (data embedded) |
| Swedish language pack | Missing | Fixed |
| Input validation | Cast error on non-numeric input | Handled |
| Dry-run | Not available | `--dry-run` flag |
| Error reporting | Silent TT macro failure | Per-host pass/fail summary |
