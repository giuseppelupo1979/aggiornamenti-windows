"""Aggiornamenti.exe: doppio clic e si apre la finestra.

Al primo avvio da una cartella qualsiasi (per esempio Download) il programma si installa da solo
nella cartella utente, crea i collegamenti e la voce in Impostazioni > App, poi si apre.

  --background   solo il server (usato dall'avvio all'accesso e dai riavvii)
  --demo         modalità demo su una porta separata, senza modifiche al sistema
  --uninstall    rimuove programma, collegamenti, attività pianificata e dati
"""

import os
import shutil
import subprocess
import sys
import time
import urllib.request

import server

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0)
APP_ID = server.APP_ID
INSTALL_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Aggiornamenti")
INSTALLED_EXE = os.path.join(INSTALL_DIR, "Aggiornamenti.exe")
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Aggiornamenti"


def up(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=2)
        return True
    except Exception:
        return False


def quit_running(port):
    try:
        urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/quit", data=b"{}",
                                                      method="POST"), timeout=3)
    except Exception:
        pass


def edge_path():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(p):
                return p
    return None


def open_window(url):
    edge = edge_path()
    if not edge:
        os.startfile(url)
        return
    # profilo normale di Edge: niente schermate di benvenuto; --app toglie barra degli indirizzi e schede
    subprocess.Popen([edge, f"--app={url}", "--window-size=900,980"], creationflags=DETACHED)


def ps(script):
    return server.powershell(script, timeout=120)


# ---------------------------------------------------------------- installazione

def shortcut(path, target, args=""):
    q = lambda s: s.replace("'", "''")
    ps(f"$l=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(path)}');"
       f"$l.TargetPath='{q(target)}';$l.Arguments='{q(args)}';$l.IconLocation='{q(target)},0';"
       f"$l.WorkingDirectory='{q(os.path.dirname(target))}';$l.Description='Aggiornamenti';$l.Save()")


def shortcut_paths():
    start = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs", "Aggiornamenti.lnk")
    rc, desktop = ps("[Environment]::GetFolderPath('Desktop')")
    return start, os.path.join(desktop.strip(), "Aggiornamenti.lnk")


def stop_installed_copies():
    """Chiude ogni copia in esecuzione dell'exe installato (finestra, server, modalità demo):
    Windows non permette di sovrascrivere un programma aperto."""
    for port in (server.PORT, 8766):
        if up(port):
            quit_running(port)
    target = INSTALLED_EXE.replace("'", "''")
    ps(f"Get-Process | Where-Object {{ $_.Path -eq '{target}' -and $_.Id -ne {os.getpid()} }} | Stop-Process -Force")


def install():
    """Copia l'exe nella cartella utente e lo registra come programma installato."""
    import winreg
    os.makedirs(INSTALL_DIR, exist_ok=True)
    stop_installed_copies()
    for attempt in range(20):   # il file si libera qualche istante dopo la chiusura dei processi
        try:
            shutil.copy2(sys.executable, INSTALLED_EXE)
            break
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.5)
    icon = os.path.join(INSTALL_DIR, "icon.png")
    shutil.copy2(os.path.join(server.RES, "assets", "icon.png"), icon)
    for lnk in shortcut_paths():
        shortcut(lnk, INSTALLED_EXE)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        for name, value in (("DisplayName", "Aggiornamenti"), ("DisplayVersion", server.VERSION),
                            ("Publisher", "Giuseppe Lupo"), ("DisplayIcon", INSTALLED_EXE),
                            ("InstallLocation", INSTALL_DIR),
                            ("UninstallString", f'"{INSTALLED_EXE}" --uninstall'),
                            ("URLInfoAbout", f"https://github.com/{server.REPO}")):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, os.path.getsize(INSTALLED_EXE) // 1024)
    # nome e icona con cui compaiono le notifiche (invece di "Windows PowerShell")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{APP_ID}") as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "Aggiornamenti")
        winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, icon)


def uninstall():
    import winreg
    quit_running(server.PORT)
    server.run(["taskkill", "/F", "/IM", "Aggiornamenti.exe", "/FI", f"PID ne {os.getpid()}"], timeout=30)
    if server.login_enabled():
        # l'attività è stata creata con i privilegi: per toglierla serve la stessa conferma di Windows
        import ctypes
        ctypes.windll.shell32.ShellExecuteW(None, "runas", "schtasks.exe", f"/Delete /TN {server.TASK_NAME} /F", None, 0)
    for lnk in shortcut_paths():
        try:
            os.remove(lnk)
        except OSError:
            pass
    for key in (UNINSTALL_KEY, rf"Software\Classes\AppUserModelId\{APP_ID}"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except OSError:
            pass
    shutil.rmtree(os.path.join(os.environ.get("LOCALAPPDATA", ""), "AggiornamentiWin"), ignore_errors=True)
    # l'exe in uso non può cancellarsi da solo: lo fa un comando che parte dopo la sua chiusura
    subprocess.Popen(f'cmd /c ping 127.0.0.1 -n 3 > nul & rmdir /s /q "{INSTALL_DIR}"',
                     creationflags=NO_WINDOW | DETACHED, close_fds=True)


def main():
    args = sys.argv[1:]
    if "--background" in args:
        return server.main()
    if "--uninstall" in args:
        return uninstall()
    demo = "--demo" in args
    frozen = getattr(sys, "frozen", False)

    # avviato fuori dalla cartella di installazione (es. da Download): si installa o aggiorna e si riapre da lì
    if frozen and not demo and os.path.normcase(sys.executable) != os.path.normcase(INSTALLED_EXE):
        install()
        subprocess.Popen([INSTALLED_EXE], creationflags=DETACHED, close_fds=True)
        return

    port = server.PORT
    if not up(port):
        cmd = [sys.executable, "--background"] if frozen else [sys.executable, os.path.abspath(__file__), "--background"]
        if demo:
            cmd.append("--demo")
        # con l'avvio all'accesso attivo si riparte dall'attività pianificata (privilegi senza richiesta)
        if not demo and server.login_enabled():
            server.run(["schtasks", "/Run", "/TN", server.TASK_NAME], timeout=30)
        else:
            subprocess.Popen(cmd, creationflags=NO_WINDOW | DETACHED, close_fds=True)
        for _ in range(60):
            if up(port):
                break
            time.sleep(0.5)
    open_window(f"http://127.0.0.1:{port}/")


def message(text):
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, text, "Aggiornamenti", 0x10)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # mai la finestra tecnica di Python: un messaggio comprensibile e il dettaglio nel registro
        import traceback
        server.log_line("avvio", traceback.format_exc())
        if server.LANG == "it":
            message(f"Aggiornamenti non è riuscito ad avviarsi.\n\n{e}\n\nChiudi eventuali finestre di Aggiornamenti "
                    f"e riprova. Il dettaglio è nel registro:\n{server.LOG_FILE}")
        else:
            message(f"Aggiornamenti could not start.\n\n{e}\n\nClose any Aggiornamenti window and try again. "
                    f"Details are in the log:\n{server.LOG_FILE}")
