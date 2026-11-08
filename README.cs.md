# LocalChef Studio

[🇬🇧 English](README.md) · **🇨🇿 Čeština**

**Offline správce, parser a převodník receptů pro chytré kuchyňské spotřebiče.**

LocalChef Studio je aplikace pro počítač (Python, PyQt6), která uchovává recepty v offline kuchařce ve tvém počítači a provede tě vařením krok po kroku. Pracuje s recepty pro **Thermomix® TM6** a **Monsieur Cuisine Smart** i se stovkami dalších webů s recepty – názvy spotřebičů a služeb slouží jen k popisu kompatibility.

**[⬇️ Instalátor pro Windows](#instalátor-pro-windows-doporučeno)** · [Releases](https://github.com/johnpreclik/localchef-studio/releases/latest)

> **Platforma:** LocalChef Studio je psané především pro **Windows 10/11** – tam se vyvíjí a testuje. Verze pro Docker (Linux, NAS) je **experimentální a v běžném provozu nebyla otestovaná**; automaticky se ověřuje jen její sestavení a spuštění.

## Funkce

- **Offline kuchařka** – uloží suroviny, kroky, tipy, obrázek, autora a odkaz na zdroj receptu a každý recept ukáže v jednotné kartě receptu, ať je z kteréhokoli webu; funguje bez internetu.
- **Hledání** – jedna úvodní stránka hledá v kuchařce i na webech s recepty, podle názvu nebo suroviny; na zahraničních webech v jejich jazyce (hledaný výraz se přeloží).
- **Přehrávač vaření** – velké ciferníky čas / teplota / rychlost, zvýrazněné suroviny aktuálního kroku, přepočet dávky, metrické jednotky a jemné kroky.
- **Převod mezi spotřebiči** – každý recept dostane verzi pro oba podporované typy (vestavěná pravidla, volitelně AI přes Gemini); recepty z ostatních webů převede offline asistent.
- **Překlady** – čeština a angličtina přes DeepL, Gemini nebo úplně offline (Argos Translate); když chybí, aplikace ho při startu sama stáhne a ukáže průběh; recept, který už v cílovém jazyce je, se nepřekládá.
- **Export do PDF** – přehledný list receptu na jednu stránku.
- **Záloha** – export označených receptů do jednoho `.7z` a import jedné či více záloh na libovolném počítači.
- **Aplikace v telefonu přes Wi-Fi** – kuchařka v prohlížeči telefonu nebo tabletu přes QR kód.
- **Vestavěný návod** česky i anglicky (❓ Návod).

Dokumentace: [návod](docs/LocalChef_Studio_navod_CZ.md) ([PDF](docs/LocalChef_Studio_navod_CZ.pdf)) · [úplná dokumentace](docs/LocalChef_Studio_dokumentace_CZ.md) ([PDF](docs/LocalChef_Studio_dokumentace_CZ.pdf))

## Spuštění z Pythonu (3.10+, testováno na 3.13 / Windows)

```
py -m pip install -r requirements.txt
py localchef_studio_v1.6.py
```

Verze je v názvu souboru. Všechna data jsou uložená místně ve složce `localchef_data` vedle programu: recepty, nastavení, API klíče a data relace vestavěného prohlížeče. Data ze starší verze se převezmou samy. Složka se do Gitu nikdy nenahrává (viz `.gitignore`) a nemá se sdílet – jsou v ní tvoje API klíče.

## Instalátor pro Windows (doporučeno)

Nejjednodušší cesta, jak dostat LocalChef Studio do Windows 10/11 – Python není potřeba.

**[⬇️ Stáhnout LocalChef_Studio_1.6.exe](https://github.com/johnpreclik/localchef-studio/releases/latest/download/LocalChef_Studio_1.6.exe)** (asi 280 MB) · [všechny soubory posledního vydání](https://github.com/johnpreclik/localchef-studio/releases/latest)

Je to klasický instalátor se zástupcem v nabídce Start (volitelně i na ploše) a odinstalací. Instaluje se pro aktuálního uživatele do `%LOCALAPPDATA%\Programs\LocalChef Studio` (bez administrátora). Instalátor není podepsaný, SmartScreen se proto může zeptat: *Další informace → Přesto spustit*. Recepty a nastavení (`localchef_data`) aktualizace zachová a odinstalace je nesmaže. Při startu aplikace zjistí, jestli je na GitHubu nová verze, a když souhlasíš, sama ji stáhne a nainstaluje (⚙️ Nastavení → 🔄 Zkontrolovat aktualizace).

Každé vydání má také **LocalChef_Studio_1.6_python.zip** (spuštění z Pythonu nebo sestavení vlastního exe) a **LocalChef_Studio_1.6_docker.zip** (soubory pro Docker).

## Sestavení exe pro Windows

Spusť `build_exe.bat` – vytvoří `dist\LocalChefStudio\LocalChefStudio.exe` se všemi knihovnami (1–2 GB kvůli offline překladači). Instalátor se pak sestaví programem [Inno Setup](https://jrsoftware.org/isinfo.php):

```
iscc /DAppVersion=1.6 installer\localchef_studio.iss
```

Totéž umí na GitHubu workflow [Windows installer](.github/workflows/windows-installer.yml) (spouští se ručně): spustí `build_exe.bat`, vyzkouší program, postaví instalátor, zkušebně ho nainstaluje a odinstaluje a může vytvořit GitHub Release.

## Docker (experimentální)

Aplikace běží na virtuální obrazovce v kontejneru a ovládá se z prohlížeče (noVNC na portu **6080**); aplikace pro telefon je na portu **3665**. Verze pro Docker nebyla otestovaná v běžném provozu – případné problémy prosím nahlas.

### Linux – sestavení přímo z GitHubu

Nic není potřeba předem stahovat, Docker si zdrojový kód vezme z GitHubu sám:

```
docker build -t localchef-studio -f docker/Dockerfile https://github.com/johnpreclik/localchef-studio.git#main
docker run -d --name localchef --restart unless-stopped --shm-size=1g -p 6080:6080 -p 3665:3665 -e LOCALCHEF_LAN_HOST=IP_POCITACE -e VNC_PASSWORD=heslo -v "$HOME/localchef_data:/data/localchef_data" localchef-studio
```

Pak v prohlížeči otevři http://localhost:6080/.

- `IP_POCITACE` = adresa počítače v síti (pro QR kód v telefonu), např. `192.168.1.10`.
- Nastav `VNC_PASSWORD` (max. 8 znaků) – port 6080 je vidět v celé síti.
- `--build-arg WITH_ARGOS=0` v příkazu `docker build` vynechá offline překladač (obraz je asi o 2 GB menší).
- Recepty a nastavení zůstávají ve složce `~/localchef_data`.
- Aktualizace: znovu `docker build`, pak `docker rm -f localchef` a stejný `docker run`. Data zůstanou.
- Bez přístupu na GitHub: rozbal `LocalChef_Studio_1.6_docker.zip` z Releases a v jeho složce spusť `docker build -t localchef-studio -f docker/Dockerfile .`.
- Když tvůj uživatel není ve skupině `docker`, dej před `docker` ještě `sudo`.

### NAS, např. TrueNAS SCALE 24.10+

Stejné dva příkazy v shellu NASu (TrueNAS: *System → Shell*), se `sudo`, adresou NASu v `LOCALCHEF_LAN_HOST` a daty na úložišti: `-v /mnt/POOL/apps/localchef:/data/localchef_data` (`POOL` = název úložiště). Nebo přes webové rozhraní TrueNAS: *Apps → Discover → Custom App → Install via YAML* se souborem [`docker-compose.yml`](docker-compose.yml) (uprav tři označené hodnoty).

### Windows (Docker Desktop)

Spusť `build_docker.bat` (`build_docker.bat noargos` vynechá offline překladač). Otevře http://localhost:6080/.

Workflow [Docker build](.github/workflows/docker-build.yml) sestaví obraz z GitHubu stejným příkazem, spustí ho a ověří, že aplikace, noVNC i server pro telefon odpovídají.

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

LocalChef Studio je nezávislý open-source projekt a není spojený se společnostmi Vorwerk (Thermomix / Cookidoo) ani Lidl (Monsieur Cuisine), není jimi schválený ani podporovaný. Všechny ochranné známky patří jejich vlastníkům.

Nástroj je určený pro vzdělávací účely a osobní potřebu. Neslouží k pirátství ani k obcházení předplatného či jiných omezení přístupu. Recepty, texty a fotografie patří jejich autorům a provozovatelům webů; ukládej jen recepty, ke kterým máš legální přístup, a dodržuj podmínky použití webů. Úplné znění je v [`DISCLAIMER.txt`](DISCLAIMER.txt).
