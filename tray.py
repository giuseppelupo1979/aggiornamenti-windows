"""Icona di Aggiornamenti nell'area di notifica, vicino all'orologio.

Mostra quanti aggiornamenti sono disponibili (nel suggerimento e con un pallino sull'icona) e offre
un menu: Apri · Controlla ora · Esci. Gira nel processo in background, insieme al server.
"""

import os
import subprocess
import threading
import time

import server

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:          # avvio dal sorgente senza le librerie: niente icona, il resto funziona
    pystray = None

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TEXT = {
    "it": {"open": "Apri Aggiornamenti", "check": "Controlla ora", "quit": "Esci",
           "none": "Tutto aggiornato", "some": lambda n: "1 aggiornamento disponibile" if n == 1 else f"{n} aggiornamenti disponibili",
           "scanning": "Controllo in corso…", "updating": "Aggiornamento in corso…"},
    "en": {"open": "Open Aggiornamenti", "check": "Check now", "quit": "Quit",
           "none": "Everything is up to date", "some": lambda n: "1 update available" if n == 1 else f"{n} updates available",
           "scanning": "Checking…", "updating": "Updating…"},
}[server.LANG]


def base_image():
    path = os.path.join(server.RES, "assets", "icon.png")
    return Image.open(path).convert("RGBA").resize((64, 64), Image.LANCZOS)


def with_badge(img):
    """Pallino in alto a destra quando ci sono aggiornamenti."""
    img = img.copy()
    d = ImageDraw.Draw(img)
    d.ellipse((38, 0, 63, 25), fill=(255, 107, 94, 255), outline=(22, 22, 23, 255), width=3)
    return img


def open_window():
    """Apre la finestra passando da Esplora risorse: parte senza privilegi anche se il server li ha."""
    exe = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Aggiornamenti", "Aggiornamenti.exe")
    if server.FROZEN and os.path.exists(exe):
        subprocess.Popen(["explorer.exe", exe], creationflags=NO_WINDOW)
    else:
        os.startfile(server.PAGE_URL)


def check_now():
    with server.lock:
        if server.state["scanning"] or server.state["running"]:
            return
        server.state["scanning"] = True
    threading.Thread(target=server.do_scan, args=(True,), daemon=True).start()


def run(on_quit):
    """Blocca il thread chiamante (deve essere il principale) finché l'utente sceglie Esci."""
    if pystray is None:
        return False
    plain = base_image()
    badge = with_badge(plain)

    def quit_app(icon, _item):
        # mai a metà di un aggiornamento: in quel caso ci si chiude appena finisce
        if on_quit():
            icon.stop()
        else:
            server.notify("Aggiornamenti", server.t("quit_later"))

    menu = pystray.Menu(
        pystray.MenuItem(TEXT["open"], lambda i, _: open_window(), default=True),
        pystray.MenuItem(TEXT["check"], lambda i, _: check_now()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(TEXT["quit"], quit_app),
    )
    icon = pystray.Icon("Aggiornamenti", plain, "Aggiornamenti", menu)

    def refresh():
        last = None
        while True:
            pending = server.visible_pending()
            with server.lock:
                scanning, running = server.state["scanning"], server.state["running"]
            n = len(pending)
            status = TEXT["scanning"] if scanning else TEXT["updating"] if running else TEXT["some"](n) if n else TEXT["none"]
            cur = (status, n > 0)
            if cur != last:
                icon.title = f"Aggiornamenti · {status}"
                icon.icon = badge if n else plain
                last = cur
            time.sleep(3)

    threading.Thread(target=refresh, daemon=True).start()
    icon.run()
    return True
