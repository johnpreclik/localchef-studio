# LocalChef Studio – návod k použití

Verze 1.5 · stručný návod pro každodenní vaření. Podrobnosti jsou v dokumentaci a v aplikaci pod tlačítkem ❓ Návod.

## 1. Začínáme

**Instalace:** stáhněte `LocalChef_Studio_1.5.exe` z https://github.com/johnpreclik/localchef-studio/releases/latest a spusťte ho (SmartScreen: „Další informace → Přesto spustit“). Aplikace se objeví v nabídce Start.

**Spuštění:** dvojklik na `LocalChefStudio.exe` (nebo `py localchef_studio_v1.5.py`). Při prvním startu se ukáže okno **Co je nového a podmínky použití** – po dočtení klikněte na OK. Pokud se vám aplikace líbí, můžete autora podpořit tlačítkem **💛 Podpořit vývoj** (Ko-fi, PayPal, Revolut).

**Offline překladač:** aplikace se pak zeptá, jestli stáhnout offline překladač (recepty pak jde překládat i bez internetu a bez klíčů). Zvolte **ANO**, nebo **NE**. Když se už ptát nemá, zaškrtněte **Příště se již neptat**. Stáhnout ho jde kdykoli v **⚙️ Nastavení → 📥 Stáhnout offline překladač**.

**Přihlášení na Cookidoo** (jen pro recepty Thermomix):

1. Klikněte nahoře na 🟢 Cookidoo.cz.
2. Na webu klikněte na přihlášení a zadejte svůj účet Cookidoo.
3. Hotovo – aplikace si přihlášení pamatuje i po dalším spuštění.

Recepty Monsieur Cuisine a dalších webů přihlášení nepotřebují.

**Jazyk aplikace:** ⚙️ Nastavení → 🌐 UI → Čeština / English.

## 2. Najít a uložit recept

**Hledání:** klikněte na **🏠 Domů**, napište název nebo surovinu a zvolte hledání podle názvu nebo suroviny. Uvidíte recepty z vaší kuchařky i z webů (Cookidoo, Monsieur Cuisine, Prima FRESH, Chefkoch, Allrecipes, BBC Good Food).

**Jeden recept:**

1. Otevřete konkrétní recept (ne seznam receptů).
2. Klikněte nahoře na **⬇️ ULOŽIT RECEPT**.
3. Vyberte kategorii, nebo napište novou, a potvrďte.

Z ostatních webů se uloží jen recept: suroviny, postup a tipy, bez reklam a článků. Stránky jen s videem uložit nejde.

## 3. Vaření podle receptu

1. V seznamu vlevo klikněte na recept.
2. Zvolte zobrazení: **📄 Karta receptu** (stránka receptu), **🍲 Režim Thermomix (TM6)** nebo **🤖 Monsieur Cuisine Smart (MCS)**.
3. Mezi kroky se posouváte tlačítky **◀ PŘEDCHOZÍ KROK** a **DALŠÍ KROK ▶**.

**Co uvidíte:** ciferníky s časem, teplotou a rychlostí, seznam surovin se zvýrazněním toho, co patří do aktuálního kroku, a text kroku. Recept z jednoho robota se pro druhý převede sám.

**Užitečná tlačítka:**

- **⚖️ Dávka** – přepočet množství (např. dvojnásobek),
- **🔍 Jemné kroky** – drobné úkony jako na displeji robota,
- **📏 Metrické** – převede unce a hrnky na gramy a mililitry,
- **🖨️ Export do PDF** – přehledný list receptu na jednu stránku.

Před vařením vždy zkontrolujte teploty a časy – převody dělá stroj.

## 4. Recept v telefonu nebo tabletu

1. Telefon i počítač musí být připojené ke stejné Wi-Fi.
2. V aplikaci klikněte vlevo dole na **📱 QR kód**.
3. Naskenujte ho fotoaparátem telefonu (nebo opište adresu z řádku 📡 Wi-Fi server).
4. V telefonu vyberte recept a vařte. Počítač musí zůstat zapnutý.

Když se telefon nepřipojí, povolte aplikaci ve firewallu Windows.

## 5. Překlad receptu

V liště receptu klikněte na **🇬🇧 English** nebo **🇨🇿 Čeština** (zpět na původní jazyk **🌐 Originál**). Překlad poběží na pozadí a uloží se – příště se jen načte. Celou kuchařku přeloží **⚙️ → 🌍 Přeložit všechny recepty**.

Aplikace překládá přes DeepL nebo Gemini (s klíčem), jinak offline překladačem.

## 6. Klíče pro lepší překlady a převody (zdarma)

- **Gemini** (nejlepší převody mezi roboty): https://aistudio.google.com/app/apikey → přihlásit se Google účtem → **Create API key** → klíč vložit v ⚙️ → ✨ Gemini AI klíč. Zdarma, bez karty, s denními limity.
- **DeepL** (nejpřesnější překlady): https://www.deepl.com/pro-api → **DeepL API Free** (500 000 znaků měsíčně zdarma; karta jen k ověření) → klíč z části API Keys vložit v ⚙️ → 🔑 DeepL.

Klíče zůstávají jen ve vašem počítači. Nikomu je nedávejte.

## 7. Záloha a přenos receptů

**Export:** v seznamu vlevo označte recepty (**Ctrl + klik**, **Shift + klik**, nebo klik na celou kategorii) → pravé tlačítko → **📦 Exportovat zálohu (.7z)**. Vznikne jeden soubor ve složce `exported_recipes`.

**Import:** na druhém počítači klikněte vlevo na **📥 Importovat recepty (.7z)** a vyberte jeden nebo víc souborů. Když recept už máte, aplikace se zeptá, jestli ho přepsat.

**Celá kuchařka:** zavřete aplikaci a zkopírujte složku `localchef_data` vedle programu.

**Smazání:** 🗑️ Smazat přesune recept do koše `recipes_smazane` – nic se neztratí natrvalo.

## 8. Když něco nejde

| Problém | Co udělat |
|---|---|
| Recept z Cookidoo nemá kroky | přihlaste se, počkejte na načtení stránky a uložte znovu |
| Recept nejde uložit | zkuste stejný recept z jiného webu přes 🏠 Domů |
| Divné kroky | recept uložte znovu |
| Překlad nejde | zadejte klíč Gemini, nebo stáhněte offline překladač v ⚙️ |
| Telefon se nepřipojí | stejná Wi-Fi, povolit aplikaci ve firewallu |

Podrobnosti o chybách jsou v souboru `localchef_data/app.log`.

LocalChef Studio je nezávislý projekt, není spojený se společnostmi Vorwerk (Thermomix, Cookidoo) ani Lidl (Monsieur Cuisine). Názvy jsou ochranné známky svých vlastníků.
