## LocalChef Studio {version}

🇬🇧 English · 🇨🇿 Čeština níže

**Offline recipe manager, parser, and converter for smart kitchen appliances.** Written primarily for Windows 10/11; the Docker version is experimental and untested in everyday use.

### Install (Windows 10/11, 64-bit)

1. Download **LocalChef_Studio_{version}.exe** below and run it.
2. Windows SmartScreen may warn about an unknown publisher (the installer is not code-signed): click **More info → Run anyway**.
3. The app installs for the current user into `%LOCALAPPDATA%\Programs\LocalChef Studio` (no administrator needed) and adds a Start menu shortcut.

Your recipes and settings are stored in `localchef_data` next to the program. Updating to a newer version keeps them; uninstalling does **not** delete them. Moving from an older portable version: copy its data folder into the install folder, or use the .7z backup (Export / Import recipes).

### Other downloads

- **LocalChef_Studio_{version}_python.zip** – run the app from Python (`py localchef_studio_v{version}.py`) or build your own .exe with `build_exe.bat`; includes the PDF documentation.
- **LocalChef_Studio_{version}_docker.zip** – Docker version (experimental): `build_docker.bat` on Windows with Docker Desktop, `docker build -t localchef-studio -f docker/Dockerfile .` on Linux, or `docker-compose.yml` for a NAS (TrueNAS). The app then runs in a browser at http://localhost:6080/. On Linux it can also be built straight from GitHub – see the README.

What's new is shown in the app on first start (ℹ️ What's new). Documentation: [docs](https://github.com/johnpreclik/localchef-studio/tree/main/docs).

---

### Čeština

**Offline správce, parser a převodník receptů pro chytré kuchyňské spotřebiče.** Psané především pro Windows 10/11; verze pro Docker je experimentální a v běžném provozu neotestovaná.

#### Instalace (Windows 10/11, 64bit)

1. Stáhni níže **LocalChef_Studio_{version}.exe** a spusť ho.
2. Windows SmartScreen může varovat před neznámým vydavatelem (instalátor není podepsaný): klikni na **Další informace → Přesto spustit**.
3. Aplikace se nainstaluje pro aktuálního uživatele do `%LOCALAPPDATA%\Programs\LocalChef Studio` (bez administrátora) a přidá zástupce do nabídky Start.

Recepty a nastavení jsou ve složce `localchef_data` vedle programu. Aktualizace na novější verzi je zachová, odinstalace je **nesmaže**. Přechod ze starší přenosné verze: zkopíruj její datovou složku do složky instalace, nebo použij zálohu .7z (Export / Import receptů).

#### Další soubory

- **LocalChef_Studio_{version}_python.zip** – spuštění z Pythonu (`py localchef_studio_v{version}.py`) nebo sestavení vlastního exe přes `build_exe.bat`; obsahuje i PDF dokumentaci.
- **LocalChef_Studio_{version}_docker.zip** – verze pro Docker (experimentální): `build_docker.bat` na Windows s Docker Desktop, `docker build -t localchef-studio -f docker/Dockerfile .` na Linuxu, nebo `docker-compose.yml` pro NAS (TrueNAS). Aplikace pak běží v prohlížeči na http://localhost:6080/. Na Linuxu jde sestavit i přímo z GitHubu – viz README.

Co je nového ukáže aplikace při prvním spuštění (ℹ️ Co je nového). Dokumentace: [docs](https://github.com/johnpreclik/localchef-studio/tree/main/docs).

---

LocalChef Studio is an independent open-source project and is not affiliated with, endorsed by, or connected to Vorwerk (Thermomix / Cookidoo) or Lidl (Monsieur Cuisine). All trademarks belong to their respective owners. The program bundles PyQt6 (GPL v3); source code: this repository (MIT).

LocalChef Studio je nezávislý open-source projekt a není spojený se společnostmi Vorwerk (Thermomix / Cookidoo) ani Lidl (Monsieur Cuisine). Všechny ochranné známky patří jejich vlastníkům. Program obsahuje PyQt6 (GPL v3); zdrojový kód: tento repozitář (MIT).
