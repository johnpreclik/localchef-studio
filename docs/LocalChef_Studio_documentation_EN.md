# LocalChef Studio – Documentation

Version 1.6 · offline cookbook and kitchen robot cooking guide

LocalChef Studio is an independent project. It is not affiliated with, endorsed by, or connected to Vorwerk (Thermomix / Cookidoo) or Lidl (Monsieur Cuisine). Their names are used in this documentation only to describe compatibility and are trademarks of their respective owners.

## 1. What the app does

LocalChef Studio saves recipes from recipe websites into your own offline cookbook on your computer and lets you cook them step by step with a kitchen robot. Recipes then work without internet and can be converted for another robot type, translated, printed, backed up and shown on a phone or tablet in the kitchen.

Main features at a glance:

- **Offline cookbook** – a recipe is saved with its ingredients and steps and is shown in the app's own recipe card (image, author, a link to the source, ingredients, method, nutrition, tips), also offline.
- **Compatible websites** – recipes for Thermomix TM6 (Cookidoo), Monsieur Cuisine Smart (monsieur-cuisine.com) and hundreds of other recipe sites (Prima FRESH, Allrecipes, BBC Good Food…).
- **Search** – the 🏠 Home start page searches your cookbook and websites, by name or ingredient.
- **Two robots** – every recipe has a version for Thermomix TM6 and Monsieur Cuisine Smart (MCS); the second one is created by automatic conversion. Recipes from other sites are converted by the offline assistant.
- **Recipe player** – large dials with time, temperature and speed, highlighted ingredients for the current step, batch and unit conversion, detailed steps.
- **Translations** – recipe and card into Czech or English: DeepL, Gemini or fully offline.
- **PDF** – a clean one-page recipe sheet.
- **.7z backup** – export selected recipes into one file and import them (also on another computer).
- **Phone** – the computer acts as a server; recipes open in the phone's browser over home Wi-Fi.
- **Built-in guide** – the ❓ How to use button (Czech and English).

The app is a single file `localchef_studio_v1.6.py` (the version is in the name). It runs as a Python script (chapter 2), as a stand-alone `LocalChefStudio.exe` without Python (chapter 3), or in Docker, for example on a NAS (chapter 4). The interface is in Czech or English.

**Platform:** the app is written primarily for **Windows 10/11**, where it is developed and tested. The Docker version is experimental and has not been tested in everyday use.

Recipes are saved through the built-in browser. Everything else works with the data saved in the `localchef_data` folder, so it works offline. Internet is only needed for saving from the web, web search and online translators.

### Installing with the installer (easiest)

Download **LocalChef_Studio_1.6.exe** from the Releases page (https://github.com/johnpreclik/localchef-studio/releases/latest) and run it. The installer (Czech or English) installs the app for the current user into `%LOCALAPPDATA%\Programs\LocalChef Studio`, without administrator rights, adds a Start menu shortcut (optionally a desktop one) and an uninstaller in Windows Settings. The installer is not code-signed, so SmartScreen may ask: "More info → Run anyway". Data (`localchef_data`) live next to the program; updates keep them and uninstalling does not delete them. If the app is installed where it cannot write (Program Files), it uses `%LOCALAPPDATA%\LocalChef Studio\localchef_data`.

## 2. Requirements and installation (running the .py)

The app needs **Python 3.10 or newer** (developed and tested with Python 3.13 on Windows).

| Library (pip) | Required | Purpose |
|---|---|---|
| PyQt6 | yes | app window, buttons, recipe list |
| PyQt6-WebEngine | yes | built-in browser and the recipe card |
| beautifulsoup4 | yes | reading recipes from saved pages |
| argostranslate | no | offline translator without internet or keys (chapter 13) |
| deepl | no | DeepL translator when you have its API key |
| recipe-scrapers | no | saving recipes from hundreds of other sites |
| py7zr | no | recipe backup and import (.7z, chapter 17) |

Install everything from the app folder:

```
py -m pip install -r requirements.txt
```

`argostranslate` pulls in large libraries (torch, ctranslate2…), so installation takes about a gigabyte and a while. Yellow "not on PATH" warnings are harmless. If `py` does not work (Python from the Microsoft Store), use `python`.

Start:

```
py localchef_studio_v1.6.py
```

Start it from the folder where the data should live: `localchef_data` is created in the current command-line folder. On first start Windows may ask about network access – allow it for private networks, otherwise the phone app won't work (chapter 15).

**Upgrading from an older version:** start the new version from the same folder. It takes over the old data folder on first start – recipes and settings stay.

## 3. Stand-alone program (.exe)

`build_exe.bat` builds `LocalChefStudio.exe`, which runs on Windows without Python. It includes everything: the built-in browser, the offline translator and backups. Build it once on a computer with Python.

1. Put `localchef_studio_v1.6.py` and `build_exe.bat` in the same folder (the script finds the versioned file itself).
2. Double-click `build_exe.bat`. It installs PyInstaller and the libraries and builds the program in "folder" mode.
3. The finished program is in `dist\LocalChefStudio`.

The first build takes long (downloading libraries can take tens of minutes). Because of the offline translator the folder is 1–2 GB.

**Moving to another computer:** copy the whole `dist\LocalChefStudio` folder; the exe alone does not work. The program is clean, without data; on first start it creates an empty `localchef_data` next to the exe. With the exe all data always live next to the program, including the offline translator's language models (`localchef_data\argos_packages`).

**Be prepared:** Windows SmartScreen warns about an unsigned program ("More info → Run anyway"). Antivirus software sometimes distrusts PyInstaller programs – add the folder to exceptions if needed. If the built program does not work, change `--windowed` to `--console` in `build_exe.bat` and rebuild; errors then appear in the console.

## 4. Docker and NAS (TrueNAS)

The app runs in Docker on a virtual screen inside the container and is used from a web browser through noVNC (port **6080**); the phone app runs on port **3665** as usual.

> The Docker version is **experimental** and has not been tested in everyday use; only its build and start are checked automatically.

**Windows (Docker Desktop):** run `build_docker.bat`. It builds the image, starts the `localchef` container and opens http://localhost:6080/. `build_docker.bat noargos` leaves out the offline translator (about 2 GB smaller). Container data live in `docker_data\localchef_data`, separate from the Windows version.

**Linux:** the image is built straight from GitHub – nothing has to be downloaded first:

```
docker build -t localchef-studio -f docker/Dockerfile https://github.com/johnpreclik/localchef-studio.git#main
docker run -d --name localchef --restart unless-stopped --shm-size=1g -p 6080:6080 -p 3665:3665 -e LOCALCHEF_LAN_HOST=YOUR_PC_IP -e VNC_PASSWORD=password -v "$HOME/localchef_data:/data/localchef_data" localchef-studio
```

Then open http://localhost:6080/. `YOUR_PC_IP` is the computer's address on your network (for the phone QR code). `--build-arg WITH_ARGOS=0` in `docker build` leaves out the offline translator. Use `sudo` before `docker` if your user is not in the `docker` group. Without access to GitHub, unpack `LocalChef_Studio_1.6_docker.zip` from Releases and run `docker build -t localchef-studio -f docker/Dockerfile .` inside it.

**NAS (e.g. TrueNAS SCALE 24.10 and newer):** the same build from GitHub, in the NAS shell (TrueNAS: System → Shell):

```
sudo docker build -t localchef-studio -f docker/Dockerfile https://github.com/johnpreclik/localchef-studio.git#main
sudo docker run -d --name localchef --restart unless-stopped --shm-size=1g -p 6080:6080 -p 3665:3665 -e LOCALCHEF_LAN_HOST=NAS_IP -e VNC_PASSWORD=password -v /mnt/POOL/apps/localchef:/data/localchef_data localchef-studio
```

- Replace `NAS_IP` with the NAS address on your network (the phone gets it in the QR code) and `POOL` with your pool name.
- `VNC_PASSWORD` protects the browser UI – on a NAS port 6080 is visible on the whole network, so set it (VNC uses at most 8 characters).
- Updating: repeat `docker build`, then `sudo docker rm -f localchef` and `docker run` again. Data stay in the folder on your pool.
- Alternative through the TrueNAS web UI (Apps → Discover → Custom App → Install via YAML): the `docker-compose.yml` file from the repository.

## 5. Interface and first start

The window has the cookbook panel on the left and the work area on the right with the top bar, the recipe bar and the built-in browser or player.

### Left panel (top to bottom)

| Element | What it does |
|---|---|
| ➕ Expand all / ➖ Collapse all | expands or collapses all categories |
| Category filter, ⭐ Favourites, ➕ New category | one category, favourites only, create a category |
| Machine filter | all / 🟢 Cookidoo only (TM6) / 🔵 Monsieur Cuisine only / ⚫ other sites only |
| Names | language of names in the list (original, English, Czech, app language) |
| 🔍 Search recipes | filters by name, ignores accents |
| Recipe tree | recipes by category; click opens, Ctrl/Shift + click selects several, right-click opens a menu |
| ⭐ Favourite / 🏷️ Change category / 🗑️ Delete | work with the selected recipe (chapter 9) |
| 📥 Import recipes / 📦 Export selected | .7z backup (chapter 17) |
| 📡 Wi-Fi server + 📱 QR code | address and QR code for the phone (chapter 15) |

### Top bar (left to right)

| Element | What it does |
|---|---|
| ◀ Back | previous page in the built-in browser |
| 🏠 Home | start page with search (chapter 6) |
| 🟢 Cookidoo.cz / 🔵 Monsieur-Cuisine | opens the recipe website in the built-in browser |
| address bar | page address, also status while working (e.g. translation progress) |
| ⬇️ SAVE RECIPE | saves the open recipe (chapter 8) |
| 💛 Donation | voluntary support for the author: Ko-fi, PayPal or Revolut (QR code too) |
| ❓ How to use | the built-in guide |
| ⚙️ Settings | settings menu (below) |

### Recipe bar

View: 📄 Recipe card / 🍲 Thermomix Mode (TM6) / 🤖 Monsieur Cuisine Smart (MCS), language 🌐 Original / 🇬🇧 English / 🇨🇿 Čeština, 🔄 Translate again and 🖨️ Export to PDF.

### ⚙️ Settings menu

| Section | Items |
|---|---|
| Translation | 🌍 Translate all recipes, ✨ Gemini AI Key, 📥 Download offline translator, 🔑 DeepL |
| Appearance | app language (Czech / English), dark / light mode, icon style (🟢/🔵 or 🍲/🤖) |
| App | ❓ How to use, ℹ️ What's new and terms of use, 🔄 Check for updates |

### First start step by step

1. Start the app (chapter 2, 3 or 4). It creates an empty cookbook.
2. The **What's new and terms of use** window appears. OK unlocks after you scroll to the end.
3. The app checks the **offline translator**. If it is missing, it downloads it by itself and shows the progress in percent in a window (chapter 13).
4. Then it checks whether a **new version** is on GitHub. If so, it asks: *A new version is available on GitHub – download and install it?* After **YES** the installer is downloaded (its size and the SHA-256 checksum from GitHub are checked), the app closes, the new version is installed silently into the same folder and starts again. Recipes and settings (`localchef_data`) stay. **Skip this version** turns the question off for that version; you can check by hand in ⚙️ → 🔄 Check for updates. When running from Python the app only offers the download page; in Docker it does not look for new versions.
5. Click 🏠 Home, find a recipe and save it with ⬇️ SAVE RECIPE. For Cookidoo, log in first (chapter 7).
6. Optionally enter Gemini or DeepL keys (chapter 14).

## 6. Recipe search (🏠 Home)

The start page searches **your cookbook** and **recipe websites** at the same time: Cookidoo, Monsieur Cuisine, Prima FRESH, Allrecipes and BBC Good Food, by **name** or by **ingredient**.

- Web results are grouped by source, with a picture and a link. A click opens the recipe in the built-in browser, where you save it.
- When a site finds nothing and shows "popular recipes" instead, the app ignores them.
- In name search, results containing the search word come first (the word stem is compared without accents).
- **Search term translation:** each site has its language. English sites (Allrecipes, BBC Good Food) get a Czech term translated into English ("zelňačka" → "sauerkraut soup"), Czech sites get an English term in Czech. A site in another language (e.g. a German site added to `search_sources`) gets the term as typed first and, if it finds nothing, the English translation. The site then shows "🌍 searched as …".
- The term's language is recognised by accents and a dictionary; otherwise the interface language applies. Czech dishes (zelňačka, svíčková, kulajda…) come from a built-in dictionary, the rest is translated by DeepL, Gemini or the offline translator. Translated terms are remembered in `search_translations.json`.
- A term whose language cannot be told ("spaghetti") is searched as typed first and translated only when nothing is found. Likewise, when a Czech site finds nothing, the term translated from English is tried (and the other way round).
- When a site refuses automatic search (bot protection, HTTP 403/429), the site shows "the website refused automatic search" and the app does not ask it again for an hour. The link to the search on the website stays.
- Chefkoch was removed in version 1.6: it refuses embedded browsers (HTTP 403), so neither searching nor saving worked there.
- The search bar stays at the top while you scroll through the results.
- The same search works from the phone (chapter 15); the computer does the searching.
- The list of sites can be extended in `config.json` (`search_sources`).

## 7. Logging in to websites

On **Cookidoo** you must log in with your account before saving recipes; without it the site shows only the title and ingredients. **Monsieur Cuisine** recipes are public and save without an account. Other sites usually need no login.

The app reads recipes from the pages you see in the built-in browser – what you don't see, the app doesn't see either. That is why you log in inside the app:

1. Click 🟢 Cookidoo.cz in the top bar.
2. Click log in on the website and sign in as in any browser.

The login is remembered in `localchef_data/browser_profile`. **Subscription:** Cookidoo shows full recipes only with an active membership. The app does not get around any restriction – it saves only what the site shows you after logging in.

## 8. Saving recipes

### One recipe

1. Open the recipe detail in the built-in browser (not a list of recipes).
2. Click ⬇️ SAVE RECIPE. The app waits until the page is fully loaded.
3. Pick a category or type a new one.
4. "Recipe … was saved including the conversion for the other machine" means done.

Saving the same recipe again replaces it with a fresh version and removes its old conversions and translations; category and favourite stay. Useful when something was saved wrong.

### Other sites

Save recipes from other sites the same way (find them via 🏠 Home, for example). The app keeps **only the recipe**: ingredients, method and tips separately. The author, image and a link to the source are kept too. A new recipe is offered into its website's category (Cookidoo, Prima FRESH, Allrecipes…). Video-only pages cannot be saved.

### What is saved

- a local snapshot of the page for the **recipe card** (without scripts; styles, fonts and images are stored once in the shared `web_assets` folder),
- title, ingredients, steps and tips including machine settings,
- data for **detailed steps** (chapter 11) – from the Monsieur Cuisine API or the Cookidoo page data,
- the **version for the other robot** (chapter 12).

### How the app recognises a recipe

It tries these sources in order and uses the first that works:

1. structured recipe data (JSON-LD) embedded by most sites,
2. special reading for Monsieur Cuisine (method text; step cards for community recipes),
3. generic HTML search by typical names (ingredients, instructions…),
4. the page section under a "Method / Preparation" heading up to the next heading of the same level,
5. the visible page text under headings like "Ingredients", "Preparation"…

For other sites the recipe-scrapers library helps too. What the app used is recorded in `recipe.json` (`extraction`).

## 9. Categories and organising the cookbook

Each recipe belongs to one category. Default categories: Uncategorized, Breakfast, Snacks, Starters, Soups, Salads, Lunches, Dinners, Main dishes, Side dishes, Sauces, Spreads & dips, Bread & pastry, Sweets & desserts, Drinks, Non-alcoholic cocktails, Cocktails, Preserving. A new recipe is offered into its website's category (Cookidoo, Monsieur Cuisine, Prima FRESH, Allrecipes, BBC Good Food, other sites by their address) and every website has its own coloured icon in the list. Create your own by typing a new name or with ➕ New category. They are stored in Czech; the English interface only shows the English name.

- **Change category:** 🏷️ Change category…, right-click → 🏷️ Move to category, or drag and drop onto another category.
- **Favourites:** ⭐ marks a recipe; favourites are at the top of their category, the ⭐ Favourites filter shows only them.
- **Selecting several recipes:** Ctrl + click (one by one), Shift + click (a range), click a category (all its recipes) – for backups.
- **Delete:** 🗑️ Delete moves the recipe to the trash folder `localchef_data/recipes_smazane`. Nothing is deleted for good; move the folder back into `recipes` to restore it.

## 10. Viewing and cooking

**📄 Recipe card** shows the recipe in the app's own design, whichever website it comes from: image, title, author, a link to the source (website badge), description, servings and time, ingredients, method, nutrition and tips. It works offline and follows the light and dark look. A switch on the card shows the steps for 🍲 Thermomix TM6 or 🤖 Monsieur Cuisine (for other websites also the original steps) with setting chips (⏱ time, 🌡 temperature, 🌀 speed). Units are converted to metric (the original in brackets) and to the chosen batch. All recipes saved before work the same – nothing is converted; when no ingredients or method could be extracted, the saved page is shown. The phone shows the same card.

**🍲 Thermomix Mode (TM6)** and **🤖 Monsieur Cuisine Smart (MCS)** open the player for that robot. A recipe from another source is shown in its converted version (chapter 12).

| Player part | What it shows |
|---|---|
| Dials ⏱️ TIME, 🌡️ TEMPERATURE, 🔪 SPEED | robot settings for the current step; for MCS also programs (Roasting, Kneading…) |
| 🛒 Ingredients | the full list; ingredients of the current step are highlighted, even partial amounts ("now 20 g") |
| Step text | large font, machine icons as coloured labels, tips for converted recipes |
| ◀ PREVIOUS STEP / NEXT STEP ▶ | move between steps |

Controls: **⚖️ Batch** scales amounts, **📏 Metric** converts ounces, pounds, cups and °F to metric units, **🔍 Detailed steps** switches between normal and detailed steps; the recipe language is switched in the recipe bar.

**🖨️ Export to PDF** saves a clean one-page A4 sheet: photo, nutrition, ingredients, method and tips, in the shown language and batch size. The default folder is `localchef_data/pdf_exports`.

## 11. Detailed steps

Detailed steps split a recipe into small actions like a robot display: every weighing and every machine setting is a separate step with its own dials. They are on by default in the player and on the phone.

| Recipe source | How they are made | Accuracy |
|---|---|---|
| Monsieur Cuisine | from the "guided cooking" in their API (exact mode, time, temperature, speed, weight) | exact values |
| Cookidoo | from the page data; amounts from the ingredient list and section headings are added to weighing steps | very good |
| older and other recipes | by splitting normal steps into sentences and actions when opened | good |

The counter shows which normal step a detailed step belongs to (e.g. "STEP 7 / 12 (main 3)"). Switching between normal and detailed steps keeps your place in the recipe.

## 12. Conversion between Thermomix TM6 and Monsieur Cuisine Smart

Every saved recipe automatically gets a version for the other robot (`recipe_mcs.json` or `recipe_tm6.json`).

| Thermomix TM6 | Monsieur Cuisine Smart | Note |
|---|---|---|
| Varoma | Steam program / 120 °C | MCS has no Varoma temperature |
| Spoon speed 🥄 | speed 1 + reverse ↺ | MCS has no slow stirring |
| half speeds (0.5, 1.5…) | rounded to whole steps | MCS has whole steps only |
| Dough mode 🌾 | Kneading program | |
| reverse ↺ | reverse ↺ | |
| 120 °C for sautéing | tip: up to 130 °C or the Roasting program | TM6 cannot go above 120 °C manually |

MCS to TM6 works the other way round. A converted step gets a box with a tip on what changed.

- **Built-in conversion (offline)** always works, without internet or keys.
- **AI conversion with Gemini** is used when a ✨ Gemini key is set; if it fails, the built-in conversion takes over. Conversions made without a key are upgraded automatically once you add one.
- **Recipes from other sites** are converted by the offline assistant: steps that can be done in the robot get suggested time, temperature and speed, the rest are marked as manual.

A converted recipe is an aid, not a recipe verified by the manufacturer. Check temperatures, times and speeds before cooking.

## 13. Translations and the offline translator

Recipes and cards can be translated into Czech or English in the recipe bar (🌐 Original / 🇬🇧 English / 🇨🇿 Čeština) or on the phone. Translation runs in the background and is stored – next time it just loads. **⚙️ → 🌍 Translate all recipes** translates the whole cookbook.

| Order | Translator | Used when | Internet |
|---|---|---|---|
| 1 | DeepL | a DeepL key is set | yes |
| 2 | Gemini (Google AI) | a Gemini key is set | yes |
| 3 | Argos Translate (offline) | installed with language models | only to download models |

If one translator fails (quota, outage), the app tries the next one. Translation works sentence by sentence with a memory (`translation_cache.json`), so the TM6 and MCS versions, detailed steps and the card share translations. The recipe's language is recognised from its text (a language tag from the page only counts when the text agrees). A recipe that is already in the target language is not translated – it is just shown, even without a translator or keys. Translation and bulk translation run in the background; you can keep using the app meanwhile.

### Offline translator (Argos Translate)

Translates on your computer, without a key and without internet. It needs language models, downloaded once (tens to hundreds of MB each).

- **At start** the app checks whether the translator is installed and has models. If not, it **downloads it by itself** and shows the progress in percent in a window (from Python it first installs the library with pip – no percentage there). **Hide** closes the window while the download continues, **Cancel** stops it, **Don't download automatically next time** turns automatic downloading off.
- Download it any time in **⚙️ → 📥 Download offline translator**. When running from Python the app can also install the `argostranslate` library; the exe includes it.
- It runs in a separate process, so even a crash won't take the app down; the first translation after start takes a moment (loading models).
- Models are stored in the user profile (.py) or in `localchef_data\argos_packages` (exe).

## 14. API keys and online services

Keys are optional – without them the app saves recipes, converts between robots and translates offline. With them quality is much better.

| Key | Purpose | Where to get it | Price |
|---|---|---|---|
| Gemini (Google AI) – ✨ Gemini AI Key | TM6 ↔ MCS conversions and other-site recipes, translations | https://aistudio.google.com/app/apikey → Create API key | free with daily limits, no payment card |
| DeepL – 🔑 DeepL | the most accurate translations | https://www.deepl.com/pro-api → DeepL API Free | free 500,000 characters a month; card for verification only |

- A Gemini key starts with `AIza`, a DeepL Free key ends with `:fx`. Enter them in ⚙️ Settings.
- Don't send sensitive personal data to the Gemini free tier – Google handles it differently from the paid tier. Recipes are fine.
- Keys are stored only on your computer in `localchef_data/config.json`. Never share them.
- The Gemini model is `gemini-2.5-flash`; another one can be set in `config.json` (`gemini_model`).

Online services the app talks to: recipe websites (browsing, searching, saving), `mc-api.tecpal.com` (Monsieur Cuisine detailed steps), `generativelanguage.googleapis.com` (Gemini), `api-free.deepl.com` / `api.deepl.com` (DeepL), the Argos package server (only when downloading models), `api.qrserver.com` (QR code image). Everything else works offline.

## 15. Phone and tablet app (Wi-Fi)

While the app runs on the computer, open the cookbook in the phone's browser at the address shown in the left panel (e.g. `http://192.168.0.200:3665`). Nothing is installed on the phone.

1. Phone and computer must be on the same Wi-Fi or home network.
2. Click 📱 QR code and scan it with the phone, or type the address.
3. Bookmark the address or add it to the home screen.

The phone has the recipe list, the TM6 / MCS player, a phone-friendly card, batch scaling, detailed steps, search and its own Czech / English switch. A missing translation is created by the computer in the background.

**Security:** the address has no password – anyone on the same network can open it and view recipes (but cannot edit or delete them). Fine at home; don't leave the app running on a public network. If the phone cannot connect, allow the app in Windows Firewall (port 3665).

## 16. Where data are stored

All data live in the `localchef_data` folder – with the exe always next to `LocalChefStudio.exe`, with the .py in the folder you start it from.

| File / folder | Content |
|---|---|
| `catalog.db` | recipe list: title, category, favourite, machine, path |
| `config.json` | settings and API keys |
| `app.log` | activity and error log |
| `recipes/` | one subfolder per recipe |
| `recipes_smazane/` | trash for deleted recipes |
| `web_assets/` | shared styles, fonts and images of recipe cards |
| `exported_recipes/` | default place for .7z backups |
| `pdf_exports/` | default place for PDFs |
| `browser_profile/` | session data of the built-in browser (cookies) |
| `browser_cache/` | temporary browser cache (can be deleted) |
| `argos_packages/` | offline translator language models (exe only) |

In a recipe folder: `recipe.json` (original), `page_snapshot.html` (card), `recipe_mcs.json` / `recipe_tm6.json` (conversion), `recipe_en.json`, `recipe_cs.json` and `page_snapshot_en/cs.html` (translations), `translation_cache.json`, `extras.json` (picture, nutrition, tips) and `_debug_*` files.

Settings in `config.json`: `ui_lang`, `gemini_api_key`, `gemini_model`, `deepl_api_key`, `icon_style`, `title_lang`, `custom_categories`, `search_sources`, `mcs_home_url`, `whats_new_hidden`, `offline_tr_never_ask`.

The database remembers the full path of each recipe folder. If the folder is not there (another drive or computer), the app finds it by name in `recipes`. Recipe folders copied into `recipes` appear in the cookbook at start.

## 17. Backup, export and import

### Backing up selected recipes (.7z)

1. Select recipes in the list on the left: Ctrl + click, Shift + click, or click a whole category.
2. Right-click → **📦 Export backup (.7z)**, or the **📦 Export selected** button below the list.
3. Choose where to save the file (default `localchef_data/exported_recipes`).

The backup contains everything: ingredients and steps, translations, conversions for both robots and the recipe card with its styles and images, so the card works on another computer even offline.

### Import

The **📥 Import recipes (.7z)** button on the left – pick one or more files. Categories and favourites are kept. If a recipe is already in your cookbook, the app asks: **Yes** = replace it with the backup version (the current one goes to the `recipes_smazane` trash), **No** = keep the current one. The app accepts only backups made by LocalChef Studio.

### The whole cookbook

Close the app and copy the whole `localchef_data` folder (`browser_cache` can be left out). To restore, put the folder back or next to the exe. When giving it to someone else, leave out `config.json` (keys) and `browser_profile` (logins).

Recipes are protected by copyright – backups are for your personal use, don't distribute them widely.

## 18. Troubleshooting

The first place to look is `localchef_data/app.log`. An unexpected error does not crash the app: it shows a message with the path to this file and keeps running.

| Problem | Cause | Solution |
|---|---|---|
| A Cookidoo recipe has no steps | not logged in or the page did not load | log in, wait for the page and save again |
| "Recipe not recognised" | the site has no recipe in a known form | try the same recipe from another site, install `recipe-scrapers` |
| Odd or missing steps | an older save | save the recipe again |
| Web search finds nothing | the site doesn't know the word (e.g. a Czech dish on an English site) | try another word or ingredient search |
| Translation: quota (HTTP 429) | Gemini limit reached | wait, or let DeepL / offline translate |
| Translation: language model missing | the offline translator lacks the language | ⚙️ → 📥 Download offline translator |
| The phone cannot connect | firewall or another network | allow port 3665, check it is the same Wi-Fi |
| Import: "not a recipe backup from this app" | the .7z was not made by LocalChef Studio | import only backups from the app |

When saving, debug files `_debug_visible_text.txt`, `_debug_ld.json` and `_debug_api.json` are written to the recipe folder – they show what the app got from the page and help fix reading when a site changes its layout.

## 19. Legal notice

LocalChef Studio is an independent project for educational purposes and personal use. It is not meant for piracy or for getting around subscriptions or other access restrictions. Recipes, texts, photos and graphics belong to their authors and the website operators; save only recipes you have legitimate access to and do not distribute them. Saving pages may be restricted by a website's terms of use – the user is responsible for following them. The app is provided "as is", without warranty. Conversions and translations are machine-made; check temperatures, times, speeds, quantities and allergens before cooking. Thermomix and Cookidoo are trademarks of Vorwerk, Monsieur Cuisine is a trademark of Lidl; LocalChef Studio is not affiliated with them. The full text is in `DISCLAIMER.txt` and in the app (ℹ️ What's new and terms of use).
