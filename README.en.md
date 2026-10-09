# Aggiornamenti for Windows

**Keeps every program on your PC up to date with one click.** Open Aggiornamenti, see which programs have a new version and update them all at once, without visiting each vendor's website. Free, no ads, no account. *Aggiornamenti* is Italian for "updates".

[Versione italiana →](README.md)

![The Aggiornamenti window](docs/finestra.png)

## Install (3 minutes)

1. **[Download Aggiornamenti](https://github.com/giuseppelupo1979/aggiornamenti-windows/releases/latest/download/Aggiornamenti-x64.exe)**, for almost every PC. Only for ARM PCs (Surface Pro X, Snapdragon Copilot+ laptops) use **[this version](https://github.com/giuseppelupo1979/aggiornamenti-windows/releases/latest/download/Aggiornamenti-arm64.exe)**. Not sure? *Start → Settings → System → About → System type*.
2. **Open the downloaded file.** Windows will most likely show a blue **"Windows protected your PC"** screen (in Italian: "PC protetto da Windows"), as it does for every new program that isn't signed with a paid certificate. Click **More info**, then **Run anyway**.
3. **Done.** The window opens and the first check starts. The program has installed itself: you'll find it in the **Start menu** and on the **Desktop**. You can delete the downloaded file.

**Recommended:** at the bottom of the window open *Administrator rights off*, press **Turn on** and answer **Yes** once. From then on updates install silently and Aggiornamenti starts by itself at login for the daily check.

## Using it

Click the programs to update (or **Select all**) and press **Update**; each one shows a progress bar. *Major version* updates are never selected for you. Hover a row and click **Exclude** to hide a program. *Automatic check* can notify you daily or update everything at night. When a new version of Aggiornamenti is out, a box at the top offers to **Install** it.

## FAQ

- **Is it safe?** It uses **winget**, Microsoft's official package manager included in Windows 11, which downloads each update from the vendor and verifies it. The code is public here, and the exe is built by GitHub Actions from this code.
- **Does it send data anywhere?** No. Only the connections needed to check and download updates, plus a request to GitHub every six hours to see whether a new version of Aggiornamenti exists. No account, no telemetry.
- **My antivirus flags it.** Some antivirus tools wrongly flag programs built with PyInstaller. Compare the SHA-256 checksum published on the [release page](https://github.com/giuseppelupo1979/aggiornamenti-windows/releases/latest).
- **Some programs are missing.** Programs winget doesn't know are listed under *Not checked*. Microsoft Edge isn't listed because it updates itself.
- **Uninstall:** *Start → Settings → Apps → Installed apps → Aggiornamenti → Uninstall*.

## Under the hood

A small local server (Python, standard library only) driving winget, with a web interface shown in a Microsoft Edge app window. It listens only on `127.0.0.1`. x64 and ARM64 exes are built by [GitHub Actions](.github/workflows/build.yml). There is also a Mac version: [aggiornamenti-mac](https://github.com/giuseppelupo1979/aggiornamenti-mac).

[MIT License](LICENSE). Provided **without warranty**: it installs and updates software on your PC, so use it at your own risk. Made by Giuseppe Lupo with Claude (Anthropic).
