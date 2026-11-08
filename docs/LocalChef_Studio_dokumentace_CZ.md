# LocalChef Studio – dokumentace

Verze 1.5 · offline kuchařka a průvodce vařením s kuchyňským robotem

LocalChef Studio je nezávislý projekt. Není spojený se společnostmi Vorwerk (Thermomix, Cookidoo) ani Lidl (Monsieur Cuisine) a není jimi schválený ani podporovaný. Jejich názvy se v této dokumentaci používají jen k popisu kompatibility a jsou ochrannými známkami svých vlastníků.

## 1. Co aplikace dělá

LocalChef Studio ukládá recepty z webů s recepty do vlastní offline kuchařky v počítači a umí je vařit krok po kroku na kuchyňském robotu. Recepty pak fungují bez internetu, dají se převést pro jiný typ robota, přeložit, vytisknout, zálohovat a zobrazit v telefonu nebo tabletu v kuchyni.

Hlavní funkce v kostce:

- **Offline kuchařka** – recept se uloží do počítače se surovinami a kroky a s místním snímkem stránky (karta receptu) pro osobní prohlížení offline.
- **Kompatibilní weby** – recepty pro Thermomix TM6 (Cookidoo), Monsieur Cuisine Smart (monsieur-cuisine.com) a stovky dalších webů s recepty (Prima FRESH, Chefkoch, Allrecipes, BBC Good Food…).
- **Hledání** – úvodní stránka 🏠 Domů hledá ve vlastní kuchařce i na webech, podle názvu nebo suroviny.
- **Dva roboty** – každý recept má verzi pro Thermomix TM6 i Monsieur Cuisine Smart (MCS); druhá vzniká automatickým převodem. Recepty z ostatních webů převede offline asistent.
- **Přehrávač receptu** – velké ciferníky s časem, teplotou a rychlostí, zvýrazněné suroviny aktuálního kroku, přepočet dávky a jednotek, jemné kroky.
- **Překlady** – recept i kartu přeloží do češtiny nebo angličtiny: DeepL, Gemini nebo úplně offline.
- **PDF** – přehledný list receptu na jednu stránku.
- **Záloha .7z** – export označených receptů do jednoho souboru a jejich import (i na jiném počítači).
- **Telefon** – počítač slouží jako server, recepty se otevřou v prohlížeči telefonu přes domácí Wi-Fi.
- **Návod v aplikaci** – tlačítko ❓ Návod (česky i anglicky).

Aplikace je jeden soubor `localchef_studio_v1.5.py` (číslo verze je v názvu). Spustit se dá jako Python skript (kapitola 2), jako samostatný program `LocalChefStudio.exe` bez Pythonu (kapitola 3), nebo v Dockeru, třeba na NASu (kapitola 4). Rozhraní je česky nebo anglicky.

**Platforma:** aplikace je psaná především pro **Windows 10/11**, kde se vyvíjí a testuje. Verze pro Docker je experimentální a v běžném provozu nebyla otestovaná.

Recepty se ukládají přes vestavěný prohlížeč. Všechno ostatní pracuje s uloženými daty ve složce `localchef_data`, takže funguje i bez internetu. Internet potřebují jen ukládání z webu, hledání na webech a online překladače.

### Instalace z instalátoru (nejjednodušší)

Stáhni **LocalChef_Studio_1.5.exe** ze stránky Releases (https://github.com/johnpreclik/localchef-studio/releases/latest) a spusť ho. Instalátor (česky nebo anglicky) nainstaluje aplikaci pro aktuálního uživatele do `%LOCALAPPDATA%\Programs\LocalChef Studio`, bez administrátora, přidá zástupce do nabídky Start (volitelně na plochu) a odinstalaci do Nastavení Windows. Instalátor není podepsaný, SmartScreen se proto může zeptat: „Další informace → Přesto spustit“. Data (`localchef_data`) jsou vedle programu; aktualizace je zachová a odinstalace je nesmaže. Kdyby se aplikace nainstalovala tam, kam nejde zapisovat (Program Files), použije `%LOCALAPPDATA%\LocalChef Studio\localchef_data`.

## 2. Požadavky a instalace (spuštění jako .py)

Aplikace potřebuje **Python 3.10 nebo novější** (vyvíjena a testována na Pythonu 3.13 ve Windows).

| Knihovna (pip) | Povinná | K čemu slouží |
|---|---|---|
| PyQt6 | ano | okno aplikace, tlačítka, seznam receptů |
| PyQt6-WebEngine | ano | vestavěný prohlížeč a karta receptu |
| beautifulsoup4 | ano | čtení receptů z uložených stránek |
| argostranslate | ne | offline překladač bez internetu a bez klíčů (kapitola 13) |
| deepl | ne | překladač DeepL, když máš jeho API klíč |
| recipe-scrapers | ne | ukládání receptů ze stovek dalších webů |
| py7zr | ne | záloha a import receptů (.7z, kapitola 17) |

Instalace všeho najednou ze složky aplikace:

```
py -m pip install -r requirements.txt
```

`argostranslate` s sebou stáhne velké knihovny (torch, ctranslate2…), instalace proto zabere řádově gigabajt a trvá déle. Žlutá varování „not on PATH“ jsou neškodná. Když příkaz `py` nefunguje (Python z Microsoft Store), použij `python`.

Spuštění:

```
py localchef_studio_v1.5.py
```

Spouštěj ze složky, kde mají být data: složka `localchef_data` se vytváří v aktuální složce příkazového řádku. Při prvním spuštění se Windows může zeptat na síťový přístup – povol ho pro soukromou síť, jinak nepůjde aplikace v telefonu (kapitola 15).

**Přechod ze starší verze:** spusť novou verzi ze stejné složky. Při prvním startu převezme starou datovou složku – recepty i nastavení zůstanou.

## 3. Samostatný program (.exe)

Skript `build_exe.bat` sestaví program `LocalChefStudio.exe`, který běží na Windows bez nainstalovaného Pythonu. Obsahuje vše včetně vestavěného prohlížeče, offline překladače a zálohování. Sestavení stačí udělat jednou na počítači s Pythonem.

1. Dej `localchef_studio_v1.5.py` a `build_exe.bat` do stejné složky (skript si soubor s verzí najde sám).
2. Spusť `build_exe.bat` dvojklikem. Nainstaluje PyInstaller a knihovny a sestaví program v režimu „složka“.
3. Hotový program je ve složce `dist\LocalChefStudio`.

První sestavení trvá dlouho (stahování knihoven i desítky minut). Výsledná složka má kvůli offline překladači 1–2 GB.

**Přenos na jiný počítač:** zkopíruj celou složku `dist\LocalChefStudio`. Samotné exe bez zbytku složky nefunguje. Program je čistý, bez dat; při prvním spuštění si vedle exe vytvoří prázdnou `localchef_data`. U exe jsou všechna data vždy vedle programu, i jazykové modely offline překladače (`localchef_data\argos_packages`).

**Na co se připravit:** Windows SmartScreen u nepodepsaného programu ukáže varování („Další informace → Přesto spustit“). Antivirus někdy zbytečně podezírá programy z PyInstalleru – případně přidej složku do výjimek. Když sestavený program nefunguje, změň v `build_exe.bat` přepínač `--windowed` na `--console` a sestav znovu; chyby se vypíšou do konzole.

## 4. Docker a NAS (TrueNAS)

Aplikace jde spustit v Dockeru. Běží na virtuální obrazovce v kontejneru a ovládá se z prohlížeče přes noVNC (port **6080**); aplikace pro telefon běží na portu **3665** jako obvykle.

> Verze pro Docker je **experimentální** a v běžném provozu nebyla otestovaná; automaticky se ověřuje jen její sestavení a spuštění.

**Windows (Docker Desktop):** spusť `build_docker.bat`. Sestaví obraz, spustí kontejner `localchef` a otevře http://localhost:6080/. `build_docker.bat noargos` vynechá offline překladač (obraz je asi o 2 GB menší). Data kontejneru jsou v `docker_data\localchef_data`, oddělená od Windows verze.

**Linux:** obraz se sestaví přímo z GitHubu – nic není potřeba předem stahovat:

```
docker build -t localchef-studio -f docker/Dockerfile https://github.com/johnpreclik/localchef-studio.git#main
docker run -d --name localchef --restart unless-stopped --shm-size=1g -p 6080:6080 -p 3665:3665 -e LOCALCHEF_LAN_HOST=IP_POCITACE -e VNC_PASSWORD=heslo -v "$HOME/localchef_data:/data/localchef_data" localchef-studio
```

Pak otevři http://localhost:6080/. `IP_POCITACE` je adresa počítače v síti (pro QR kód v telefonu). `--build-arg WITH_ARGOS=0` v `docker build` vynechá offline překladač. Když tvůj uživatel není ve skupině `docker`, dej před `docker` ještě `sudo`. Bez přístupu na GitHub rozbal `LocalChef_Studio_1.5_docker.zip` z Releases a v jeho složce spusť `docker build -t localchef-studio -f docker/Dockerfile .`.

**NAS (např. TrueNAS SCALE 24.10 a novější):** stejné sestavení z GitHubu, v shellu NASu (TrueNAS: System → Shell):

```
sudo docker build -t localchef-studio -f docker/Dockerfile https://github.com/johnpreclik/localchef-studio.git#main
sudo docker run -d --name localchef --restart unless-stopped --shm-size=1g -p 6080:6080 -p 3665:3665 -e LOCALCHEF_LAN_HOST=IP_NASU -e VNC_PASSWORD=heslo -v /mnt/POOL/apps/localchef:/data/localchef_data localchef-studio
```

- `IP_NASU` nahraď adresou NASu v síti (telefon ji dostane v QR kódu), `POOL` názvem úložiště.
- `VNC_PASSWORD` chrání ovládání v prohlížeči – na NASu je port 6080 vidět v celé síti, heslo proto nastav (VNC bere nejvýš 8 znaků).
- Aktualizace na novou verzi: zopakuj `docker build`, pak `sudo docker rm -f localchef` a znovu `docker run`. Data zůstanou ve složce na úložišti.
- Alternativa přes webové rozhraní TrueNAS (Apps → Discover → Custom App → Install via YAML): soubor `docker-compose.yml` z repozitáře.

## 5. Rozhraní a první spuštění

Okno má vlevo panel s kuchařkou a vpravo pracovní plochu s horní lištou, lištou receptu a vestavěným prohlížečem nebo přehrávačem.

### Levý panel (shora dolů)

| Prvek | Co dělá |
|---|---|
| ➕ Rozbalit vše / ➖ Sbalit vše | rozbalí nebo sbalí všechny kategorie |
| Filtr kategorií, ⭐ Oblíbené, ➕ Nová kategorie | jedna kategorie, jen oblíbené, založení kategorie |
| Filtr strojů | všechny / 🟢 jen Cookidoo (TM6) / 🔵 jen Monsieur Cuisine / ⚫ jen ostatní weby |
| Názvy | jazyk názvů v seznamu (originál, angličtina, čeština, podle jazyka aplikace) |
| 🔍 Hledat recepty | filtruje podle názvu, nedbá na diakritiku |
| Strom receptů | recepty podle kategorií; klik otevře, Ctrl/Shift + klik označí víc, pravé tlačítko menu |
| ⭐ Oblíbené / 🏷️ Změnit kategorii / 🗑️ Smazat | práce s vybraným receptem (kapitola 9) |
| 📥 Importovat recepty / 📦 Exportovat označené | záloha .7z (kapitola 17) |
| 📡 Wi-Fi server + 📱 QR kód | adresa a QR kód pro telefon (kapitola 15) |

### Horní lišta (zleva doprava)

| Prvek | Co dělá |
|---|---|
| ◀ Zpět | předchozí stránka ve vestavěném prohlížeči |
| 🏠 Domů | úvodní stránka s hledáním (kapitola 6) |
| 🟢 Cookidoo.cz / 🔵 Monsieur-Cuisine | otevře web s recepty ve vestavěném prohlížeči |
| adresní řádek | adresa stránky, při práci i stav (např. průběh překladu) |
| ⬇️ ULOŽIT RECEPT | uložení otevřeného receptu (kapitola 8) |
| 💛 Podpořit vývoj | dobrovolná podpora autora: Ko-fi, PayPal nebo Revolut (i QR kód) |
| ❓ Návod | návod k použití v aplikaci |
| ⚙️ Nastavení | menu nastavení (níže) |

### Lišta receptu

Zobrazit: 📄 Karta receptu / 🍲 Režim Thermomix (TM6) / 🤖 Monsieur Cuisine Smart (MCS), jazyk 🌐 Originál / 🇬🇧 English / 🇨🇿 Čeština, 🔄 Přeložit znovu a 🖨️ Export do PDF.

### Menu ⚙️ Nastavení

| Oddíl | Položky |
|---|---|
| Překlad | 🌍 Přeložit všechny recepty, ✨ Gemini AI klíč, 📥 Stáhnout offline překladač, 🔑 DeepL |
| Vzhled | jazyk aplikace (čeština / angličtina), tmavý / světlý režim, styl ikon (🟢/🔵 nebo 🍲/🤖) |
| Aplikace | ❓ Návod k použití, ℹ️ Co je nového a podmínky použití |

### První spuštění krok za krokem

1. Spusť aplikaci (kapitola 2, 3 nebo 4). Vytvoří si prázdnou kuchařku.
2. Ukáže se okno **Co je nového a podmínky použití**. Tlačítko OK se odemkne po dočtení do konce.
3. Aplikace zkontroluje **offline překladač**. Když chybí, nabídne stažení (ANO / NE) s volbou „Příště se již neptat“. Stáhnout ho jde kdykoli v ⚙️ → 📥 Stáhnout offline překladač.
4. Klikni na 🏠 Domů, najdi recept a ulož ho tlačítkem ⬇️ ULOŽIT RECEPT. Pro Cookidoo se nejdřív přihlas (kapitola 7).
5. Volitelně zadej klíče Gemini nebo DeepL (kapitola 14).

## 6. Hledání receptů (🏠 Domů)

Úvodní stránka hledá zároveň ve **tvé kuchařce** a na **webech s recepty**: Cookidoo, Monsieur Cuisine, Prima FRESH, Chefkoch, Allrecipes a BBC Good Food. Hledat jde podle **názvu** nebo podle **suroviny**.

- Výsledky z webů se ukazují po zdrojích, s obrázkem a odkazem. Klik otevře recept ve vestavěném prohlížeči, kde ho uložíš.
- Když web nic nenajde a místo výsledků nabídne „populární recepty“, aplikace je nebere.
- Při hledání podle názvu jsou výsledky, které hledané slovo obsahují, první (porovnává se kmen slova bez diakritiky – „zelňačka“ najde i „Zelná polévka“).
- Stejné hledání funguje z telefonu (kapitola 15); výsledky pak vyhledá počítač.
- Seznam webů jde rozšířit v `config.json` (klíč `search_sources`).

## 7. Přihlášení na webech

Na **Cookidoo** se před ukládáním receptů musíš přihlásit svým účtem. Bez přihlášení web ukáže jen název a suroviny a postup skryje. Recepty **Monsieur Cuisine** jsou veřejné a ukládají se bez účtu. Ostatní weby přihlášení obvykle nepotřebují.

Aplikace recepty čte ze stránek, které vidíš ve vestavěném prohlížeči. Co nevidíš ty, nevidí ani aplikace. Proto se přihlašuje přímo v ní:

1. Klikni na 🟢 Cookidoo.cz v horní liště.
2. Na webu klikni na přihlášení a přihlas se, stejně jako v běžném prohlížeči.

Přihlášení se pamatuje ve složce `localchef_data/browser_profile`, takže po dalším spuštění jsi stále přihlášený (dokud ho web sám nezruší). **Předplatné:** Cookidoo zpřístupňuje plné recepty jen s aktivním členstvím. Aplikace žádné omezení neobchází – uloží jen to, co ti web po přihlášení skutečně ukáže.

## 8. Ukládání receptů

### Jeden recept

1. Ve vestavěném prohlížeči otevři detail receptu (ne seznam receptů).
2. Klikni na ⬇️ ULOŽIT RECEPT. Aplikace počká, až se stránka úplně načte.
3. Vyber kategorii, nebo napiš novou.
4. Potvrzení „Recept … byl uložen včetně konverze pro druhý stroj“ znamená hotovo.

Uložením stejného receptu znovu se recept přepíše čerstvou verzí a smažou se jeho staré převody a překlady. Kategorie i oblíbení zůstanou. Hodí se, když se něco uložilo špatně.

### Ostatní weby

Recepty z dalších webů ulož stejně (najdi je třeba přes 🏠 Domů). Aplikace z nich vezme **jen recept**: suroviny, postup a tipy zvlášť. Karta receptu je očištěná od menu, reklam, souvisejících článků a diskuze; autor receptu zůstává. Stránky jen s videem uložit nejde.

### Co se uloží

- místní snímek stránky pro **kartu receptu** (bez skriptů; styly, písma a obrázky se uloží jednou do sdílené složky `web_assets`),
- název, suroviny, kroky a tipy včetně nastavení stroje,
- data pro **jemné kroky** (kapitola 11) – u Monsieur Cuisine z jejich API, u Cookidoo z datové verze stránky,
- **verze pro druhý robot** (kapitola 12).

### Jak aplikace recept rozpozná

Zkouší zdroje v tomto pořadí a použije první, který funguje:

1. strukturovaná data receptu (JSON-LD), která vkládá většina webů,
2. speciální čtení pro Monsieur Cuisine (text postupu, u komunitních receptů karty kroků),
3. obecné hledání v HTML podle typických názvů (ingredients, instructions…),
4. oddíl stránky pod nadpisem „Postup / Příprava“ až po další nadpis stejné úrovně,
5. viditelný text stránky pod nadpisy „Suroviny“, „Příprava“…

U ostatních webů navíc pomáhá knihovna recipe-scrapers. Z čeho aplikace vycházela, zapisuje do `recipe.json` (pole `extraction`).

## 9. Kategorie a organizace kuchařky

Každý recept patří do jedné kategorie. Výchozí kategorie: Nezařazené, Monsieur Cuisine, Hlavní jídla, Polévky, Pečení & Dezerty, Omáčky, Cizojazyčné. Vlastní vzniknou napsáním nového názvu nebo tlačítkem ➕ Nová kategorie. V databázi se ukládají česky; v anglickém rozhraní se jen zobrazí anglický název.

- **Změna kategorie:** 🏷️ Změnit kategorii…, pravé tlačítko → 🏷️ Přesunout do kategorie, nebo přetažení myší na jinou kategorii.
- **Oblíbené:** ⭐ označí recept hvězdičkou; oblíbené jsou v kategorii nahoře, filtr ⭐ Oblíbené ukáže jen je.
- **Označení více receptů:** Ctrl + klik (jednotlivě), Shift + klik (rozsah), klik na kategorii (všechny její recepty) – pro export zálohy.
- **Smazání:** 🗑️ Smazat přesune recept do koše `localchef_data/recipes_smazane`. Nic se nemaže natrvalo; recept vrátíš přesunutím jeho složky zpět do `recipes`.

## 10. Prohlížení a vaření podle receptu

**📄 Karta receptu** ukáže recept tak, jak vypadal na webu, i bez internetu. V tmavém režimu se karta ztmaví, obrázky zůstanou v původních barvách.

**🍲 Režim Thermomix (TM6)** a **🤖 Monsieur Cuisine Smart (MCS)** otevřou přehrávač pro daný robot. Když recept pochází z jiného zdroje, zobrazí se převedená verze (kapitola 12).

| Část přehrávače | Co ukazuje |
|---|---|
| Ciferníky ⏱️ ČAS, 🌡️ TEPLOTA, 🔪 OTÁČKY | nastavení robota pro aktuální krok; u MCS i programy (Opékání, Hnětení…) |
| 🛒 Suroviny | celý seznam; suroviny aktuálního kroku jsou zvýrazněné, i jen část množství („teď 20 g“) |
| Text kroku | velkým písmem, ikony stroje jako barevné štítky, tipy u převedeného receptu |
| ◀ PŘEDCHOZÍ KROK / DALŠÍ KROK ▶ | posun mezi kroky |

Ovládání: **⚖️ Dávka** přepočítá množství, **📏 Metrické** převede unce, libry, hrnky a °F na metrické jednotky, **🔍 Jemné kroky** přepíná běžné a jemné kroky, jazyk receptu přepínají tlačítka v liště receptu.

**🖨️ Export do PDF** uloží přehledný list receptu na jednu stránku A4: fotka, nutriční hodnoty, suroviny, postup a tipy, v zobrazeném jazyce a dávce. Výchozí složka je `localchef_data/pdf_exports`.

## 11. Jemné kroky

Jemné kroky rozloží recept na drobné úkony jako na displeji robota: každé navážení a každé nastavení stroje je samostatný krok s vlastními ciferníky. Jsou zapnuté ve výchozím stavu v přehrávači i v telefonu.

| Zdroj receptu | Jak vznikají | Přesnost |
|---|---|---|
| Monsieur Cuisine | z „řízeného vaření“ v jejich API (přesný režim, čas, teplota, rychlost, váha) | přesné hodnoty |
| Cookidoo | z datové verze stránky; k navažování doplní množství ze surovin a nadpisy sekcí | velmi dobrá |
| starší a ostatní recepty | rozdělením běžných kroků na věty a úkony při otevření | dobrá |

Počítadlo ukazuje, ke kterému běžnému kroku jemný krok patří (např. „KROK 7 / 12 (hlavní 3)“). Přepnutí mezi běžnými a jemnými kroky tě nechá na stejném místě receptu.

## 12. Převod mezi Thermomix TM6 a Monsieur Cuisine Smart

Každý uložený recept dostane automaticky verzi pro druhý robot (`recipe_mcs.json` nebo `recipe_tm6.json`).

| Thermomix TM6 | Monsieur Cuisine Smart | Poznámka |
|---|---|---|
| Varoma | program Pára / 120 °C | MCS nemá teplotu Varoma |
| rychlost Vařečka 🥄 | rychlost 1 + levý chod ↺ | MCS nemá pomalé míchání |
| poloviční rychlosti (0.5, 1.5…) | zaokrouhleno na celé stupně | MCS má jen celé stupně |
| režim Těsto 🌾 | program Hnětení | |
| zpětný chod ↺ | levý chod ↺ | |
| 120 °C při restování | tip: až 130 °C nebo program Opékání | TM6 ručně víc než 120 °C neumí |

Převod z MCS na TM6 platí obráceně. U převedeného kroku je rámeček s tipem, co se změnilo.

- **Vestavěný převod (offline)** funguje vždy, bez internetu a bez klíčů.
- **AI převod přes Gemini** se použije, když je zadaný ✨ Gemini klíč; když selže, nastoupí vestavěný převod. Převody udělané bez klíče se po jeho zadání samy vylepší.
- **Recepty z ostatních webů** převede offline asistent: kroky, které jde dělat v robotu, dostanou návrh času, teploty a rychlosti, ostatní jsou označené jako ruční.

Převedený recept je pomůcka, ne ověřený recept výrobce. Před vařením zkontroluj teploty, časy a rychlosti.

## 13. Překlady a offline překladač

Recept i kartu receptu jde přeložit do češtiny nebo angličtiny: v liště receptu (🌐 Originál / 🇬🇧 English / 🇨🇿 Čeština) nebo v telefonu. Překlad běží na pozadí a hotový se uloží – příště se jen načte. **⚙️ → 🌍 Přeložit všechny recepty** přeloží celou kuchařku.

| Pořadí | Překladač | Kdy se použije | Internet |
|---|---|---|---|
| 1 | DeepL | je zadaný DeepL klíč | ano |
| 2 | Gemini (Google AI) | je zadaný Gemini klíč | ano |
| 3 | Argos Translate (offline) | je nainstalovaný a má jazykové modely | jen při stažení modelů |

Když jeden překladač selže (limit, výpadek), aplikace bez ptaní zkusí další. Překládá se po větách s pamětí (`translation_cache.json`), takže verze TM6, MCS, jemné kroky i karta sdílí stejné překlady. Česky psaný recept se do češtiny nepřekládá.

### Offline překladač (Argos Translate)

Překládá přímo v počítači, bez klíče a bez internetu. Potřebuje jazykové modely, které se stahují jednou (každý desítky až stovky MB).

- **Při startu** aplikace zkontroluje, jestli je překladač nainstalovaný a má modely. Když ne, zeptá se **ANO / NE**; zaškrtnutím **Příště se již neptat** se dotaz vypne.
- Stáhnout ho jde kdykoli v **⚙️ → 📥 Stáhnout offline překladač**. Při spuštění z Pythonu umí aplikace doinstalovat i knihovnu `argostranslate`, v exe je přibalená.
- Běží v samostatném procesu, takže ani jeho pád aplikaci neshodí; první překlad po startu chvíli trvá (načítá modely).
- Modely jsou u .py v uživatelském profilu, u exe v `localchef_data\argos_packages`.

## 14. API klíče a online služby

Klíče nejsou povinné – aplikace bez nich ukládá recepty, převádí mezi roboty a překládá offline. S nimi je kvalita výrazně lepší.

| Klíč | K čemu | Kde ho získat | Cena |
|---|---|---|---|
| Gemini (Google AI) – ✨ Gemini AI klíč | převody TM6 ↔ MCS a receptů z ostatních webů, překlady | https://aistudio.google.com/app/apikey → Create API key | zdarma s denními limity, bez platební karty |
| DeepL – 🔑 DeepL | nejpřesnější překlady | https://www.deepl.com/pro-api → DeepL API Free | zdarma 500 000 znaků měsíčně; karta jen k ověření |

- Klíč Gemini začíná `AIza`, klíč DeepL Free končí `:fx`. Vložíš je v ⚙️ Nastavení.
- Do bezplatné úrovně Gemini neposílej citlivé osobní údaje – Google s nimi zachází jinak než u placené. Recepty jsou v pořádku.
- Klíče jsou jen v počítači v `localchef_data/config.json`. Nikomu je nedávej.
- Model Gemini je `gemini-2.5-flash`; jiný jde nastavit v `config.json` (`gemini_model`).

Online služby, se kterými aplikace komunikuje: weby s recepty (při prohlížení, hledání a ukládání), `mc-api.tecpal.com` (jemné kroky Monsieur Cuisine), `generativelanguage.googleapis.com` (Gemini), `api-free.deepl.com` / `api.deepl.com` (DeepL), balíčkový server Argos (jen při stažení modelů), `api.qrserver.com` (obrázek QR kódu). Všechno ostatní funguje bez internetu.

## 15. Aplikace v telefonu a tabletu (Wi-Fi)

Když běží aplikace v počítači, otevřeš kuchařku v prohlížeči telefonu na adrese z levého panelu (např. `http://192.168.0.200:3665`). Nic se do telefonu neinstaluje.

1. Telefon i počítač musí být ve stejné Wi-Fi nebo domácí síti.
2. Klikni na 📱 QR kód a naskenuj ho telefonem, nebo adresu opiš.
3. Adresu si ulož do záložek nebo na plochu.

Telefon umí seznam receptů, přehrávač TM6 / MCS, kartu upravenou pro mobil, přepočet dávky, jemné kroky, hledání a vlastní přepínač čeština / angličtina. Chybějící překlad vytvoří počítač na pozadí.

**Bezpečnost:** adresa není chráněná heslem – kdokoli ve stejné síti ji může otevřít a recepty si prohlédnout (upravovat ani mazat je nejde). Doma to nevadí, na veřejné síti aplikaci nenechávej spuštěnou. Když se telefon nepřipojí, povol aplikaci ve firewallu Windows (port 3665).

## 16. Kde jsou data uložena

Všechna data jsou ve složce `localchef_data` – u exe vždy vedle `LocalChefStudio.exe`, u .py ve složce, ze které aplikaci spouštíš.

| Soubor / složka | Obsah |
|---|---|
| `catalog.db` | seznam receptů: název, kategorie, oblíbené, stroj, cesta |
| `config.json` | nastavení a API klíče |
| `app.log` | záznam činnosti a chyb |
| `recipes/` | jedna podsložka na recept |
| `recipes_smazane/` | koš smazaných receptů |
| `web_assets/` | sdílené styly, písma a obrázky karet receptu |
| `exported_recipes/` | výchozí místo pro zálohy .7z |
| `pdf_exports/` | výchozí místo pro PDF |
| `browser_profile/` | data relace vestavěného prohlížeče (cookies) |
| `browser_cache/` | dočasná mezipaměť prohlížeče (lze smazat) |
| `argos_packages/` | jazykové modely offline překladače (jen u exe) |

Ve složce receptu: `recipe.json` (originál), `page_snapshot.html` (karta), `recipe_mcs.json` / `recipe_tm6.json` (převod), `recipe_en.json`, `recipe_cs.json` a `page_snapshot_en/cs.html` (překlady), `translation_cache.json`, `extras.json` (obrázek, nutriční hodnoty, tipy) a ladicí soubory `_debug_*`.

Nastavení v `config.json`: `ui_lang`, `gemini_api_key`, `gemini_model`, `deepl_api_key`, `icon_style`, `title_lang`, `custom_categories`, `search_sources`, `mcs_home_url`, `whats_new_hidden`, `offline_tr_never_ask`.

Databáze si pamatuje úplnou cestu ke složce receptu. Když tam složka není (jiný disk, jiný počítač), aplikace ji dohledá podle názvu v `recipes`. Složky receptů zkopírované do `recipes` se při startu samy objeví v kuchařce.

## 17. Záloha, export a import receptů

### Záloha vybraných receptů (.7z)

1. V seznamu vlevo označ recepty: Ctrl + klik, Shift + klik, nebo klik na celou kategorii.
2. Pravé tlačítko → **📦 Exportovat zálohu (.7z)**, nebo tlačítko **📦 Exportovat označené** pod seznamem.
3. Vyber, kam soubor uložit (výchozí `localchef_data/exported_recipes`).

Záloha obsahuje vše: suroviny a kroky, překlady, převody pro oba roboty i kartu receptu s jejími styly a obrázky, takže karta funguje i na jiném počítači bez internetu.

### Import

Tlačítko **📥 Importovat recepty (.7z)** vlevo – vyber jeden nebo víc souborů. Kategorie a oblíbené se zachovají. Když některý recept už v kuchařce je, aplikace se zeptá: **Ano** = přepsat verzí ze zálohy (současná jde do koše `recipes_smazane`), **Ne** = ponechat současnou. Aplikace přijme jen zálohy vytvořené LocalChef Studiem.

### Celá kuchařka

Zavři aplikaci a zkopíruj celou složku `localchef_data` (`browser_cache` můžeš vynechat). Obnova = vrátit složku na místo nebo vedle exe. Pro jiného člověka nekopíruj `config.json` (klíče) ani `browser_profile` (přihlášení).

Recepty jsou chráněné autorským právem – zálohy jsou pro tvou osobní potřebu, nešiř je hromadně.

## 18. Řešení problémů

První místo, kam se dívat, je `localchef_data/app.log`. Neošetřená chyba aplikaci neshodí: ukáže hlášku s cestou k tomuto souboru a pracuje dál.

| Problém | Příčina | Řešení |
|---|---|---|
| Recept z Cookidoo nemá kroky | nejsi přihlášený nebo se stránka nenačetla | přihlas se, počkej na načtení a ulož znovu |
| „Recept nerozpoznán“ | web nemá recept ve známé podobě | zkus stejný recept z jiného webu, nainstaluj `recipe-scrapers` |
| Divné nebo chybějící kroky | starší uložení | recept ulož znovu |
| Hledání na webu nic nenajde | web výraz nezná (např. české slovo na Chefkochu) | zkus jiné slovo nebo hledání podle suroviny |
| Překlad: limit (HTTP 429) | vyčerpaný limit Gemini | počkej, nebo nech překlad na DeepL / offline |
| Překlad: chybí jazykový model | offline překladač nemá jazyk | ⚙️ → 📥 Stáhnout offline překladač |
| Telefon se nepřipojí | firewall nebo jiná síť | povol port 3665, zkontroluj stejnou Wi-Fi |
| Import: „není to záloha receptů z této aplikace“ | soubor .7z nevytvořilo LocalChef Studio | importuj jen zálohy z aplikace |

Při uložení se do složky receptu zapíšou ladicí soubory `_debug_visible_text.txt`, `_debug_ld.json` a `_debug_api.json` – podle nich jde zjistit, co aplikace ze stránky dostala, a opravit čtení, když web změní vzhled.

## 19. Právní upozornění

LocalChef Studio je nezávislý projekt pro vzdělávací účely a osobní potřebu. Neslouží k pirátství, k obcházení předplatného ani jiných omezení přístupu. Recepty, texty, fotografie a grafika patří jejich autorům a provozovatelům webů; ukládej jen recepty, ke kterým máš legální přístup, a nešiř je. Ukládání stránek může omezovat podmínky použití webu – za jejich dodržení odpovídá uživatel. Aplikace se poskytuje „tak, jak je“, bez záruky. Převody a překlady jsou strojové; před vařením zkontroluj teploty, časy, rychlosti, množství a alergeny. Thermomix a Cookidoo jsou ochranné známky společnosti Vorwerk, Monsieur Cuisine je ochranná známka společnosti Lidl; LocalChef Studio s nimi není spojené. Úplné znění je v souboru `DISCLAIMER.txt` a v aplikaci (ℹ️ Co je nového a podmínky použití).
