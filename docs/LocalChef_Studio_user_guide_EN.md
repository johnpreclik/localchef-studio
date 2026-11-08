# LocalChef Studio – User Guide

Version 1.5 · a short guide for everyday cooking. Details are in the documentation and in the app under the ❓ How to use button.

## 1. Getting started

**Install:** download `LocalChef_Studio_1.5.exe` from https://github.com/johnpreclik/localchef-studio/releases/latest and run it (SmartScreen: "More info → Run anyway"). The app appears in the Start menu.

**Start:** double-click `LocalChefStudio.exe` (or `py localchef_studio_v1.5.py`). On first start the **What's new and terms of use** window appears – read it to the end and click OK. If you like the app, you can support the author with the **💛 Donation** button (Ko-fi, PayPal, Revolut).

**Offline translator:** the app then asks whether to download the offline translator (recipes can then be translated without internet and without keys). Choose **YES** or **NO**. If it should not ask again, tick **Don't ask again**. You can download it any time in **⚙️ Settings → 📥 Download offline translator**.

**Logging in to Cookidoo** (Thermomix recipes only):

1. Click 🟢 Cookidoo.cz at the top.
2. Click log in on the website and enter your Cookidoo account.
3. Done – the app remembers the login after restarts.

Monsieur Cuisine and other sites need no login.

**App language:** ⚙️ Settings → 🌐 UI → Čeština / English.

## 2. Find and save a recipe

**Search:** click **🏠 Home**, type a name or ingredient and choose search by name or by ingredient. You will see recipes from your cookbook and from websites (Cookidoo, Monsieur Cuisine, Prima FRESH, Chefkoch, Allrecipes, BBC Good Food).

**One recipe:**

1. Open a specific recipe (not a list of recipes).
2. Click **⬇️ SAVE RECIPE** at the top.
3. Pick a category or type a new one and confirm.

From other sites only the recipe is kept: ingredients, method and tips, without ads or articles. Video-only pages cannot be saved.

## 3. Cooking with a recipe

1. Click a recipe in the list on the left.
2. Choose a view: **📄 Recipe card** (the recipe page), **🍲 Thermomix Mode (TM6)** or **🤖 Monsieur Cuisine Smart (MCS)**.
3. Move between steps with **◀ PREVIOUS STEP** and **NEXT STEP ▶**.

**What you see:** dials with time, temperature and speed, the ingredient list with the ones for the current step highlighted, and the step text. A recipe for one robot is converted for the other automatically.

**Useful buttons:**

- **⚖️ Batch** – scales amounts (e.g. double),
- **🔍 Detailed steps** – small actions like on the robot's display,
- **📏 Metric** – converts ounces and cups to grams and millilitres,
- **🖨️ Export to PDF** – a clean one-page recipe sheet.

Always check temperatures and times before cooking – conversions are machine-made.

## 4. Recipe on a phone or tablet

1. Phone and computer must be on the same Wi-Fi.
2. In the app, click **📱 QR Code** at the bottom left.
3. Scan it with the phone's camera (or type the address from the 📡 Wi-Fi server line).
4. Pick a recipe on the phone and cook. The computer must stay on.

If the phone cannot connect, allow the app in Windows Firewall.

## 5. Translating a recipe

In the recipe bar click **🇬🇧 English** or **🇨🇿 Čeština** (back to the original with **🌐 Original**). The translation runs in the background and is stored – next time it just loads. **⚙️ → 🌍 Translate all recipes** translates the whole cookbook.

The app translates with DeepL or Gemini (with a key), otherwise with the offline translator.

## 6. Keys for better translations and conversions (free)

- **Gemini** (best conversions between robots): https://aistudio.google.com/app/apikey → sign in with a Google account → **Create API key** → paste it in ⚙️ → ✨ Gemini AI Key. Free, no card, daily limits.
- **DeepL** (most accurate translations): https://www.deepl.com/pro-api → **DeepL API Free** (500,000 characters a month free; card for verification only) → copy the key from API Keys and paste it in ⚙️ → 🔑 DeepL.

Keys stay only on your computer. Never share them.

## 7. Backing up and moving recipes

**Export:** select recipes in the list on the left (**Ctrl + click**, **Shift + click**, or click a whole category) → right-click → **📦 Export backup (.7z)**. One file is created in the `exported_recipes` folder.

**Import:** on the other computer click **📥 Import recipes (.7z)** on the left and pick one or more files. If you already have a recipe, the app asks whether to replace it.

**The whole cookbook:** close the app and copy the `localchef_data` folder next to the program.

**Delete:** 🗑️ Delete moves a recipe to the `recipes_smazane` trash – nothing is lost for good.

## 8. When something goes wrong

| Problem | What to do |
|---|---|
| A Cookidoo recipe has no steps | log in, wait for the page to load and save again |
| A recipe cannot be saved | try the same recipe from another site via 🏠 Home |
| Odd steps | save the recipe again |
| Translation fails | add a Gemini key or download the offline translator in ⚙️ |
| The phone cannot connect | same Wi-Fi, allow the app in the firewall |

Error details are in `localchef_data/app.log`.

LocalChef Studio is an independent project and is not affiliated with Vorwerk (Thermomix / Cookidoo) or Lidl (Monsieur Cuisine). The names are trademarks of their owners.
