"""Genera il manifest per il catalogo winget (microsoft/winget-pkgs) di una versione pubblicata.

Uso: python tools/winget_manifest.py 0.5.0
Legge gli SHA-256 dagli asset della Release su GitHub e scrive i tre file in
winget/manifests/g/GiuseppeLupo/Aggiornamenti/<versione>/. L'invio a microsoft/winget-pkgs (una pull
request con `wingetcreate submit` o a mano) resta una scelta di chi pubblica: non lo fa questo script.
"""
import os
import sys
import urllib.request

PKG = "GiuseppeLupo.Aggiornamenti"
REPO = "giuseppelupo1979/aggiornamenti-windows"


def sha(version, arch):
    url = f"https://github.com/{REPO}/releases/download/v{version}/Aggiornamenti-{arch}.exe.sha256"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "AggiornamentiWin"}), timeout=30) as r:
        return r.read().decode().split()[0].upper()


def main(version):
    out = os.path.join(os.path.dirname(__file__), "..", "winget", "manifests", "g", "GiuseppeLupo", "Aggiornamenti", version)
    os.makedirs(out, exist_ok=True)
    head = "# yaml-language-server: $schema=https://aka.ms/winget-manifest.{kind}.1.9.0.schema.json\n\n"
    installers = "".join(f"""- Architecture: {arch}
  InstallerUrl: https://github.com/{REPO}/releases/download/v{version}/Aggiornamenti-{arch}.exe
  InstallerSha256: {sha(version, arch)}
""" for arch in ("x64", "arm64"))
    files = {
        f"{PKG}.yaml": head.format(kind="version") + f"""PackageIdentifier: {PKG}
PackageVersion: {version}
DefaultLocale: it-IT
ManifestType: version
ManifestVersion: 1.9.0
""",
        f"{PKG}.installer.yaml": head.format(kind="installer") + f"""PackageIdentifier: {PKG}
PackageVersion: {version}
InstallerType: exe
Scope: user
InstallModes:
- silent
InstallerSwitches:
  Silent: --install
  SilentWithProgress: --install
UpgradeBehavior: install
MinimumOSVersion: 10.0.17763.0
Installers:
{installers}ManifestType: installer
ManifestVersion: 1.9.0
""",
        f"{PKG}.locale.it-IT.yaml": head.format(kind="defaultLocale") + f"""PackageIdentifier: {PKG}
PackageVersion: {version}
PackageLocale: it-IT
Publisher: Giuseppe Lupo
PublisherUrl: https://github.com/giuseppelupo1979
PackageName: Aggiornamenti
PackageUrl: https://github.com/{REPO}
License: MIT
LicenseUrl: https://github.com/{REPO}/blob/main/LICENSE
ShortDescription: Aggiorna con un clic i programmi del PC che winget conosce.
Description: Pagina locale che elenca i programmi con una versione nuova e li aggiorna tutti insieme tramite winget, con aggiornamento notturno, rinvii, storico e ritorno alla versione precedente.
Tags:
- updater
- winget
- aggiornamenti
ReleaseNotesUrl: https://github.com/{REPO}/releases/tag/v{version}
ManifestType: defaultLocale
ManifestVersion: 1.9.0
""",
    }
    for name, text in files.items():
        with open(os.path.join(out, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print(os.path.abspath(out))


if __name__ == "__main__":
    main(sys.argv[1])
