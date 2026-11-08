# LocalChef Studio

[🇬🇧 English](README.md) · **🇨🇿 Čeština**

**Offline správce, parser a převodník receptů pro chytré kuchyňské spotřebiče.**

LocalChef Studio je aplikace pro počítač (Python, PyQt6), která uchovává recepty v offline kuchařce ve tvém počítači a provede tě vařením krok po kroku. Pracuje s recepty pro **Thermomix® TM6** a **Monsieur Cuisine Smart** i se stovkami dalších webů s recepty – názvy spotřebičů a služeb slouží jen k popisu kompatibility.

## Funkce

- **Offline kuchařka** – recepty se surovinami, kroky, tipy a kopií stránky 1:1; fungují bez internetu.
- **Hledání** – jedna úvodní stránka hledá v kuchařce i na webech s recepty, podle názvu nebo suroviny.
- **Přehrávač vaření** – velké ciferníky čas / teplota / rychlost, zvýrazněné suroviny aktuálního kroku, přepočet dávky, metrické jednotky a jemné kroky.
- **Převod mezi spotřebiči** – každý recept dostane verzi pro oba podporované typy (vestavěná pravidla, volitelně AI přes Gemini); recepty z ostatních webů převede offline asistent.
- **Překlady** – čeština a angličtina přes DeepL, Gemini nebo úplně offline (Argos Translate); stažení aplikace nabídne při startu.
- **Export do PDF** – přehledný list receptu na jednu stránku.
- **Záloha** – export označených receptů do jednoho `.7z` a import jedné či více záloh na libovolném počítači.
- **Aplikace v telefonu přes Wi-Fi** – kuchařka v prohlížeči telefonu nebo tabletu přes QR kód.
- **Vestavěný návod** česky i anglicky (❓ Návod).

Dokumentace: [návod](docs/LocalChef_Studio_navod_CZ.md) ([PDF](docs/LocalChef_Studio_navod_CZ.pdf)) · [úplná dokumentace](docs/LocalChef_Studio_dokumentace_CZ.md) ([PDF](docs/LocalChef_Studio_dokumentace_CZ.pdf))

## Stažení a instalace (Windows 10/11)

Stáhni **LocalChef_Studio_1.5.exe** z [Releases](https://github.com/johnpreclik/localchef-studio/releases/latest) a spusť ho – klasický instalátor se zástupcem v nabídce Start a odinstalací. Instaluje se pro aktuálního uživatele do `%LOCALAPPDATA%\Programs\LocalChef Studio` (bez administrátora). Instalátor není podepsaný, SmartScreen se proto může zeptat: *Další informace → Přesto spustit*. Recepty a nastavení (`localchef_data`) aktualizace zachová a odinstalace je nesmaže.

## Spuštění z Pythonu (3.10+, testováno na 3.13 / Windows)

```
py -m pip install -r requirements.txt
py localchef_studio_v1.5.py
```

Verze je v názvu souboru. Data (recepty, nastavení, přihlášení) jsou ve složce `localchef_data` vedle programu; data ze starší verze se převezmou samy. Složka se do Gitu nikdy nenahrává (viz `.gitignore`) – obsahuje API klíče, přihlášení a uložené recepty.

## Sestavení exe pro Windows

Spusť `build_exe.bat` – vytvoří `dist\LocalChefStudio\LocalChefStudio.exe` se všemi knihovnami (1–2 GB kvůli offline překladači).

Vydání (exe + instalátor) sestavuje workflow [Windows installer](.github/workflows/windows-installer.yml): spustí `build_exe.bat`, vyzkouší program, postaví instalátor Inno Setup (`installer/localchef_studio.iss`), zkušebně ho nainstaluje a odinstaluje a vytvoří GitHub Release.

## Docker

Aplikace běží na virtuální obrazovce v kontejneru a ovládá se z prohlížeče (noVNC na portu **6080**); aplikace pro telefon je na portu **3665**.

**Windows (Docker Desktop):** spusť `build_docker.bat` (`build_docker.bat noargos` vynechá offline překladač). Otevře http://localhost:6080/.

**NAS / Linux, např. TrueNAS SCALE 24.10+** – obraz se sestaví přímo z GitHubu. V shellu NASu (TrueNAS: *System → Shell*):

```
sudo docker build -t localchef-studio -f docker/Dockerfile https://github.com/johnpreclik/localchef-studio.git#main
sudo docker run -d --name localchef --restart unless-stopped --shm-size=1g -p 6080:6080 -p 3665:3665 -e LOCALCHEF_LAN_HOST=IP_NASU -e VNC_PASSWORD=heslo -v /mnt/POOL/apps/localchef:/data/localchef_data localchef-studio
```

- `IP_NASU` = adresa NASu v síti (pro QR kód v telefonu), `POOL` = název úložiště.
- Nastav `VNC_PASSWORD` (max. 8 znaků) – na NASu je port 6080 vidět v celé síti.
- Aktualizace: znovu `docker build`, pak `sudo docker rm -f localchef` a stejný `docker run`. Data zůstanou na úložišti.
- Přes webové rozhraní TrueNAS: *Apps → Discover → Custom App → Install via YAML* se souborem [`docker-compose.yml`](docker-compose.yml) (uprav tři označené hodnoty).

Sestavení Dockeru automaticky ověřuje workflow [Docker build](.github/workflows/docker-build.yml): obraz sestaví z GitHubu stejným příkazem, spustí ho a zkontroluje aplikaci, noVNC i server pro telefon.

## Vývoj

- Testy bez Qt: `python tests/run_all.py` (volitelně `-v` nebo jména testů).
- PDF dokumentace se generuje z Markdownu v `docs/`: `python tools/build_docs.py`.

## Podpora

Pokud se vám LocalChef Studio líbí a chcete podpořit jeho další vývoj, můžete mi koupit kafe:
[Ko-fi](https://ko-fi.com/johnpreclik) · [PayPal](https://paypal.me/johnpreclik) · [Revolut](https://revolut.me/preca). Děkuji!

## Licence

Vlastní kód LocalChef Studia je pod [licencí MIT](LICENSE).

Knihovny třetích stran mají vlastní licence: PyQt6 a PyQt6-WebEngine GPL v3, py7zr LGPL 2.1+, beautifulsoup4, argostranslate, deepl a recipe-scrapers MIT. Zdrojový kód jde používat podle MIT; sestavený program, který obsahuje PyQt6 (`.exe` pro Windows nebo Docker obraz), se šíří podle podmínek GPL v3 – šiř ho proto spolu s tímto zdrojovým kódem.

## Upozornění

LocalChef Studio is an independent open-source project and is not affiliated with, endorsed by, or connected to Vorwerk (Thermomix / Cookidoo) or Lidl (Monsieur Cuisine). All trademarks belong to their respective owners.

LocalChef Studio je nezávislý projekt a není spojený se společnostmi Vorwerk (Thermomix / Cookidoo) ani Lidl (Monsieur Cuisine), není jimi schválený ani podporovaný. Všechny ochranné známky patří jejich vlastníkům.

Nástroj je určený pro vzdělávací účely a osobní potřebu. Neslouží k pirátství ani k obcházení předplatného či jiných omezení přístupu. Recepty, texty a fotografie patří jejich autorům a provozovatelům webů; ukládej jen recepty, ke kterým máš legální přístup, a dodržuj podmínky použití webů. Úplné znění je v [`DISCLAIMER.txt`](DISCLAIMER.txt).
