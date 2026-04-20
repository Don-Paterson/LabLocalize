"""
lab_localize.py  –  CCES Lab Localisation Tool
================================================
Replaces:  Gaia-Settings.cmd / Gaia-settings.ps1 (TeraTerm macros)
           Windows-Localize.cmd / Windows-Localize.ps1

Single script, deploy identically to all three Windows lab machines.
Behaviour is determined automatically by COMPUTERNAME at runtime:

  A-GUI    – Windows locale (self) + Gaia SSH to A-SMS and A-GW
  A-HOST   – Windows locale only (self)
  A-REMOTE – Windows locale only (self)
  Other    – exits with an informational message (not a lab machine)

No CSV files required at runtime – all locale data is embedded.
No TeraTerm or ttpmacro.exe dependency.

Usage
-----
    python lab_localize.py              # normal run
    python lab_localize.py --dry-run    # print what would be sent, no changes

Requirements
------------
    pip install paramiko        (A-GUI only; not required on A-HOST / A-REMOTE)
"""

import argparse
import ctypes
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

# Paramiko is only required on A-GUI.  Import it lazily so that A-HOST and
# A-REMOTE can run without it installed.  _require_paramiko() is called in
# main() only when the hostname check confirms we are on A-GUI.
paramiko = None  # populated by _require_paramiko() if needed


def _require_paramiko() -> None:
    """Import paramiko into the module-level name, or exit with a clear message."""
    global paramiko
    if paramiko is not None:
        return
    try:
        import paramiko as _pm
        paramiko = _pm
    except ImportError:
        print("\n  ERROR: Paramiko is not installed.")
        print("  Run:  pip install paramiko\n")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
#  LOCALE CATALOGUE
#  Each entry covers both Windows settings and Gaia clish settings.
#
#  Fields
#  ------
#  country         : display name shown in the menu
#  win_lang        : BCP-47 language tag for Windows cmdlets
#  win_geoid       : Windows GeoID (Set-WinHomeLocation)
#  win_input_tip   : HKL:KLID pair for InputMethodTips
#  win_tz          : Windows timezone name (Set-TimeZone / tzutil)
#  gaia_continent  : first arg to Gaia clish "set timezone X / Y"
#  gaia_city       : second arg to Gaia clish "set timezone X / Y"
#  gaia_kb         : Gaia dbset keyboard:mapping value
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Locale:
    country:        str
    win_lang:       str
    win_geoid:      int
    win_input_tip:  str
    win_tz:         str
    gaia_continent: str
    gaia_city:      str
    gaia_kb:        str


LOCALES: list[Locale] = [
    Locale("Austria",              "de-AT", 14,  "0809:00000407", "W. Europe Standard Time",        "Europe",  "Vienna",       "de"),
    Locale("Belgium",              "fr-BE", 21,  "080C:0000080C", "Romance Standard Time",          "Europe",  "Brussels",     "be-latin1"),
    Locale("Bulgaria",             "bg-BG", 35,  "0402:00030402", "FLE Standard Time",              "Europe",  "Sofia",        "bg"),
    Locale("Croatia",              "hr-HR", 108, "041A:0000041A", "Central European Standard Time", "Europe",  "Zagreb",       "cz-lat2"),
    Locale("Cyprus",               "el-CY", 59,  "0408:00000408", "E. Europe Standard Time",        "Europe",  "Nicosia",      "uk"),
    Locale("Czech Republic",       "cs-CZ", 75,  "0405:00000405", "Central Europe Standard Time",   "Europe",  "Prague",       "cz-lat2"),
    Locale("Danish",               "da",    61,  "0406:00000406", "Romance Standard Time",          "Europe",  "Copenhagen",   "dk"),
    Locale("Estonia",              "et-EE", 70,  "0425:00000425", "FLE Standard Time",              "Europe",  "Tallinn",      "uk"),
    Locale("Finland",              "fi",    77,  "040B:0000040B", "FLE Standard Time",              "Europe",  "Helsinki",     "fi"),
    Locale("France",               "fr-FR", 84,  "040C:0000040C", "Romance Standard Time",          "Europe",  "Paris",        "fr"),
    Locale("Germany",              "de-DE", 94,  "0407:00000407", "W. Europe Standard Time",        "Europe",  "Berlin",       "de"),
    Locale("Greece",               "el-GR", 98,  "0408:00000408", "GTB Standard Time",              "Europe",  "Athens",       "uk"),
    Locale("Hungary",              "hu-HU", 109, "040E:0000040E", "Central Europe Standard Time",   "Europe",  "Budapest",     "hu"),
    Locale("Ireland",              "en-IE", 68,  "1809:00001809", "GMT Standard Time",              "Europe",  "Dublin",       "uk"),
    Locale("Italy",                "it-IT", 118, "0410:00000410", "W. Europe Standard Time",        "Europe",  "Rome",         "it"),
    Locale("Latvia",               "lv-LV", 140, "0426:00020426", "FLE Standard Time",              "Europe",  "Riga",         "uk"),
    Locale("Lithuania",            "lt-LT", 141, "0427:00010427", "FLE Standard Time",              "Europe",  "Vilnius",      "uk"),
    Locale("Luxembourg",           "lb-LU", 147, "046E:0000046E", "W. Europe Standard Time",        "Europe",  "Luxembourg",   "fr"),
    Locale("Malta",                "en-MT", 163, "0809:00000809", "W. Europe Standard Time",        "Europe",  "Malta",        "uk"),
    Locale("Netherlands",          "nl-NL", 176, "0813:00020409", "W. Europe Standard Time",        "Europe",  "Amsterdam",    "uk"),
    Locale("Norway",               "nb-NO", 177, "0414:00000414", "W. Europe Standard Time",        "Europe",  "Oslo",         "no"),
    Locale("Poland",               "pl-PL", 191, "0415:00000415", "Central European Standard Time", "Europe",  "Warsaw",       "pl"),
    Locale("Portugal",             "pt-PT", 193, "0816:00000816", "GMT Standard Time",              "Europe",  "Lisbon",       "pt-latin1"),
    Locale("Romania",              "ro-RO", 200, "0418:00010418", "GTB Standard Time",              "Europe",  "Bucharest",    "uk"),
    Locale("Russia",               "ru-RU", 203, "0419:00000419", "Russian Standard Time",          "Europe",  "Moscow",       "ru"),
    Locale("Slovakia",             "sk-SK", 143, "041B:0000041B", "Central Europe Standard Time",   "Europe",  "Bratislava",   "cz-lat2"),
    Locale("Slovenia",             "sl-SI", 212, "0424:00000424", "Central Europe Standard Time",   "Europe",  "Ljubljana",    "uk"),
    Locale("South Africa",         "en-ZA", 209, "1C09:00000409", "South Africa Standard Time",     "Africa",  "Johannesburg", "uk"),
    Locale("Spain",                "es-ES", 226, "0C0A:0000040A", "Romance Standard Time",          "Europe",  "Madrid",       "es"),
    Locale("Sweden",               "sv-SE", 221, "083B:0000083B", "W. Europe Standard Time",        "Europe",  "Stockholm",    "se-latin1"),
    Locale("Switzerland (French)", "fr-CH", 223, "100C:0000100C", "W. Europe Standard Time",        "Europe",  "Zurich",       "fr_CH"),
    Locale("Switzerland (German)", "de-CH", 223, "0807:00000807", "W. Europe Standard Time",        "Europe",  "Zurich",       "sg"),
    Locale("Turkey",               "tr-TR", 235, "041F:0000041F", "Turkey Standard Time",           "Europe",  "Istanbul",     "trq"),
    Locale("UK | English",         "en-GB", 242, "0809:00000809", "GMT Standard Time",              "Europe",  "London",       "uk"),
    Locale("US | English",         "en-US", 244, "0409:00020409", "Mountain Standard Time",         "America", "Denver",       "us"),
]


# ─────────────────────────────────────────────────────────────────────────────
#  GAIA SSH TARGETS
# ─────────────────────────────────────────────────────────────────────────────

GAIA_HOSTS = [
    {"name": "A-SMS", "ip": "10.1.1.101"},
    {"name": "A-GW",  "ip": "10.1.1.1"},
]

GAIA_SSH_USER    = "admin"
GAIA_SSH_PASS    = "Chkp!234"
GAIA_EXPERT_PASS = "Chkp!234"
GAIA_SSH_PORT    = 22
GAIA_SSH_TIMEOUT = 15   # seconds per connect attempt


# ─────────────────────────────────────────────────────────────────────────────
#  HOSTNAME-BASED MODE DETECTION
#
#  A-GUI    → MODE_GUI  : Windows locale (self) + Gaia SSH to A-SMS / A-GW
#  A-HOST   → MODE_WIN  : Windows locale only
#  A-REMOTE → MODE_WIN  : Windows locale only
#  Other    → MODE_UNKNOWN : print message and exit
# ─────────────────────────────────────────────────────────────────────────────

MODE_GUI     = "gui"
MODE_WIN     = "windows_only"
MODE_UNKNOWN = "unknown"

_HOST_MODE_MAP: dict[str, str] = {
    "A-GUI":    MODE_GUI,
    "A-HOST":   MODE_WIN,
    "A-REMOTE": MODE_WIN,
}


def get_mode() -> tuple[str, str]:
    """Return (mode, hostname_uppercased)."""
    hostname = socket.gethostname().upper()
    mode = _HOST_MODE_MAP.get(hostname, MODE_UNKNOWN)
    return mode, hostname


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

SEP  = "─" * 56
SEP2 = "═" * 56


def print_banner(mode: str, hostname: str) -> None:
    if mode == MODE_GUI:
        scope = "A-GUI (Windows) + A-SMS + A-GW (Gaia SSH)"
    elif mode == MODE_WIN:
        scope = f"{hostname}  –  Windows locale only"
    else:
        scope = hostname
    padded = scope.center(52)
    print(f"""
╔══════════════════════════════════════════════════════╗
║          CCES Lab Localisation Tool                  ║
║  {padded}  ║
╚══════════════════════════════════════════════════════╝
""")


def is_admin() -> bool:
    """Return True if the current process has admin rights (Windows)."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False   # non-Windows / can't determine


def print_menu(locales: list[Locale]) -> None:
    cols = 2
    rows = (len(locales) + cols - 1) // cols
    col_w = 30
    for r in range(rows):
        line = ""
        for c in range(cols):
            idx = r + c * rows
            if idx < len(locales):
                entry = f"{idx + 1:>2}. {locales[idx].country}"
                line += entry.ljust(col_w)
        print(line)


def prompt_choice(count: int) -> int:
    """Prompt until a valid integer in [1, count] is entered."""
    while True:
        raw = input("\n  Enter number and press Enter: ").strip()
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= count:
                return n
        print(f"  Invalid – please enter a number between 1 and {count}.")


# ─────────────────────────────────────────────────────────────────────────────
#  WINDOWS LOCALISATION  (runs locally on whichever machine invokes the script)
# ─────────────────────────────────────────────────────────────────────────────

def apply_windows_locale(loc: Locale, hostname: str, dry_run: bool) -> bool:
    """
    Apply Windows timezone, language, locale, and keyboard settings locally.
    Returns True on success.
    """
    ps_script = f"""
$ErrorActionPreference = 'Stop'
$lang  = '{loc.win_lang}'
$geoid = {loc.win_geoid}
$tip   = '{loc.win_input_tip}'
$tz    = '{loc.win_tz}'

Write-Host "  [Windows] Setting timezone: $tz"
Set-TimeZone -Name $tz
tzutil /s $tz

Write-Host "  [Windows] Setting locale / region: $lang (GeoID $geoid)"
Set-WinHomeLocation -GeoId $geoid
Set-Culture $lang
Set-WinSystemLocale -SystemLocale $lang

Write-Host "  [Windows] Setting UI language override: $lang"
Set-WinUILanguageOverride -Language $lang

Write-Host "  [Windows] Setting user language list + input method"
$list = New-WinUserLanguageList $lang
$list[0].InputMethodTips.Clear()
$list[0].InputMethodTips.Add($tip)
Set-WinUserLanguageList $list -Force

# Set-SystemPreferredUILanguage requires the language pack to be installed.
# Skip gracefully if it is missing rather than failing the whole script.
$installed = (Get-InstalledLanguage).LanguageId
if ($installed -contains $lang) {{
    Write-Host "  [Windows] Setting system preferred UI language: $lang"
    Set-SystemPreferredUILanguage $lang
}} else {{
    Write-Host "  [Windows] Language pack for $lang not installed - UI language unchanged (timezone + keyboard still applied)"
}}
Write-Host "  [Windows] Done."
"""
    if dry_run:
        print(f"\n  [DRY-RUN] Would run PowerShell on {hostname}:\n{ps_script}")
        return True

    try:
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, timeout=60
        )
        for line in result.stdout.splitlines():
            print(f"  {line}")
        if result.returncode != 0:
            print(f"\n  [Windows] ERROR (exit {result.returncode}):")
            for line in result.stderr.splitlines():
                print(f"    {line}")
            return False
        return True
    except FileNotFoundError:
        # pwsh not found – try legacy powershell.exe
        print("  [Windows] pwsh not found, trying powershell.exe ...")
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True, text=True, timeout=60
            )
            for line in result.stdout.splitlines():
                print(f"  {line}")
            return result.returncode == 0
        except Exception as e:
            print(f"  [Windows] FAILED: {e}")
            return False
    except subprocess.TimeoutExpired:
        print("  [Windows] TIMEOUT after 60s")
        return False
    except Exception as e:
        print(f"  [Windows] FAILED: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  GAIA SSH CONFIGURATION  (A-GUI only – connects to A-SMS and A-GW)
# ─────────────────────────────────────────────────────────────────────────────

def _recv_until(chan, prompt: str, timeout: float = 10.0) -> str:
    """
    Read from an interactive SSH channel until `prompt` appears in the output,
    or until `timeout` seconds elapse.  Returns all output collected.
    """
    buf = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if chan.recv_ready():
            chunk = chan.recv(4096).decode("utf-8", errors="replace")
            buf += chunk
            if prompt in buf:
                return buf
        else:
            time.sleep(0.1)
    return buf   # caller checks whether prompt was found


def configure_gaia_host(host: dict, loc: Locale, dry_run: bool) -> tuple[str, bool, str]:
    """
    SSH into a Gaia host and apply timezone + keyboard.
    Returns (hostname, success, detail_message).

    Sequence mirrors the original TeraTerm macro exactly:
        clish: lock database override
        clish: set timezone <continent> / <city>
        clish: expert  → enter expert password
        expert: dbset keyboard:mapping <kb>
        expert: dbset save
        expert: /bin/kbd_map_xlate keyboard:mapping < /config/db/initial
        expert: exit
        clish: save config
        clish: set user admin shell /etc/cli.sh
        clish: save config
        clish: reboot  → confirm y
    """
    name = host["name"]
    ip   = host["ip"]

    commands_clish = [
        ("lock database override",                               ">", 8),
        (f"set timezone {loc.gaia_continent} / {loc.gaia_city}", ">", 8),
        ("expert",                                               "assword:", 8),
    ]
    commands_expert_auth = (GAIA_EXPERT_PASS, "#", 8)
    commands_expert = [
        (f"dbset keyboard:mapping {loc.gaia_kb}", "#", 6),
        ("dbset save",                            "#", 6),
        ("/bin/kbd_map_xlate keyboard:mapping < /config/db/initial", "#", 10),
        ("exit",                                  ">", 6),
    ]
    commands_clish_post = [
        ("save config",                     ">", 8),
        ("set user admin shell /etc/cli.sh", ">", 8),
        ("save config",                     ">", 8),
    ]
    reboot_cmd = ("reboot", "y/n", 10)

    if dry_run:
        all_cmds = (
            [c[0] for c in commands_clish]
            + [GAIA_EXPERT_PASS]
            + [c[0] for c in commands_expert]
            + [c[0] for c in commands_clish_post]
            + ["reboot", "y"]
        )
        detail = f"Would send to {ip}:\n" + "\n".join(f"    {c}" for c in all_cmds)
        return (name, True, detail)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    chan = None

    try:
        client.connect(
            hostname=ip,
            port=GAIA_SSH_PORT,
            username=GAIA_SSH_USER,
            password=GAIA_SSH_PASS,
            look_for_keys=False,
            allow_agent=False,
            timeout=GAIA_SSH_TIMEOUT,
        )
        chan = client.invoke_shell(term="vt100", width=200, height=50)
        time.sleep(1)  # let the shell banner settle

        # Drain the login banner
        _recv_until(chan, ">", timeout=10)

        # ── clish phase ──────────────────────────────────────────────────────
        for cmd, expect, tmo in commands_clish:
            chan.send(cmd + "\n")
            out = _recv_until(chan, expect, timeout=tmo)
            if expect not in out:
                return (name, False,
                        f"Timed out waiting for '{expect}' after: {cmd!r}\nGot: {out!r}")

        # ── enter expert mode ─────────────────────────────────────────────────
        chan.send(commands_expert_auth[0] + "\n")
        out = _recv_until(chan, commands_expert_auth[1], timeout=commands_expert_auth[2])
        if commands_expert_auth[1] not in out:
            return (name, False,
                    f"Timed out waiting for expert shell after password\nGot: {out!r}")

        # ── expert commands ───────────────────────────────────────────────────
        for cmd, expect, tmo in commands_expert:
            chan.send(cmd + "\n")
            out = _recv_until(chan, expect, timeout=tmo)
            if expect not in out:
                return (name, False,
                        f"Timed out waiting for '{expect}' after: {cmd!r}\nGot: {out!r}")

        # ── clish post-config ─────────────────────────────────────────────────
        for cmd, expect, tmo in commands_clish_post:
            chan.send(cmd + "\n")
            out = _recv_until(chan, expect, timeout=tmo)
            if expect not in out:
                return (name, False,
                        f"Timed out waiting for '{expect}' after: {cmd!r}\nGot: {out!r}")

        # ── reboot ────────────────────────────────────────────────────────────
        chan.send(reboot_cmd[0] + "\n")
        out = _recv_until(chan, reboot_cmd[1], timeout=reboot_cmd[2])
        if reboot_cmd[1].lower() in out.lower():
            chan.send("y\n")
        # Connection will drop as the host reboots – that's expected.
        time.sleep(2)

        return (name, True, f"Configured {loc.gaia_continent}/{loc.gaia_city}, kb={loc.gaia_kb}. Rebooting.")

    except paramiko.AuthenticationException:
        return (name, False, "SSH authentication failed – check credentials in script.")
    except paramiko.SSHException as e:
        return (name, False, f"SSH error: {e}")
    except TimeoutError:
        return (name, False, f"Connection timed out ({GAIA_SSH_TIMEOUT}s) – is {ip} reachable?")
    except OSError as e:
        return (name, False, f"Network error: {e}")
    except Exception as e:
        return (name, False, f"Unexpected error: {type(e).__name__}: {e}")
    finally:
        try:
            if chan:
                chan.close()
            client.close()
        except Exception:
            pass


def configure_gaia_hosts(loc: Locale, dry_run: bool) -> dict[str, bool]:
    """Configure all Gaia hosts in parallel. Returns {name: success}."""
    results = {}
    with ThreadPoolExecutor(max_workers=len(GAIA_HOSTS)) as pool:
        futures = {
            pool.submit(configure_gaia_host, host, loc, dry_run): host["name"]
            for host in GAIA_HOSTS
        }
        for future in as_completed(futures):
            name, ok, detail = future.result()
            results[name] = ok
            status = "✓  OK" if ok else "✗  FAILED"
            print(f"\n  [{name}] {status}")
            for line in detail.splitlines():
                print(f"         {line}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="CCES Lab Localisation Tool")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be done without making any changes."
    )
    args = parser.parse_args()
    dry_run: bool = args.dry_run

    # ── Detect which machine we are running on ────────────────────────────────
    mode, hostname = get_mode()

    print_banner(mode, hostname)

    if mode == MODE_UNKNOWN:
        print(f"  This script is not intended to run on {hostname}.")
        print(f"  Expected: A-GUI, A-HOST, or A-REMOTE.\n")
        sys.exit(0)

    if dry_run:
        print("  *** DRY-RUN MODE – no changes will be made ***\n")

    # ── Admin check ───────────────────────────────────────────────────────────
    if not dry_run and not is_admin():
        print("  ERROR: This script must be run as Administrator.\n"
              "  Right-click the shortcut and choose 'Run as administrator'.\n")
        sys.exit(1)

    # ── On A-GUI, verify Paramiko is available before the student wastes time
    #    filling in the menu only to hit an import error afterwards.
    if mode == MODE_GUI:
        _require_paramiko()

    # ── Country menu ──────────────────────────────────────────────────────────
    print(f"  {SEP}")
    print("  Select your country / locale:")
    print(f"  {SEP}\n")
    print_menu(LOCALES)
    print(f"\n  {SEP}")
    choice = prompt_choice(len(LOCALES))
    loc = LOCALES[choice - 1]

    # ── Confirmation ──────────────────────────────────────────────────────────
    print(f"\n  {SEP2}")
    print(f"  Selected  : {loc.country}")
    print(f"  Win TZ    : {loc.win_tz}")
    print(f"  Win Lang  : {loc.win_lang}")
    if mode == MODE_GUI:
        print(f"  Gaia TZ   : {loc.gaia_continent} / {loc.gaia_city}")
        print(f"  Gaia KB   : {loc.gaia_kb}")
    print(f"  {SEP2}")

    confirm = input("\n  Proceed? (Y/N): ").strip().upper()
    if confirm != "Y":
        print("  Cancelled.\n")
        sys.exit(0)

    # ── Step 1: Windows localisation (always runs, on whichever host this is) ─
    step_total = "2" if mode == MODE_GUI else "1"
    print(f"\n  {SEP}")
    print(f"  Step 1/{step_total}  –  Applying Windows locale to {hostname} ...")
    print(f"  {SEP}")
    win_ok = apply_windows_locale(loc, hostname, dry_run)
    print(f"\n  [{hostname}] {'✓  OK' if win_ok else '✗  FAILED (check output above)'}")

    # ── Step 2: Gaia SSH (A-GUI only) ─────────────────────────────────────────
    gaia_results: dict[str, bool] = {}
    if mode == MODE_GUI:
        print(f"\n  {SEP}")
        print("  Step 2/2  –  Configuring Gaia hosts via SSH ...")
        print(f"  {SEP}")
        gaia_results = configure_gaia_hosts(loc, dry_run)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n  {SEP2}")
    print("  SUMMARY")
    print(f"  {SEP2}")
    all_ok = win_ok and all(gaia_results.values())
    print(f"  {hostname:<8} : {'✓  OK' if win_ok else '✗  FAILED'}")
    for name, ok in gaia_results.items():
        print(f"  {name:<8} : {'✓  OK – rebooting' if ok else '✗  FAILED'}")
    print(f"  {SEP2}")

    if not all_ok:
        print(f"\n  One or more steps failed.  {hostname} will NOT be rebooted automatically.")
        print("  Review the errors above, correct and re-run, or configure manually.\n")
        sys.exit(1)

    if dry_run:
        print("\n  Dry-run complete.  Nothing was changed.\n")
        sys.exit(0)

    # ── Reboot this machine ───────────────────────────────────────────────────
    if mode == MODE_GUI:
        print("\n  All Gaia hosts are rebooting.")
    print(f"  {hostname} will reboot in 15 seconds to apply Windows locale changes.")
    print("  Close any open work now.\n")

    for i in range(15, 0, -1):
        print(f"  Rebooting in {i:>2}s ...", end="\r")
        time.sleep(1)

    print(f"\n  Rebooting {hostname} now ...\n")
    subprocess.run(["shutdown", "/r", "/t", "0"], check=False)


if __name__ == "__main__":
    main()
