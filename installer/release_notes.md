## LocalChef Studio {version}

**Offline recipe manager, parser, and converter for smart kitchen appliances.**

### Install (Windows 10/11, 64-bit)

1. Download **LocalChef_Studio_{version}.exe** below and run it.
2. Windows SmartScreen may warn about an unknown publisher (the installer is not code-signed): click **More info → Run anyway**.
3. The app installs for the current user into `%LOCALAPPDATA%\Programs\LocalChef Studio` (no administrator needed) and adds a Start menu shortcut.

Your recipes, settings and logins are stored in `localchef_data` next to the program. Updating to a newer version keeps them; uninstalling does **not** delete them. Moving from an older portable version: copy its data folder into the install folder, or use the .7z backup (Export / Import recipes).

### Instalace (česky)

Stáhni **LocalChef_Studio_{version}.exe** a spusť ho. SmartScreen může varovat před neznámým vydavatelem (instalátor není podepsaný) – **Další informace → Přesto spustit**. Aplikace se nainstaluje pro aktuálního uživatele do `%LOCALAPPDATA%\Programs\LocalChef Studio` bez administrátora. Recepty a nastavení jsou ve složce `localchef_data` vedle programu; aktualizace je zachová, odinstalace je **nesmaže**.

### Other downloads

- **LocalChef_Studio_{version}_python.zip** – run the app from Python (`py localchef_studio_v{version}.py`) or build your own .exe with `build_exe.bat`; includes the PDF documentation.
- **LocalChef_Studio_{version}_docker.zip** – Docker version: `build_docker.bat` on Windows with Docker Desktop, or `docker-compose.yml` for a NAS (TrueNAS). The app then runs in a browser at http://localhost:6080/.

What's new is shown in the app on first start (ℹ️ What's new). Documentation: [docs](https://github.com/johnpreclik/localchef-studio/tree/main/docs).

---

LocalChef Studio is an independent open-source project and is not affiliated with, endorsed by, or connected to Vorwerk (Thermomix / Cookidoo) or Lidl (Monsieur Cuisine). All trademarks belong to their respective owners. The program bundles PyQt6 (GPL v3); source code: this repository (MIT).
