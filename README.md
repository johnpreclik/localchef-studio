# LocalChef Studio

**🇬🇧 English** · [🇨🇿 Čeština](README.cs.md)

**Offline recipe manager, parser, and converter for smart kitchen appliances.**

LocalChef Studio is a desktop app (Python, PyQt6) that keeps your recipes in an offline cookbook on your own computer and guides you through cooking step by step. It works with recipes for **Thermomix® TM6** and **Monsieur Cuisine Smart** and with hundreds of other recipe websites – the appliance and service names are used only to describe compatibility.

## Features

- **Offline cookbook** – recipes saved with ingredients, steps, tips and a 1:1 copy of the page; works without internet.
- **Search** – one start page searches your cookbook and recipe websites, by name or by ingredient.
- **Cooking player** – large time / temperature / speed dials, highlighted ingredients for the current step, batch scaling, metric conversion and detailed steps.
- **Conversion between appliances** – each recipe gets a version for both supported appliance types (built-in rules, optionally AI via Gemini); recipes from other websites are converted by an offline assistant.
- **Translations** – Czech and English via DeepL, Gemini or a fully offline translator (Argos Translate); the app offers to download it at start.
- **PDF export** – a clean one-page recipe sheet.
- **Backup** – export selected recipes into a single `.7z` and import one or more backups on any computer.
- **Phone app over Wi-Fi** – open the cookbook in a phone or tablet browser via a QR code.
- **Built-in user guide** in Czech and English (❓ How to use).

Documentation: [user guide](docs/LocalChef_Studio_user_guide_EN.md) ([PDF](docs/LocalChef_Studio_user_guide_EN.pdf)) · [full documentation](docs/LocalChef_Studio_documentation_EN.md) ([PDF](docs/LocalChef_Studio_documentation_EN.pdf))

## Download and install (Windows 10/11)

Download **LocalChef_Studio_1.5.exe** from [Releases](https://github.com/johnpreclik/localchef-studio/releases/latest) and run it – a standard installer with a Start menu shortcut and an uninstaller. It installs for the current user into `%LOCALAPPDATA%\Programs\LocalChef Studio` (no administrator). The installer is not code-signed, so SmartScreen may ask: *More info → Run anyway*. Recipes and settings (`localchef_data`) survive updates and are not deleted on uninstall.

## Run with Python (3.10+, tested on 3.13 / Windows)

```
py -m pip install -r requirements.txt
py localchef_studio_v1.5.py
```

The version is part of the file name. Data (recipes, settings, logins) are stored in `localchef_data` next to the program; data from an older version are taken over automatically. This folder is never committed (see `.gitignore`) – it holds API keys, logins and saved recipes.

## Build a Windows .exe

Run `build_exe.bat` – it creates `dist\LocalChefStudio\LocalChefStudio.exe` with all libraries (1–2 GB because of the offline translator).

Release builds (exe + installer) are made by the [Windows installer](.github/workflows/windows-installer.yml) workflow: it runs `build_exe.bat`, starts the program, builds the Inno Setup installer (`installer/localchef_studio.iss`), test-installs and uninstalls it and publishes a GitHub release.

## Docker

The app runs on a virtual screen inside the container and is used from a web browser (noVNC on port **6080**); the phone app is on port **3665**.

**Windows (Docker Desktop):** run `build_docker.bat` (`build_docker.bat noargos` leaves out the offline translator). It opens http://localhost:6080/.

**NAS / Linux, e.g. TrueNAS SCALE 24.10+** – the image is built straight from GitHub. In the NAS shell (TrueNAS: *System → Shell*):

```
sudo docker build -t localchef-studio -f docker/Dockerfile https://github.com/johnpreclik/localchef-studio.git#main
sudo docker run -d --name localchef --restart unless-stopped --shm-size=1g -p 6080:6080 -p 3665:3665 -e LOCALCHEF_LAN_HOST=NAS_IP -e VNC_PASSWORD=password -v /mnt/POOL/apps/localchef:/data/localchef_data localchef-studio
```

- `NAS_IP` = the NAS address on your network (used in the phone QR code), `POOL` = your pool name.
- Set `VNC_PASSWORD` (max. 8 characters) – on a NAS port 6080 is reachable from the whole network.
- Update: run `docker build` again, then `sudo docker rm -f localchef` and the same `docker run`. Data stay on your pool.
- TrueNAS web UI alternative: *Apps → Discover → Custom App → Install via YAML* with [`docker-compose.yml`](docker-compose.yml) (edit the three marked values).

The Docker build is checked automatically by the [Docker build](.github/workflows/docker-build.yml) workflow, which builds the image from GitHub with the same command, starts it and checks the app, noVNC and the phone server.

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
