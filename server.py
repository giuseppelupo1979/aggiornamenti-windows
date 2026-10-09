#!/usr/bin/env python3
"""Aggiornamenti per Windows: server locale che trova le app da aggiornare e le aggiorna in silenzio.

Fork della versione macOS (github.com/giuseppelupo1979/aggiornamenti-mac): stessa pagina,
motore diverso. Qui la fonte è winget, il gestore di pacchetti di Windows, che copre il suo
repository, il Microsoft Store e molte app installate a mano.

Solo libreria standard. Ascolta soltanto su 127.0.0.1.
"""

import concurrent.futures as cf
import ctypes
import datetime as dt
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

VERSION = "0.2.1"   # tenere allineata con CHANGELOG.md
# --demo: dati finti, cartelle temporanee, nessuna modifica al sistema (per prove e screenshot)
DEMO = "--demo" in sys.argv
HOST = "127.0.0.1"
PORT = int(os.environ.get("AGG_PORT") or (8766 if DEMO else 8765))
FROZEN = getattr(sys, "frozen", False)          # eseguito come Aggiornamenti.exe (PyInstaller)
ROOT = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
RES = getattr(sys, "_MEIPASS", ROOT)             # index.html e risorse impacchettate nell'exe
if FROZEN:
    # ogni processo figlio (server in background, riavvii, copia elevata) deve estrarre i propri file:
    # altrimenti riusa la cartella temporanea del padre, che sparisce quando il padre si chiude
    os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
REPO = "giuseppelupo1979/aggiornamenti-windows"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
TASK_NAME = "Aggiornamenti"
APP_ID = "GiuseppeLupo.Aggiornamenti"   # registrato dall'installazione: nome e icona delle notifiche

LOCAL = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
CACHE = os.path.join(LOCAL, "AggiornamentiWin", "cache")
SUPPORT = (tempfile.mkdtemp(prefix="aggiornamenti-demo-") if DEMO
           else os.path.join(LOCAL, "AggiornamentiWin"))
EXCLUDED_FILE = os.path.join(SUPPORT, "esclusi.json")
SETTINGS_FILE = os.path.join(SUPPORT, "impostazioni.json")
LOG_FILE = os.path.join(LOCAL, "AggiornamentiWin", "aggiornamenti.log")
PAGE_URL = f"http://{HOST}:{PORT}"
os.makedirs(CACHE, exist_ok=True)
os.makedirs(SUPPORT, exist_ok=True)

WINGET = shutil.which("winget") or os.path.join(LOCAL, "Microsoft", "WindowsApps", "winget.exe")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def system_lang():
    forced = os.environ.get("AGG_LANG")
    if forced:
        return "it" if forced.startswith("it") else "en"
    try:
        lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "it" if lcid & 0x3FF == 0x10 else "en"   # 0x10 = italiano
    except Exception:
        return "en"


LANG = system_lang()

MESSAGES = {
    "available": ("{n} aggiornamento disponibile", "{n} aggiornamenti disponibili", "{n} update available", "{n} updates available"),
    "upd_ok": ("{n} app aggiornata", "{n} app aggiornate", "{n} app updated", "{n} apps updated"),
    "upd_fail": ("{n} non riuscita", "{n} non riuscite", "{n} failed", "{n} failed"),
    "upd_postponed": ("{n} rimandata perché aperta", "{n} rimandate perché aperte", "{n} postponed (in use)", "{n} postponed (in use)"),
    "freed": ("liberati {x}", "liberati {x}", "{x} freed", "{x} freed"),
    "auto_title": ("Aggiornamento automatico",) * 2 + ("Automatic update",) * 2,
    "test": ("Le notifiche funzionano. Un clic qui apre la pagina.",) * 2 + ("Notifications work. Click here to open the page.",) * 2,
    "busy": ("Attendi la fine dell'operazione in corso",) * 2 + ("Wait for the current operation to finish",) * 2,
    "self_title": ("Aggiornamenti {x} disponibile",) * 2 + ("Aggiornamenti {x} is available",) * 2,
    "self_body": ("Apri la pagina per installare la nuova versione.",) * 2 + ("Open the page to install the new version.",) * 2,
    "self_dirty": ("La cartella del programma contiene modifiche locali: aggiornala a mano con git.",) * 2
                  + ("The program folder has local changes: update it manually with git.",) * 2,
    "downloading": ("Scarico {x}",) * 2 + ("Downloading {x}",) * 2,
    "id_cut": ("Identificativo troncato da winget, impossibile aggiornare in automatico: {x}",) * 2
              + ("Identifier truncated by winget, cannot update automatically: {x}",) * 2,
    "tech_diff": ("Questa app si aggiorna con un sistema diverso da quello con cui è stata installata: usa il suo aggiornamento interno, oppure disinstallala e reinstallala.",) * 2
                 + ("This app updates through a different installer than the one it was installed with: use its built-in updater, or uninstall and reinstall it.",) * 2,
    "installer_failed": ("L'installer del programma non è andato a buon fine: se il programma era aperto (anche solo nell'area di notifica) chiudilo e riprova, oppure rispondi Sì alla richiesta di Windows.",) * 2
                        + ("The program's installer failed: if the program was open (even just in the notification area) close it and try again, or answer Yes to Windows' prompt.",) * 2,
    "app_open": ("{x} è aperto: chiudilo (anche dall'area di notifica vicino all'orologio) e riprova.",) * 2
                + ("{x} is running: close it (including from the notification area by the clock) and try again.",) * 2,
    "closing": ("Chiudo {x}",) * 2 + ("Quitting {x}",) * 2,
    "need_admin": ("Questo aggiornamento richiede i privilegi di amministratore: attivali in basso nella pagina.",) * 2
                  + ("This update needs administrator rights: turn them on at the bottom of the page.",) * 2,
}


def t(key, n=1, **kw):
    forms = MESSAGES[key]
    return forms[(0 if LANG == "it" else 2) + (0 if n == 1 else 1)].format(n=n, **kw)


lock = threading.Lock()
state = {
    "scanning": False, "scanned_at": None, "scan_error": None,
    "items": [], "jobs": {}, "running": False, "batch": None,
    "unchecked": [], "macos": [], "cleaning": False,
    "self": {"latest": None, "url": None, "notes": "", "checked_at": 0, "status": None, "log": ""},
}


def log_line(*parts):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(p) for p in parts) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- utilità

def decode(b):
    """winget e i comandi di sistema, quando l'output è catturato, scrivono nella codifica OEM della
    console (es. 850) e non in UTF-8: si prova UTF-8 e, se non è valido, la codifica di sistema."""
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        for enc in ("oem", "mbcs", "cp1252"):
            try:
                return b.decode(enc)
            except (UnicodeDecodeError, LookupError):
                pass
        return b.decode("utf-8", "replace")


def run(cmd, timeout=1800):
    p = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
    out = (p.stdout or b"") + (p.stderr or b"")
    return p.returncode, decode(out)


def run_stream(cmd, on_line, timeout=3600):
    """Passa ogni riga (anche quelle chiuse da \\r, le barre di avanzamento) a on_line."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    timer = threading.Timer(timeout, p.kill)
    timer.start()
    out, buf = [], b""
    try:
        while True:
            chunk = p.stdout.read1(4096)
            if not chunk:
                break
            buf += chunk
            *parts, buf = re.split(rb"[\r\n]", buf)
            for part in parts:
                line = decode(part).rstrip()
                if line.strip():
                    out.append(line)
                    on_line(line)
        return p.wait(), "\n".join(out)
    finally:
        timer.cancel()


def powershell(script, timeout=300):
    return run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-Command", "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + script], timeout=timeout)


def set_progress(jid, **kw):
    with lock:
        job = state["jobs"].get(jid)
        if job is not None:
            job.update(kw)


def vparts(v):
    return [int(x) for x in re.findall(r"\d+", v or "")]


def newer(candidate, installed):
    a, b = vparts(candidate), vparts(installed)
    return bool(a and b and a > b)


def is_major(candidate, installed):
    a, b = vparts(candidate), vparts(installed)
    return bool(a and b and a[0] != b[0])


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


# ---------------------------------------------------------------- esclusioni e impostazioni

def item_key(item):
    return item["id"]


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return {**default, **json.load(f)} if isinstance(default, dict) and default else json.load(f)
    except Exception:
        return dict(default)


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_excluded():
    return _load(EXCLUDED_FILE, {})


def save_excluded(data):
    _save(EXCLUDED_FILE, data)


DEFAULT_SETTINGS = {
    "daily_check": True, "check_time": "09:00",
    "auto_update": False, "auto_time": "03:00",
    "last_check_day": None, "last_auto_day": None, "last_auto": None, "last_cleanup": None,
    "welcomed": False,
}


def load_settings():
    return _load(SETTINGS_FILE, DEFAULT_SETTINGS)


def save_settings(data):
    _save(SETTINGS_FILE, data)


# ---------------------------------------------------------------- avvio all'accesso e privilegi

def launch_command():
    """Comando che avvia il server senza finestra: l'exe stesso, oppure pythonw accanto al python in uso."""
    if FROZEN:
        return sys.executable, "--background"
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    return exe, os.path.join(ROOT, "server.py")


def login_enabled():
    rc, _ = run(["schtasks", "/Query", "/TN", TASK_NAME], timeout=30)
    return rc == 0


def set_login(enabled):
    """Attività pianificata all'accesso con privilegi elevati: avvio senza finestre né richieste UAC.
    Crearla richiede di essere già amministratore (lo si ottiene una volta con elevate())."""
    if DEMO:
        return True
    if not enabled:
        run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], timeout=30)
        return True
    exe, arg = launch_command()
    q = lambda x: x.replace("'", "''")
    argument = arg if FROZEN else f'"{arg}"'
    # Register-ScheduledTask invece di schtasks: le impostazioni predefinite di schtasks impediscono
    # l'avvio a batteria, fermano il programma quando il portatile passa alla batteria e lo uccidono
    # dopo 3 giorni. Qui: parte sempre, nessun limite di durata, mai due copie insieme.
    script = (
        f"$a=New-ScheduledTaskAction -Execute '{q(exe)}' -Argument '{q(argument)}' -WorkingDirectory '{q(ROOT)}';"
        "$u=$env:USERDOMAIN+'\\'+$env:USERNAME;"
        "$t=New-ScheduledTaskTrigger -AtLogOn -User $u;"
        "$p=New-ScheduledTaskPrincipal -UserId $u -LogonType Interactive -RunLevel Highest;"
        "$s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable;"
        f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $a -Trigger $t -Principal $p -Settings $s -Force | Out-Null")
    rc, out = powershell(script, timeout=60)
    log_line("attività all'accesso", rc, out.strip())
    return rc == 0


def elevate_and_enable_login():
    """Riavvia il server come amministratore (una richiesta UAC) e crea l'attività all'accesso."""
    exe, arg = launch_command()
    args = f"{arg} --enable-login" if FROZEN else f'"{arg}" --enable-login'
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, ROOT, 0)


def notify(title, message):
    if DEMO:
        print("notifica:", title, "-", message, flush=True)
        return
    x = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&apos;")
    xml = (f"<toast activationType='protocol' launch='{PAGE_URL}'><visual><binding template='ToastGeneric'>"
           f"<text>{x(title)}</text><text>{x(message)}</text></binding></visual></toast>")
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] > $null;"
        f"$d = New-Object Windows.Data.Xml.Dom.XmlDocument; $d.LoadXml('{xml.replace(chr(39), chr(34))}');"
        # AppId dell'installazione se registrato, altrimenti quello di PowerShell (sempre presente)
        f"$app = '{APP_ID}'; if (-not (Test-Path 'HKCU:\\Software\\Classes\\AppUserModelId\\{APP_ID}')) "
        "{ $app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe' };"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show("
        "(New-Object Windows.UI.Notifications.ToastNotification $d))")
    rc, out = powershell(script, timeout=60)
    if rc != 0:
        log_line("notifica fallita", out)


# ---------------------------------------------------------------- winget

def parse_table(text):
    """Legge le tabelle a colonne fisse di winget. Restituisce una lista di dict con chiavi
    name, id, version, available, source (vuote se la colonna manca). Indipendente dalla lingua:
    usa la posizione delle colonne, non i titoli."""
    lines = [l.split("\r")[-1].rstrip() for l in text.replace("\r\n", "\n").split("\n")]
    rows = []
    i = 0
    while i < len(lines):
        if re.fullmatch(r"-{20,}", lines[i].strip()) and i > 0:
            header = lines[i - 1]
            starts = [m.start() for m in re.finditer(r"\S+", header)]
            keys = ["name", "id", "version", "available", "source"][:len(starts)]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"^\d+ \S", lines[i]):
                line = lines[i]
                vals = []
                for k, s in enumerate(starts):
                    e = starts[k + 1] if k + 1 < len(starts) else None
                    vals.append(line[s:e].strip() if len(line) > s else "")
                row = dict(zip(keys, vals))
                for k in ("name", "id", "version", "available", "source"):
                    row.setdefault(k, "")
                if row["id"]:
                    rows.append(row)
                i += 1
        i += 1
    return rows


WG_COMMON = ["--accept-source-agreements", "--disable-interactivity"]


def winget_full_ids():
    """`winget export` dà gli identificativi completi (la tabella li tronca con «…»)."""
    path = os.path.join(CACHE, "export.json")
    rc, out = run([WINGET, "export", "-o", path, "--include-versions"] + WG_COMMON, timeout=600)
    ids = set()
    try:
        with open(path, encoding="utf-8-sig") as f:
            for src in json.load(f).get("Sources", []):
                for p in src.get("Packages", []):
                    ids.add(p.get("PackageIdentifier", ""))
    except Exception:
        pass
    return ids


TRUNC = re.compile(r"(…|\.\.\.|\?)$")   # "…" diventa "..." o "?" se winget scrive in codifica OEM


def resolve_id(raw, full):
    if not TRUNC.search(raw):
        return raw
    prefix = TRUNC.sub("", raw)
    cands = [i for i in full if i.startswith(prefix)]
    return cands[0] if len(cands) == 1 else None


# si aggiornano da soli con il proprio sistema: winget li elenca ma non riesce ad aggiornarli
SELF_UPDATING = {"Microsoft.Edge", "Microsoft.EdgeWebView2Runtime", "Microsoft.Edge.Beta", "Microsoft.Edge.Dev"}

TECH_DIFF = re.compile(r"tecnologia di installazione|install technology", re.I)
NOT_FOUND = re.compile(r"non (è|e|.) stato trovato alcun pacchetto installato|no installed package found", re.I)
NOT_APPLICABLE = re.compile(r"non si applica al sistema|does not apply to your system|no applicable upgrade", re.I)

SYSTEM_NAMES = re.compile(r"redistributable|runtime|driver|update for|windows sdk|\.net |webview2|"
                          r"microsoft edge update|visual c\+\+", re.I)


# ---------------------------------------------------------------- programmi installati (registro di Windows)

_arp = []   # [{name, location, icon}] dal registro "Programmi e funzionalità"


def load_arp():
    """Nome, cartella e icona di ogni programma installato, dalle chiavi Uninstall del registro."""
    script = (
        "$k=@('HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "'HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*');"
        "Get-ItemProperty $k -ErrorAction SilentlyContinue | Where-Object DisplayName | "
        "Select-Object DisplayName, InstallLocation, DisplayIcon | ConvertTo-Json -Compress")
    rc, out = powershell(script, timeout=120)
    entries = []
    try:
        data = json.loads(out.strip() or "[]")
        for e in data if isinstance(data, list) else [data]:
            icon = (e.get("DisplayIcon") or "").split(",")[0].strip().strip('"')
            loc = (e.get("InstallLocation") or "").strip().strip('"')
            if not loc and icon.lower().endswith(".exe"):
                loc = os.path.dirname(icon)
            entries.append({"name": e["DisplayName"].strip(), "location": loc.rstrip("\\"), "icon": icon})
    except Exception as ex:
        log_line("registro programmi", ex)
    _arp[:] = entries


def arp_for(name):
    """Voce del registro che corrisponde al nome mostrato da winget (che può essere troncato)."""
    n = name.strip().lower()
    if not n:
        return None
    exact = [e for e in _arp if e["name"].lower() == n]
    if exact:
        return exact[0]
    pref = [e for e in _arp if e["name"].lower().startswith(n) or n.startswith(e["name"].lower())]
    return pref[0] if len(pref) == 1 else None


ICONS = os.path.join(CACHE, "icons")


def extract_icons(paths):
    """Estrae in un colpo solo le icone dei programmi (PNG 64x64) e restituisce {percorso: id}."""
    os.makedirs(ICONS, exist_ok=True)
    ids, todo = {}, []
    for p in set(paths):
        if not p or not os.path.exists(p) or not p.lower().endswith((".exe", ".ico")):
            continue
        key = hashlib.sha1(p.lower().encode()).hexdigest()[:16]
        ids[p] = key
        if not os.path.exists(os.path.join(ICONS, key + ".png")):
            todo.append((p, key))
    if todo:
        lines = ";".join(
            "try { $i=" + ("New-Object Drawing.Icon('{0}')" if p.lower().endswith(".ico")
                           else "[Drawing.Icon]::ExtractAssociatedIcon('{0}')").format(p.replace("'", "''"))
            + f"; $b=New-Object Drawing.Bitmap 64,64; $g=[Drawing.Graphics]::FromImage($b);"
              f"$g.InterpolationMode='HighQualityBicubic'; $g.DrawImage($i.ToBitmap(),0,0,64,64);"
              f"$b.Save('{os.path.join(ICONS, k + '.png')}') }} catch {{}}"
            for p, k in todo)
        powershell("Add-Type -AssemblyName System.Drawing;" + lines, timeout=300)
    return {p: k for p, k in ids.items() if os.path.exists(os.path.join(ICONS, k + ".png"))}


def running_in(location):
    """Processi in esecuzione dentro la cartella di un programma: [{id, path, window}]."""
    if not location or len(location) < 6:
        return []
    loc = location.replace("'", "''")
    rc, out = powershell(
        f"Get-Process | Where-Object {{ $_.Path -and $_.Path.StartsWith('{loc}\\', 'OrdinalIgnoreCase') }} | "
        "Select-Object Id, Path, @{n='Window';e={$_.MainWindowHandle -ne 0}} | ConvertTo-Json -Compress", timeout=60)
    try:
        data = json.loads(out.strip() or "[]")
        return [{"id": d["Id"], "path": d["Path"], "window": bool(d["Window"])}
                for d in (data if isinstance(data, list) else [data]) if d["Id"] != os.getpid()]
    except Exception:
        return []


def close_apps(procs, log):
    """Chiude con garbo: prima le finestre; i programmi senza finestra (area di notifica) si fermano.
    Se un programma con finestra non si chiude (es. documento da salvare) non lo si forza: False."""
    ids = ",".join(str(p["id"]) for p in procs)
    powershell(f"Get-Process -Id {ids} -ErrorAction SilentlyContinue | ForEach-Object {{ [void]$_.CloseMainWindow() }}", timeout=30)
    for _ in range(16):
        time.sleep(0.5)
        alive = [p for p in procs if pid_alive(p["id"])]
        if not alive:
            return True
    if any(p["window"] for p in alive):
        return False
    powershell("Stop-Process -Id " + ",".join(str(p["id"]) for p in alive) + " -ErrorAction SilentlyContinue", timeout=30)
    time.sleep(1)
    return not any(pid_alive(p["id"]) for p in alive)


def pid_alive(pid):
    rc, out = run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], timeout=20)
    return str(pid) in out


def reopen(paths):
    """Riapre i programmi chiusi tramite Esplora risorse: partono senza privilegi di amministratore
    anche quando Aggiornamenti li ha."""
    for p in paths:
        if os.path.exists(p):
            subprocess.Popen(["explorer.exe", p], creationflags=NO_WINDOW)


def scan_winget():
    rc, out = run([WINGET, "upgrade", "--include-unknown"] + WG_COMMON, timeout=900)
    upgrades = parse_table(out)
    # interrogato su tutte le sorgenti winget a volte omette pacchetti (es. Microsoft 365 Apps)
    # che elenca sulla sola sorgente winget: si uniscono i due risultati
    rc, out_w = run([WINGET, "upgrade", "--include-unknown", "--source", "winget"] + WG_COMMON, timeout=900)
    seen_ids = {r["id"] for r in upgrades}
    upgrades += [{**r, "source": "winget"} for r in parse_table(out_w) if r["id"] not in seen_ids]
    rc, out_list = run([WINGET, "list"] + WG_COMMON, timeout=900)
    installed = parse_table(out_list)
    full = winget_full_ids()
    load_arp()

    # stessa app elencata sia dal Microsoft Store sia da winget: si tiene la copia winget
    by_name = {}
    for r in upgrades:
        key = TRUNC.sub("", r["name"]).strip().lower()
        if key not in by_name or (by_name[key].get("source") == "msstore" and r.get("source") != "msstore"):
            by_name[key] = r
    upgrades = list(by_name.values())

    blocked = load_settings().get("unupgradable") or {}
    items, skipped = [], []
    for r in upgrades:
        pid = resolve_id(r["id"], full)
        if pid in SELF_UPDATING:
            continue
        b = blocked.get(pid or "")
        if b and b.get("version") == r["version"]:
            # già fallito per un motivo che winget non può superare: si mostra tra le non controllate
            skipped.append({"name": TRUNC.sub("", r["name"]).strip(), "version": r["version"],
                            "reason": b["reason"], "path": None})
            continue
        unknown = r["version"].startswith("<") or r["version"].lower() in ("unknown", "sconosciuto")
        source = r.get("source") or "winget"
        items.append({
            "id": f"winget:{pid or r['id']}", "kind": "winget", "token": pid, "name": TRUNC.sub("", r["name"]).strip(),
            "installed": r["version"], "latest": r["available"],
            "source": "msstore" if source == "msstore" else "winget",
            "major": is_major(r["available"], r["version"]) and not unknown,
            "verified": pid is not None,
            "system": bool(SYSTEM_NAMES.search(r["name"])),
        })
    for it in items:
        it["key"] = item_key(it)
        a = arp_for(it["name"])
        if a:
            it["location"], it["icon_src"] = a["location"], a["icon"]

    # app installate che winget non sa aggiornare: niente origine, e non sono pacchetti di sistema MSIX
    unchecked = []
    seen = set()
    for r in installed:
        if r.get("source") or r["id"].startswith("MSIX\\") or SYSTEM_NAMES.search(r["name"]):
            continue
        if r["name"].strip() == "Aggiornamenti" or "Aggiornamenti" in r["id"]:
            continue   # sé stesso: si aggiorna con il proprio meccanismo
        name = TRUNC.sub("", r["name"]).strip()
        if name in seen:
            continue
        seen.add(name)
        a = arp_for(name)
        unchecked.append({"name": name, "version": r["version"], "reason": "no_source", "path": None,
                          "icon_src": a["icon"] if a else ""})
    unchecked += skipped
    # icone vere dei programmi; "path" è l'id dell'icona che la pagina chiede a /api/icon
    for u in skipped:
        a = arp_for(u["name"])
        u["icon_src"] = a["icon"] if a else ""
    icon_ids = extract_icons([x.get("icon_src", "") for x in items + unchecked])
    for x in items + unchecked:
        x["path"] = icon_ids.get(x.pop("icon_src", "") or "")
    unchecked.sort(key=lambda u: u["name"].lower())
    return items, unchecked


def scan_windows_update():
    """Aggiornamenti di Windows in attesa (solo lettura, tramite l'API di Windows Update)."""
    rc, out = powershell("try { $s=(New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher();"
                         "$r=$s.Search('IsInstalled=0 and IsHidden=0');"
                         "$r.Updates | ForEach-Object { 'WU:' + $_.Title } } catch { exit 1 }", timeout=300)
    if rc != 0:
        return []
    return [l.strip()[3:] for l in out.splitlines() if l.strip().startswith("WU:")][:5]


# ---------------------------------------------------------------- demo

DEMO_ITEMS = [
    ("Google Chrome", "Google.Chrome", "140.0.7339.81", "141.0.7390.55", "winget", False),
    ("Mozilla Firefox", "Mozilla.Firefox", "143.0", "143.0.4", "winget", False),
    ("7-Zip", "7zip.7zip", "24.09", "25.01", "winget", True),
    ("VLC media player", "VideoLAN.VLC", "3.0.21", "3.0.22", "winget", False),
    ("Visual Studio Code", "Microsoft.VisualStudioCode", "1.104.2", "1.105.0", "winget", False),
    ("Spotify", "9NCBCSZSJRSB", "1.2.72.438", "1.2.74.477", "msstore", False),
]


def demo_scan():
    time.sleep(2.5)
    items = [{"id": f"winget:{pid}", "kind": "winget", "token": pid, "name": n, "installed": a, "latest": b,
              "source": s, "major": m, "verified": True, "key": f"winget:{pid}"} for n, pid, a, b, s, m in DEMO_ITEMS]
    with lock:
        state.update(items=items, macos=[], scanning=False, scanned_at=time.time(),
                     unchecked=[{"name": "Driver audio Realtek", "version": "6.0.9", "reason": "no_source", "path": None},
                                {"name": "Software stampante", "version": "2.1", "reason": "no_source", "path": None}])


def demo_update(item):
    jid, total = item["id"], 120 * 1048576
    for i in range(1, 41):
        got = total * i // 40
        set_progress(jid, phase="download", bytes=got, total=total, pct=round(3 + 67 * got / total, 1))
        time.sleep(0.12)
    for phase, pct in (("verify", 72), ("install", 80), ("finish", 95)):
        set_progress(jid, phase=phase, pct=pct, bytes=None, total=None)
        time.sleep(0.7)
    with lock:
        state["jobs"][jid]["status"] = "done"
        state["items"] = [{**i, "updated": True} if i["id"] == jid else i for i in state["items"]]


# ---------------------------------------------------------------- scansione

def do_scan(force_self_check=False):
    threading.Thread(target=check_self_update, args=(force_self_check,), daemon=True).start()
    if DEMO:
        return demo_scan()
    try:
        with cf.ThreadPoolExecutor(2) as ex:
            f_wu = ex.submit(scan_windows_update)
            items, unchecked = scan_winget()
            wu = f_wu.result()
        items.sort(key=lambda i: (i.get("system", False), i["name"].lower()))
        with lock:
            state.update(items=items, unchecked=unchecked, macos=wu, scan_error=None)
            state["jobs"] = {k: v for k, v in state["jobs"].items() if v["status"] == "running"}
    except Exception as e:
        log_line("scansione", e)
        with lock:
            state["scan_error"] = str(e)
    finally:
        with lock:
            state["scanning"] = False
            state["scanned_at"] = time.time()


# ---------------------------------------------------------------- aggiornamento

def winget_progress(jid):
    """Fasi e percentuali dall'output di winget (italiano o inglese)."""
    cur = {"floor": 0}

    def on_line(line):
        low = line.lower()
        m = re.search(r"([\d.,]+)\s*(KB|MB|GB)\s*/\s*([\d.,]+)\s*(KB|MB|GB)", line)
        if m:
            mult = {"KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}
            got = float(m.group(1).replace(",", ".")) * mult[m.group(2)]
            tot = float(m.group(3).replace(",", ".")) * mult[m.group(4)]
            if tot:
                cur["floor"] = 3
                set_progress(jid, phase="download", bytes=int(got), total=int(tot),
                             pct=round(3 + 67 * min(got / tot, 1), 1))
            return
        m = re.search(r"(\d{1,3})\s?%", line)
        if m and cur["floor"] <= 3:
            set_progress(jid, phase="download", pct=round(3 + 0.67 * int(m.group(1)), 1))
            return
        for words, phase, floor in (
            (("riuscit", "successfully"), "finish", 95),
            (("hash", "verific", "verif"), "verify", 72),
            (("installazione", "installing", "install"), "install", 80),
            (("download", "scaricament"), "download", 3),
        ):
            if any(w in low for w in words):
                if floor >= cur["floor"]:
                    cur["floor"] = floor
                    set_progress(jid, phase=phase, pct=floor if phase != "download" else None,
                                 bytes=None, total=None)
                break
    return on_line


def update_one(item):
    if DEMO:
        return demo_update(item)
    jid = item["id"]
    lines = []

    def log(text):
        if text.strip():
            lines.append(text.rstrip())
            with lock:
                state["jobs"][jid]["log"] = "\n".join(lines)[-6000:]

    ok, reason = False, None
    reopen_paths = []
    procs = running_in(item.get("location", ""))
    if procs:
        set_progress(jid, phase="closing", pct=1)
        log(t("closing", x=item["name"]))
        if close_apps(procs, log):
            icon = (arp_for(item["name"]) or {}).get("icon", "").lower()
            # si riaprono le finestre e l'exe principale (per i programmi dell'area di notifica)
            reopen_paths = sorted({p["path"] for p in procs if p["window"] or p["path"].lower() == icon})
        else:
            log(t("app_open", x=item["name"]))
            item = {**item, "token": None, "_blocked": True}
    if item.get("_blocked"):
        pass
    elif not item.get("token"):
        log(t("id_cut", x=item["id"]))
    else:
        cmd = [WINGET, "upgrade", "--id", item["token"], "--exact", "--silent", "--include-unknown",
               "--accept-package-agreements"] + WG_COMMON
        if item.get("source") == "msstore":
            cmd += ["--source", "msstore"]
        on_line = winget_progress(jid)
        try:
            rc, _ = run_stream(cmd, lambda l: (log(l), on_line(l)))
            ok = rc == 0
            text = "\n".join(lines)
            if not ok and NOT_FOUND.search(text) and "--source" not in cmd:
                # winget a volte elenca un aggiornamento e poi non trova l'app: si riprova sulla sola sorgente winget
                lines.clear()
                rc, _ = run_stream(cmd + ["--source", "winget"], lambda l: (log(l), on_line(l)))
                ok = rc == 0
                text = "\n".join(lines)
            reason = None if ok else ("tech_diff" if TECH_DIFF.search(text) else
                                      "not_found" if NOT_FOUND.search(text) else
                                      "not_applicable" if NOT_APPLICABLE.search(text) else None)
            if reason:
                # non si ripropone finché la versione installata resta questa
                s = load_settings()
                s.setdefault("unupgradable", {})[item["token"]] = {"reason": reason, "version": item["installed"]}
                save_settings(s)
            elif not ok and re.search(r"codice di uscita|exit code", text, re.I):
                running = app_running(item["name"])
                log(t("app_open", x=running) if running else t("installer_failed"))
            if reason == "tech_diff":
                log(t("tech_diff"))
            if not ok and not is_admin() and re.search(r"amministrator|administrator|0x80070005|elevat", "\n".join(lines), re.I):
                log(t("need_admin"))
        except Exception as e:
            log(str(e))
    if reopen_paths:
        set_progress(jid, phase="reopening", pct=98)
        reopen(reopen_paths)
    with lock:
        if ok:
            state["jobs"][jid]["status"] = "done"
            state["items"] = [{**i, "updated": True} if i["id"] == jid else i for i in state["items"]]
        elif reason:
            # non è un errore da correggere ma un limite di winget: si sposta subito tra le non controllate
            state["jobs"][jid]["status"] = "moved"
            state["items"] = [{**i, "moved": True} if i["id"] == jid else i for i in state["items"]]
            state["unchecked"] = sorted(state["unchecked"] + [{"name": item["name"], "version": item["installed"],
                                                               "reason": reason, "path": None}],
                                        key=lambda u: u["name"].lower())
        else:
            state["jobs"][jid]["status"] = "error"


def app_running(name):
    """Nome del processo in esecuzione che corrisponde all'app (prima parola del nome), se c'è."""
    word = re.split(r"[\s\-_.(]", name.strip())[0]
    if len(word) < 4:
        return None
    rc, out = powershell(f"Get-Process -ErrorAction SilentlyContinue | Where-Object {{ $_.ProcessName -like '*{word}*' }} "
                         "| Select-Object -First 1 -Expand ProcessName", timeout=30)
    return out.strip() or None


def winget_download_dirs():
    temp = os.environ.get("TEMP") or tempfile.gettempdir()
    return [os.path.join(temp, "WinGet"), os.path.join(CACHE, "export.json")]


def dir_size(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for r, _, fs in os.walk(path):
        for f in fs:
            try:
                total += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return total


def cleanup():
    """Cancella gli installer scaricati da winget e i file temporanei. Restituisce i byte liberati."""
    with lock:
        state["cleaning"] = True
    freed = 0
    try:
        if DEMO:
            freed = int(0.9 * 1024 ** 3)
        else:
            for d in winget_download_dirs() + glob.glob(os.path.join(CACHE, "agg-*")):
                if os.path.exists(d):
                    size = dir_size(d)
                    if os.path.isdir(d):
                        shutil.rmtree(d, ignore_errors=True)
                    else:
                        os.remove(d)
                    freed += size - (dir_size(d) if os.path.exists(d) else 0)
    except Exception as e:
        log_line("pulizia", e)
    s = load_settings()
    s["last_cleanup"] = {"at": time.time(), "freed": freed}
    save_settings(s)
    with lock:
        state["cleaning"] = False
    return freed


def do_updates(ids):
    with lock:
        todo = [i for i in state["items"] if i["id"] in ids and not i.get("updated") and not i.get("moved")]
        for i in todo:
            state["jobs"][i["id"]] = {"status": "queued", "log": "", "phase": None, "pct": None, "bytes": None, "total": None}
        state["batch"] = {"total": len(todo), "done": 0}
    for item in todo:
        with lock:
            state["jobs"][item["id"]].update(status="running", phase="prepare", pct=0)
        update_one(item)
        with lock:
            state["batch"]["done"] += 1
    if todo:
        cleanup()
    with lock:
        state["running"] = False


# ---------------------------------------------------------------- pianificazione

def visible_pending():
    excluded = load_excluded()
    with lock:
        return [i for i in state["items"] if not i.get("updated") and not i.get("moved") and i.get("key") not in excluded]


def start_scan_sync():
    with lock:
        if state["running"]:
            return False
        already = state["scanning"]
        state["scanning"] = True
    if not already:
        do_scan()
        return True
    while True:
        time.sleep(2)
        with lock:
            if not state["scanning"]:
                return True


def scheduled_check():
    if not start_scan_sync():
        return
    todo = visible_pending()
    if todo:
        names = ", ".join(i["name"] for i in todo[:3]) + ("…" if len(todo) > 3 else "")
        notify(t("available", len(todo)), names)
    latest = self_update_available()
    s = load_settings()
    if latest and s.get("self_notified") != latest:
        notify(t("self_title", x=latest), t("self_body"))
        s["self_notified"] = latest
        save_settings(s)


def auto_update():
    if not start_scan_sync():
        return
    ids, postponed = [], []
    for i in visible_pending():
        if i.get("major") or i.get("verified") is False:
            continue
        if running_in(i.get("location", "")):
            postponed.append(i["name"])   # mai chiudere un programma mentre lo stai usando
        else:
            ids.append(i["id"])
    if ids:
        with lock:
            if state["running"] or state["scanning"]:
                return
            state["running"] = True
        do_updates(set(ids))
    with lock:
        updated = [i["name"] for i in state["items"] if i["id"] in ids and i.get("updated")]
        failed = [i["name"] for i in state["items"] if i["id"] in ids and not i.get("updated")]
    s = load_settings()
    s["last_auto"] = {"at": time.time(), "updated": updated, "failed": failed, "postponed": postponed}
    save_settings(s)
    if updated or failed or postponed:
        parts = []
        if updated:
            parts.append(t("upd_ok", len(updated)))
        if failed:
            parts.append(t("upd_fail", len(failed)))
        if postponed:
            parts.append(t("upd_postponed", len(postponed)))
        lc = s.get("last_cleanup") or {}
        if lc.get("freed"):
            parts.append(t("freed", x=human(lc["freed"])))
        notify(t("auto_title"), ", ".join(parts))


def due(hhmm, last_day, now):
    try:
        h, m = map(int, hhmm.split(":"))
    except Exception:
        return False
    return last_day != now.date().isoformat() and now >= now.replace(hour=h, minute=m, second=0, microsecond=0)


def scheduler():
    while True:
        time.sleep(30)
        try:
            now = dt.datetime.now()
            today = now.date().isoformat()
            s = load_settings()
            if s["auto_update"] and due(s["auto_time"], s["last_auto_day"], now):
                s["last_auto_day"] = s["last_check_day"] = today
                save_settings(s)
                auto_update()
            elif s["daily_check"] and due(s["check_time"], s["last_check_day"], now):
                s["last_check_day"] = today
                save_settings(s)
                scheduled_check()
        except Exception as e:
            log_line("scheduler", e)


# ---------------------------------------------------------------- aggiornamento di Aggiornamenti

def install_method():
    if FROZEN:
        return "exe"
    return "git" if os.path.isdir(os.path.join(ROOT, ".git")) else "archive"


def exe_asset_name():
    arch = "arm64" if os.environ.get("PROCESSOR_ARCHITECTURE", "").upper() == "ARM64" else "x64"
    return f"Aggiornamenti-{arch}.exe"


def check_self_update(force=False):
    with lock:
        info = state["self"]
        if not force and time.time() - info["checked_at"] < 6 * 3600:
            return
        info["checked_at"] = time.time()
    if DEMO:
        with lock:
            # in demo nessuna versione finta da installare: confonderebbe chi prova il programma
            state["self"].update(latest=VERSION, url=f"https://github.com/{REPO}/releases", notes="Demo")
        return
    try:
        req = urllib.request.Request(RELEASES_API, headers={"User-Agent": "AggiornamentiWin",
                                                             "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            rel = json.load(r)
        latest = str(rel.get("tag_name", "")).lstrip("v")
        if latest:
            with lock:
                state["self"].update(latest=latest, url=rel.get("html_url"), notes=rel.get("body") or "",
                                     assets={a.get("name"): a.get("browser_download_url") for a in rel.get("assets", [])})
    except Exception as e:
        log_line("controllo nuova versione", e)


def self_update_available():
    with lock:
        latest = state["self"]["latest"]
    return latest if latest and newer(latest, VERSION) else None


def restart_server():
    time.sleep(1.5)
    os.environ["AGG_RESTARTED"] = "1"
    # su Windows execv non mantiene il processo: se ne avvia uno nuovo e si esce
    args = ([sys.executable, "--background"] if FROZEN
            else [sys.executable, os.path.join(ROOT, "server.py")]) + sys.argv[1:]
    subprocess.Popen(args,
                     creationflags=NO_WINDOW | getattr(subprocess, "DETACHED_PROCESS", 0), close_fds=True)
    os._exit(0)


def do_self_update():
    global VERSION
    latest = self_update_available()
    lines = []

    def log(text):
        if text and text.strip():
            lines.append(text.strip())
            with lock:
                state["self"]["log"] = "\n".join(lines)[-6000:]

    ok = False
    try:
        if DEMO:
            time.sleep(3)
            ok = True
        elif install_method() == "exe":
            with lock:
                url = (state["self"].get("assets") or {}).get(exe_asset_name())
            if not url:
                log(f"{exe_asset_name()} non presente nella Release")
            else:
                exe = sys.executable
                new, old = exe + ".new", exe + ".old"
                log(t("downloading", x=url))
                req = urllib.request.Request(url, headers={"User-Agent": "AggiornamentiWin"})
                with urllib.request.urlopen(req, timeout=600) as r, open(new, "wb") as f:
                    shutil.copyfileobj(r, f)
                # un exe in esecuzione non si può sovrascrivere, ma si può rinominare
                if os.path.exists(old):
                    os.remove(old)
                os.replace(exe, old)
                os.replace(new, exe)
                ok = True
        elif install_method() == "git":
            rc, out = run(["git", "-C", ROOT, "status", "--porcelain", "--untracked-files=no"], timeout=60)
            if out.strip():
                log(t("self_dirty") + "\n" + out)
            else:
                rc, out = run(["git", "-C", ROOT, "fetch", "--tags", "origin"], timeout=300)
                log(out)
                rc, branch = run(["git", "-C", ROOT, "rev-parse", "--abbrev-ref", "HEAD"], timeout=30)
                cmd = (["git", "-C", ROOT, "checkout", f"v{latest}"] if branch.strip() == "HEAD"
                       else ["git", "-C", ROOT, "merge", "--ff-only", f"origin/{branch.strip()}"])
                rc, out = run(cmd, timeout=300)
                log(out)
                ok = rc == 0
        else:
            url = f"https://github.com/{REPO}/archive/refs/tags/v{latest}.zip"
            work = tempfile.mkdtemp(prefix="agg-", dir=CACHE)
            try:
                archive = os.path.join(work, "src.zip")
                log(t("downloading", x=url))
                req = urllib.request.Request(url, headers={"User-Agent": "AggiornamentiWin"})
                with urllib.request.urlopen(req, timeout=300) as r, open(archive, "wb") as f:
                    shutil.copyfileobj(r, f)
                shutil.unpack_archive(archive, work)
                src = next(iter(glob.glob(os.path.join(work, "aggiornamenti-windows-*"))), None)
                if src and os.path.exists(os.path.join(src, "server.py")):
                    shutil.copytree(src, ROOT, dirs_exist_ok=True)
                    ok = True
            finally:
                shutil.rmtree(work, ignore_errors=True)
    except Exception as e:
        log(str(e))
    with lock:
        state["self"]["status"] = "restarting" if ok else "error"
        state["running"] = False
    if ok and not DEMO:
        restart_server()
    elif ok:
        time.sleep(1.5)
        VERSION = latest
        with lock:
            state["self"]["status"] = None


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def snapshot(self):
        available, method = self_update_available(), install_method()
        with lock:
            return {
                "scanning": state["scanning"], "scanned_at": state["scanned_at"],
                "scan_error": state["scan_error"], "items": state["items"], "jobs": state["jobs"],
                "running": state["running"], "batch": state["batch"], "cleaning": state["cleaning"],
                "version": VERSION, "lang": LANG, "demo": DEMO, "platform": "windows",
                "repo": REPO, "admin": is_admin() or DEMO,
                "self": {**state["self"], "available": available, "method": method},
                "excluded": load_excluded(), "unchecked": state["unchecked"], "macos": state["macos"],
                "settings": {**load_settings(), "login": login_enabled() if not DEMO else False, "notifier": True},
                "password": is_admin() or DEMO,
            }

    def host_ok(self):
        return self.headers.get("Host") in (f"{HOST}:{PORT}", f"localhost:{PORT}")

    def handle_one_request(self):
        # un errore in una richiesta finisce nel registro invece di chiudere la connessione in silenzio
        try:
            super().handle_one_request()
        except Exception:
            import traceback
            log_line("richiesta", self.path if hasattr(self, "path") else "", traceback.format_exc())
            raise

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, {"error": "forbidden"})
        u = urlparse(self.path)
        if u.path == "/":
            with open(os.path.join(RES, "index.html"), "rb") as f:
                return self.send(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/api/state":
            return self.send(200, self.snapshot())
        if u.path == "/api/icon":
            from urllib.parse import parse_qs
            key = parse_qs(u.query).get("path", [""])[0]
            f = os.path.join(ICONS, key + ".png")
            if re.fullmatch(r"[0-9a-f]{16}", key) and os.path.exists(f):
                with open(f, "rb") as fh:
                    return self.send(200, fh.read(), "image/png")
            return self.send(404, b"", "image/png")
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if not self.host_ok():
            return self.send(403, {"error": "forbidden"})
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"):
            return self.send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        u = urlparse(self.path)
        if u.path == "/api/scan":
            with lock:
                if not state["scanning"] and not state["running"]:
                    state["scanning"] = True
                    threading.Thread(target=do_scan, args=(True,), daemon=True).start()
            return self.send(200, self.snapshot())
        if u.path == "/api/update":
            ids = set(body.get("ids") or [])
            with lock:
                if state["running"] or state["scanning"] or not ids:
                    return self.send(409, {"error": t("busy")})
                state["running"] = True
            threading.Thread(target=do_updates, args=(ids,), daemon=True).start()
            return self.send(200, self.snapshot())
        if u.path == "/api/self-update":
            with lock:
                if state["running"] or state["scanning"] or state["cleaning"]:
                    return self.send(409, {"error": t("busy")})
                state["running"] = True
                state["self"].update(status="updating", log="")
            if not self_update_available():
                with lock:
                    state["running"] = False
                    state["self"]["status"] = None
                return self.send(409, {"error": "no update"})
            threading.Thread(target=do_self_update, daemon=True).start()
            return self.send(200, self.snapshot())
        if u.path == "/api/quit":
            # usato dalla copia elevata per prendere il posto di questa
            with lock:
                busy = state["running"]
            if busy:
                return self.send(409, {"error": t("busy")})
            self.send(200, {"ok": True})
            threading.Timer(0.3, lambda: os._exit(0)).start()
            return
        if u.path == "/api/elevate":
            # una sola richiesta UAC: il server riparte come amministratore e crea l'avvio all'accesso
            if not DEMO and not is_admin():
                elevate_and_enable_login()
            return self.send(200, self.snapshot())
        if u.path == "/api/cleanup":
            with lock:
                if state["running"] or state["scanning"] or state["cleaning"]:
                    return self.send(409, {"error": t("busy")})
                state["running"] = True

            def job():
                try:
                    cleanup()
                finally:
                    with lock:
                        state["running"] = False
            threading.Thread(target=job, daemon=True).start()
            return self.send(200, self.snapshot())
        if u.path == "/api/settings":
            s = load_settings()
            now = dt.datetime.now()
            for flag, tkey, dkey in (("daily_check", "check_time", "last_check_day"),
                                     ("auto_update", "auto_time", "last_auto_day")):
                changed = False
                if flag in body and bool(body[flag]) != s[flag]:
                    s[flag] = bool(body[flag])
                    changed = True
                if tkey in body and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(body[tkey])):
                    changed = changed or s[tkey] != body[tkey]
                    s[tkey] = body[tkey]
                if changed:
                    h, m = map(int, s[tkey].split(":"))
                    passed = now >= now.replace(hour=h, minute=m, second=0, microsecond=0)
                    s[dkey] = now.date().isoformat() if passed else None
            if "welcomed" in body:
                s["welcomed"] = bool(body["welcomed"])
            save_settings(s)
            if "login" in body:
                if body["login"] and not is_admin() and not DEMO:
                    elevate_and_enable_login()
                else:
                    set_login(bool(body["login"]))
            return self.send(200, self.snapshot())
        if u.path == "/api/notify-test":
            notify("Aggiornamenti", t("test"))
            return self.send(200, self.snapshot())
        if u.path == "/api/open-software-update":
            os.startfile("ms-settings:windowsupdate") if not DEMO else None
            return self.send(200, self.snapshot())
        if u.path == "/api/exclude":
            key = str(body.get("key") or "")
            if not key:
                return self.send(400, {"error": "missing key"})
            with lock:
                excluded = load_excluded()
                if body.get("exclude"):
                    excluded[key] = {"name": str(body.get("name") or key), "path": None,
                                     "kind": body.get("kind"), "since": time.time()}
                else:
                    excluded.pop(key, None)
                save_excluded(excluded)
            return self.send(200, self.snapshot())
        self.send(404, {"error": "not found"})


def main():
    for a in ("--background",):
        if a in sys.argv:
            sys.argv.remove(a)
    if FROZEN:
        try:
            os.remove(sys.executable + ".old")   # resto di un auto-aggiornamento
        except OSError:
            pass
        try:   # la versione mostrata in Impostazioni > App segue gli auto-aggiornamenti
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Aggiornamenti",
                                0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
        except OSError:
            pass
    if "--enable-login" in sys.argv:
        # avviato elevato da /api/elevate: crea l'attività e prosegue come server amministratore
        sys.argv.remove("--enable-login")
        set_login(True)
        # il server non elevato occupa ancora la porta: gli si chiede di chiudersi
        try:
            urllib.request.urlopen(urllib.request.Request(f"{PAGE_URL}/api/quit", data=b"{}", method="POST"), timeout=3)
        except Exception:
            pass
        os.environ["AGG_RESTARTED"] = "1"
    if not DEMO and is_admin() and login_enabled():
        # le attività create dalle versioni fino alla 0.2.0 avevano le impostazioni sbagliate: si riscrivono
        threading.Thread(target=set_login, args=(True,), daemon=True).start()
    with lock:
        state["scanning"] = True
    attempts = 20 if os.environ.pop("AGG_RESTARTED", None) else 1
    for i in range(attempts):
        try:
            srv = ThreadingHTTPServer((HOST, PORT), Handler)
            break
        except OSError:
            if i == attempts - 1:
                print("Porta già in uso: Aggiornamenti è già attivo.", flush=True)
                sys.exit(0)
            time.sleep(0.5)
    threading.Thread(target=do_scan, daemon=True).start()
    threading.Thread(target=scheduler, daemon=True).start()
    for d in glob.glob(os.path.join(CACHE, "agg-*")):
        shutil.rmtree(d, ignore_errors=True)
    print(f"Aggiornamenti su {PAGE_URL}", flush=True)
    if DEMO:
        return srv.serve_forever()
    # icona vicino all'orologio nel thread principale, server in un thread a parte
    sys.modules.setdefault("server", sys.modules[__name__])   # tray importa "server": stesso stato
    import tray
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if not tray.run(on_quit=lambda: os._exit(0)):
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    main()
