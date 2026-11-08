# LocalChef Studio

**🇬🇧 English** · [🇨🇿 Čeština](README.cs.md)

**Offline recipe manager, parser, and converter for smart kitchen appliances.**

LocalChef Studio is a desktop app (Python, PyQt6) that keeps your recipes in an offline cookbook on your own computer and guides you through cooking step by step. It works with recipes for **Thermomix® TM6** and **Monsieur Cuisine Smart** and with hundreds of other recipe websites – the appliance and service names are used only to describe compatibility.

**[⬇️ Windows installer](#windows-installer-recommended)** · [Releases](https://github.com/johnpreclik/localchef-studio/releases/latest)

> **Platform:** LocalChef Studio is written primarily for **Windows 10/11** – that is where it is developed and tested. The Docker version (Linux, NAS) is **experimental and has not been tested in everyday use**; only its build and start are checked automatically.

## Features

- **Offline cookbook** – saves the recipe's ingredients, steps, tips, image, author and a link to its source and shows every recipe in one unified recipe card, whichever website it comes from; works without internet.
- **Search** – one start page searches your cookbook and recipe websites, by name or by ingredient; foreign sites are searched in their own language (the search term is translated).
- **Cooking player** – large time / temperature / speed dials, highlighted ingredients for the current step, batch scaling, metric conversion and detailed steps.
- **Conversion between appliances** – each recipe gets a version for both supported appliance types (built-in rules, optionally AI via Gemini); recipes from other websites are converted by an offline assistant.
- **Translations** – Czech and English via DeepL, Gemini or a fully offline translator (Argos Translate); the app downloads it at start by itself and shows the progress; a recipe already in the target language is not translated.
- **PDF export** – a clean one-page recipe sheet.
- **Backup** – export selected recipes into a single `.7z` and import one or more backups on any computer.
- **Phone app over Wi-Fi** – open the cookbook in a phone or tablet browser via a QR code.
- **Built-in user guide** in Czech and English (❓ How to use).

Documentation: [user guide](docs/LocalChef_Studio_user_guide_EN.md) ([PDF](docs/LocalChef_Studio_user_guide_EN.pdf)) · [full documentation](docs/LocalChef_Studio_documentation_EN.md) ([PDF](docs/LocalChef_Studio_documentation_EN.pdf))

## Run with Python (3.10+, tested on 3.13 / Windows)

```
py -m pip install -r requirements.txt
py localchef_studio_v1.6.py
```

The version is part of the file name. All data are stored locally in `localchef_data` next to the program: recipes, settings, API keys and the built-in browser's session data. Data from an older version are taken over automatically. This folder is never committed (see `.gitignore`) and should not be shared – it contains your API keys.

## Windows installer (recommended)

The easiest way to get LocalChef Studio on Windows 10/11 – no Python needed.

**[⬇️ Download LocalChef_Studio_1.6.exe](https://github.com/johnpreclik/localchef-studio/releases/latest/download/LocalChef_Studio_1.6.exe)** (about 280 MB) · [all files of the latest release](https://github.com/johnpreclik/localchef-studio/releases/latest)

It is a standard installer with a Start menu shortcut (optionally a desktop one) and an uninstaller. It installs for the current user into `%LOCALAPPDATA%\Programs\LocalChef Studio` (no administrator). The installer is not code-signed, so SmartScreen may ask: *More info → Run anyway*. Recipes and settings (`localchef_data`) survive updates and are not deleted on uninstall. At start the app checks GitHub for a new version and, if you agree, downloads and installs it by itself (⚙️ Settings → 🔄 Check for updates).

Each release also has **LocalChef_Studio_1.6_python.zip** (run from Python or build your own .exe) and **LocalChef_Studio_1.6_docker.zip** (Docker files).

## Build a Windows .exe

Run `build_exe.bat` – it creates `dist\LocalChefStudio\LocalChefStudio.exe` with all libraries (1–2 GB because of the offline translator). The installer is then built with [Inno Setup](https://jrsoftware.org/isinfo.php):

```
iscc /DAppVersion=1.6 installer\localchef_studio.iss
```

The [Windows installer](.github/workflows/windows-installer.yml) workflow can do the same on GitHub (started by hand): it runs `build_exe.bat`, starts the program, builds the installer, test-installs and uninstalls it and can publish a GitHub release.

## Docker (experimental)

The app runs on a virtual screen inside the container and is used from a web browser (noVNC on port **6080**); the phone app is on port **3665**. The Docker version has not been tested in everyday use – please report any problems.

### Linux – build straight from GitHub

No need to download anything first; Docker fetches the source from GitHub itself:

```
docker build -t localchef-studio -f docker/Dockerfile https://github.com/johnpreclik/localchef-studio.git#main
docker run -d --name localchef --restart unless-stopped --shm-size=1g -p 6080:6080 -p 3665:3665 -e LOCALCHEF_LAN_HOST=YOUR_PC_IP -e VNC_PASSWORD=password -v "$HOME/localchef_data:/data/localchef_data" localchef-studio
```

Then open http://localhost:6080/ in a browser.

- `YOUR_PC_IP` = the computer's address on your network (used in the phone QR code), e.g. `192.168.1.10`.
- Set `VNC_PASSWORD` (max. 8 characters) – port 6080 is reachable from the whole network.
- Add `--build-arg WITH_ARGOS=0` to `docker build` to leave out the offline translator (the image is about 2 GB smaller).
- Recipes and settings are kept in `~/localchef_data`.
- Update: run `docker build` again, then `docker rm -f localchef` and the same `docker run`. Data stay in place.
- Without internet access to GitHub: unpack `LocalChef_Studio_1.6_docker.zip` from Releases and run `docker build -t localchef-studio -f docker/Dockerfile .` inside it.
- Use `sudo` before `docker` if your user is not in the `docker` group.

### NAS, e.g. TrueNAS SCALE 24.10+

The same two commands in the NAS shell (TrueNAS: *System → Shell*), with `sudo`, the NAS address in `LOCALCHEF_LAN_HOST` and data on your pool: `-v /mnt/POOL/apps/localchef:/data/localchef_data` (`POOL` = your pool name). Alternatively in the TrueNAS web UI: *Apps → Discover → Custom App → Install via YAML* with [`docker-compose.yml`](docker-compose.yml) (edit the three marked values).

### Windows (Docker Desktop)

Run `build_docker.bat` (`build_docker.bat noargos` leaves out the offline translator). It opens http://localhost:6080/.

The [Docker build](.github/workflows/docker-build.yml) workflow builds the image from GitHub with the same command, starts it and checks that the app, noVNC and the phone server respond.

## Development

- Tests without Qt: `python tests/run_all.py` (optionally `-v` or test names).
- PDF documentation is generated from the Markdown in `docs/`: `python tools/build_docs.py`.

## Support

If you like LocalChef Studio and want to support its further development, you can buy me a coffee:
[Ko-fi](https://ko-fi.com/johnpreclik) · [PayPal](https://paypal.me/johnpreclik) · [Revolut](https://revolut.me/preca). Thank you!

## License

LocalChef Studio's own code is released under the [MIT License](LICENSE).

Third-party components keep their own licenses: PyQt6 and PyQt6-WebEngine are GPL v3, py7zr is LGPL 2.1+, beautifulsoup4, argostranslate, deepl and recipe-scrapers are MIT. The source code can be used under MIT; a built program that bundles PyQt6 (the Windows `.exe` or the Docker image) is distributed under the terms of GPL v3, so share it together with this source code.

## Disclaimer

LocalChef Studio is an independent open-source project and is not affiliated with, endorsed by, or connected to Vorwerk (Thermomix / Cookidoo) or Lidl (Monsieur Cuisine). All trademarks belong to their respective owners.

The tool is intended for educational purposes and personal use. It is not meant for piracy or for getting around subscriptions or other access restrictions. Recipes, texts and photos belong to their authors and website operators; save only recipes you have legitimate access to and follow each website's terms of use. See [`DISCLAIMER.txt`](DISCLAIMER.txt) for the full text.
