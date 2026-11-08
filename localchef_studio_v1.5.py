import sys
import json
import os
import subprocess
import importlib.util
import re
import socket
import sqlite3
import threading
import time
import traceback
import tempfile
import shutil
import hashlib
import mimetypes
import unicodedata
import html as html_mod
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path


# ==========================================
# REŽIM OFFLINE PŘEKLADAČE (spouští se jako samostatný proces: "--argos-worker vstup.json vystup.json")
# Je úplně nahoře, aby se v něm nikdy nenačetlo Qt – jen Argos. Funguje stejně z .py i ze sestaveného .exe.
# ==========================================
def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(".").resolve()


_WORKER_UI = {"en": False}


def req_ui_en() -> bool:
    return _WORKER_UI["en"]


def _argos_worker_main(in_path: str, out_path: str):
    res = {"ok": False, "error": "worker nedoběhl"}
    try:
        req = json.loads(Path(in_path).read_text(encoding="utf-8"))
        _WORKER_UI["en"] = req.get("ui") == "en"
        en = req.get("ui") == "en"
        if req.get("packages_dir"):
            os.environ["ARGOS_PACKAGES_DIR"] = req["packages_dir"]
        if os.name == "nt" and getattr(sys, "frozen", False):
            # torch hledá své DLL jen ve vybraných složkách; přidáme knihovny přibalené k exe,
            # aby nebyl potřeba nainstalovaný Microsoft Visual C++ Redistributable
            base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            for d in (base, base / "torch" / "lib", base / "ctranslate2", base / "onnxruntime" / "capi"):
                if d.is_dir():
                    try:
                        os.add_dll_directory(str(d))
                    except OSError:
                        pass
            os.environ["PATH"] = str(base) + os.pathsep + str(base / "torch" / "lib") + os.pathsep + os.environ.get("PATH", "")
        import importlib.metadata
        import argostranslate.package as pkg
        import argostranslate.translate as tr

        def installed():
            return [[x.from_code, x.to_code] for x in pkg.get_installed_packages()]

        def ensure(a, b):
            if [a, b] in installed():
                return
            try:
                pkg.update_package_index()
                avail = pkg.get_available_packages()
            except Exception as e:
                raise RuntimeError(f"language model {a}->{b} is missing and cannot be downloaded (is there an internet connection?): {e}" if en
                                   else f"chybí jazykový model {a}->{b} a nejde stáhnout (je připojení k internetu?): {e}")
            cand = next((x for x in avail if x.from_code == a and x.to_code == b), None)
            if cand is None:
                raise LookupError(f"Argos has no model {a}->{b}" if en else f"Argos nemá model {a}->{b}")
            pkg.install_from_path(cand.download())

        act = req["action"]
        if act == "status":
            try:
                ver = importlib.metadata.version("argostranslate")
            except Exception:
                ver = "?"
            res = {"version": ver, "pairs": installed(), "packages_dir": os.environ.get("ARGOS_PACKAGES_DIR", "")}
        elif act == "install":
            for a, b in req["pairs"]:
                ensure(a, b)
            res = {"pairs": installed()}
        elif act == "translate":
            s_lang, t_lang = req["src"], req["tgt"]
            have = installed()
            if [s_lang, t_lang] in have:
                route = [(s_lang, t_lang)]
            elif s_lang != "en" and t_lang != "en" and [s_lang, "en"] in have and ["en", t_lang] in have:
                route = [(s_lang, "en"), ("en", t_lang)]
            else:
                try:
                    ensure(s_lang, t_lang)
                    route = [(s_lang, t_lang)]
                except LookupError:
                    route = [(s_lang, "en"), ("en", t_lang)]
                    for a, b in route:
                        ensure(a, b)
            out = []
            for s in req["texts"]:
                t = s
                for a, b in route:
                    t = tr.translate(t, a, b)
                out.append(t)
            res = {"texts": out}
        else:
            raise ValueError("unknown action " + str(act))
        res["ok"] = True
    except Exception as e:
        import traceback as _tb
        msg = str(e) if isinstance(e, (RuntimeError, LookupError)) else f"{type(e).__name__}: {e}"
        if "WinError 126" in msg or "WinError 127" in msg or "DLL load failed" in msg:
            msg += ("\n\nMicrosoft Visual C++ Redistributable (x64) is probably missing on this computer. Install it: "
                    "https://aka.ms/vs/17/release/vc_redist.x64.exe and restart the app." if req_ui_en() else
                    "\n\nNa tomto počítači nejspíš chybí Microsoft Visual C++ Redistributable (x64). Nainstalujte ho: "
                    "https://aka.ms/vs/17/release/vc_redist.x64.exe a aplikaci spusťte znovu.")
        res = {"ok": False,
               "error": msg,
               "trace": _tb.format_exc()}
    Path(out_path).write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__" and len(sys.argv) >= 4 and sys.argv[1] == "--argos-worker":
    _argos_worker_main(sys.argv[2], sys.argv[3])
    sys.exit(0)

from bs4 import BeautifulSoup

from PyQt6.QtCore import QUrl, Qt, QTimer, QMarginsF, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPageLayout, QPageSize, QPixmap, QImage, QAction, QActionGroup, QTextDocument, QPdfWriter
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTreeWidget, QTreeWidgetItem, QSplitter,
    QLabel, QMessageBox, QStackedWidget, QTextBrowser, QProgressBar,
    QFileDialog, QFrame, QComboBox, QCheckBox, QInputDialog, QAbstractItemView,
    QDialog, QMenu, QToolButton
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineSettings
)

try:
    import deepl
    HAS_DEEPL = True
except ImportError:
    HAS_DEEPL = False

# ==========================================
# LOKALIZACE ROZHRANÍ (UI DICTIONARY)
# ==========================================
# Název aplikace (do 1.1 „Cookidoo & Monsieur Cuisine Studio“ – přejmenováno, aby nepoužíval cizí ochranné známky).
# Verze je i v názvu souboru (localchef_studio_vX.Y.py) – při nové verzi soubor přejmenuj (git mv).
APP_NAME = "LocalChef Studio"
APP_TAGLINE = {"cs": "offline kuchařka a průvodce vařením s robotem", "en": "Offline Cookbook & Kitchen Robot Guide"}
APP_VERSION = "1.5"

UI_TEXTS = {
    "cs": {
        "window_title": f"{APP_NAME} {APP_VERSION} – {APP_TAGLINE['cs']}",
        "wifi_label": "📡 Wi-Fi server: ",
        "qr_btn": "📱 QR kód",
        "expand_btn": "➕ Rozbalit vše",
        "collapse_btn": "➖ Sbalit vše",
        "all_categories": "📁 Všechny kategorie",
        "plat_all": "🔄 Všechny stroje",
        "plat_tm6": "🟢 Jen Cookidoo (TM6)",
        "plat_mcs": "🔵 Jen Monsieur Cuisine",
        "plat_other": "⚫ Jen ostatní weby",
        "icon_dots": "Ikony: 🟢 / 🔵",
        "icon_bots": "Ikony: 🍲 / 🤖",
        "only_fav": "⭐ Oblíbené",
        "search_ph": "🔍 Hledat recepty...",
        "fav_btn": "⭐ Oblíbené",
        "fav_btn_on": "💛 Odebrat z oblíbených",
        "fav_btn_off": "⭐ Přidat do oblíbených",
        "cat_btn": "🏷️ Změnit kategorii...",
        "card_btn": "📄 Karta receptu",
        "tm_btn": "🍲 Režim Thermomix (TM6)",
        "mcs_btn": "🤖 Monsieur Cuisine Smart (MCS)",
        "pdf_btn": "🖨️ Export do PDF",
        "del_btn": "🗑️ Smazat",
        "home_tm_btn": "🟢 Cookidoo.cz",
        "home_mcs_btn": "🔵 Monsieur-Cuisine",
        "back_btn": "◀ Zpět",
        "dark_on": "🌙 Tmavý režim: ZAP",
        "light_on": "☀️ Světlý režim: ZAP",
        "save_single": "⬇️ ULOŽIT RECEPT",
        "donate_btn": "💛 Podpořit vývoj",
        "lang_orig": "🌐 Originál",
        "lang_en": "🇬🇧 English",
        "lang_cs": "🇨🇿 Čeština",
        "batch_lbl": "Hromadný překlad...",
        "cancel_btn": "✖ Zastavit",
        "time_lbl": "⏱️ ČAS",
        "temp_lbl": "🌡️ TEPLOTA",
        "speed_lbl": "🔪 OTÁČKY",
        "ingredients_lbl": "🛒 Suroviny",
        "step_title": "POSTUP PŘÍPRAVY — KROK",
        "prev_btn": "◀ PŘEDCHOZÍ KROK",
        "next_btn": "DALŠÍ KROK ▶",
        "metric_on": "📏 Metrické: ZAP",
        "metric_off": "📏 Metrické: VYP",
        "fine_on": "🔍 Jemné kroky: ZAP",
        "fine_off": "🔍 Jemné kroky: VYP",
        "ui_lang_label": "🌐 UI:",
        "key_btn": "🔑 DeepL (volitelné)",
        "ai_key_btn": "✨ Gemini AI klíč"
    },
    "en": {
        "window_title": f"{APP_NAME} {APP_VERSION} – {APP_TAGLINE['en']}",
        "wifi_label": "📡 Wi-Fi server: ",
        "qr_btn": "📱 QR Code",
        "expand_btn": "➕ Expand all",
        "collapse_btn": "➖ Collapse all",
        "all_categories": "📁 All Categories",
        "plat_all": "🔄 All Machines",
        "plat_tm6": "🟢 Cookidoo Only (TM6)",
        "plat_mcs": "🔵 Monsieur Cuisine Only",
        "plat_other": "⚫ Other Sites Only",
        "icon_dots": "Icons: 🟢 / 🔵",
        "icon_bots": "Icons: 🍲 / 🤖",
        "only_fav": "⭐ Favorites",
        "search_ph": "🔍 Search recipes...",
        "fav_btn": "⭐ Favorite",
        "fav_btn_on": "💛 Remove from Favorites",
        "fav_btn_off": "⭐ Add to Favorites",
        "cat_btn": "🏷️ Change Category...",
        "card_btn": "📄 Recipe card",
        "tm_btn": "🍲 Thermomix Mode (TM6)",
        "mcs_btn": "🤖 Monsieur Cuisine Smart (MCS)",
        "pdf_btn": "🖨️ Export to PDF",
        "del_btn": "🗑️ Delete",
        "home_tm_btn": "🟢 Cookidoo.cz",
        "home_mcs_btn": "🔵 Monsieur-Cuisine",
        "back_btn": "◀ Back",
        "dark_on": "🌙 Dark Mode: ON",
        "light_on": "☀️ Light Mode: ON",
        "save_single": "⬇️ SAVE RECIPE",
        "donate_btn": "💛 Donation",
        "lang_orig": "🌐 Original",
        "lang_en": "🇬🇧 English",
        "lang_cs": "🇨🇿 Czech",
        "batch_lbl": "Bulk translation...",
        "cancel_btn": "✖ Cancel",
        "time_lbl": "⏱️ TIME",
        "temp_lbl": "🌡️ TEMP",
        "speed_lbl": "🔪 SPEED",
        "ingredients_lbl": "🛒 Ingredients",
        "step_title": "PREPARATION — STEP",
        "prev_btn": "◀ PREVIOUS STEP",
        "next_btn": "NEXT STEP ▶",
        "metric_on": "📏 Metric: ON",
        "metric_off": "📏 Metric: OFF",
        "fine_on": "🔍 Detailed steps: ON",
        "fine_off": "🔍 Detailed steps: OFF",
        "ui_lang_label": "🌐 UI:",
        "key_btn": "🔑 DeepL (optional)",
        "ai_key_btn": "✨ Gemini AI Key"
    }
}

# ==========================================
# PŘEKLAD ROZHRANÍ PRO TEXTY MIMO UI_TEXTS (dialogy, hlášky, mobil)
# Klíč = český text, hodnota = anglický. tx("…", n=5) doplní proměnné.
# ==========================================
EN_UI = {
    # QR
    "QR kód pro přístup z mobilu / tabletu": "QR code for phone / tablet access",
    "Naskenuj QR kód fotoaparátem v mobilu:": "Scan the QR code with your phone camera:",
    "Nelze stáhnout QR kód (chybí internet pro API).\nOpiš adresu ručně.": "Cannot download the QR code (no internet for the API).\nType the address manually.",
    # levý panel
    "📚 Moje Offline Kuchařka": "📚 My Offline Cookbook",
    "Přepnout styl ikon před recepty": "Switch the icon style shown in front of recipes",
    "Rozbalit všechny kategorie": "Expand all categories",
    "Sbalit všechny kategorie": "Collapse all categories",
    # horní lišta
    "Přeložit znovu – smaže uložený překlad tohoto jazyka a přeloží recept i kartu znovu":
        "Translate again – deletes the saved translation for this language and translates the recipe and card again",
    "📥 Stáhnout offline překladač": "📥 Download offline translator",
    "Stav offline překladače (Argos Translate) a stažení jazykových modelů pro překlad bez internetu a bez klíčů":
        "Offline translator status (Argos Translate) and download of language models for translating without internet or API keys",
    # klíče
    "DeepL API klíč": "DeepL API key",
    "Zadej svůj DeepL API klíč (volitelná záloha pro překlady):": "Enter your DeepL API key (optional fallback for translations):",
    "Uloženo": "Saved",
    "DeepL API klíč byl uložen.": "The DeepL API key was saved.",
    "Google Gemini API klíč (volitelný)": "Google Gemini API key (optional)",
    "Zadej bezplatný Gemini API klíč (z aistudio.google.com) pro překlady receptů\na obousměrnou AI konverzi TM6 <-> Monsieur Cuisine.\nPokud necháš prázdné, použije se offline překladač (je-li nainstalován) a vestavěný konvertor:":
        "Enter a free Gemini API key (from aistudio.google.com) for recipe translations\nand two-way AI conversion TM6 <-> Monsieur Cuisine.\nLeave empty to use the offline translator (if installed) and the built-in converter:",
    "Nastavení Gemini klíče bylo uloženo.": "The Gemini key setting was saved.",
    # offline překladač
    "Offline překladač": "Offline translator",
    "offline překladač": "offline translator",
    "Offline překladač (Argos Translate) není nainstalovaný.\n\nInstalace (jednorázově, stáhne i větší knihovny):\n    py -m pip install argostranslate\n\nPotom aplikaci restartuj a tady stáhni jazyky.":
        "The offline translator (Argos Translate) is not installed.\n\nInstall it once (it also downloads larger libraries):\n    py -m pip install argostranslate\n\nThen restart the app and download the languages here.",
    "🌍 Zjišťuji stav offline překladače…": "🌍 Checking the offline translator…",
    "Offline překladač je nainstalovaný, ale nejde spustit:\n\n{err}\n\nPodrobnosti: {log}":
        "The offline translator is installed but cannot start:\n\n{err}\n\nDetails: {log}",
    "žádné": "none",
    "Argos Translate {ver} funguje.\n\nStažené jazykové modely: {have}": "Argos Translate {ver} works.\n\nDownloaded language models: {have}",
    "\n\n✅ Čeština a angličtina jsou stažené – překlad funguje i bez internetu a bez klíčů.":
        "\n\n✅ Czech and English are downloaded – translation works without internet and without keys.",
    "\n\nChybí: {missing}\n\nStáhnout je teď? (jednorázově, potřebuje internet, každý model má desítky až stovky MB)":
        "\n\nMissing: {missing}\n\nDownload them now? (one-time, needs internet, each model is tens to hundreds of MB)",
    "📥 Stahuji jazykové modely…": "📥 Downloading language models…",
    "Stažení se nepodařilo:\n\n{err}": "The download failed:\n\n{err}",
    "✅ Hotovo. Stažené modely: {have}\n\nPřeklad teď funguje i bez internetu.": "✅ Done. Downloaded models: {have}\n\nTranslation now works without internet.",
    # překlad
    "Překlad": "Translation",
    "Pro překlad je potřeba jedna z možností:\n\n• ✨ Gemini AI klíč (zdarma z aistudio.google.com) – nejlepší kvalita\n• offline překladač: py -m pip install argostranslate – pak v ⚙️ → 📥 Stáhnout offline překladač stáhni jazyky\n  (potom funguje bez klíče i bez internetu)":
        "Translation needs one of these:\n\n• ✨ Gemini AI key (free from aistudio.google.com) – best quality\n• offline translator: py -m pip install argostranslate – then download languages via ⚙️ → 📥 Download offline translator\n  (then it works without keys and without internet)",
    "⏳ Překládám do {lang} – {engine}…": "⏳ Translating to {lang} – {engine}…",
    "⏳ Překládám do {lang} – {engine}… {s} s": "⏳ Translating to {lang} – {engine}… {s} s",
    "Překlad se nepodařilo vytvořit:\n\n{err}\n\nZůstává zobrazen originál. Zkusit to můžeš znovu (🔄 Přeložit znovu).":
        "The translation could not be created:\n\n{err}\n\nThe original stays on screen. You can try again (🔄 Translate again).",
    "neznámá chyba": "unknown error",
    "Přeložit znovu": "Translate again",
    "🔄 Přeložit znovu": "🔄 Translate again",
    "Nejprve vyber recept.": "First select a recipe.",
    "Nejprve přepni jazyk na 🇬🇧 EN nebo 🇨🇿 CZ – přeloží se znovu ten zobrazený.":
        "First switch the language to 🇬🇧 EN or 🇨🇿 CZ – the displayed one will be translated again.",
    "Smaže uložený překlad tohoto jazyka a přeloží recept znovu": "Deletes the saved translation for this language and translates the recipe again",
    # přehrávač
    "Název receptu": "Recipe title",
    "KROK 1 Z X": "STEP 1 OF X",
    "🌍 Jazyk receptu:": "🌍 Recipe language:",
    "⚖️ Dávka:": "⚖️ Batch:",
    "Jemné kroky: každé navážení a každé nastavení stroje jako samostatný krok":
        "Detailed steps: every weighing and every machine setting as a separate step",
    "⏱️ ČAS": "⏱️ TIME",
    "🌡️ TEPLOTA": "🌡️ TEMP",
    "🔪 OTÁČKY": "🔪 SPEED",
    "🔪 RYCHLOST / PROGRAM": "🔪 SPEED / PROGRAM",
    "🔪 RYCHLOST / PRG": "🔪 SPEED / PRG",
    "🛒 Suroviny": "🛒 Ingredients",
    "KROK": "STEP",
    "hlavní": "main",
    "🤖 MONSIEUR CUISINE (Zdroj: {p})": "🤖 MONSIEUR CUISINE (Source: {p})",
    "🍲 THERMOMIX TM6 (Zdroj: {p})": "🍲 THERMOMIX TM6 (Source: {p})",
    "⚠️ U tohoto receptu se nepodařilo automaticky rozpoznat jednotlivé kroky. Otevři recept na webu, počkej na plné načtení textu a klikni znovu na <b>⬇️ ULOŽIT RECEPT</b>.":
        "⚠️ The individual steps of this recipe could not be detected. Open the recipe on the website, wait until it is fully loaded and click <b>⬇️ SAVE RECIPE</b> again.",
    "Kroky nenalezeny.": "No steps found.",
    "⏳ Připravuji konverzi pro {dev}...": "⏳ Preparing the conversion for {dev}...",
    "Chyba konverze": "Conversion error",
    # ukládání / kategorie
    "Otevři detail": "Open a recipe",
    "Nejprve na Cookidoo rozklikni konkrétní recept.": "First open a specific recipe on Cookidoo.",
    "Nejprve na Monsieur-Cuisine.com rozklikni konkrétní recept.": "First open a specific recipe on Monsieur-Cuisine.com.",
    "Teď je zobrazená už uložená karta receptu. Pro uložení otevři recept na webu Cookidoo nebo Monsieur Cuisine.":
        "This is an already saved recipe card. To save a recipe, open it on the Cookidoo or Monsieur Cuisine website.",
    "Kategorie": "Category",
    "Vyber kategorii:": "Choose a category:",
    "Recept '{title}' ({plat}) byl uložen včetně konverze pro druhý stroj!":
        "Recipe '{title}' ({plat}) was saved, including the conversion for the other machine!",
    "Vyber recept": "Select a recipe",
    "Nejprve vyber recept v seznamu vlevo.": "First select a recipe in the list on the left.",
    "Nejprve vyber recept ze stromu vlevo.": "First select a recipe in the tree on the left.",
    "Změnit kategorii": "Change category",
    "Nová kategorie:": "New category:",
    "Export do PDF": "Export to PDF",
    "Uloženo do:\n{path}": "Saved to:\n{path}",
    "Chyba": "Error",
    "Nastala chyba, aplikace ale běží dál:\n\n{err}\n\nPodrobnosti: {log}": "An error occurred, but the app keeps running:\n\n{err}\n\nDetails: {log}",
    # mobil – hlášky ze serveru
    "⚠️ Překladač není nastaven – v desktopové aplikaci zadej ✨ Gemini klíč nebo nainstaluj argostranslate. Zobrazuji originál.":
        "⚠️ No translator is set up – enter a ✨ Gemini key in the desktop app or install argostranslate. Showing the original.",
    "❌ Překlad selhal: {err} – zobrazuji originál.": "❌ Translation failed: {err} – showing the original.",
    "⏳ Překládám… zatím zobrazuji originál, stránka se sama obnoví.": "⏳ Translating… showing the original for now, the page refreshes by itself.",
    "Karta receptu není pro tento recept k dispozici.": "The recipe card is not available for this recipe.",
    "❌ Překlad karty se nepodařil": "❌ Translating the card failed",
    "🔄 Zkusit znovu": "🔄 Try again",
    "⏳ Překládám kartu do {lang}…": "⏳ Translating the card to {lang}…",
    "Stránka se obnoví sama ({s} s).": "The page refreshes by itself ({s} s).",
    # chyby překladu
    "vyčerpán limit bezplatných dotazů (HTTP 429) – zkus to za chvíli": "free request limit reached (HTTP 429) – try again in a moment",
    "klíč byl odmítnut ({txt}) – zkontroluj ✨ Gemini klíč": "the key was rejected ({txt}) – check the ✨ Gemini key",
    "model nenalezen (HTTP 404) – v config.json nastav platný \"gemini_model\"": "model not found (HTTP 404) – set a valid \"gemini_model\" in config.json",
    "nedostupné připojení k internetu ({txt})": "no internet connection ({txt})",
    "Není k dispozici žádný překladač – zadej ✨ Gemini klíč, nebo nainstaluj offline překladač: py -m pip install argostranslate":
        "No translator available – enter a ✨ Gemini key or install the offline translator: py -m pip install argostranslate",
    "offline překladač nestihl odpovědět včas": "the offline translator did not respond in time",
    "offline překladač spadl (kód {code})": "the offline translator crashed (code {code})",
    "Překladač nevrátil výsledek (zkontroluj Gemini klíč nebo instalaci argostranslate).": "The translator returned no result (check the Gemini key or the argostranslate installation).",
    # v12: nové rozhraní, PDF, hromadný překlad, kategorie, hledání
    "Hotovo: přeloženo {ok} z {t}.": "Done: translated {ok} of {t}.",
    "➕ Nová kategorie": "➕ New category",
    "Založit novou kategorii (vybraný recept do ní můžeš rovnou přesunout)": "Create a new category (you can move the selected recipe into it right away)",
    "V jakém jazyce ukazovat názvy receptů (přeložený název je k dispozici po překladu receptu)": "Language of recipe names in the list (a translated name is available once the recipe has been translated)",
    "⚙️ Nastavení": "⚙️ Settings",
    "❓ Návod": "❓ How to use",
    # offline překladač – kontrola při startu
    "ANO": "YES",
    "NE": "NO",
    "Příště se již neptat": "Don’t ask again",
    "Překladač je vždy možné stáhnout v ⚙️ Nastavení → 📥 Stáhnout offline překladač.":
        "You can always download the translator in ⚙️ Settings → 📥 Download offline translator.",
    "Offline překladač (Argos Translate) není nainstalovaný.": "The offline translator (Argos Translate) is not installed.",
    "Offline překladači chybí jazykové modely: {missing}.": "The offline translator is missing language models: {missing}.",
    "Stáhnout ho teď? Překlad receptů pak funguje i bez internetu a bez API klíčů. Stahuje se jednou (stovky MB, bez Pythonu knihoven až 1–2 GB).":
        "Download it now? Recipe translation then works without internet and without API keys. It is downloaded once "
        "(hundreds of MB; up to 1–2 GB including the Python libraries).",
    "📥 Stahuji offline překladač…": "📥 Downloading the offline translator…",
    "V této verzi programu offline překladač chybí – stáhni novou verzi aplikace.":
        "This build of the program has no offline translator – download a new version of the app.",
    "Instalace knihovny argostranslate selhala – podrobnosti jsou v app.log.":
        "Installing the argostranslate library failed – details are in app.log.",
    "Offline překladač (Argos Translate) není nainstalovaný.\n\nNainstalovat ho teď i s jazykovými modely? Jednorázově se stáhnou knihovny a modely (zhruba 1–2 GB), potřebuje to internet a pár minut.":
        "The offline translator (Argos Translate) is not installed.\n\nInstall it now together with the language models? "
        "Libraries and models are downloaded once (about 1–2 GB); it needs internet and a few minutes.",
    # záloha receptů (.7z)
    "Chybí knihovna py7zr (py -m pip install py7zr).": "The py7zr library is missing (py -m pip install py7zr).",
    "Export potřebuje knihovnu py7zr:\n\n    py -m pip install py7zr\n\nPotom aplikaci restartuj.":
        "Export needs the py7zr library:\n\n    py -m pip install py7zr\n\nThen restart the app.",
    "Import potřebuje knihovnu py7zr:\n\n    py -m pip install py7zr\n\nPotom aplikaci restartuj.":
        "Import needs the py7zr library:\n\n    py -m pip install py7zr\n\nThen restart the app.",
    "Export receptů": "Export recipes",
    "Import receptů": "Import recipes",
    "Export se nepodařil:\n\n{err}": "Export failed:\n\n{err}",
    "Import se nepodařil:\n\n{err}": "Import failed:\n\n{err}",
    "Exportováno receptů: {n} ({mb} MB)\n\nUloženo do:\n{path}": "Recipes exported: {n} ({mb} MB)\n\nSaved to:\n{path}",
    "Nejdřív v seznamu vlevo označ recepty (Ctrl/Shift + klik, nebo celou kategorii).":
        "First select recipes in the list on the left (Ctrl/Shift + click, or a whole category).",
    "Nové recepty: {a}\nNahrazené: {b}\nPřeskočené (už v kuchařce): {c}":
        "New recipes: {a}\nReplaced: {b}\nSkipped (already in the cookbook): {c}",
    "Problémy:": "Problems:",
    "V souborech nejsou žádné recepty k importu.": "The files contain no recipes to import.",
    "Zabalí označené recepty do jednoho souboru .7z (do složky exported_recipes). Na jiném počítači je nahraješ tlačítkem 📥 Importovat recepty.":
        "Packs the selected recipes into one .7z file (in the exported_recipes folder). Load them on another computer with 📥 Import recipes.",
    "chybí recipe.json": "recipe.json is missing",
    "není to záloha receptů z této aplikace": "not a recipe backup from this app",
    "složku receptu nejde nahradit": "the recipe folder cannot be replaced",
    "{n} z {total} receptů už v kuchařce je:\n\n{names}\n\nPřepsat je verzí ze zálohy?\nAno = přepsat (současná verze půjde do koše recipes_smazane), Ne = ponechat současnou.":
        "{n} of {total} recipes are already in your cookbook:\n\n{names}\n\nReplace them with the backup version?\n"
        "Yes = replace (the current version goes to the recipes_smazane trash), No = keep the current one.",
    "Žádný z vybraných receptů nejde exportovat.": "None of the selected recipes can be exported.",
    "📥 Importovat recepty (.7z)…": "📥 Import recipes (.7z)…",
    "📥 Importuji recepty…": "📥 Importing recipes…",
    "📥 Rozbaluji zálohy…": "📥 Unpacking backups…",
    "📦 Balím recepty do .7z…": "📦 Packing recipes into .7z…",
    "📦 Exportovat označené (.7z)…": "📦 Export selected (.7z)…",
    "📦 Exportovat zálohu (.7z)…": "📦 Export backup (.7z)…",
    "📦 Exportovat zálohu – {n} receptů (.7z)…": "📦 Export backup – {n} recipes (.7z)…",
    "❓ Návod k použití": "❓ How to use",
    "🌍 Přeložit všechny recepty (EN + CZ)…": "🌍 Translate all recipes (EN + CZ)…",
    "Vzhled": "Appearance",
    "Zobrazit:": "View:",
    "Jazyk:": "Language:",
    "🖨️ Připravuji PDF…": "🖨️ Preparing the PDF…",
    "Hromadný překlad": "Bulk translation",
    "Přeložit {n} receptů ({k} překladů: EN a CZ, recept i karta)?\n\nPřekladač: {engine}\nBěží to na pozadí, aplikaci můžeš dál používat. Už hotové překlady se přeskočí.":
        "Translate {n} recipes ({k} translations: EN and CZ, recipe and card)?\n\nTranslator: {engine}\nIt runs in the background, you can keep using the app. Finished translations are skipped.",
    "🌍 Překládám {d}/{t}: {cur}": "🌍 Translating {d}/{t}: {cur}",
    "Názvy: originál": "Names: original",
    "Názvy: English": "Names: English",
    "Názvy: čeština": "Names: Czech",
    "Nová kategorie": "New category",
    "Název nové kategorie:": "Name of the new category:",
    "⏹ Zastavuji po dokončení aktuálního receptu…": "⏹ Stopping after the current recipe…",
    "Hromadný překlad už běží – průběh vidíš v modré liště nahoře.": "Bulk translation is already running – see the blue bar at the top.",
    "Všechny recepty už jsou přeložené do angličtiny i češtiny. 👍": "All recipes are already translated into English and Czech. 👍",
    "Nepovedlo se: {f} (podrobnosti v app.log). Spusť hromadný překlad znovu – hotové se přeskočí.": "Failed: {f} (details in app.log). Run the bulk translation again – finished ones are skipped.",
    "Přesunout vybraný recept „{t}“ do kategorie „{c}“?": "Move the selected recipe “{t}” into the category “{c}”?",
    "PDF se nepodařilo uložit do:\n{path}\n\nZkus jinou složku (např. Dokumenty).": "The PDF could not be saved to:\n{path}\n\nTry another folder (e.g. Documents).",
    "Hromadný překlad zastaven.": "Bulk translation stopped.",
    "Recept zatím není přeložený – zobrazuji původní název": "The recipe is not translated yet – showing the original name",
    "Nalezeno: {n}": "Found: {n}",
    "Nic nenalezeno – zkus jiné slovo nebo zruš filtry nahoře.": "Nothing found – try another word or clear the filters above.",
    "PDF se nepodařilo vytvořit:\n\n{err}": "The PDF could not be created:\n\n{err}",
    "Názvy: podle jazyka aplikace": "Names: same as app language",
    "🏷️ Přesunout do kategorie": "🏷️ Move to category",
    "➕ Nová…": "➕ New…",
    "Založí novou kategorii a recept do ní rovnou přesune": "Creates a new category and moves the recipe into it",
    "Všechny recepty už jsou přeložené do angličtiny i češtiny. 👍\n\nChceš je přeložit všechny znovu (např. po změně překladače nebo kvůli lepší kvalitě)?\nStávající překlady se smažou.":
        "All recipes are already translated into English and Czech. 👍\n\nDo you want to translate them all again (e.g. after changing the translator or for better quality)?\nExisting translations will be deleted.",
    "teď": "now",
    "Aplikace": "App",
    "ℹ️ Co je nového a podmínky použití (verze {v})": "ℹ️ What's new and terms of use (version {v})",
    "🔎 Hledat recept (web i kuchařka)…": "🔎 Search recipes (web and cookbook)…",
    "podle názvu": "by name",
    "podle suroviny": "by ingredient",
    "🔎 Hledat": "🔎 Search",
    "Hledání": "Search",
    "Vestavěný server neběží (port {p} je obsazený), stránku s výsledky nejde zobrazit.": "The built-in server is not running (port {p} is busy), the results page cannot be shown.",
    "Nejprve otevři stránku s receptem (Cookidoo, Monsieur Cuisine nebo jiný web s recepty).": "First open a recipe page (Cookidoo, Monsieur Cuisine or another recipe website).",
    "Recept nerozpoznán": "Recipe not recognised",
    "Na této stránce se nepodařilo najít suroviny nebo postup receptu.\n\nTip: nainstaluj knihovnu recipe-scrapers (py -m pip install recipe-scrapers), ta zná stovky webů s recepty.":
        "No ingredients or method could be found on this page.\n\nTip: install the recipe-scrapers library (py -m pip install recipe-scrapers), it knows hundreds of recipe websites.",
    "🏠 Domů": "🏠 Home",
    "Jen video": "Video only",
    "Tahle stránka obsahuje jen video – nejsou na ní suroviny ani postup, takže recept nejde uložit.\n\nZkus najít stejný recept jako textový (např. přes 🏠 Domů a hledání).":
        "This page contains only a video – there are no ingredients or method, so the recipe cannot be saved.\n\nTry to find the same recipe as text (e.g. via 🏠 Home and search).",
}

# Výchozí kategorie aplikace – v DB zůstávají česky, jen se jinak zobrazí.
CATEGORY_EN = {
    "Nezařazené": "Uncategorized", "Hlavní jídla": "Main dishes", "Polévky": "Soups",
    "Pečení & Dezerty": "Baking & Desserts", "Omáčky": "Sauces", "Cizojazyčné": "Foreign-language",
    "Kolekce": "Collection",
}

_UI_STATE = {"lang": "cs"}


def ui_lang() -> str:
    return _UI_STATE["lang"]


def set_ui_lang(lang: str):
    _UI_STATE["lang"] = "en" if lang == "en" else "cs"


def tx(text: str, **kw) -> str:
    s = EN_UI.get(text, text) if _UI_STATE["lang"] == "en" else text
    return s.format(**kw) if kw else s


def txl(text: str, lang: str, **kw) -> str:
    """Jako tx(), ale pro zadaný jazyk (mobil si volí jazyk sám, nezávisle na počítači)."""
    s = EN_UI.get(text, text) if lang == "en" else text
    return s.format(**kw) if kw else s


def cat_label(raw: str) -> str:
    return CATEGORY_EN.get(raw, raw) if _UI_STATE["lang"] == "en" else raw


def cat_from_label(label: str) -> str:
    for raw, en in CATEGORY_EN.items():
        if label == en:
            return raw
    return label


def _data_dir_beside_app() -> Path:
    """Datová složka vedle programu. Do verze 1.2 se jmenovala cookidoo_data – při prvním startu se přejmenuje
    a cesty v catalog.db se přepíšou (recepty, nastavení i přihlášení zůstanou). Když to nejde (složku drží jiný
    program), použije se stará složka."""
    new, old = app_dir() / "localchef_data", app_dir() / "cookidoo_data"
    if new.exists() or not old.is_dir():
        return new
    try:
        old.rename(new)
    except OSError as e:
        _DATA_NOTES.append(f"Složku cookidoo_data nejde přejmenovat na localchef_data ({e}) – používám starou")
        return old
    try:
        conn = sqlite3.connect(new / "catalog.db")
        conn.execute("UPDATE recipes SET folder_path = replace(folder_path, ?, ?)", (str(old.resolve()), str(new.resolve())))
        conn.commit()
        conn.close()
    except Exception as e:
        _DATA_NOTES.append(f"Cesty v catalog.db se nepřepsaly ({e}) – recepty se dohledají podle názvu složky")
    _DATA_NOTES.append("Datová složka cookidoo_data přejmenována na localchef_data (nový název aplikace)")
    return new



def _dir_writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".zapis_test"
        probe.write_text("1", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _data_dir() -> Path:
    """Data jsou vedle programu (přenosné, i u exe). Když tam zapisovat nejde – program nainstalovaný do
    Program Files nebo na disk jen pro čtení – použije se %LOCALAPPDATA%/LocalChef Studio/localchef_data."""
    d = _data_dir_beside_app()
    if _dir_writable(d):
        return d
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    alt = Path(base) / "LocalChef Studio" / "localchef_data"
    _DATA_NOTES.append(f"Do {d} nejde zapisovat – data jsou v {alt}")
    return alt


_DATA_NOTES: list = []
BASE_DIR = _data_dir()
SESSION_DIR = BASE_DIR / "browser_profile"
CACHE_DIR = BASE_DIR / "browser_cache"
RECIPES_DIR = BASE_DIR / "recipes"
PDF_DIR = BASE_DIR / "pdf_exports"
DB_PATH = BASE_DIR / "catalog.db"
CONFIG_PATH = BASE_DIR / "config.json"
LAN_PORT = 3665

for d in (BASE_DIR, SESSION_DIR, CACHE_DIR, RECIPES_DIR, PDF_DIR):
    d.mkdir(parents=True, exist_ok=True)


def resolve_recipe_folder(path_str) -> Path:
    """DB ukládá absolutní cesty. Po přenesení na jiný disk/počítač (nebo do exe) se složka dohledá podle názvu."""
    p = Path(path_str or "")
    if p.exists():
        return p
    name = [x for x in re.split(r'[\\/]', str(path_str or '')) if x][-1:] or ['']
    alt = RECIPES_DIR / name[0]
    return alt if alt.exists() else p


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(data: dict):
    cfg = load_config()
    cfg.update(data)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


APP_LOG = BASE_DIR / "app.log"


def log(msg: str):
    """Bezpečný výpis: na Windows konzoli neshodí aplikaci kvůli znakům jako →, a zapisuje i do app.log."""
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        print(line)
    except Exception:
        try:
            print(line.encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass
    try:
        with open(APP_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_api_key() -> str:
    return load_config().get("deepl_api_key", "")


def save_api_key(key: str):
    save_config({"deepl_api_key": key.strip()})


def load_gemini_key() -> str:
    return load_config().get("gemini_api_key", "")


def save_gemini_key(key: str):
    save_config({"gemini_api_key": key.strip()})


def load_icon_style() -> str:
    return load_config().get("icon_style", "dots")


def save_icon_style(style: str):
    save_config({"icon_style": style})


TM_SYMBOLS_MAP = {
    "\ue001": " 🌾 [Těsto] ",
    "\ue002": " 🥄 [Vařečka] ",
    "\ue003": " ↺ [Zpětný chod] ",
    "\ue004": " ↻ [Klasický chod] ",
    "\ue005": " 🌾 [Hnětení/Klas] ",
    "\ue006": " 🥄 [Vaření/Míchání] ",
    "\ue007": " ⚖️ [Váha] ",
    "\ue008": " ♨️ [Varoma] ",
    "\ue009": " ⚡ [Turbo] ",
}

MCS_SYMBOLS_MAP = {
    "\ue001": " 🌾 [Program Hnětení] ",
    "\ue002": " ↺ [Rychlost 1 + Levý chod] ",
    "\ue003": " ↺ [Levý chod] ",
    "\ue004": " ↻ [Pravý chod] ",
    "\ue005": " 🌾 [Program Hnětení] ",
    "\ue006": " ↺ [Rychlost 1 + Levý chod] ",
    "\ue007": " ⚖️ [Váha] ",
    "\ue008": " ♨️ [Program Pára / 120 °C] ",
    "\ue009": " ⚡ [Tlačítko Turbo] ",
}

UNICODE_FRACTIONS = {
    "½": 0.5, "⅓": 1/3, "⅔": 2/3, "¼": 0.25, "¾": 0.75,
    "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875
}

DARK_THEME_QSS = """
QMainWindow, QWidget { background-color: #1E1E1E; color: #E0E0E0; font-family: "Segoe UI", sans-serif; }
QLineEdit, QComboBox, QTreeWidget, QTextBrowser {
    background-color: #252526; color: #F0F0F0; border: 1px solid #3E3E42; border-radius: 5px; padding: 5px;
}
QTreeWidget::item { padding: 4px; }
QTreeWidget::item:selected { background-color: #094771; color: #FFFFFF; }
QPushButton {
    background-color: #333337; color: #F0F0F0; border: 1px solid #48484D; border-radius: 5px; padding: 6px 10px;
}
QPushButton:hover { background-color: #3E3E42; }
QSplitter::handle { background-color: #333337; }
"""

LIGHT_THEME_QSS = """
QMainWindow, QWidget { background-color: #F4F5F7; color: #202124; font-family: "Segoe UI", sans-serif; }
QLineEdit, QComboBox, QTreeWidget, QTextBrowser {
    background-color: #FFFFFF; color: #202124; border: 1px solid #CCCCCC; border-radius: 5px; padding: 5px;
}
QTreeWidget::item { padding: 4px; }
QTreeWidget::item:selected { background-color: #D2E3FC; color: #174EA6; }
QPushButton {
    background-color: #FFFFFF; color: #202124; border: 1px solid #CCCCCC; border-radius: 5px; padding: 6px 10px;
}
QPushButton:hover { background-color: #E8EAED; }
QSplitter::handle { background-color: #DADCE0; }
"""


def get_local_ip() -> str:
    # V Dockeru je vlastní IP kontejneru pro telefon k ničemu → adresu počítače předá build_docker.bat
    override = os.environ.get("LOCALCHEF_LAN_HOST", "").strip()
    if override:
        return override
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            recipe_id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            portions TEXT,
            total_time TEXT,
            folder_path TEXT,
            category TEXT DEFAULT 'Nezařazené',
            is_favorite INTEGER DEFAULT 0,
            source_platform TEXT DEFAULT 'tm6',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("PRAGMA table_info(recipes)")
    existing_cols = [row[1] for row in c.fetchall()]
    if "category" not in existing_cols:
        c.execute("ALTER TABLE recipes ADD COLUMN category TEXT DEFAULT 'Nezařazené'")
    if "is_favorite" not in existing_cols:
        c.execute("ALTER TABLE recipes ADD COLUMN is_favorite INTEGER DEFAULT 0")
    if "source_platform" not in existing_cols:
        c.execute("ALTER TABLE recipes ADD COLUMN source_platform TEXT DEFAULT 'tm6'")
    for col in ("title_en", "title_cs"):
        if col not in existing_cols:
            c.execute(f"ALTER TABLE recipes ADD COLUMN {col} TEXT")
    conn.commit()
    conn.close()


DELETED_MARK = ".smazano"        # záložní značka, když složku nejde přesunout (např. je otevřená jinde)
DELETED_DIR = BASE_DIR / "recipes_smazane"     # koš: smazané recepty se přesunou sem, ve recipes zůstanou jen platné


def move_recipe_to_trash(folder: Path) -> Path | None:
    """Přesune složku receptu do localchef_data/recipes_smazane. Když to nejde, aspoň ji označí značkou."""
    folder = Path(folder)
    if not folder.is_dir():
        return None
    try:
        folder.resolve().relative_to(RECIPES_DIR.resolve())
    except ValueError:
        return None                                   # mimo recipes nic nepřesouváme
    DELETED_DIR.mkdir(parents=True, exist_ok=True)
    target = DELETED_DIR / folder.name
    n = 2
    while target.exists():
        target = DELETED_DIR / f"{folder.name}_{n}"
        n += 1
    try:
        shutil.move(str(folder), str(target))
        (target / DELETED_MARK).unlink(missing_ok=True)
        return target
    except Exception as e:
        log(f"Složku {folder.name} se nepodařilo přesunout do koše ({e}), jen ji označuji")
        try:
            (folder / DELETED_MARK).write_text("Recept byl smazán v aplikaci.\n", encoding="utf-8")
        except OSError:
            pass
        return None


def sync_catalog_from_folders() -> int:
    """Doplní do catalog.db recepty, které leží v localchef_data/recipes, ale databáze o nich neví
    (zkopírované od někoho jiného, ze zálohy…). Nic nepřepisuje, jen přidává. Vrátí počet přidaných."""
    if not RECIPES_DIR.exists():
        return 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    known = {r[0] for r in c.execute("SELECT recipe_id FROM recipes")}
    added = 0
    # Recepty smazané ve starších verzích nemají značku .smazano. Při prvním startu této verze se proto
    # složky, o kterých existující kuchařka neví, jen označí jako smazané (nevrátí se). Prázdná kuchařka
    # (nová instalace, předaná data bez catalog.db) naopak načte všechno.
    first_sync_flag = BASE_DIR / ".catalog_sync_v1"
    mark_unknown_as_deleted = not first_sync_flag.exists() and bool(known)
    marked = 0
    for folder in sorted(RECIPES_DIR.iterdir()):
        try:
            rj = folder / "recipe.json"
            if not folder.is_dir() or not rj.exists():
                continue
            if (folder / DELETED_MARK).exists():
                move_recipe_to_trash(folder)          # dřív jen označené → teď do koše
                continue
            data = json.loads(rj.read_text(encoding="utf-8"))
            rid = str(data.get("recipe_id") or "").strip()
            if not rid or rid in known:
                continue
            if mark_unknown_as_deleted:
                move_recipe_to_trash(folder)          # smazaný ve starší verzi → do koše
                marked += 1
                continue
            plat = str(data.get("source_platform") or data.get("device") or "tm6").lower()
            c.execute("""
                INSERT INTO recipes (recipe_id, title, url, portions, total_time, folder_path, category, is_favorite, source_platform)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (rid, data.get("title") or folder.name, data.get("url", ""), str(data.get("portions", "")),
                  str(data.get("total_time", "")), str(folder.resolve()), data.get("category") or "Nezařazené",
                  1 if data.get("is_favorite") else 0, plat if plat in ("mcs", "other") else "tm6"))
            known.add(rid)
            added += 1
        except Exception as e:
            log(f"Složku {folder.name} se nepodařilo zařadit do kuchařky: {e}")
    conn.commit()
    conn.close()
    try:
        first_sync_flag.write_text("1", encoding="utf-8")
    except OSError:
        pass
    if marked:
        log(f"První spuštění: {marked} dříve smazaných receptů přesunuto do {DELETED_DIR.name}")
    if added:
        log(f"Do kuchařky doplněno {added} receptů ze složky recipes")
    return added


def set_title_translation(folder: Path, lang: str, title: str):
    """Uloží přeložený název do katalogu (seznam receptů vlevo a v mobilu ho pak umí ukázat)."""
    if lang not in ("en", "cs") or not title:
        return
    try:
        rid = json.loads((Path(folder) / "recipe.json").read_text(encoding="utf-8")).get("recipe_id")
        if not rid:
            return
        conn = sqlite3.connect(DB_PATH)
        conn.execute(f"UPDATE recipes SET title_{lang} = ? WHERE recipe_id = ?", (title, rid))
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"Přeložený název se nepodařilo uložit: {e}")


def repair_fragmented_steps() -> int:
    """Recepty z Cookidoo uložené s kroky rozsekanými podle <nobr> („3 Sek./Stufe 5“ jako samostatný krok)
    se opraví z uložených dat Cookidoo (_debug_api.json). Odvozené soubory (verze pro MCS, překlady receptu) se smažou
    a při dalším otevření vzniknou znovu ze správných kroků."""
    fixed = 0
    if not RECIPES_DIR.exists():
        return 0
    for folder in RECIPES_DIR.iterdir():
        try:
            rj, api_f = folder / "recipe.json", folder / "_debug_api.json"
            if not rj.exists() or not api_f.exists():
                continue
            data = json.loads(rj.read_text(encoding="utf-8"))
            if (data.get("extraction") or {}).get("steps") != "ld+json" or data.get("steps_repaired"):
                continue
            api = json.loads(api_f.read_text(encoding="utf-8") or "{}")
            if not isinstance(api, dict) or not api.get("recipeStepGroups"):
                continue
            _, j_steps = cookidoo_json_to_basic(api)
            data["steps_repaired"] = True
            if j_steps and [x.get("text") for x in j_steps] != [x.get("text") for x in (data.get("steps") or [])]:
                data["steps"] = j_steps
                data["extraction"]["steps"] = "cookidoo-json"
                for f in list(folder.glob("recipe_*.json")):
                    f.unlink()
                fixed += 1
            rj.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log(f"Oprava kroků {folder.name} selhala: {e}")
    if fixed:
        log(f"Opraveny rozsekané kroky u {fixed} receptů (z uložených dat Cookidoo)")
    return fixed


def backfill_translated_titles() -> int:
    """Názvy z už hotových překladů (recipe_en.json, recipe_cs.json…) doplní do katalogu."""
    n = 0
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT recipe_id, folder_path, title_en, title_cs FROM recipes "
                            "WHERE title_en IS NULL OR title_cs IS NULL").fetchall()
        for rid, fp, t_en, t_cs in rows:
            folder = resolve_recipe_folder(fp)
            for lang, cur in (("en", t_en), ("cs", t_cs)):
                if cur:
                    continue
                for name in ("recipe", "recipe_tm6", "recipe_mcs"):
                    f = folder / f"{name}_{lang}.json"
                    if f.exists():
                        try:
                            t = json.loads(f.read_text(encoding="utf-8")).get("title")
                        except Exception:
                            t = None
                        if t:
                            conn.execute(f"UPDATE recipes SET title_{lang} = ? WHERE recipe_id = ?", (t, rid))
                            n += 1
                        break
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"Doplnění přeložených názvů selhalo: {e}")
    return n


def search_key(text: str) -> str:
    """Pro hledání: malá písmena a bez diakritiky (kulajda = Kulajda, svickova = svíčková)."""
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(ch for ch in t if not unicodedata.combining(ch))


def set_recipe_json_field(folder: Path, key: str, value):
    """Zapíše hodnotu (kategorie, oblíbené) i do recipe*.json, aby se přenesla s kopií složky."""
    for json_file in Path(folder).glob("recipe*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            data[key] = value
            json_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log(f"Zápis {key} do {json_file.name} selhal: {e}")


def get_recipe_icon_prefix(source_platform: str, is_fav: bool, icon_style: str) -> str:
    plat = (source_platform or "tm6").lower()
    if icon_style == "bots":
        plat_ic = {"mcs": "🤖", "other": "🍽️"}.get(plat, "🍲")
    else:
        plat_ic = {"mcs": "🔵", "other": "⚫"}.get(plat, "🟢")
    fav_ic = "⭐ " if is_fav else ""
    return f"{fav_ic}{plat_ic} "


def _parse_amount(val_str: str) -> float | None:
    s = val_str.strip()
    if not s:
        return None
    total = 0.0
    for ch, fval in UNICODE_FRACTIONS.items():
        if ch in s:
            total += fval
            s = s.replace(ch, " ").strip()
    if not s:
        return total if total > 0 else None
    parts = s.split()
    try:
        for p in parts:
            if "/" in p:
                num, den = p.split("/", 1)
                total += float(num) / float(den)
            else:
                total += float(p.replace(",", "."))
        return total
    except Exception:
        return None


def _format_num(val: float) -> str:
    if abs(val - round(val)) < 0.05:
        return str(int(round(val)))
    return f"{val:.1f}".rstrip("0").rstrip(".")


_FRAC_CHARS = "½⅓⅔¼¾⅛⅜⅝⅞"
_QTY = r'(\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?(?:\s*[½⅓⅔¼¾⅛⅜⅝⅞])?|[½⅓⅔¼¾⅛⅜⅝⅞])'
# jednotky, u kterých se množství násobí podle dávky (hmotnost, objem, kusy, lžíce…)
_SCALE_UNITS = (r'(?:kg|dkg|mg|g|gramů|gramy|gram|gr|ml|cl|dl|l|litr\w*|lžíc\w*|lžičk\w*|hrnk\w*|hrnek|ks|kus\w*|'
                r'stroužk\w*|plátk\w*|špetk\w*|balíč\w*|EL|TL|Prise\w*|Stück|Stk|Zehe\w*|Bund|Pck|Päckchen|'
                r'tbsp|tsp|tablespoons?|teaspoons?|cups?|oz|lbs?|pounds?|ounces?|pieces?|cloves?|pinch(?:es)?|'
                r'łyżk\w*|łyżeczk\w*|szt\w*)')
_STEP_SCALE_UNITS = r'(?:kg|dkg|g|gramů|gramy|gram|ml|cl|dl|l|litr\w*|oz|lbs?|cups?)'


def _clean_fractions(s: str) -> str:
    return s.replace("⁄", "/").replace(" ", " ").replace(" ", " ")


def _scale_match(m, factor: float) -> str:
    raw = m.group(0)
    val = _parse_amount(raw)
    if val is None or val == 0:
        return raw
    return _format_num(val * factor)


def scale_ingredient_line(line: str, factor: float) -> str:
    """Vynásobí množství suroviny podle dávky. Zvládne číslo na začátku (i rozsah 2–3), číslo s jednotkou
    kdekoli v řádku ("Mehl 200 g") a gramáž v závorce; procenta ani velikosti (vel. M) nemění."""
    if abs(factor - 1.0) < 0.01:
        return line
    s = _clean_fractions(line.strip())
    lead = re.match(r'^' + _QTY + r'(?:\s*[-–]\s*' + _QTY + r')?(?![\d.,]|\s*%)', s)
    if lead and lead.group(0).strip():
        part = re.sub(_QTY, lambda m: _scale_match(m, factor), lead.group(0))
        s = part + s[lead.end():]
    else:
        s = re.sub(r'(?<![\w.,/(])' + _QTY + r'(?=\s*' + _SCALE_UNITS + r'\b)',
                   lambda m: _scale_match(m, factor), s, count=1, flags=re.IGNORECASE)
    # gramáž v závorce: "1 balíček (250 g)"
    s = re.sub(r'(?<=\()(\d+(?:[.,]\d+)?)(?=\s*(?:g|gram\w*|ml|l|kg|oz|lb)\b)',
               lambda m: _scale_match(m, factor), s, flags=re.IGNORECASE)
    return s


def scale_step_text(html: str, factor: float) -> str:
    """V textu kroku přepočítá jen hmotnost a objem (200 g, 0,5 l) – teploty, časy ani rychlosti se nemění."""
    if abs(factor - 1.0) < 0.01 or not html:
        return html
    parts = re.split(r'(<[^>]+>)', _clean_fractions(html))
    pat = re.compile(r'(?<![\w.,/°])' + _QTY + r'(?=\s*' + _STEP_SCALE_UNITS + r'\b)', re.IGNORECASE)
    for i, part in enumerate(parts):
        if part.startswith("<"):
            continue
        parts[i] = pat.sub(lambda m: _scale_match(m, factor), part)
    return "".join(parts)


_METRIC_UNITS = [
    # (regex jednotky, násobek, cílová jednotka)
    (r'fl\.?\s*oz\.?|fluid\s+ounces?', 29.57, "ml"),
    (r'oz\.?|ounces?', 28.35, "g"),
    (r'lbs?\.?|pounds?', 453.6, "g"),
    (r'cups?', 240, "ml"),
    (r'tablespoons?|tbsps?\.?|Tbsp\.?', 15, "ml"),
    (r'teaspoons?|tsps?\.?', 5, "ml"),
    (r'pints?|pt\.', 473, "ml"),
    (r'quarts?|qt\.', 946, "ml"),
    (r'gallons?|gal\.', 3785, "ml"),
    (r'sticks?(?:\s+of)?\s+butter', 113, "g"),
    (r'inch(?:es)?|in\.', 2.54, "cm"),
]


def _fmt_metric(val: float, unit: str) -> str:
    if unit == "ml" and val >= 1000:
        return f"{_format_num(val / 1000)} l"
    if unit == "g" and val >= 1000:
        return f"{_format_num(val / 1000)} kg"
    if unit == "cm":
        return f"{_format_num(round(val * 2) / 2)} cm"
    if val >= 50:
        val = round(val / 5) * 5
    return f"{_format_num(val)} {unit}"


def convert_text_to_metric(text: str, html_highlight: bool = True) -> str:
    """Imperiální jednotky → metrické (°F, oz, lb, cup, tbsp, tsp, fl oz, pint, quart, stick, inch)."""
    if not text:
        return text

    def wrap(metric_str: str, orig_str: str) -> str:
        if html_highlight:
            return f"<span style='color:#4FC3F7; font-weight:bold;'>{metric_str}</span> <span style='color:#888888; font-size:0.85em;'>[orig: {orig_str.strip()}]</span>"
        return f"{metric_str} [orig: {orig_str.strip()}]"

    text = _clean_fractions(text)

    def repl_temp(m):
        f_val = float(m.group(1).replace(",", "."))
        if f_val < 150:                      # 100 °F a méně v receptech prakticky není → nejspíš něco jiného
            return m.group(0)
        c_val = round((f_val - 32.0) * 5.0 / 9.0 / 5.0) * 5
        return wrap(f"{c_val} °C", m.group(0))

    text = re.sub(r'\b(\d{3}(?:[.,]\d+)?)\s*(?:°\s*F\b|degrees?\s+F(?:ahrenheit)?\b|F\b(?!\w))', repl_temp, text, flags=re.IGNORECASE)

    unit_alt = "|".join(f"(?P<u{i}>{u})" for i, (u, _, _) in enumerate(_METRIC_UNITS))
    pat = re.compile(r'(?<![\w.,/])' + _QTY + r'(?:\s*[-–]\s*' + _QTY + r')?\s*(?:' + unit_alt + r')(?![\w])', re.IGNORECASE)

    def repl(m):
        idx = next(i for i in range(len(_METRIC_UNITS)) if m.group(f"u{i}"))
        _, mult, unit = _METRIC_UNITS[idx]
        v1 = _parse_amount(m.group(1))
        if v1 is None:
            return m.group(0)
        if m.group(2):
            v2 = _parse_amount(m.group(2))
            if v2 is not None:
                a1, a2 = _fmt_metric(v1 * mult, unit).rsplit(" ", 1), _fmt_metric(v2 * mult, unit)
                return wrap(f"{a1[0]}–{a2}", m.group(0))
        return wrap(_fmt_metric(v1 * mult, unit), m.group(0))

    parts = re.split(r'(<[^>]+>)', text)
    for i, part in enumerate(parts):
        if not part.startswith("<"):
            parts[i] = pat.sub(repl, part)
    return "".join(parts)


_TIME_UNIT_RE = re.compile(r'(\d+(?:[.,]\d+)?(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?)\s*([A-Za-zÀ-ž]+\.?)')


def normalize_dial_time(t) -> str:
    """Čas na „displeji“ jazykově neutrálně: '10 minut' → '10 min', '2 hodiny' → '2 h', '30 Sek.' → '30 s'."""
    s = str(t or "").strip()
    if not s or s == "—":
        return "—"
    out = []
    for num, unit in _TIME_UNIT_RE.findall(s):
        u = unit.lower().rstrip(".")
        if u.startswith(("h", "std", "godz")):
            out.append(f"{num} h")
        elif u.startswith(("mi", "m")):
            out.append(f"{num} min")
        elif u.startswith(("s", "v")):
            out.append(f"{num} s")
    return " ".join(out) if out else s


TM_SYMBOLS_EN = {
    "\ue001": " 🌾 [Dough] ", "\ue002": " 🥄 [Gentle stir] ", "\ue003": " ↺ [Reverse] ", "\ue004": " ↻ [Forward] ",
    "\ue005": " 🌾 [Knead] ", "\ue006": " 🥄 [Stir] ", "\ue007": " ⚖️ [Scale] ", "\ue008": " ♨️ [Varoma] ", "\ue009": " ⚡ [Turbo] ",
}
MCS_SYMBOLS_EN = {
    "\ue001": " 🌾 [Kneading program] ", "\ue002": " ↺ [Speed 1 + Reverse] ", "\ue003": " ↺ [Reverse] ", "\ue004": " ↻ [Forward] ",
    "\ue005": " 🌾 [Kneading program] ", "\ue006": " ↺ [Speed 1 + Reverse] ", "\ue007": " ⚖️ [Scale] ",
    "\ue008": " ♨️ [Steam program / 120 °C] ", "\ue009": " ⚡ [Turbo button] ",
}


def format_tm_icons_html(text: str, is_mcs: bool = False, ui: str | None = None) -> str:
    en = (ui or ui_lang()) == "en"
    sym_map = (MCS_SYMBOLS_EN if en else MCS_SYMBOLS_MAP) if is_mcs else (TM_SYMBOLS_EN if en else TM_SYMBOLS_MAP)
    bg_col = "#1A237E" if is_mcs else "#3E2723"
    fg_col = "#80D8FF" if is_mcs else "#FFD54F"
    for pua, badge in sym_map.items():
        text = text.replace(
            pua,
            f"<span style='background-color:{bg_col}; color:{fg_col}; padding:2px 6px; border-radius:4px; font-weight:bold;'>{badge}</span>"
        )
    return text


def extract_html_from_mhtml(mhtml_path: Path) -> str:
    try:
        import email
        raw_bytes = mhtml_path.read_bytes()
        msg = email.message_from_bytes(raw_bytes)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    except Exception:
        pass
    return mhtml_path.read_text(encoding="utf-8", errors="ignore")


def ensure_clean_html_snapshot(folder: Path) -> Path | None:
    html_file = folder / "page_snapshot.html"
    if html_file.exists():
        return html_file
    mhtml_file = folder / "page_snapshot.mhtml"
    if mhtml_file.exists():
        extracted = extract_html_from_mhtml(mhtml_file)
        if extracted:
            html_file.write_text(extracted, encoding="utf-8")
            return html_file
    return None


def extract_tm_dials(step_text: str) -> dict:
    clean = step_text.replace("℃", " °C").replace("℉", " °F")     # MCS píše teplotu jedním znakem „125℃“
    for k, v in TM_SYMBOLS_MAP.items():
        clean = clean.replace(k, v)

    time_match = re.search(r'(\d+\s*(?:hodin[auy]?|hod|h|hr|hrs|std|hours?|vteřin[ay]?|vteřin|sekund[ay]?|sek|sekund|sec|seconds?|sekunden|s|min|minuty|minut|minutes?|minuten|m))\b', clean, re.IGNORECASE)
    dial_time = time_match.group(1).strip() if time_match else "—"

    temp_match = re.search(r'(Varoma|Pára|Steam|Dampfgaren|\d{2,3}\s*°\s*[CF])', clean, re.IGNORECASE)
    dial_temp = temp_match.group(1).strip() if temp_match else "—"

    reverse = "↺ Reverse" if ("zpětný chod" in clean.lower() or "levý chod" in clean.lower() or "linkslauf" in clean.lower() or "↺" in clean or "reverse" in clean.lower()) else ""
    knead = "🌾 Knead" if ("Hnětení" in clean or "Klas" in clean or "Kneten" in clean or "🌾" in clean or "dough" in clean.lower() or "knead" in clean.lower()) else ""
    spoon = "🥄 Spoon" if ("Míchání" in clean or "Vařečka" in clean or "🥄" in clean) else ""

    speed_match = re.search(r'(?:rychlost|rychlosti|stupni|stupeň|speed|stufe|velocidad|vitesse|🔪)\s*(\d+(?:[.,]\d+)?)', clean, re.IGNORECASE)
    if speed_match:
        dial_speed = f"Speed {speed_match.group(1)}"
        if reverse: dial_speed += f" ({reverse})"
    elif knead: dial_speed = knead
    elif spoon: dial_speed = f"{spoon} {reverse}".strip()
    elif "turbo" in clean.lower(): dial_speed = "⚡ Turbo"
    else: dial_speed = reverse if reverse else "—"

    # MCS: "v programu Opékání/5 minut/při 120 °C"
    prog_m = re.search(r'(?:v\s+)?program(?:u|em)?\s+([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž]+)', clean)
    if prog_m:
        prog = prog_m.group(1)
        if prog.lower() not in ("zpětný", "turbo", "pára"):
            dial_speed = f"Program {prog}" if dial_speed == "—" else f"{dial_speed} · {prog}"

    return {"time": dial_time, "temp": dial_temp, "speed": dial_speed}


def convert_step_text_to_mcs_heuristic(text: str) -> tuple[str, dict]:
    mcs_txt = text
    notes = []

    if "\ue008" in mcs_txt or re.search(r'\bVarom[ayou]\b', mcs_txt, re.IGNORECASE):
        mcs_txt = mcs_txt.replace("\ue008", " ♨️ [Program Pára / 120 °C] ")
        mcs_txt = re.sub(r'\bVaroma\b', 'Pára (120 °C / napařovací nástavec)', mcs_txt, flags=re.IGNORECASE)
        notes.append("💡 MCS: Místo teploty Varoma zvolte program 'Pára' (Steam) nebo nastavte 120 °C.")

    if "\ue006" in mcs_txt or "\ue002" in mcs_txt:
        mcs_txt = mcs_txt.replace("\ue006", " ↺ [Rychlost 1 + Levý chod] ").replace("\ue002", " ↺ [Rychlost 1 + Levý chod] ")
        notes.append("💡 MCS: Stroj nemá pomalou 'vařečku' – použijte Rychlost 1 se zapnutým Levým chodem (↺).")

    if "\ue005" in mcs_txt or "\ue001" in mcs_txt or re.search(r'\b(hnět|těsto|knead)\b', mcs_txt, re.IGNORECASE):
        mcs_txt = mcs_txt.replace("\ue005", " 🌾 [Program Hnětení] ").replace("\ue001", " 🌾 [Program Hnětení] ")
        notes.append("💡 MCS: Použijte automatický program 'Hnětení' (Knead).")

    def round_half_speed(m):
        prefix = m.group(1)
        val_str = m.group(2).replace(",", ".")
        try:
            val = float(val_str)
            rounded = 1 if val < 1.0 else int(round(val))
            return f"{prefix} {rounded}"
        except Exception:
            return m.group(0)

    if re.search(r'(rychlost|rychlosti|stupni|stupeň|speed|stufe)\s*(\d+[.,]5)', mcs_txt, re.IGNORECASE):
        mcs_txt = re.sub(r'(rychlost|rychlosti|stupni|stupeň|speed|stufe)\s*(\d+[.,]5)', round_half_speed, mcs_txt, flags=re.IGNORECASE)
        notes.append("💡 MCS: Rychlost byla zaokrouhlena na celé číslo (MCS má stupně 1–10 bez půlek).")

    if re.search(r'120\s*°\s*C', mcs_txt, re.IGNORECASE) and re.search(r'(rest|osmah|zpen|cibul|olej|másl|mas)', mcs_txt, re.IGNORECASE):
        notes.append("💡 MCS Tip: Pro prudší orestování můžete na MCS nastavit až 130 °C nebo program 'Restování' (Roast).")

    for k, v in MCS_SYMBOLS_MAP.items():
        mcs_txt = mcs_txt.replace(k, v)

    dials = extract_tm_dials(mcs_txt)
    if "Varoma" in dials["temp"]:
        dials["temp"] = "120 °C / Pára"
    if "Spoon" in dials["speed"]:
        dials["speed"] = "Speed 1 (↺ Levý chod)"
    sp_m = re.search(r'Speed\s+(\d+)[.,]5', dials["speed"])
    if sp_m:
        v = int(sp_m.group(1))
        dials["speed"] = re.sub(r'Speed\s+\d+[.,]5', f"Speed {max(1, v)}", dials["speed"])

    if notes:
        notes_html = "<br><div style='margin-top:10px; padding:8px 12px; background-color:#1A237E; color:#80D8FF; border-left:4px solid #00E5FF; border-radius:4px; font-size:17px;'>" + "<br>".join(notes) + "</div>"
        full_html = mcs_txt + notes_html
    else:
        full_html = mcs_txt

    return full_html, dials


def convert_step_text_to_tm6_heuristic(text: str) -> tuple[str, dict]:
    tm_txt = text
    notes = []

    if re.search(r'\b(pára|páry|steam|dampfgaren|napařovací|parní)\b', tm_txt, re.IGNORECASE):
        tm_txt = re.sub(r'\b(program\s+pára|steam|dampfgaren)\b', ' \ue008 ', tm_txt, flags=re.IGNORECASE)
        notes.append("💡 TM6: Místo programu Pára nastavte teplotu 'Varoma' (♨️) a použijte Varoma mísu.")

    if re.search(r'(levý chod|linkslauf|reverse|↺)', tm_txt, re.IGNORECASE) and re.search(r'(rychlost|speed|stufe|stupeň)\s*1\b', tm_txt, re.IGNORECASE):
        notes.append("💡 TM6: Pro jemné míchání bez sekání můžete na TM6 zvolit rychlost 'Vařečka' (🥄) + Zpětný chod (↺).")

    if re.search(r'\b(hnětení|kneten|knead)\b', tm_txt, re.IGNORECASE):
        notes.append("💡 TM6: Zvolte režim hnětení těsta 'Klas' (🌾).")

    if re.search(r'(130\s*°\s*C|anbraten|roast|restování|opékání)', tm_txt, re.IGNORECASE):
        tm_txt = re.sub(r'130\s*°\s*C', '120 °C (Varoma pro prudké odpaření)', tm_txt, flags=re.IGNORECASE)
        notes.append("💡 TM6: Manuální maximum TM6 je 120 °C – nastavte 120 °C + Zpětný chod (↺).")

    dials = extract_tm_dials(tm_txt)
    if any(k in dials["temp"].lower() for k in ("pára", "steam", "dampfgaren", "130")):
        dials["temp"] = "Varoma" if "pára" in dials["temp"].lower() or "steam" in dials["temp"].lower() else "120 °C"

    if notes:
        notes_html = "<br><div style='margin-top:10px; padding:8px 12px; background-color:#1B5E20; color:#A5D6A7; border-left:4px solid #00E676; border-radius:4px; font-size:17px;'>" + "<br>".join(notes) + "</div>"
        full_html = tm_txt + notes_html
    else:
        full_html = tm_txt

    return full_html, dials


def convert_recipe_via_gemini_api(orig_data: dict, gemini_key: str, target_device: str = "mcs") -> dict | None:
    generic = (orig_data.get("source_platform") or "").lower() == "other"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
    
    clean_steps = []
    for st in orig_data.get("steps", []):
        txt = st.get("text", "")
        for k, v in TM_SYMBOLS_MAP.items():
            txt = txt.replace(k, v)
        clean_steps.append(txt)

    prompt_data = {
        "title": orig_data.get("title", ""),
        "ingredients": orig_data.get("ingredients", []),
        "steps": clean_steps
    }

    if generic:
        dev_name = "Silvercrest Monsieur Cuisine Smart (MCS z Lidlu)" if target_device == "mcs" else "Vorwerk Thermomix TM6"
        system_instruction = (
            f"Jsi špičkový expert na kuchyňský robot {dev_name}. Vstupní recept je běžný recept pro klasické vaření "
            "(z webu s recepty). Převeď ho na postup pro tento robot. Zachovej původní jazyk receptu!\n"
            "1. Kroky, které jde udělat v robotu (sekání, mixování, hnětení, šlehání, restování, vaření, dušení, pára, "
            "rozpouštění, ohřev), přepiš na postup v mixovací nádobě s nastavením čas / teplota / rychlost.\n"
            "2. Kroky mimo robot (pečení v troubě, smažení na pánvi, grilování, chlazení, servírování) ponech jako ruční "
            "a nastavení nech prázdné (\"—\").\n"
            "3. Používej jen nastavení, která robot opravdu umí"
            + (" (max. 130 °C, rychlosti 1–10, programy Hnětení, Pára, Restování; žádná Varoma ani Vařečka)." if target_device == "mcs"
               else " (max. 120 °C a Varoma, rychlosti 0,5–10, Vařečka 🥄, režim Těsto 🌾, zpětný chod ↺).") + "\n"
            "4. Nesměšuj kroky, zachovej pořadí a množství surovin.\n"
        )
        suffix_label = "[Monsieur Cuisine]" if target_device == "mcs" else "[Thermomix TM6]"
    elif target_device == "mcs":
        system_instruction = (
            "Jsi špičkový expert na kuchyňské roboty Thermomix TM6 a Silvercrest Monsieur Cuisine Smart (MCS z Lidlu). "
            "Převeď vstupní recept z Thermomixu tak, aby perfektně fungoval na Monsieur Cuisine Smart. "
            "Zachovej původní jazyk receptu! Pravidla pro Monsieur Cuisine Smart:\n"
            "1. MCS nemá teplotu 'Varoma' -> změň na 'Program Pára (Steam)' nebo '120 °C' a použij napařovací nástavec.\n"
            "2. MCS nemá rychlost 'Vařečka (Spoon)' -> změň na 'Rychlost 1 + Levý chod (↺)'.\n"
            "3. MCS nemá poloviční rychlosti (0.5, 1.5, 2.5...) -> zaokrouhli je na celá čísla (1 až 10).\n"
            "4. Režim 'Klas / Těsto' -> změň na 'Program Hnětení (Knead)'.\n"
            "5. Při restování na 120 °C doporuč 'Program Restování (Roast) / 130 °C'.\n"
        )
        suffix_label = "[Monsieur Cuisine]"
    else:
        system_instruction = (
            "Jsi špičkový expert na kuchyňské roboty Silvercrest Monsieur Cuisine Smart (MCS) a Vorwerk Thermomix TM6. "
            "Převeď vstupní recept z Monsieur Cuisine Smart tak, aby perfektně fungoval na Thermomixu TM6. "
            "Zachovej původní jazyk receptu! Pravidla pro Thermomix TM6:\n"
            "1. Program 'Pára (Steam / Dampfgaren)' -> změň na teplotu 'Varoma' a Varoma mísu.\n"
            "2. 'Rychlost 1 + Levý chod' při jemném míchání -> změň na 'Rychlost Vařečka (🥄 Spoon) + Zpětný chod (↺)'.\n"
            "3. Program 'Hnětení (Knead / Kneten)' -> změň na režim 'Klas (🌾 Dough)'.\n"
            "4. Teplotu '130 °C / Program Restování (Roast / Anbraten)' -> změň na '120 °C + Zpětný chod (↺)'.\n"
        )
        suffix_label = "[Thermomix TM6]"

    format_spec = (
        "Vrať POUZE validní JSON objekt v tomto formátu:\n"
        "{\n"
        f'  "title": "název receptu {suffix_label}",\n'
        '  "ingredients": ["surovina 1", ...],\n'
        '  "steps": [\n'
        '    {"text": "upravený text kroku", "time": "čas na budíku", "temp": "teplota na budíku", "speed": "rychlost/program na budíku"}\n'
        "  ]\n"
        "}"
    )

    payload = {
        "contents": [{
            "parts": [{"text": f"{system_instruction}\n{format_spec}\n\nVstupní recept:\n{json.dumps(prompt_data, ensure_ascii=False)}"}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        res_json = json.loads(resp.read().decode("utf-8"))
        raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw_text)

        out_steps = []
        for st in parsed.get("steps", []):
            txt = st.get("text", "")
            out_steps.append({
                "html": txt,
                "text": txt,
                "dials": {
                    "time": st.get("time") or "—",
                    "temp": st.get("temp") or "—",
                    "speed": st.get("speed") or "—"
                }
            })

        return {
            "recipe_id": orig_data.get("recipe_id"),
            "title": parsed.get("title", f"{orig_data.get('title', '')} {suffix_label}"),
            "url": orig_data.get("url"),
            "category": orig_data.get("category"),
            "portions": orig_data.get("portions"),
            "total_time": orig_data.get("total_time"),
            "source_platform": orig_data.get("source_platform", "tm6"),
            "device": target_device,
            "ingredients": parsed.get("ingredients", orig_data.get("ingredients", [])),
            "steps": out_steps
        }


# ==========================================
# OFFLINE ASISTENT: běžný recept (z jiného webu) → kroky pro TM6 / Monsieur Cuisine bez klíče Gemini
# Podle činnosti v kroku navrhne nastavení robota; co se v robotu dělat nedá (trouba, pánev…), označí jako ruční.
# ==========================================
_ASSIST_RULES = [
    # (klíč, regex činnosti cs/en/de/pl, TM6 nastavení, MCS nastavení)  – {t} = čas z textu kroku
    ("manual", r"troub|pečt|peč[eí]|zapéct|grilu|pánv|pánev|smaž|fritov|oven|bake|roast(?:ing)? in|grill|frying pan|skillet|pan-fr|deep[- ]fr|backofen|backen|pfanne|braten in|grillen|piekarnik|piec|patelni|chlad|lednic|refrigerat|chill|fridge|kühlschrank|servír|podáv|serve|servieren|ozdob|garnish",
     None, None),
    ("knead", r"hněť|hnět|uhněť|knead|kneten|zagnie", ("2 min", "—", "🌾 Těsto"), ("2 min", "—", "Program Hnětení")),
    ("whip", r"šleh|ušleh|whip|whisk(?! together)|schlagen|steif|ubij", ("—", "—", "šlehací metla, rychlost 3.5"), ("—", "—", "šlehací nástavec, rychlost 4")),
    ("grate", r"nastrouh|strouh|grate|reiben|zetrz", ("10 s", "—", "rychlost 10"), ("10 s", "—", "rychlost 10")),
    ("blend", r"rozmix|mixuj|rozmělni|pyré|purée|puree|blend|pürier|zmiks", ("1 min", "—", "rychlost 5→10"), ("1 min", "—", "rychlost 5→10")),
    ("chop", r"nasekej|posekej|sekejte|nakrájejte nadrobno|nadrobno|chop|mince|dice finely|hacken|zerkleinern|posiek|drobno", ("5 s", "—", "rychlost 5"), ("5 s", "—", "rychlost 5")),
    ("steam", r"v páře|napař|dus\w* v páře|steam|dämpf|dampfgar|na parze", ("{t}", "Varoma", "rychlost 1"), ("{t}", "Pára", "Program Pára")),
    ("melt", r"rozpusť|rozpust|melt|schmelz|roztop", ("3 min", "50 °C", "rychlost 2"), ("3 min", "50 °C", "rychlost 2")),
    ("saute", r"osmahn|orestuj|restuj|zpěň|sauté|saute|sweat|soften the onion|fry the onion|anbraten|andünsten|anschwitzen|podsmaż|zeszkl", ("{t}", "120 °C", "↺ rychlost 1"), ("{t}", "130 °C", "↺ rychlost 1")),
    ("cook", r"vař|povař|uvař|duste|dus|provař|zredukuj|boil|simmer|cook|stew|kochen|köcheln|garen|dünsten|gotuj|duś", ("{t}", "100 °C", "↺ rychlost 1"), ("{t}", "100 °C", "↺ rychlost 1")),
    ("warm", r"ohřej|zahřej|prohřej|warm|heat the milk|erwärm|erhitz|podgrz", ("3 min", "37 °C", "rychlost 2"), ("3 min", "37 °C", "rychlost 2")),
    ("mix", r"promíchej|smíchej|vmíchej|zamíchej|přidej|mix|stir|combine|add|verrühr|vermisch|unterheb|zugeben|wymieszaj|dodaj", ("20 s", "—", "↺ rychlost 3"), ("20 s", "—", "↺ rychlost 3")),
]
_ASSIST_TXT = {
    "cs": {"tm6": "Thermomix TM6", "mcs": "Monsieur Cuisine", "hint": "🤖 Návrh pro {dev}", "manual": "✋ Ruční krok (mimo robot)",
           "note": "Nastavení navrhl offline asistent podle textu kroku – zkontroluj ho. Přesnější převod udělá Gemini (⚙️ Nastavení → klíč Gemini)."},
    "en": {"tm6": "Thermomix TM6", "mcs": "Monsieur Cuisine", "hint": "🤖 Suggestion for {dev}", "manual": "✋ Manual step (outside the machine)",
           "note": "Settings were suggested by the offline assistant from the step text – please check them. Gemini gives a more precise conversion (⚙️ Settings → Gemini key)."},
}
_ASSIST_TIME_RE = re.compile(r'(\d+(?:[.,]\d+)?(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?)\s*(hodin\w*|hod\.?|h\b|hours?|hrs?|stunden?|std\.?|godz\w*|minut\w*|min\.?|minutes?|minuten?|sekund\w*|sek\.?|s\b|seconds?|secs?)', re.IGNORECASE)


_ASSIST_EN = [("Program Hnětení", "Knead program"), ("Program Pára", "Steam program"), ("Pára", "Steam"), ("🌾 Těsto", "🌾 Dough"),
               ("šlehací metla", "butterfly whisk"), ("šlehací nástavec", "whisk attachment"), ("rychlost", "speed")]


def _assist_lang(v: str, lang: str) -> str:
    if lang != "en":
        return v
    for cs_txt, en_txt in _ASSIST_EN:
        v = v.replace(cs_txt, en_txt)
    return v


def assist_step(text: str, device: str, lang: str = "cs") -> tuple[str, dict, str]:
    """Jeden krok běžného receptu → (html s návrhem, displeje robota, druh kroku).
    Když krok obsahuje dvě činnosti (např. nasekat a pak orestovat), navrhne obě po sobě."""
    t = text or ""
    low = t.lower()
    L = _ASSIST_TXT["en" if lang == "en" else "cs"]
    m_time = _ASSIST_TIME_RE.search(t)
    t_found = normalize_dial_time(m_time.group(0)) if m_time else ""
    hits = []
    for r in _ASSIST_RULES:
        m = re.search(r[1], low)
        if m:
            hits.append((m.start(), r))
    machine = sorted([h for h in hits if h[1][0] != "manual"], key=lambda h: h[0])
    manual = any(h[1][0] == "manual" for h in hits)
    # „mix/přidej“ je jen obecné – když je v kroku jiná činnost, má přednost ona
    if len(machine) > 1:
        machine = [h for h in machine if h[1][0] != "mix"] or machine
    if not machine or (manual and all(h[1][0] == "mix" for h in machine)):
        dials = {"time": t_found or "—", "temp": "—", "speed": "—"}
        box = f"<div style='margin-top:10px; padding:8px 12px; background-color:#37474F; color:#ECEFF1; border-radius:6px; font-size:17px;'>{L['manual']}</div>"
        return html_mod.escape(t) + box, dials, "manual"
    sugg, dials = [], {}
    for _, rule in machine[:2]:
        setting = rule[2] if device != "mcs" else rule[3]
        default_t = "5 min" if rule[0] == "saute" else "10 min" if rule[0] in ("cook", "steam") else "—"
        time_v = setting[0].replace("{t}", t_found or default_t)
        dials = {"time": time_v, "temp": _assist_lang(setting[1], lang), "speed": _assist_lang(setting[2], lang)}
        sugg.append(" / ".join(x for x in (dials["time"], dials["temp"], dials["speed"]) if x and x != "—"))
    box = (f"<div style='margin-top:10px; padding:8px 12px; background-color:#1B5E20; color:#C8E6C9; border-left:4px solid #00E676; border-radius:6px; font-size:17px;'>"
           f"{L['hint'].format(dev=L[device if device in ('tm6', 'mcs') else 'tm6'])}: <b>{' → '.join(sugg)}</b></div>")
    return html_mod.escape(t) + box, dials, "+".join(r[0] for _, r in machine[:2])


def assist_convert_recipe(orig_data: dict, device: str) -> dict:
    lang = orig_data.get("language") or guess_lang([orig_data.get("title", "")] + list(orig_data.get("ingredients", [])) +
                                                   [s.get("text", "") for s in orig_data.get("steps", [])])
    ui = "cs" if lang == "cs" else "en"
    steps = []
    for st in orig_data.get("steps", []):
        h, dials, kind = assist_step(st.get("text") or _plain(st.get("html")), device, ui)
        steps.append({"html": h, "text": st.get("text") or _plain(st.get("html")), "dials": dials, "assist": kind})
    if steps:
        note = _ASSIST_TXT[ui]["note"]
        steps[0]["html"] = f"<div style='margin-bottom:10px; color:#FFB74D; font-size:15px;'>ℹ️ {html_mod.escape(note)}</div>" + steps[0]["html"]
    badge = "[Monsieur Cuisine]" if device == "mcs" else "[Thermomix TM6]"
    return {
        "recipe_id": orig_data.get("recipe_id"), "title": f"{orig_data.get('title', 'Recept')} {badge}", "url": orig_data.get("url"),
        "category": orig_data.get("category"), "portions": orig_data.get("portions"), "total_time": orig_data.get("total_time"),
        "source_platform": "other", "device": device, "ingredients": orig_data.get("ingredients", []),
        "steps": steps, "fine_steps": [dict(s, parent=i) for i, s in enumerate(steps)], "converted_by": "offline-assistant",
    }


def ensure_device_recipe_file(folder: Path, target_device: str) -> Path | None:
    orig_path = folder / "recipe.json"
    if not orig_path.exists():
        return None

    orig_data = json.loads(orig_path.read_text(encoding="utf-8"))
    source_plat = orig_data.get("source_platform", "tm6").lower()

    if source_plat == target_device:
        return orig_path

    converted_filename = "recipe_mcs.json" if target_device == "mcs" else "recipe_tm6.json"
    converted_path = folder / converted_filename
    gemini_key = load_gemini_key()
    if converted_path.exists():
        try:
            made_by = json.loads(converted_path.read_text(encoding="utf-8")).get("converted_by", "")
        except Exception:
            made_by = ""
        # převod udělaný offline (bez klíče) se po zadání klíče Gemini jednou vylepší
        if not (gemini_key and made_by in ("offline", "offline-assistant")):
            return converted_path

    if gemini_key:
        try:
            ai_payload = convert_recipe_via_gemini_api(orig_data, gemini_key, target_device=target_device)
            if ai_payload and ai_payload.get("steps"):
                if source_plat == "other":
                    ai_payload["fine_steps"] = [dict(s, parent=i) for i, s in enumerate(ai_payload["steps"])]
                else:
                    ai_payload["fine_steps"] = convert_fine_steps_for_device(get_fine_steps(orig_data), target_device)
                ai_payload["converted_by"] = "gemini"
                for f in folder.glob(f"{converted_path.stem}_*.json"):      # staré překlady převodu
                    f.unlink()
                converted_path.write_text(json.dumps(ai_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                return converted_path
        except Exception as e:
            log(f"Gemini AI fallback na offline konvertor ({target_device}): {e}")
            if converted_path.exists():
                return converted_path

    if source_plat == "other":
        payload = assist_convert_recipe(orig_data, target_device)
        converted_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return converted_path

    conv_steps = []
    for st in orig_data.get("steps", []):
        raw_txt = st.get("text", "")
        if target_device == "mcs":
            c_html, c_dials = convert_step_text_to_mcs_heuristic(raw_txt)
        else:
            c_html, c_dials = convert_step_text_to_tm6_heuristic(raw_txt)
        clean_plain = BeautifulSoup(c_html, "html.parser").get_text(" ", strip=True)
        conv_steps.append({
            "html": c_html,
            "text": clean_plain,
            "dials": c_dials
        })

    badge = "[Monsieur Cuisine]" if target_device == "mcs" else "[Thermomix TM6]"
    conv_payload = {
        "recipe_id": orig_data.get("recipe_id"),
        "title": f"{orig_data.get('title', 'Recept')} {badge}",
        "url": orig_data.get("url"),
        "category": orig_data.get("category"),
        "portions": orig_data.get("portions"),
        "total_time": orig_data.get("total_time"),
        "source_platform": source_plat,
        "device": target_device,
        "ingredients": orig_data.get("ingredients", []),
        "steps": conv_steps,
        "fine_steps": convert_fine_steps_for_device(get_fine_steps(orig_data), target_device),
        "converted_by": "offline",
    }
    converted_path.write_text(json.dumps(conv_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return converted_path


def get_base_prefix_for_device(folder: Path, target_device: str) -> str:
    orig_path = folder / "recipe.json"
    source_plat = "tm6"
    if orig_path.exists():
        try:
            source_plat = json.loads(orig_path.read_text(encoding="utf-8")).get("source_platform", "tm6").lower()
        except Exception:
            pass
    if source_plat == target_device:
        return "recipe"
    return "recipe_mcs" if target_device == "mcs" else "recipe_tm6"


# ==========================================
# PŘEKLAD: DeepL (je-li klíč) → Gemini (je-li klíč) → Argos (offline) + mezipaměť vět
# ==========================================
LANG_NAMES = {"cs": "Czech", "en": "English", "de": "German", "pl": "Polish", "fr": "French", "es": "Spanish", "it": "Italian"}
GEMINI_MODEL_DEFAULT = "gemini-2.5-flash"
_TR_SEG_RE = re.compile(r'(<[^>]+>|&[a-zA-Z#0-9]+;|\n)')
_PH_SPLIT_RE = re.compile(r'(⟦\d+⟧)')


def _ph_encode(s: str) -> str:
    return re.sub(r'[\ue000-\uf8ff]', lambda m: f"⟦{ord(m.group(0)) - 0xE000}⟧", s)


def _ph_decode(s: str) -> str:
    return re.sub(r'⟦\s*(\d+)\s*⟧', lambda m: chr(0xE000 + int(m.group(1))), s)


def _piecewise(fn, strings: list[str]) -> list[str]:
    """Pro překladače, které neumí zachovat značky: přeloží jen části mezi značkami ⟦n⟧."""
    pieces = [_PH_SPLIT_RE.split(s) for s in strings]
    todo = sorted({x for parts in pieces for x in parts if x and not _PH_SPLIT_RE.fullmatch(x) and _LETTER_RE.search(x)})
    done = dict(zip(todo, fn(todo))) if todo else {}
    return ["".join(done.get(x, x) for x in parts) for parts in pieces]
_LETTER_RE = re.compile(r'[A-Za-zÀ-ž]{2,}')
_ARGOS_LOCK = threading.Lock()
_CACHE_LOCK = threading.Lock()


def has_argos() -> bool:
    try:
        return importlib.util.find_spec("argostranslate") is not None
    except Exception:
        return False


def translation_available() -> bool:
    return bool(load_gemini_key()) or has_argos() or (HAS_DEEPL and bool(load_api_key()))


def guess_lang(texts: list[str]) -> str:
    s = " ".join(t for t in texts if t)[:5000].lower()
    scores = {
        "cs": len(re.findall(r'[řěů]', s)) * 3 + len(re.findall(r'\b(vložte|přidejte|minut|nádoby|rychlost)\b', s)) * 3,
        "de": len(re.findall(r'[äöüß]', s)) * 2 + len(re.findall(r'\b(und|die|der|mit|zugeben|stufe)\b', s)) * 3,
        "pl": len(re.findall(r'[ąęłńśźż]', s)) * 3 + len(re.findall(r'\b(dodaj|się|obroty)\b', s)) * 3,
        "fr": len(re.findall(r'\b(et|les|des|ajoutez|vitesse)\b', s)) * 3,
        "en": len(re.findall(r'\b(and|the|with|add|speed)\b', s)) * 3,
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "en"


def _gemini_translate(strings: list[str], target_lang: str, key: str) -> list[str]:
    model = load_config().get("gemini_model", GEMINI_MODEL_DEFAULT)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    out: list[str] = []
    for i in range(0, len(strings), 120):
        chunk = strings[i:i + 120]
        prompt = (
            "You translate cooking-recipe text for a Thermomix / Monsieur Cuisine kitchen app. "
            f"Translate every string in the JSON array below into {LANG_NAMES.get(target_lang, target_lang)}. "
            "Keep numbers, units, temperatures, times, slashes and machine settings in the same format "
            "(e.g. '5 sek/rychlost 5' -> '5 sec/speed 5'). Keep emoji and the names Varoma, Thermomix, Monsieur Cuisine, Turbo. "
            "Markers like ⟦3⟧ are machine icons: keep every marker exactly once, at the matching place in the sentence. "
            "If a string is already in the target language, return it unchanged. "
            "Return ONLY a JSON array of strings with exactly the same number of items in the same order.\n\n"
            + json.dumps(chunk, ensure_ascii=False)
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}],
                   "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=90) as resp:
            res = json.loads(resp.read().decode("utf-8"))
        arr = json.loads(res["candidates"][0]["content"]["parts"][0]["text"])
        if not isinstance(arr, list) or len(arr) != len(chunk):
            raise ValueError("Gemini vrátil jiný počet položek, než kolik bylo posláno")
        out.extend(str(x) for x in arr)
    return out


OFFLINE_PAIRS = [("cs", "en"), ("en", "cs"), ("de", "en"), ("pl", "en")]

ARGOS_PACKAGES_DIR = BASE_DIR / "argos_packages"


def _argos_python() -> str:
    exe = sys.executable or "python"
    if exe.lower().endswith("pythonw.exe"):
        cand = exe[:-len("pythonw.exe")] + "python.exe"
        if Path(cand).exists():
            return cand
    return exe


def argos_call(req: dict, timeout: int) -> dict:
    """Spustí offline překladač v samostatném procesu (z .py i z .exe). Když spadne, vrátí se jen chyba."""
    req = dict(req, ui=ui_lang())
    if getattr(sys, "frozen", False):
        ARGOS_PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
        req["packages_dir"] = str(ARGOS_PACKAGES_DIR)     # u exe: jazykové modely vedle programu → přenosné
    flags = 0x08000000 if os.name == "nt" else 0         # CREATE_NO_WINDOW – žádné blikající okno konzole
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    with tempfile.TemporaryDirectory(prefix="cc_argos_") as td:
        inp, outp = Path(td) / "req.json", Path(td) / "res.json"
        inp.write_text(json.dumps(req, ensure_ascii=False), encoding="utf-8")
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--argos-worker", str(inp), str(outp)]
        else:
            cmd = [_argos_python(), "-X", "utf8", str(Path(__file__).resolve()), "--argos-worker", str(inp), str(outp)]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=flags, env=env, cwd=str(app_dir()))
        except subprocess.TimeoutExpired:
            raise RuntimeError(tx("offline překladač nestihl odpovědět včas"))
        except OSError as e:
            raise RuntimeError(f"{tx('Offline překladač')}: {e}")
        if not outp.exists():
            err = (proc.stderr or b"").decode("utf-8", "replace")
            log(f"Offline překladač skončil bez výsledku (kód {proc.returncode}):\n{err[-4000:]}")
            lines = [ln for ln in err.strip().splitlines() if ln.strip()]
            raise RuntimeError(tx("offline překladač spadl (kód {code})", code=proc.returncode) + (f": {lines[-1]}" if lines else ""))
        res = json.loads(outp.read_text(encoding="utf-8"))
    if not res.get("ok"):
        log(f"Offline překladač: {res.get('error')}\n{res.get('trace', '')}")
        raise RuntimeError(res.get("error") or tx("neznámá chyba"))
    return res


def offline_translator_state() -> dict:
    """Je offline překladač nainstalovaný a má jazykové modely? {"installed": bool, "missing": [(src, tgt), …]}"""
    if not has_argos():
        return {"installed": False, "missing": list(OFFLINE_PAIRS)}
    st = argos_call({"action": "status"}, 600)
    pairs = [tuple(x) for x in st.get("pairs", [])]
    return {"installed": True, "missing": [pr for pr in OFFLINE_PAIRS if pr not in pairs], "pairs": pairs}


def install_offline_translator() -> dict:
    """Doinstaluje offline překladač: při spuštění z Pythonu knihovnu argostranslate (pip), pak chybějící jazykové
    modely. V exe je knihovna přibalená, stahují se jen modely."""
    if not has_argos():
        if getattr(sys, "frozen", False):
            raise RuntimeError(tx("V této verzi programu offline překladač chybí – stáhni novou verzi aplikace."))
        flags = 0x08000000 if os.name == "nt" else 0
        proc = subprocess.run([_argos_python(), "-m", "pip", "install", "argostranslate"], capture_output=True,
                              timeout=3600, creationflags=flags)
        if proc.returncode != 0:
            log("Instalace argostranslate selhala:\n" + (proc.stderr or b"").decode("utf-8", "replace")[-4000:])
            raise RuntimeError(tx("Instalace knihovny argostranslate selhala – podrobnosti jsou v app.log."))
        importlib.invalidate_caches()
        log("Offline překladač (argostranslate) nainstalován")
    st = offline_translator_state()
    if st["missing"]:
        return argos_call({"action": "install", "pairs": [list(x) for x in st["missing"]]}, 3600)
    return {"pairs": [list(x) for x in st.get("pairs", [])]}


def _argos_translate(strings: list[str], src: str, tgt: str) -> list[str]:
    with _ARGOS_LOCK:
        return argos_call({"action": "translate", "src": src, "tgt": tgt, "texts": strings}, timeout=3600)["texts"]


def _deepl_translate(strings: list[str], tgt: str) -> list[str]:
    client = deepl.DeepLClient(load_api_key())
    res = client.translate_text(strings, target_lang="EN-US" if tgt == "en" else tgt.upper())
    return [r.text for r in (res if isinstance(res, list) else [res])]


def _friendly_error(e: Exception) -> str:
    code = getattr(e, "code", None)
    txt = str(e)
    if code == 429 or "429" in txt:
        return tx("vyčerpán limit bezplatných dotazů (HTTP 429) – zkus to za chvíli")
    if code in (400, 401, 403) or any(f"HTTP Error {c}" in txt for c in (400, 401, 403)):
        return tx("klíč byl odmítnut ({txt}) – zkontroluj ✨ Gemini klíč", txt=txt)
    if code == 404 or "HTTP Error 404" in txt:
        return tx("model nenalezen (HTTP 404) – v config.json nastav platný \"gemini_model\"")
    if "timed out" in txt.lower() or "urlopen error" in txt.lower():
        return tx("nedostupné připojení k internetu ({txt})", txt=txt)
    return txt


def translate_strings(strings: list[str], target_lang: str, source_lang: str) -> tuple[list[str], str]:
    """Pořadí: DeepL (je-li klíč) → Gemini (je-li klíč) → offline překladač. Když jeden selže, zkusí další."""
    errors = []
    if HAS_DEEPL and load_api_key():
        try:
            return _piecewise(lambda xs: _deepl_translate(xs, target_lang), strings), "deepl"
        except Exception as e:
            errors.append(f"DeepL: {e}")
    key = load_gemini_key()
    if key:
        try:
            return _gemini_translate(strings, target_lang, key), "gemini"
        except Exception as e:
            errors.append(f"Gemini: {_friendly_error(e)}")
    if has_argos():
        try:
            return _piecewise(lambda xs: _argos_translate(xs, source_lang, target_lang), strings), "argos"
        except Exception as e:
            errors.append(f"{tx('Offline překladač')}: {e}")
    raise RuntimeError("; ".join(errors) or
                       tx("Není k dispozici žádný překladač – zadej ✨ Gemini klíč, nebo nainstaluj offline překladač: py -m pip install argostranslate"))


_INLINE_TAG_RE = re.compile(r'</?(?:nobr|span|b|strong|em|i|u|mark|small|abbr|font)(?:\s[^>]*)?>', re.IGNORECASE)
_CS_WORDS = {"suroviny", "tipy", "tip", "příprava", "postup", "porce", "porcí", "celkový", "celkem", "poznámky", "poznámka",
             "obtížnost", "snadné", "střední", "náročné", "přidat", "upravte", "uvařte", "dnes", "zařízení", "příslušenství",
             "nutriční", "hodnoty", "kolekce", "hodnocení", "moje", "velikost", "počet", "recepty", "doba", "čas", "minut"}
_DE_WORDS = {"und", "mit", "die", "der", "das", "den", "zugeben", "stufe", "zutaten", "zubereitung", "geben", "dann", "auf", "ein", "eine"}


def detect_unit_lang(text: str, default: str) -> str:
    """Jazyk jedné věty. Karta z cookidoo.cz u německého receptu míchá české nadpisy (Suroviny, Tipy…)
    s německým textem receptu – každá část se tak přeloží ze správného jazyka."""
    low = text.lower()
    words = set(re.findall(r'[a-záčďéěíňóřšťúůýžäöüß]+', low))
    cs = len(re.findall(r'[ěščřžůťďň]', low)) * 2 + len(words & _CS_WORDS) * 2
    de = len(re.findall(r'[äöüß]', low)) * 2 + len(words & _DE_WORDS) * 2
    if cs > de and cs >= 2:
        return "cs"
    if de > cs and de >= 2:
        return "de"
    return default


# ==========================================
# JEDNOTKY A NASTAVENÍ STROJE PŘI PŘEKLADU
# Zkratky (TL, EL, Pck., Msp.…) se před překladem rozepíšou, aby jim překladač rozuměl, a co po překladu
# zůstane nepřeložené, se nahradí podle tabulky. Nastavení stroje (3 Sek./Stufe 5) se sjednotí.
# ==========================================
_UNIT_EXPAND = {      # zdrojová zkratka → plné slovo (jen hned za číslem)
    "TL": "Teelöffel", "EL": "Esslöffel", "Pck.": "Päckchen", "Pck": "Päckchen", "Pkg.": "Packung", "Msp.": "Messerspitze",
    "Stk.": "Stück", "Bd.": "Bund", "Prise": "Prise", "tsp": "teaspoon", "tbsp": "tablespoon", "Tbsp": "tablespoon",
}
# klíč jednotky: (regex tvarů ve všech jazycích, (en jedn., en mn.), (cs 1, cs 2–4 a zlomky, cs 5+))
UNIT_DEFS = [
    ("tsp", r"TL|Teelöffel|tsp\.?|teaspoons?|čajov\w*\s+lžič\w*|čajových\s+lžiček|lžičk\w*|lžiček|łyżeczk\w*", ("tsp", "tsp"), ("lžička", "lžičky", "lžiček")),
    ("tbsp", r"EL|Esslöffel|tbsp\.?|Tbsp\.?|tablespoons?|polévkov\w*\s+lžíc\w*|lžíce|lžic|lžící|łyżk\w*", ("tbsp", "tbsp"), ("lžíce", "lžíce", "lžic")),
    ("pinch", r"Msp\.?|Messerspitzen?|Prisen?|pinch(?:es)?|špetk\w*|špetek|szczypt\w*", ("pinch", "pinches"), ("špetka", "špetky", "špetek")),
    ("pack", r"Pck\.?|Pkg\.?|Päckchen|Packung(?:en)?|packets?|packs?|pck\.?|balíč\w*|balíček|opakowani\w*", ("pack", "packs"), ("balíček", "balíčky", "balíčků")),
    ("clove", r"Zehen?|cloves?|stroužk\w*|stroužek|ząbk\w*", ("clove", "cloves"), ("stroužek", "stroužky", "stroužků")),
    ("piece", r"Stück|Stk\.?|pcs?\.?|pieces?|ks|kus\w*|szt\.?", ("pc", "pcs"), ("ks", "ks", "ks")),
    ("slice", r"Scheiben?|slices?|plát\w*|plátek|plastr\w*", ("slice", "slices"), ("plátek", "plátky", "plátků")),
    ("bunch", r"Bund|Bd\.|bunch(?:es)?|svaz\w*|svazek|pęcz\w*", ("bunch", "bunches"), ("svazek", "svazky", "svazků")),
    ("pot", r"Becher|pots?|tubs?|kelím\w*|kelímek", ("pot", "pots"), ("kelímek", "kelímky", "kelímků")),
    ("can", r"Dosen?|cans?|tins?|plechov\w*|puszk\w*", ("can", "cans"), ("plechovka", "plechovky", "plechovek")),
    ("cube", r"Würfel|cubes?|kostk\w*|kostek", ("cube", "cubes"), ("kostka", "kostky", "kostek")),
    ("sprig", r"Zweige?|sprigs?|snít\w*|snítek", ("sprig", "sprigs"), ("snítka", "snítky", "snítek")),
    ("handful", r"Handvoll|handfuls?|hrst\w*", ("handful", "handfuls"), ("hrst", "hrsti", "hrstí")),
]
_FOREIGN_ABBR_RE = re.compile(r'(?<![\w.,/])(\d+(?:[.,]\d+)?(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?|[½⅓⅔¼¾⅛⅜⅝⅞])\s*(TL|EL|Pck\.?|pck\.?|Pkg\.?|Msp\.?|Stk\.?|Bd\.|tsp\.?|tbsp\.?|Tbsp\.?)(?=[\s,;)]|$)')


def _unit_form(key: str, qty_txt: str, lang: str) -> str:
    d = next(x for x in UNIT_DEFS if x[0] == key)
    val = _parse_amount(qty_txt.split("-")[0].split("–")[0]) or 1
    if lang == "en":
        return d[2][0] if val <= 1 else d[2][1]
    if abs(val - round(val)) > 0.01 or val < 1:
        return d[3][1]
    v = int(round(val))
    return d[3][0] if v == 1 else (d[3][1] if 2 <= v <= 4 else d[3][2])


def expand_unit_abbr(text: str) -> str:
    """Před překladem: '1 TL Zitronensaft' → '1 Teelöffel Zitronensaft' (zkratkám překladače nerozumí)."""
    def rep_(m):
        return f"{m.group(1)} {_UNIT_EXPAND.get(m.group(2), m.group(2))}"
    return _FOREIGN_ABBR_RE.sub(rep_, text)


_SPEED_WORD = {"en": "speed", "cs": "rychlost"}
_SEC_WORD = {"en": "sec", "cs": "sek"}


def fix_translated_units(text: str, lang: str) -> str:
    """Po překladu: zbylé zkratky jednotek → cílový jazyk, '450 g of' → '450 g', nastavení stroje jednotně."""
    if lang not in ("en", "cs") or not text:
        return text

    def abbr(m):
        a = m.group(2)
        key = next((k for k, rx, _, _ in UNIT_DEFS if re.fullmatch(rx, a)), None)
        return f"{m.group(1)} {_unit_form(key, m.group(1), lang)}" if key else m.group(0)

    text = _FOREIGN_ABBR_RE.sub(abbr, text)
    if lang == "en":
        text = re.sub(r'(\d\s*(?:g|kg|ml|l|dl|cl|tsp|tbsp))\s+of\s+', r'\1 ', text)
    # nastavení stroje: '100° C.' → '100°C', '/level 2' / '/stage 2' / '/úroveň 2' → '/speed 2' | '/rychlost 2'
    text = re.sub(r'(\d)\s*°\s*C\.?(?=[\s/,;)]|$)', r'\1°C', text)
    text = re.sub(r'/\s*(?:Stufe|level|stage|step|speed|rychlost[i]?|úroveň|úrovni|stupeň|stupni|fáze|Fáze|Level|Stage|Speed)\s*(\d+(?:[.,]\d+)?)',
                  lambda m: f"/{_SPEED_WORD[lang]} {m.group(1)}", text)
    text = re.sub(r'/\s*(\d+(?:[.,]\d+)?)\.\s*(?:etapa|etapě|stupeň|stupni|úroveň|úrovni|fáze|level|stage|step|speed|rychlost)\b',
                  lambda m: f"/{_SPEED_WORD[lang]} {m.group(1)}", text)
    text = re.sub(r'/\s*(?:etapa|etapě|Etapa)\s*(\d+(?:[.,]\d+)?)', lambda m: f"/{_SPEED_WORD[lang]} {m.group(1)}", text)
    text = re.sub(r'(\d+)\s*(?:Sek\.|sek\.|seconds?|secs?|sekund[ay]?|vteřin[ay]?)(?=\s*/)', lambda m: f"{m.group(1)} {_SEC_WORD[lang]}", text)
    text = re.sub(r'(\d+)\s*(?:Min\.|minutes?|mins?|minut[ay]?)(?=\s*/)', r'\1 min', text)
    return text


class RecipeTranslator:
    """Překládá po větách; každá věta se v receptu přeloží jen jednou (sdíleno mezi TM6/MCS verzí,
    jemnými kroky i kartou receptu) a výsledek se pamatuje v translation_cache.json ve složce receptu."""

    def __init__(self, folder: Path, target_lang: str, source_lang: str):
        self.path = folder / "translation_cache.json"
        self.target_lang = target_lang
        self.source_lang = source_lang
        self.same_lang = (source_lang == target_lang)
        try:
            self.all = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        except Exception:
            self.all = {}
        self.cache = self.all.setdefault(target_lang, {})
        self.meta = self.all.setdefault("_meta", {}).setdefault(target_lang, {})
        self.pending: set[str] = set()
        self.engines: set[str] = set()
        self.sent_chars = 0

    @staticmethod
    def _units(text: str):
        text = _INLINE_TAG_RE.sub("", text or "")      # formátovací značky by rozsekaly větu na nesmyslné kousky
        text = expand_unit_abbr(text)
        for part in _TR_SEG_RE.split(text):
            if not part:
                continue
            if _TR_SEG_RE.fullmatch(part) or not _LETTER_RE.search(part):
                yield False, part
                continue
            core = part.strip()
            lead, trail = part[:len(part) - len(part.lstrip())], part[len(part.rstrip()):]
            if lead:
                yield False, lead
            for k, sent in enumerate(split_sentences(core)):
                if k:
                    yield False, " "
                yield True, _clean_ws(sent)
            if trail:
                yield False, trail

    def collect(self, text: str):
        if self.same_lang:
            return
        for tr, u in self._units(text):
            if tr and u not in self.cache:
                self.pending.add(u)

    def flush(self):
        if not self.pending:
            return
        groups: dict[str, list[str]] = {}
        for u in sorted(self.pending):
            groups.setdefault(detect_unit_lang(u, self.source_lang), []).append(u)
        pairs = []
        for lang, todo in groups.items():
            if lang == self.target_lang:                 # už je v cílovém jazyce (např. české nadpisy na kartě)
                pairs.extend((x, _ph_encode(x)) for x in todo)
                continue
            self.sent_chars += sum(len(x) for x in todo)
            translated, engine = translate_strings([_ph_encode(x) for x in todo], self.target_lang, lang)
            self.engines.add(engine)
            self.meta["engines"] = sorted(set(self.meta.get("engines", [])) | {engine})
            pairs.extend(zip(todo, translated))
        self.meta["at"] = time.strftime("%d. %m. %Y %H:%M")
        for orig, tr_txt in pairs:
            dec = fix_translated_units(_ph_decode(tr_txt), self.target_lang)
            missing = [c for c in dict.fromkeys(re.findall(r'[\ue000-\uf8ff]', orig)) if c not in dec]
            if missing:                                   # překladač značku ztratil → ikonu aspoň připojíme
                dec = dec.rstrip() + " " + "".join(missing)
            self.cache[orig] = dec
        self.pending.clear()
        with _CACHE_LOCK:
            self.path.write_text(json.dumps(self.all, ensure_ascii=False, indent=1), encoding="utf-8")

    def apply(self, text: str) -> str:
        if self.same_lang:
            return text
        return "".join(fix_translated_units(self.cache[u], self.target_lang) if tr and u in self.cache else u
                       for tr, u in self._units(text))


_CARD_SKIP = ("script, style, noscript, svg, header, nav, footer, core-header, core-transclusion, "
              "#onetrust-consent-sdk, [id*='cookie'], [class*='cookie'], [class*='Cookie'], [id*='onetrust']")
_CARD_INLINE = {"nobr", "b", "strong", "span", "a", "em", "i", "br", "sup", "sub", "small", "u", "mark", "abbr"}


def _block_text(el) -> str:
    from bs4 import NavigableString, Comment
    parts = []
    for d in el.descendants:
        if isinstance(d, Comment):
            continue
        if isinstance(d, NavigableString):
            parts.append(str(d))
        elif getattr(d, "name", None) == "br":
            parts.append("\n")
    return "".join(parts)


def _card_targets(soup):
    """Vrátí (bloky, samostatné texty) k překladu – jen text, žádné HTML, bez hlavičky/patičky/cookie lišty."""
    from bs4 import NavigableString, Comment
    body = soup.body or soup
    skip = {id(e) for e in soup.select(_CARD_SKIP)}

    def skipped(node):
        return any(id(pn) in skip for pn in node.parents) or id(node) in skip

    blocks = []
    for el in body.find_all(True):
        if el.name in _CARD_INLINE or skipped(el):
            continue
        if any(c.name not in _CARD_INLINE for c in el.find_all(True)):
            continue
        if _LETTER_RE.search(_block_text(el)):
            blocks.append(el)
    in_block = {id(b) for b in blocks}
    loose = []
    for s in body.find_all(string=True):
        if isinstance(s, Comment) or not _LETTER_RE.search(str(s)) or skipped(s):
            continue
        if any(id(pn) in in_block for pn in s.parents):
            continue
        loose.append(s)
    return blocks, loose


def translate_card_html(html: str, tr: "RecipeTranslator") -> str:
    soup = BeautifulSoup(html, "html.parser")
    blocks, loose = _card_targets(soup)
    for b in blocks:
        tr.collect(_block_text(b))
    for s in loose:
        tr.collect(str(s))
    tr.flush()
    for s in loose:
        s.replace_with(tr.apply(str(s)))
    for b in blocks:
        new_txt = tr.apply(_block_text(b))
        b.clear()
        for i, line in enumerate(new_txt.split("\n")):
            if i:
                b.append(soup.new_tag("br"))
            b.append(line)
    return str(soup)


def generate_translated_files(base_recipe_path: Path, target_lang: str, api_key: str | None = None, target_device: str = "tm6") -> tuple[Path | None, Path | None]:
    if target_lang not in ("en", "cs") or not translation_available():
        return None, None

    orig_json_path = ensure_device_recipe_file(base_recipe_path, target_device)
    if not orig_json_path or not orig_json_path.exists():
        return None, None

    prefix = get_base_prefix_for_device(base_recipe_path, target_device)
    target_json = base_recipe_path / f"{prefix}_{target_lang}.json"
    target_html = base_recipe_path / f"page_snapshot_{target_lang}.html"
    orig_html_path = ensure_clean_html_snapshot(base_recipe_path)

    recipe_data = json.loads(orig_json_path.read_text(encoding="utf-8"))
    steps = recipe_data.get("steps", [])
    fine = get_fine_steps(recipe_data)
    src_lang = recipe_data.get("language") or guess_lang(
        [recipe_data.get("title", "")] + list(recipe_data.get("ingredients", [])) + [_plain(s.get("html")) or s.get("text", "") for s in steps])

    tr = RecipeTranslator(base_recipe_path, target_lang, src_lang)
    need_json = not target_json.exists()
    need_html = orig_html_path is not None and orig_html_path.exists() and not target_html.exists()

    tips_src = [t for t in (recipe_data.get("tips") or recipe_extras(base_recipe_path).get("tips") or []) if t]
    if need_json:
        tr.collect(recipe_data.get("title", ""))
        for t in tips_src:
            tr.collect(t)
        for x in recipe_data.get("ingredients", []):
            tr.collect(x)
        for st in steps + fine:
            tr.collect(st.get("html") or st.get("text", ""))
        tr.flush()                                     # jedno dávkové volání pro celý recept

        def tr_step(st):
            h = tr.apply(st.get("html") or st.get("text", ""))
            plain = BeautifulSoup(h, "html.parser").get_text(" ", strip=True)
            new = dict(st)
            new.update({"html": h, "text": plain, "dials": st.get("dials") or extract_tm_dials(plain)})
            return new

        payload = dict(recipe_data)
        payload.update({
            "title": tr.apply(recipe_data.get("title", "Recipe")),
            "device": target_device,
            "language": target_lang,
            "source_language": src_lang,
            "ingredients": [tr.apply(x) for x in recipe_data.get("ingredients", [])],
            "steps": [tr_step(s) for s in steps],
            "fine_steps": [tr_step(s) for s in fine],
            "tips": [tr.apply(t) for t in tips_src],
            "translated_by": sorted(tr.meta.get("engines", [])) or sorted(tr.engines),
            "translated_at": tr.meta.get("at", ""),
            "translation_same_language": tr.same_lang,
        })
        target_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        set_title_translation(base_recipe_path, target_lang, payload.get("title", ""))

    if need_html:
        html_content = orig_html_path.read_text(encoding="utf-8", errors="ignore")
        try:
            if tr.same_lang:
                out_html = html_content
            else:
                out_html = translate_card_html(html_content, tr)
                info = describe_translation({"translated_by": tr.meta.get("engines", []), "translated_at": tr.meta.get("at", "")})
                banner = ("<div id='cc-tr-banner' style='background:#311B92;color:#fff;padding:8px 14px;"
                          "font:14px Segoe UI,sans-serif;'>" + info + "</div>")
                if re.search(r'<body[^>]*>', out_html):
                    out_html = re.sub(r'(<body[^>]*>)', lambda m: m.group(1) + banner, out_html, count=1)
                else:
                    out_html = banner + out_html
            target_html.write_text(out_html, encoding="utf-8")
        except Exception as e:
            log(f"Překlad karty selhal: {e}")
            raise

    log(f"Překlad {base_recipe_path.name} -> {target_lang}: odesláno {tr.sent_chars} znaků, překladač: {sorted(tr.engines) or '-'}")
    return (target_json if target_json.exists() else None), (target_html if target_html.exists() else None)


ENGINE_INFO = {"gemini": ("Gemini", True), "deepl": ("DeepL", True), "argos": ("Argos Translate", False)}


def describe_translation(data: dict, ui_lang: str = "cs") -> str:
    en = ui_lang == "en"
    if data.get("translation_same_language"):
        return "🌐 Recipe is already in this language – not translated." if en else "🌐 Recept už je v tomto jazyce – nepřekládá se."
    engines = [e for e in (data.get("translated_by") or []) if e in ENGINE_INFO]
    if engines:
        names = ", ".join(f"{ENGINE_INFO[e][0]} ({'online' if ENGINE_INFO[e][1] else 'offline'})" for e in engines)
        if all(ENGINE_INFO[e][1] for e in engines):
            kind = "purely online translation" if en else "čistě online překlad"
        elif not any(ENGINE_INFO[e][1] for e in engines):
            kind = "offline translation on this computer" if en else "offline překlad v tomto počítači"
        else:
            kind = "online + offline" if en else "kombinace online a offline"
    else:
        names, kind = ("unknown engine" if en else "neznámý překladač"), ""
    when = data.get("translated_at") or ""
    head = "🌐 Machine translation" if en else "🌐 Strojový překlad"
    return " · ".join(x for x in (head, names, kind, when) if x)


def clear_translation(folder: Path, lang: str):
    """Smaže uložený překlad (všechny verze receptu, kartu i zapamatované věty) → 'Přeložit znovu'."""
    for f in list(folder.glob(f"recipe*_{lang}.json")) + [folder / f"page_snapshot_{lang}.html"]:
        try:
            f.unlink()
        except FileNotFoundError:
            pass
    cache_path = folder / "translation_cache.json"
    if cache_path.exists():
        with _CACHE_LOCK:
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                data.pop(lang, None)
                data.get("_meta", {}).pop(lang, None)
                cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            except Exception:
                cache_path.unlink()


_TR_JOBS: dict = {}
_TR_JOBS_LOCK = threading.Lock()
_FOLDER_LOCKS: dict = {}


def _job_key(folder: Path, lang: str, device: str):
    return (str(Path(folder).resolve()), lang, device)


def translation_job_status(folder: Path, lang: str, device: str) -> dict:
    with _TR_JOBS_LOCK:
        return dict(_TR_JOBS.get(_job_key(folder, lang, device), {"state": "none"}))


def start_translation_job(folder: Path, lang: str, device: str, force: bool = False) -> dict:
    """Spustí překlad na pozadí (nikdy neblokuje okno ani mobil). Opakované volání vrací stav běžící úlohy."""
    key = _job_key(folder, lang, device)
    with _TR_JOBS_LOCK:
        job = _TR_JOBS.get(key)
        if job and job["state"] == "running":
            return dict(job)
        if job and job["state"] == "failed" and not force and time.time() - job.get("ended", 0) < 30:
            return dict(job)
        job = {"state": "running", "started": time.time(), "error": ""}
        _TR_JOBS[key] = job
        lock = _FOLDER_LOCKS.setdefault(key[0], threading.Lock())
    threading.Thread(target=_run_translation_job, args=(key, Path(folder), lang, device, lock), daemon=True).start()
    return dict(job)


def _run_translation_job(key, folder: Path, lang: str, device: str, lock):
    state, err = "failed", ""
    try:
        with lock:                       # jeden recept se nepřekládá dvakrát současně (sdílí mezipaměť vět)
            res_j, _ = generate_translated_files(folder, lang, target_device=device)
        if res_j and res_j.exists():
            state = "done"
        else:
            err = tx("Překladač nevrátil výsledek (zkontroluj Gemini klíč nebo instalaci argostranslate).")
    except Exception as e:
        err = str(e) or e.__class__.__name__
        log("Překlad selhal:\n" + traceback.format_exc())
    with _TR_JOBS_LOCK:
        _TR_JOBS[key].update(state=state, error=err, ended=time.time())


class TranslationWorker(QThread):
    finished_ok = pyqtSignal(str, Path, Path)
    failed_err = pyqtSignal(str)

    def __init__(self, folder_path: Path, target_lang: str, api_key: str, target_device: str = "tm6"):
        super().__init__()
        self.folder_path = folder_path
        self.target_lang = target_lang
        self.api_key = api_key
        self.target_device = target_device

    def run(self):
        try:
            res_json, res_html = generate_translated_files(self.folder_path, self.target_lang, self.api_key, target_device=self.target_device)
            if res_json and res_json.exists():
                self.finished_ok.emit(self.target_lang, res_json, res_html or Path())
            else:
                self.failed_err.emit("Překlad se nepodařilo dokončit (Gemini / offline překladač).")
        except Exception as e:
            self.failed_err.emit(str(e))


class DeviceConversionWorker(QThread):
    finished_ok = pyqtSignal(Path)
    failed_err = pyqtSignal(str)

    def __init__(self, folder_path: Path, target_device: str):
        super().__init__()
        self.folder_path = folder_path
        self.target_device = target_device

    def run(self):
        try:
            res_path = ensure_device_recipe_file(self.folder_path, self.target_device)
            if res_path and res_path.exists():
                self.finished_ok.emit(res_path)
            else:
                self.failed_err.emit("Nelze vytvořit konverzi receptu.")
        except Exception as e:
            self.failed_err.emit(str(e))


# ==========================================
# ROBUSTNÍ EXTRAKCE RECEPTU (v10)
# ==========================================
STEP_HEADERS = {
    "příprava", "postup", "postup přípravy", "způsob přípravy", "jak na to", "kroky", "pokyn", "pokyny", "návod",
    "zubereitung", "zubereitungsschritte", "preparation", "instructions", "method", "directions",
    "przygotowanie", "sposób przygotowania", "préparation", "preparación", "preparazione",
}
ING_HEADERS = {
    "ingredience", "suroviny", "potřebujeme", "zutaten", "ingredients", "składniki",
    "ingrédients", "ingredientes", "ingredienti",
}
STOP_HEADERS = {
    "hodnocení", "recenze", "komentáře", "tipy", "tip", "nutriční hodnoty", "výživové hodnoty",
    "podobné recepty", "mohlo by vás zajímat", "sdílet", "tiráž", "podmínky", "kontakt",
    "nährwerte", "bewertungen", "kommentare", "ähnliche rezepte", "tipps",
    "nutrition", "nutritional values", "reviews", "comments", "similar recipes", "tips",
    "wartości odżywcze", "komentarze", "podobne przepisy", "porady",
    "přidat do nákupního seznamu", "vhodné kolekce", "suroviny", "nutriční hodnoty",
    "registrujte se, abyste mohli komentovat recepty!", "přihlásit / registrace",
    # konec článku na zpravodajských webech s recepty (Prima FRESH, blogy…)
    "přečtěte si také", "související články", "související recepty", "další recepty", "vstoupit do diskuze",
    "diskuze", "nejlepší recepty e-mailem", "lesen sie auch", "das könnte sie auch interessieren",
    "related recipes", "you may also like", "read more", "more recipes", "related articles",
}
JUNK_WORDS = ("cookie", "tiráž", "copyright", "newsletter", "přihlásit", "ohodnotit",
              "do košíku", "monsieur cuisine official", "©")
STEP_MARKER_RE = re.compile(r'^(?:krok|step|schritt|etap|krok nr\.?)?\s*(\d{1,2})\s*[.):]?$', re.IGNORECASE)
NUMBERED_LINE_RE = re.compile(r'^(?:krok|step|schritt)?\s*\d{1,2}\s*[.)]\s+', re.IGNORECASE)
SETTING_RE = re.compile(
    r'(\d+\s*(?:s|sek|sec|min|h|hod)\b\.?|°\s*C|rychlost|stupe|speed|stufe|levý chod|linkslauf|varoma|turbo|pára)',
    re.IGNORECASE)


def _norm_line(line: str) -> str:
    low = line.lower().strip()
    low = re.sub(r'^[^\w]+', '', low)          # emoji / odrážky na začátku
    return low.rstrip(":").strip()


def _is_header(line: str, headers: set) -> bool:
    return _norm_line(line) in headers


def _is_junk(line: str) -> bool:
    low = line.lower()
    return any(j in low for j in JUNK_WORDS)


def _ld_is_type(obj: dict, name: str) -> bool:
    t = obj.get("@type")
    return t == name or (isinstance(t, list) and name in t)


def find_recipe_ld(soup) -> dict:
    """Najde Recipe v JSON-LD – zvládne @graph, seznamy, vnoření i @type jako seznam."""
    for sc in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.IGNORECASE)}):
        raw = sc.string or sc.get_text() or ""
        try:
            data = json.loads(raw)
        except Exception:
            continue
        stack = [data]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                if _ld_is_type(o, "Recipe"):
                    return o
                stack.extend(v for v in o.values() if isinstance(v, (dict, list)))
            elif isinstance(o, list):
                stack.extend(o)
    return {}


def _clean_ws(s: str) -> str:
    return " ".join(s.split())


def _split_instruction_string(s: str) -> list[str]:
    # nové řádky jen tam, kde opravdu končí odstavec (<br>, <p>, <li>…); <nobr>, <b> apod. větu nedělí
    s = re.sub(r'(?i)<\s*(br|/p|/li|/div|/h\d)\s*/?>', "\n", str(s or ""))
    txt = BeautifulSoup(s, "html.parser").get_text("")
    parts = [p for p in re.split(r'\n+', txt) if p.strip()]
    if len(parts) == 1:
        # "1. … 2. … 3. …" v jednom řetězci
        numbered = re.split(r'(?:^|\s)(?=\d{1,2}[.)]\s)', parts[0])
        if len([n for n in numbered if n.strip()]) > 1:
            parts = numbered
    out = []
    for p in parts:
        c = _clean_ws(NUMBERED_LINE_RE.sub("", p.strip()))
        if len(c) > 3:
            out.append(c)
    return out


def ld_instructions_to_texts(inst) -> list[str]:
    out: list[str] = []
    if not inst:
        return out
    if isinstance(inst, str):
        return _split_instruction_string(inst)
    if isinstance(inst, list):
        for x in inst:
            out.extend(ld_instructions_to_texts(x))
        return out
    if isinstance(inst, dict):
        if inst.get("itemListElement"):
            return ld_instructions_to_texts(inst["itemListElement"])
        txt = inst.get("text") or inst.get("description") or inst.get("name") or ""
        return _split_instruction_string(str(txt))
    return out


def _leaf_texts(soup, selector: str) -> list[str]:
    """Vrátí texty jen 'listových' shod – rodič, který obsahuje jinou shodu, se přeskočí (žádné duplicity)."""
    els = soup.select(selector)
    ids = {id(e) for e in els}
    out = []
    for e in els:
        if any(id(d) in ids for d in e.find_all(True)):
            continue
        if e.find_parent(["header", "nav", "footer"]):
            continue
        t = _clean_ws(e.get_text(" ", strip=True))
        t = NUMBERED_LINE_RE.sub("", t).strip()
        if t and not _is_junk(t) and t not in out:
            out.append(t)
    return out


def _blocks_after_header(lines: list[str], headers: set) -> list[list[str]]:
    blocks = []
    for i, ln in enumerate(lines):
        if not _is_header(ln, headers):
            continue
        block = []
        for nxt in lines[i + 1:]:
            if (_is_header(nxt, STEP_HEADERS) or _is_header(nxt, ING_HEADERS) or _is_header(nxt, STOP_HEADERS)
                    or _is_tips_title(nxt)):
                break
            block.append(nxt)
        blocks.append(block)
    return blocks


def steps_from_visible_text(visible_text: str) -> list[str]:
    lines = [ln.strip() for ln in visible_text.splitlines() if ln.strip()]
    blocks = _blocks_after_header(lines, STEP_HEADERS)
    if not blocks:
        return []
    # Nadpis "Příprava" se často objevuje i u doby přípravy nahoře → vezmeme blok s nejvíc větami.
    best = max(blocks, key=lambda b: sum(1 for x in b if len(x) > 25))
    marker_mode = any(STEP_MARKER_RE.match(x) for x in best)
    steps: list[str] = []
    cur: list[str] = []

    def flush():
        if cur:
            t = _clean_ws(" ".join(cur))
            if len(t) > 8:
                steps.append(t)
            cur.clear()

    for ln in best:
        if _is_junk(ln):
            continue
        if STEP_MARKER_RE.match(ln):
            flush()
            continue
        if NUMBERED_LINE_RE.match(ln):
            flush()
            cur.append(NUMBERED_LINE_RE.sub("", ln))
            continue
        if marker_mode and (cur or len(ln) > 3):
            cur.append(ln)
        elif cur and len(ln) <= 40 and SETTING_RE.search(ln):
            cur.append(ln)          # řádek s nastavením (5 min / 100 °C / rychlost 1) patří k předchozímu kroku
        elif len(ln) > 15:
            flush()
            cur.append(ln)
    flush()
    return steps


def ingredients_from_visible_text(visible_text: str) -> list[str]:
    lines = [ln.strip() for ln in visible_text.splitlines() if ln.strip()]
    blocks = _blocks_after_header(lines, ING_HEADERS)
    if not blocks:
        return []
    best = max(blocks, key=len)
    out = []
    for ln in best:
        low = ln.lower()
        if 1 < len(ln) < 120 and not _is_junk(ln) and not any(x in low for x in ("porce", "porcí", "košík", "přidat do")):
            out.append(ln)
    return out


TIPS_HEADERS = ("tipy", "tip", "tipps", "tips", "porady", "wskazówki", "astuces", "consejos", "consigli")


def extract_mcs_dom(soup) -> tuple[list[str], list[str]]:
    """Monsieur-cuisine.com: kroky v .recipe-detail-live-note (odstavce oddělené prázdným řádkem),
    suroviny v .ingredient-group-view (název a množství v oddělených buňkách)."""
    steps: list[str] = []
    note = soup.select_one(".recipe-detail-live-note .text-pre-line") or soup.select_one(".recipe-detail-live-note")
    if note:
        raw = note.get_text().replace("\r", "")
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', raw) if p.strip()]
        tips: list[str] = []
        in_tips = False
        for para in paragraphs:
            first, _, rest = para.partition("\n")
            if _norm_line(first) in TIPS_HEADERS:
                in_tips = True
                para = rest.strip()
                if not para:
                    continue
            txt = _clean_ws(para)
            if not txt:
                continue
            (tips if in_tips else steps).append(txt)
        if tips:
            steps.append("💡 Tipy: " + " ".join(tips))
    if not steps:
        # Komunitní recepty: jen vedené kroky jako karty (číslo, název, text / nastavení stroje).
        # Stránka má stejný seznam dvakrát → stačí první.
        lst = soup.select_one(".create-recipe-step-list")
        for it in (lst.select(".step-list-item") if lst else []):
            name_el, body_el = it.select_one(".step-name"), it.select_one(".step-drag-details")
            name = _clean_ws(name_el.get_text(" ", strip=True)) if name_el else ""
            body = _clean_ws(body_el.get_text(" ", strip=True)) if body_el else ""
            body = re.sub(r'(\d)\s*℃', r'\1 °C', body)
            # nastavení na kartě: „… 35sek. 1 Vlevo“ = rychlost 1 a levý chod, „8 Vpravo“ = rychlost 8
            body = re.sub(r'\b(\d{1,2}(?:[.,]5)?)\s+Vlevo\b', r'rychlost \1 / levý chod', body)
            body = re.sub(r'\b(\d{1,2}(?:[.,]5)?)\s+Vpravo\b', r'rychlost \1', body)
            txt = f"{name}: {body}" if name and body else (body or name)
            if txt:
                steps.append(txt)

    ingredients: list[str] = []
    view = soup.select_one(".ingredient-group-view")
    if view:
        for group in view.select(".v-list-group"):
            hdr = group.select_one(".v-list-group__header .v-subheader")
            items = group.select(".v-list-group__items .v-list-item")
            if not items:
                continue
            hdr_txt = _clean_ws(hdr.get_text(" ", strip=True)) if hdr else ""
            if hdr_txt and hdr_txt.lower() not in ("obecné suroviny", "allgemeine zutaten", "general ingredients"):
                ingredients.append(f"▸ {hdr_txt}")
            for it in items:
                name_el = it.select_one(".v-list-item__content .v-list-item__title")
                amt_el = it.select_one(".v-list-item__icon .v-list-item__title")
                name = _clean_ws(name_el.get_text(" ", strip=True)) if name_el else ""
                amt = _clean_ws(amt_el.get_text(" ", strip=True)) if amt_el else ""
                if name:
                    ingredients.append(f"{amt} {name}".strip())
    return steps, ingredients


_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
# „PRIMA TIP:“, „Tip:“, „Tipp!“ na začátku odstavce
_TIP_LINE_RE = re.compile(r'^\W*(?:\w+\s+){0,2}(?:tip|tipy|tipp|tipps|tips|rada)\s*[:!–-]', re.IGNORECASE)


def _is_tips_title(text: str) -> bool:
    """Nadpis části s tipy: „Tipy“, „Tipy na obměny receptu“, „Užitečné tipy“…"""
    k = search_key(_norm_line(text))
    if len(k) > 60:
        return False
    return k in {search_key(x) for x in TIPS_TITLES} or bool(re.match(r'^(?:\w+\s+)?(?:tip|tipy|tipp|tipps|tips)\b', k))


def recipe_section_from_dom(soup) -> dict:
    """Postup receptu podle struktury stránky: nadpis „Postup přípravy“ a za ním vše až po další nadpis
    stejné úrovně (dál bývají reklamy, související články, diskuze). Tipy (blockquote, „TIP:“, podnadpis
    „Tipy…“) jdou zvlášť. Vrací {"steps": [...], "tips": [...], "nodes": [prvky stránky s postupem]}."""
    best = {"steps": [], "tips": [], "nodes": []}
    for h in soup.find_all(_HEADING_TAGS):
        if h.find_parent(["header", "nav", "footer", "aside"]):
            continue
        if not _is_header(_clean_ws(h.get_text(" ", strip=True)), STEP_HEADERS):
            continue
        level = int(h.name[1])
        anchor = h
        # nadpis bývá zabalený (<div class="title"><h2>Postup</h2></div><ol>…) → o úroveň výš
        for _ in range(2):
            if anchor.find_next_sibling() is None and anchor.parent is not None and anchor.parent.name not in ("body", "html"):
                anchor = anchor.parent
        steps, tips, nodes = [], [], [anchor]
        in_tips = False
        for sib in anchor.find_next_siblings():
            name = sib.name
            text = _clean_ws(sib.get_text(" ", strip=True))
            sub_h = sib if name in _HEADING_TAGS else None
            if sub_h is None and len(text) <= 60:
                # nadpis zabalený v <div>/<p><strong>
                inner = sib.find(_HEADING_TAGS)
                if inner is not None and _clean_ws(inner.get_text(" ", strip=True)) == text:
                    sub_h = inner
            if sub_h is not None:
                if int(sub_h.name[1]) <= level:
                    break
                if _is_tips_title(text):
                    in_tips = True
                    nodes.append(sib)
                    continue
                if _is_header(text, STOP_HEADERS) or _is_header(text, ING_HEADERS):
                    break
                in_tips = False                    # podnadpis skupiny kroků („Těsto“, „Omáčka“)
                nodes.append(sib)
                continue
            if not text:
                continue
            if _is_header(text, STOP_HEADERS):
                break
            if _is_junk(text) or sib.find_parent(["aside"]) is not None or name in ("script", "style", "form", "iframe", "aside"):
                continue
            lis = [li for li in sib.find_all("li") if not li.find("li")] if name in ("ol", "ul") else []
            if not lis and name not in ("p", "blockquote") and sib.find(["ol", "ul"]):
                lis = [li for li in sib.find_all("li") if not li.find("li")]
            if lis:
                items = [_clean_ws(li.get_text(" ", strip=True)) for li in lis]
            elif name not in ("p", "blockquote") and sib.find_all("p"):
                items = [_clean_ws(p.get_text(" ", strip=True)) for p in sib.find_all("p")]
            else:
                items = [text]
            items = [NUMBERED_LINE_RE.sub("", t).strip() for t in items]
            items = [t for t in items if len(t) > 8 and not _is_junk(t)]
            if not items:
                continue
            nodes.append(sib)
            for t in items:
                if in_tips or name == "blockquote" or _TIP_LINE_RE.match(t):
                    tips.append(t)
                else:
                    steps.append(t)
        if sum(1 for s in steps if len(s) > 25) > sum(1 for s in best["steps"] if len(s) > 25):
            best = {"steps": steps, "tips": tips, "nodes": nodes}
    return best


def _locate_blocks(soup, items: list[str], exclude: list | None = None) -> list:
    """Najde prvky stránky, ve kterých jsou položky (suroviny, kroky). Skupiny surovin bývají v oddělených
    boxech, proto se hledá postupně: vždy blok s nejvíc položkami na co nejméně textu. Položka se hledá podle
    svých nejdelších slov (celých) – na webu bývá jinak seřazená („PHO vývar 1 litr“). Prvky z `exclude`
    (např. postup) a vše kolem nich se přeskočí. Málo nalezeného → []."""
    keys = []
    for it in items:
        it = str(it or "")
        if not it or it.startswith("▸"):
            continue
        words = sorted({w for w in re.findall(r'\w{4,}', it.lower()) if not w.isdigit()}, key=len, reverse=True)[:3]
        if words:
            keys.append(tuple(words))
    if not keys or soup.body is None:
        return []
    # blok nesmí být o moc delší než samotné položky – jinak je to obal celé stránky
    limit = 3 * sum(len(_clean_ws(str(x))) for x in items) + 600
    excl = {id(e) for e in (exclude or []) if e is not None}
    cands = []
    for el in soup.body.find_all(["ol", "ul", "div", "section", "table"]):
        if el.find_parent(["header", "nav", "footer", "aside"]):
            continue
        if any(id(p) in excl for p in el.parents) or id(el) in excl or any(id(d) in excl for d in el.find_all(True)):
            continue
        txt = _clean_ws(el.get_text(" ")).lower()
        if len(txt) <= limit:
            cands.append((el, txt, set(re.findall(r'\w+', txt))))
    remaining, blocks = list(keys), []
    while remaining and len(blocks) < 8:
        need = 1 if len(remaining) == 1 else 2
        best, best_cov, best_score = None, [], 0.0
        for el, txt, words in cands:
            cov = [ws for ws in remaining if all(w in words for w in ws)]
            if len(cov) >= need:
                score = len(cov) / (len(txt) + 200)       # hustota: hodně položek na málo textu
                if score > best_score:
                    best, best_cov, best_score = el, cov, score
        if best is None:
            break
        # přibrat obal s nadpisem skupiny („Masové knedlíčky“), pokud nepřidá skoro nic jiného
        while best.parent is not None and best.parent.name not in ("body", "html", "main", "article") \
                and len(_clean_ws(best.parent.get_text(" "))) <= len(_clean_ws(best.get_text(" "))) + 80:
            best = best.parent
        blocks.append(best)
        remaining = [ws for ws in remaining if ws not in best_cov]
    if len(keys) - len(remaining) < max(1, len(keys) * 0.6):
        return []
    return blocks


def _ld_people(v) -> list[str]:
    out = []
    for x in (v if isinstance(v, list) else [v]):
        n = x.get("name") if isinstance(x, dict) else x
        n = _clean_ws(str(n or ""))
        if n and n not in out:
            out.append(n)
    return out


def trim_recipe_page(soup, recipe_ld: dict, ingredients: list[str], steps: list[str]) -> bool:
    """Oholí uloženou stránku (kartu receptu) na recept: titulek, hlavní obrázek, autor, popis, suroviny,
    postup a tipy. Menu, reklamy, související články, diskuze a patička zmizí. <head> (styly) zůstává.
    Když recept na stránce nenajde, nechá ji celou a vrátí False."""
    if soup.body is None:
        return False
    keep = []
    sec = recipe_section_from_dom(soup)
    step_nodes = sec["nodes"] if sec["steps"] else []
    if not step_nodes:
        step_nodes = _locate_blocks(soup, steps)
    ing_els = _locate_blocks(soup, ingredients, exclude=step_nodes)
    if not step_nodes and not ing_els:
        return False
    keep += step_nodes
    for el in ing_els + step_nodes[:1]:
        keep.append(el)
        prev = el.find_previous_sibling()          # nadpis „Suroviny“ / „Postup“ těsně před blokem
        if prev is not None and prev.name in _HEADING_TAGS:
            keep.append(prev)
    h1 = soup.body.find("h1")
    if h1 is not None:
        keep.append(h1)
    # hlavní obrázek receptu (podle JSON-LD / og:image)
    img_url = recipe_ld.get("image") if isinstance(recipe_ld, dict) else ""
    if isinstance(img_url, list):
        img_url = img_url[0] if img_url else ""
    if isinstance(img_url, dict):
        img_url = img_url.get("url") or img_url.get("contentUrl") or ""
    if not img_url:
        og = soup.find("meta", attrs={"property": "og:image"})
        img_url = og.get("content", "") if og else ""
    stem = urllib.parse.urlparse(str(img_url or "")).path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if len(stem) >= 6:
        for img in soup.body.find_all(["img", "source"]):
            refs = " ".join(str(img.get(a) or "") for a in ("src", "srcset", "data-src", "data-srcset", "data-lazy-src", "data-original"))
            if stem in refs:
                fig = img.find_parent(["figure", "picture"]) or img
                keep.append(fig.find_parent("figure") or fig)
                break
    # autor a popis receptu
    ld = recipe_ld if isinstance(recipe_ld, dict) else {}
    for name in _ld_people(ld.get("author")):
        hits = [s.parent for s in soup.body.find_all(string=lambda x: x and _clean_ws(x) == name)]
        keep += [p for p in hits if p is not None and p.name not in ("script", "style")][:3]
    desc = _clean_ws(_plain(ld.get("description") or ""))[:60]
    if len(desc) >= 30:
        for el in soup.body.find_all(["p", "div"]):
            if _clean_ws(el.get_text(" ", strip=True)).startswith(desc) and len(el.get_text()) < len(ld.get("description") or "") * 1.5 + 50:
                keep.append(el)
                break
    # tipy pod vlastním nadpisem mimo postup („Tipy“ + následující blok)
    for h in soup.body.find_all(_HEADING_TAGS):
        if _is_tips_title(h.get_text(" ", strip=True)) and not h.find_parent(["header", "nav", "footer", "aside"]):
            keep.append(h)
            nxt = h.find_next_sibling()
            if nxt is not None:
                keep.append(nxt)
    keep += soup.body.find_all("script", attrs={"type": re.compile(r"ld\+json", re.IGNORECASE)})

    keep_ids = {id(k) for k in keep if k is not None}
    path_ids = set()
    for k in keep:
        if k is None:
            continue
        for p in k.parents:
            path_ids.add(id(p))

    def prune(el):
        for child in list(el.children):
            if not hasattr(child, "name") or child.name is None:
                continue                            # text mezi prvky necháme
            if id(child) in keep_ids:
                continue
            if id(child) in path_ids:
                prune(child)
            else:
                child.decompose()

    prune(soup.body)
    return True


def extract_recipe_content(soup, visible_text: str, fallback_title: str) -> dict:
    recipe_ld = find_recipe_ld(soup)

    title_el = soup.select_one("h1.recipe-card__title, h1")
    title = title_el.get_text(strip=True) if title_el else ""
    title = title or recipe_ld.get("name") or fallback_title

    mcs_steps, mcs_ings = extract_mcs_dom(soup)

    # --- suroviny
    ingredients, ing_src = [], ""
    if mcs_ings:
        ingredients, ing_src = mcs_ings, "mcs-dom"
    if not ingredients and recipe_ld.get("recipeIngredient"):
        ingredients = [_clean_ws(BeautifulSoup(str(x), "html.parser").get_text(" ", strip=True))
                       for x in recipe_ld["recipeIngredient"] if str(x).strip()]
        ing_src = "ld+json"
    if not ingredients:
        ingredients = _leaf_texts(soup,
            ".recipe--ingredients li, .recipe__ingredients tr, .field--name-field-recipe-ingredients .field__item, "
            "[class*='ingredient'] li, [class*='Ingredient'] li, [class*='ingredient-item']")
        ingredients = [i for i in ingredients if len(i) < 120]
        ing_src = "css" if ingredients else ""
    if not ingredients and visible_text:
        ingredients = ingredients_from_visible_text(visible_text)
        ing_src = "text" if ingredients else "none"

    # --- kroky
    step_texts, step_src = ld_instructions_to_texts(recipe_ld.get("recipeInstructions")), "ld+json"
    if not step_texts and mcs_steps:
        step_texts, step_src = mcs_steps, "mcs-dom"
    if not step_texts:
        css_steps = _leaf_texts(soup,
            ".recipe--instructions li, .recipe--instructions p, .field--name-field-recipe-instructions .field__item, "
            "[class*='preparation'] li, [class*='Preparation'] li, [class*='instruction'] li, [class*='Instruction'] li, "
            "[class*='recipe-step'], [class*='RecipeStep'], [class*='step-text'], [class*='stepText']")
        css_steps = [s for s in css_steps if len(s) > 12]
        if len(css_steps) >= 2:
            step_texts, step_src = css_steps, "css"
    tips: list[str] = []
    if not step_texts:
        sec = recipe_section_from_dom(soup)
        if sec["steps"]:
            step_texts, tips, step_src = sec["steps"], sec["tips"], "dom"
    if not step_texts and visible_text:
        step_texts, step_src = steps_from_visible_text(visible_text), "text"
    if not step_texts:
        step_src = "none"

    steps = [{"html": t, "text": t, "dials": extract_tm_dials(t)} for t in step_texts]
    return {"recipe_ld": recipe_ld, "title": title, "ingredients": ingredients, "steps": steps, "tips": tips,
            "ingredients_source": ing_src, "steps_source": step_src}




# ==========================================
# JEMNÉ KROKY (guided) – MCS API, Cookidoo JSON, fallback z běžných kroků
# ==========================================
MCS_MODE_LABELS = {
    "customized": "Manuální vaření", "roasting": "Opékání", "steaming": "Vaření v páře",
    "kneading": "Hnětení", "turbo": "Turbo", "scale": "Vážení", "sous_vide": "Sous-vide",
    "slow_cooking": "Pomalé vaření", "fermentation": "Fermentace",
}
QTY_RE = re.compile(r'\d+(?:[.,]\d+)?\s*(?:g|gramů|gramy|gram|kg|ml|l)\b', re.IGNORECASE)
WEIGH_RE = re.compile(r'\b(navaž|odvaž|vlož|přidej|nasyp|wieg|geben|weigh|add|dodaj|wsyp)\w*', re.IGNORECASE)
POUR_RE = re.compile(r'\b(nalij|přilij|füll|gieß|pour|wlej)\w*', re.IGNORECASE)
INTO_BOWL_RE = re.compile(r'(do mixovací nádob|in den mixtopf|into (?:the )?mixing bowl|do naczynia miksującego)', re.IGNORECASE)


def _is_weigh_sentence(s: str) -> bool:
    return bool(WEIGH_RE.search(s) or (POUR_RE.search(s) and INTO_BOWL_RE.search(s)))
CONJ_RE = re.compile(r'\s(?:a|i|und|and|et|y|oraz)\s')
ABBREV = {"cca", "vel", "např", "tzv", "resp", "tj", "ca", "bzw", "evtl", "approx", "etc", "min", "sek", "max", "č", "obr"}
PUA_RE = re.compile(r'[\ue000-\uf8ff]')
INLINE_SET_RE = re.compile(
    r'(\d+\s*(?:sek|sec|s|min|vteřin\w*|minut\w*|Sek\.?|Min\.?)\s*/|(?:rychlost|na stupni|stufe|speed)\s*\d|\bturbo\b|\bTěsto\s*[\ue000-\uf8ff])',
    re.IGNORECASE)


def _qty_outside_parens(s: str) -> bool:
    return bool(QTY_RE.search(re.sub(r'\([^)]*\)', ' ', s)))


GROUP_LABEL_HTML = "<div style='color:#FFB300; font-size:15px; font-weight:bold; margin-bottom:6px;'>📌 {}</div>"


def _fmt_num(v) -> str:
    f = float(v)
    return str(int(f)) if f.is_integer() else f"{f:g}"


def _fmt_secs(sec) -> str:
    sec = int(round(float(sec)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} h")
    if m:
        parts.append(f"{m} min")
    if s or not parts:
        parts.append(f"{s} s")
    return " ".join(parts)


def split_sentences(text: str) -> list[str]:
    """Dělí na věty jen mimo závorky a ne za zkratkami (cca., vel. M, …)."""
    out, buf, depth = [], [], 0
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        buf.append(ch)
        if ch in "([":
            depth += 1
        elif ch in ")]" and depth > 0:
            depth -= 1
        elif ch in ".!?" and depth == 0 and i + 2 < n and text[i + 1] == " ":
            nxt = text[i + 2]
            word = re.findall(r'(\S+)$', "".join(buf[:-1]))
            last = (word[0] if word else "").lower().strip("(")
            if (nxt.isupper() or nxt in "„\"") and last not in ABBREV and not re.fullmatch(r'[a-zA-Z]', last):
                out.append("".join(buf).strip())
                buf = []
        i += 1
    if "".join(buf).strip():
        out.append("".join(buf).strip())
    return out


def _setting_dials(setting: str) -> dict:
    d = extract_tm_dials(setting)
    clean = PUA_RE.sub(" ", setting)
    tm = re.match(r'^\s*((?:\d+\s*(?:h|hod|min|sek|sec|s|Min\.?|Sek\.?)\s*)+)', clean, re.IGNORECASE)
    if tm:
        d["time"] = _clean_ws(tm.group(1))
    return d


def _weigh_note(sentence: str, ingredients: list[str]) -> str:
    """K větě typu 'navažte sezam, sůl a vodu' doplní množství ze seznamu surovin skupiny."""
    if _qty_outside_parens(sentence) or not ingredients:
        return ""
    low = sentence.lower()
    hits = []
    for ing in ingredients:
        if not re.match(r'^\d', ing):
            continue
        words = [w for w in re.findall(r'[a-záčďéěíňóřšťúůýžäöüß]{4,}', ing.lower())
                 if w not in ("gramů", "gramy", "čajová", "čajové", "lžička", "lžíce", "polévková")]
        if words and any(w[:min(4, len(w) - 1)] in low for w in words[:2]):
            hits.append(ing)
    return f" (⚖️ {', '.join(hits)})" if hits else ""


def _fine_from_formatted(raw: str, parent: int, group: str, ingredients: list[str], structured: bool) -> list[dict]:
    raw = raw or ""
    settings = re.findall(r'<nobr>(.*?)</nobr>', raw, flags=re.S)       # Cookidoo: nastavení stroje = malé <nobr>
    idx = [0]

    def tok(m):
        t = f" §§{idx[0]}§§ "
        idx[0] += 1
        return t
    marked = re.sub(r'<nobr>.*?</nobr>', tok, raw, flags=re.S)
    plain = BeautifulSoup(marked, "html.parser").get_text()
    plain = re.sub(r'\s+([.,;:!?)])', r'\1', _clean_ws(plain))
    if plain.startswith("💡"):
        sents = [plain]
    else:
        sents = split_sentences(plain)

    def render(s: str) -> str:
        return _clean_ws(re.sub(r'§§(\d+)§§', lambda m: _clean_ws(BeautifulSoup(settings[int(m.group(1))], "html.parser").get_text()), s))

    out: list[dict] = []
    for s in sents:
        toks = re.findall(r'§§(\d+)§§', s)
        inline = None if (toks or structured) else INLINE_SET_RE.search(s)
        if toks or inline:
            first_tok = s.find("§§") if toks else inline.start()
            prefix = s[:first_tok]
            conj = list(CONJ_RE.finditer(prefix))
            if conj and (_qty_outside_parens(prefix[:conj[-1].start()]) or _is_weigh_sentence(prefix[:conj[-1].start()])):
                c = conj[-1]
                part1 = prefix[:c.start()].rstrip(" ,") + "."
                part2 = s[c.end():].strip()
                part2 = part2[:1].upper() + part2[1:]
                out.append({"text": render(part1) + _weigh_note(part1, ingredients),
                            "dials": {"time": "—", "temp": "—", "speed": "⚖️ Vážení"}, "mode": "scale"})
                s = part2
            if toks:
                setting_txt = _clean_ws(BeautifulSoup(settings[int(toks[0])], "html.parser").get_text())
                dials = _setting_dials(setting_txt)
            else:
                dials = extract_tm_dials(s)
            out.append({"text": render(s), "dials": dials, "mode": "machine"})
        elif _is_weigh_sentence(s) and (_qty_outside_parens(s) or _weigh_note(s, ingredients)) and len(s) < 220:
            out.append({"text": render(s) + _weigh_note(s, ingredients),
                        "dials": {"time": "—", "temp": "—", "speed": "⚖️ Vážení"}, "mode": "scale"})
        else:
            txt = render(s)
            if structured:
                tm = extract_tm_dials(txt)
                dials = {"time": tm["time"], "temp": "—", "speed": "—"}
            else:
                dials = extract_tm_dials(txt)
            prev = out[-1] if out else None
            if prev and prev["mode"] == "manual" and (len(txt) < 45 or len(prev["text"]) < 45) and len(prev["text"]) + len(txt) < 260:
                prev["text"] = prev["text"] + " " + txt
                if prev["dials"]["time"] == "—":
                    prev["dials"]["time"] = dials["time"]
                continue
            out.append({"text": txt, "dials": dials, "mode": "manual"})

    for i, st in enumerate(out):
        st["parent"] = parent
        st["html"] = st["text"]
        if i == 0 and group:
            st["group"] = group
            st["html"] = GROUP_LABEL_HTML.format(group) + st["text"]
    return out


def fine_steps_from_cookidoo_json(js: dict) -> list[dict]:
    groups = js.get("recipeStepGroups") or []
    if not groups:
        return []
    ing_by_group: dict[str, list[str]] = {}
    all_ings: list[str] = []
    for g in js.get("recipeIngredientGroups") or []:
        lst = []
        for ri in g.get("recipeIngredients") or []:
            q = (ri.get("quantity") or {}).get("value")
            qtxt = f"{_fmt_num(q)} " if q not in (None, 0, "0") else ""
            lst.append(_clean_ws(f"{qtxt}{ri.get('unitNotation') or ''} {ri.get('ingredientNotation') or ''}"))
        ing_by_group[_clean_ws(g.get("title") or "")] = lst
        all_ings.extend(lst)
    out, parent = [], 0
    for g in groups:
        title = _clean_ws(g.get("title") or "")
        ings = ing_by_group.get(title) or all_ings
        for k, st in enumerate(g.get("recipeSteps") or []):
            out.extend(_fine_from_formatted(st.get("formattedText") or "", parent, title if k == 0 else "", ings, True))
            parent += 1
    return out


def cookidoo_json_to_basic(js: dict) -> tuple[list[str], list[dict]]:
    ings = []
    for g in js.get("recipeIngredientGroups") or []:
        if g.get("title"):
            ings.append(f"▸ {_clean_ws(g['title'])}")
        for ri in g.get("recipeIngredients") or []:
            q = (ri.get("quantity") or {}).get("value")
            qtxt = f"{_fmt_num(q)} " if q not in (None, 0, "0") else ""
            prep = f", {ri['preparation']}" if ri.get("preparation") else ""
            ings.append(_clean_ws(f"{qtxt}{ri.get('unitNotation') or ''} {ri.get('ingredientNotation') or ''}{prep}"))
    steps = []
    for g in js.get("recipeStepGroups") or []:
        for st in g.get("recipeSteps") or []:
            txt = re.sub(r'\s+([.,;:!?)])', r'\1', _clean_ws(BeautifulSoup(st.get("formattedText") or "", "html.parser").get_text()))
            if txt:
                steps.append({"html": txt, "text": txt, "dials": extract_tm_dials(txt)})
    return ings, steps


def _mcs_serving(api: dict) -> dict | None:
    rec = (api.get("data") or {}).get("recipe") or {}
    sizes = rec.get("servingSizes") or []
    if not sizes:
        return None
    return next((s for s in sizes if s.get("id") == rec.get("defaultServingSizeId")), sizes[0])


def fine_steps_from_mcs_api(api: dict) -> list[dict]:
    ss = _mcs_serving(api)
    if not ss:
        return []
    out = []
    for st in sorted(ss.get("steps") or [], key=lambda s: (s.get("order") or 0)):
        desc = _clean_ws(st.get("description") or "")
        name = _clean_ws(st.get("name") or "")
        ds = st.get("deviceSetting") or None
        dials = {"time": "—", "temp": "—", "speed": "—"}
        mode = "manual"
        setting_txt = ""
        if ds:
            mode = (ds.get("mode") or "customized").lower()
            sets = ds.get("settings") or [{}]
            rev = bool(ds.get("reverse"))
            parts = []
            for s in sets:
                seg = []
                if s.get("time"):
                    seg.append(_fmt_secs(s["time"]))
                if s.get("temperature"):
                    seg.append(f"{_fmt_num(s['temperature'])} °C")
                if rev and mode != "scale":
                    seg.append("↺ Levý chod")
                spd = s.get("speedFloat") if s.get("speedFloat") is not None else s.get("speed")
                if spd is not None and mode != "scale":
                    seg.append(f"rychlost {_fmt_num(spd)}")
                if s.get("weight") and mode == "scale":
                    seg.append(f"⚖️ {_fmt_num(s['weight'])} g")
                if seg:
                    parts.append(" / ".join(seg))
            setting_txt = " → ".join(parts)
            f0 = sets[0] if sets else {}
            spd0 = f0.get("speedFloat") if f0.get("speedFloat") is not None else f0.get("speed")
            if f0.get("time"):
                dials["time"] = _fmt_secs(f0["time"])
            if f0.get("temperature"):
                dials["temp"] = f"{_fmt_num(f0['temperature'])} °C"
            if mode == "scale":
                dials["speed"] = f"⚖️ {_fmt_num(f0['weight'])} g" if f0.get("weight") else "⚖️ Vážení"
            elif mode == "turbo" or ds.get("turbo"):
                dials["speed"] = "⚡ Turbo"
            elif mode == "customized":
                if spd0 is not None:
                    dials["speed"] = f"Speed {_fmt_num(spd0)}" + (" (↺ Reverse)" if rev else "")
                elif rev:
                    dials["speed"] = "↺ Reverse"
            else:
                label = (name if not desc else "") or MCS_MODE_LABELS.get(mode, mode.capitalize())
                dials["speed"] = f"Program {label}" + (f" · Speed {_fmt_num(spd0)}" if spd0 is not None else "")
        if desc:
            text = desc
            if ds and mode not in ("scale", "turbo") and setting_txt:
                text += f" ({setting_txt})"
        else:
            label = name or MCS_MODE_LABELS.get(mode, "Krok")
            text = f"⚙️ {label}: {setting_txt}" if setting_txt else f"⚙️ {label}"
        out.append({"html": text, "text": text, "dials": dials, "mode": mode, "parent": None})
    return out


def mcs_api_to_basic(api: dict) -> list[dict]:
    ss = _mcs_serving(api)
    if not ss:
        return []
    steps = []
    for para in re.split(r'\n\s*\n', (ss.get("instruction") or "").replace("\r", "")):
        txt = _clean_ws(para)
        if txt:
            steps.append({"html": txt, "text": txt, "dials": extract_tm_dials(txt)})
    return steps


def fine_steps_from_steps(steps: list[dict]) -> list[dict]:
    """Fallback pro starší uložené recepty: rozdělí běžné kroky na věty/úkony."""
    out = []
    for i, st in enumerate(steps or []):
        raw = st.get("html") or st.get("text") or ""
        out.extend(_fine_from_formatted(raw, i, "", [], "<nobr>" in raw))
    return out


def get_fine_steps(data: dict) -> list[dict]:
    return (data or {}).get("fine_steps") or fine_steps_from_steps((data or {}).get("steps", []))


def map_step_index(old_steps: list[dict], new_steps: list[dict], old_idx: int, to_fine: bool) -> int:
    if not new_steps:
        return 0
    if to_fine:
        for i, st in enumerate(new_steps):
            if st.get("parent") == old_idx:
                return i
    elif 0 <= old_idx < len(old_steps) and old_steps[old_idx].get("parent") is not None:
        return min(old_steps[old_idx]["parent"], len(new_steps) - 1)
    if not old_steps:
        return 0
    return min(len(new_steps) - 1, round(old_idx * len(new_steps) / max(1, len(old_steps))))


def convert_fine_steps_for_device(fine: list[dict], target_device: str) -> list[dict]:
    out = []
    for st in fine:
        raw = st.get("html") or st.get("text", "")
        if target_device == "mcs":
            c_html, c_dials = convert_step_text_to_mcs_heuristic(raw)
        else:
            c_html, c_dials = convert_step_text_to_tm6_heuristic(raw)
        orig = st.get("dials") or {}
        o_time, o_temp, o_speed = orig.get("time", "—"), orig.get("temp", "—"), orig.get("speed", "—")
        if o_time != "—":
            c_dials["time"] = o_time
        h_temp = c_dials.get("temp", "—")
        if o_temp != "—" and not any(x in h_temp for x in ("Varoma", "Pára", "120 °C / Pára")):
            c_dials["temp"] = o_temp
        if o_speed.startswith("⚖️"):
            c_dials["speed"] = o_speed
        elif c_dials.get("speed", "—") == "—" and o_speed != "—":
            c_dials["speed"] = o_speed
        if target_device == "tm6" and re.search(r'Opékání|Roast|Anbraten|Restování', o_speed, re.IGNORECASE):
            c_dials["speed"] = "Speed 1 (↺ Reverse)"
            c_dials["temp"] = "120 °C"
        new = dict(st)
        new.update({"html": c_html, "text": BeautifulSoup(c_html, "html.parser").get_text(" ", strip=True), "dials": c_dials})
        out.append(new)
    return out


_ING_STOP = {
    # jednotky a obecná slova (cs, en, de)
    "gramu", "gramy", "gram", "gramm", "kg", "ml", "litr", "litru", "cajova", "cajove", "cajovych", "lzicka", "lzicky", "lzicek", "lzice",
    "lzic", "polevkova", "polevkove", "spetka", "spetky", "kostka", "kostky", "kostek", "kulicky", "kulicek", "listky", "listku", "strouzek",
    "strouzky", "platky", "platku", "platek", "snitky", "snitek", "stonku", "stonky", "hrst", "balicek", "balicku", "baliceku", "kus", "kusy",
    "kusu", "hrnek", "hrnku", "plechovka", "svazek", "kelimek", "nebo", "podle", "chuti", "dle", "plus", "navic", "extra", "napul", "kousky",
    "kousku", "kostky", "kosticky", "ctvrtky", "nakrajene", "nakrajeny", "nakrajenych", "rozkrojenych", "nastrouhany", "nastrouhane",
    "cerstve", "cerstveho", "cerstvy", "cerstvych", "mlete", "mleteho", "mlety", "susene", "suseneho", "suseny", "hladke", "polohrube",
    "hrube", "jemne", "studene", "teple", "vlazne", "rozpustene", "mekke", "cele", "celeho", "male", "maleho", "velke", "velkeho",
    "na", "do", "pro", "bez", "jen", "pripadne", "volitelne", "vychlazene", "pokojove", "teploty", "zhruba", "asi", "cca",
    "tsp", "tbsp", "teaspoon", "teaspoons", "tablespoon", "tablespoons", "cup", "cups", "pinch", "clove", "cloves", "slice", "slices",
    "fresh", "ground", "dried", "large", "small", "whole", "chopped", "sliced", "diced", "plus", "extra", "for", "optional", "and", "or",
    "the", "into", "pieces", "piece", "halved", "taste", "frisch", "frische", "frischer", "gemahlen", "getrocknet", "gross", "klein",
    "stuck", "stucke", "prise", "teeloffel", "essloffel", "packchen", "nach", "belieben", "und", "oder", "zum", "fur", "etwas", "geschnitten",
}
_ING_ALIAS = {"soli": ("sul", "soli", "osol"), "sul": ("sul", "soli", "osol"), "salz": ("salz", "salzen"),
              "vody": ("vod",), "voda": ("vod",), "cibule": ("cibul",), "mrkve": ("mrkev", "mrkv"), "mrkev": ("mrkev", "mrkv"),
              "vejce": ("vejc", "vajic", "zloutk", "bilk"), "eier": ("ei", "eier"), "ei": ("ei", "eier"), "eggs": ("egg",), "egg": ("egg",)}
_ING_HEADER_RE = re.compile(r'^\s*[▸►•▶]')
_QTY_UNIT_LEAD_RE = re.compile(r'^\s*(?:' + _QTY + r'(?:\s*[-–]\s*' + _QTY + r')?\s*(?:' + "|".join(d[1] for d in UNIT_DEFS) +
                               r'|kg|dkg|g|gramů|gramy|gram|ml|dl|cl|l)?\.?\s+)', re.IGNORECASE)
_AMOUNT_RE = re.compile(r'(\d+(?:[.,]\d+)?)\s*(kg|dkg|g|gramů|gramy|gram|ml|dl|l)\b', re.IGNORECASE)


def _ing_keywords(line: str) -> tuple[list[str], str]:
    """Klíčová slova suroviny (kmeny bez diakritiky) a hlavní slovo. Popis za čárkou/závorkou se ignoruje."""
    s = re.sub(r'\([^)]*\)', ' ', line)
    s = _QTY_UNIT_LEAD_RE.sub('', s, count=1)
    s = re.sub(r'\s\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l)?\s*$', '', s)          # "brown onion 50 g"
    head = re.split(r',|;|\s(?:na|nebo|plus|dle|podle|bez|pro|for|or|plus|zum|oder|nach)\s', s, maxsplit=1)[0]
    words = [w for w in re.findall(r'[a-z]{3,}', search_key(head)) if w not in _ING_STOP]
    stems = []
    for w in words:
        if w in _ING_ALIAS:
            stems.extend(_ING_ALIAS[w])
        else:
            stems.append(w if len(w) <= 4 else w[:max(4, min(6, len(w) - 2))])
    main = words[-1] if words else ""
    return list(dict.fromkeys(stems)), main


def _amount_g(text: str) -> tuple[float, str] | None:
    m = _AMOUNT_RE.search(text or "")
    if not m:
        return None
    unit = m.group(2).lower()
    unit = "g" if unit.startswith("gram") else unit
    return float(m.group(1).replace(",", ".")), unit


def match_recipe_ingredients(step_texts: list[str], all_ingredients: list[str]) -> list[list[dict]]:
    """Pro všechny kroky najednou: které suroviny se v kroku použijí.
    - hledá se jen podle názvu suroviny (ne podle jednotek, přídavných jmen a popisu „nakrájené na plátky“),
    - když je stejná surovina v receptu víckrát (knedlík / omáčka), vybere se ta správná podle skupiny,
      množství v kroku, nebo podle pořadí (první ještě nepoužitá),
    - když krok použije jen část (20 g ze 40 g másla), přidá se poznámka s množstvím pro tento krok."""
    groups, g = [], 0
    infos = []
    for i, ing in enumerate(all_ingredients):
        is_header = bool(_ING_HEADER_RE.match(ing)) or (ing.isupper() and not re.search(r'\d', ing))
        if is_header:
            g += 1
        groups.append(g)
        kws, main = ([], "") if is_header else _ing_keywords(ing)
        infos.append({"header": is_header, "kws": kws, "main": main, "amount": _amount_g(ing)})
    used = set()
    result = []
    for st in step_texts:
        low = search_key(st)
        cand = {}
        for i, inf in enumerate(infos):
            if inf["header"] or not inf["kws"]:
                continue
            hits = tuple(sorted(k for k in inf["kws"] if re.search(r'(?<![a-z])' + re.escape(k), low)))
            if hits:
                cand[i] = hits
        # suroviny, které krok „trefí“ stejnými slovy (2× máslo, 2× cukr, kuřecí prsa / kuřecí bujón) → vybrat jednu
        by_main = {}
        for i in cand:
            by_main.setdefault(cand[i], []).append(i)
        uniq_groups = [groups[i] for i in cand if len(by_main[cand[i]]) == 1]
        step_group = max(set(uniq_groups), key=uniq_groups.count) if uniq_groups else None
        chosen = set()
        notes = {}
        for main, idxs in by_main.items():
            pick = idxs
            if len(idxs) > 1:
                stem = cand[idxs[0]][0]
                m = re.search(r'(\d+(?:[.,]\d+)?)\s*(kg|g|gramu|gramy|gram|ml|l)\b[^.,;]{0,25}?' + re.escape(stem), low)
                amt = float(m.group(1).replace(",", ".")) if m else None
                exact = [i for i in idxs if amt is not None and infos[i]["amount"] and abs(infos[i]["amount"][0] - amt) < 0.01]
                multi_group = len({groups[i] for i in idxs}) > 1
                in_group = [i for i in idxs if multi_group and step_group is not None and groups[i] == step_group]
                unused = [i for i in idxs if i not in used]
                pick = exact[:1] or in_group[:1] or unused[:1] or idxs[-1:]
            for i in pick:
                chosen.add(i)
                ia = infos[i]["amount"]
                m = re.search(r'(\d+(?:[.,]\d+)?)\s*(kg|g|gramu|gramy|gram|ml|l)\b[^.,;]{0,25}?(?:' + "|".join(re.escape(k) for k in cand[i]) + ')', low)
                if ia and m:
                    amt = float(m.group(1).replace(",", "."))
                    unit = "g" if m.group(2).startswith("gram") else m.group(2)
                    if unit == ia[1] and amt < ia[0] - 0.01:
                        notes[i] = f"{_format_num(amt)} {unit}"
        used |= chosen
        result.append([{"text": ing, "active": i in chosen, "part": notes.get(i, "")} for i, ing in enumerate(all_ingredients)])
    return result


def match_step_ingredients(step_text: str, all_ingredients: list[str]) -> list[dict]:
    return match_recipe_ingredients([step_text], all_ingredients)[0]


class RecipeTreeWidget(QTreeWidget):
    recipe_moved = pyqtSignal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(18)
        self.setAnimated(True)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        # Ctrl/Shift + klik označí víc receptů (export zálohy); kliknutí na kategorii vezme všechny její recepty
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def dropEvent(self, event):
        dragged_item = self.currentItem()
        if not dragged_item or dragged_item.data(0, Qt.ItemDataRole.UserRole) is None:
            event.ignore()
            return
        target_item = self.itemAt(event.position().toPoint())
        if not target_item:
            event.ignore()
            return

        new_cat = target_item.data(0, Qt.ItemDataRole.UserRole + 3)
        r_id = dragged_item.data(0, Qt.ItemDataRole.UserRole + 1)
        folder_path = dragged_item.data(0, Qt.ItemDataRole.UserRole)

        if new_cat and r_id:
            event.accept()
            self.recipe_moved.emit(r_id, folder_path, new_cat)
        else:
            event.ignore()


LAN_WEB_APP_HTML = """<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>LocalChef Studio</title>
<style>
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    background: #121212; color: #F5F5F5;
    font-family: 'Segoe UI', system-ui, sans-serif;
    height: 100%; height: 100dvh;
    overflow: hidden;
  }
  body { display: flex; flex-direction: row; }

  #sidebar {
    width: 340px; background: #1E1E1E; border-right: 1px solid #333;
    display: flex; flex-direction: column; padding: 12px; z-index: 100;
  }
  #sidebar.hidden { display: none !important; }

  #main {
    flex: 1; display: flex; flex-direction: column;
    height: 100%; height: 100dvh; overflow: hidden;
    position: relative;
  }

  input, select {
    width: 100%; padding: 9px; background: #2A2A2A;
    border: 1px solid #444; color: white; border-radius: 6px;
    margin-bottom: 8px; font-size: 14px;
  }
  .cat-header { font-weight: bold; color: #FFB300; padding: 8px 4px; border-bottom: 1px solid #2A2A2A; }
  .rec-item { padding: 10px 12px; cursor: pointer; border-radius: 6px; margin: 3px 0; font-size: 15px; background: #252526; }
  .rec-item:hover, .rec-item.active { background: #009A3E; color: white; font-weight: bold; }

  .top-bar {
    background: #1E1E1E; padding: 8px 10px; border-bottom: 1px solid #333;
    display: flex; flex-direction: column; gap: 6px; flex-shrink: 0;
  }
  .top-row-title { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
  .btn-group { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
  .btn {
    background: #2D2D30; color: #E0E0E0; border: 1px solid #48484D;
    padding: 6px 10px; border-radius: 6px; cursor: pointer;
    font-weight: bold; font-size: 13px;
  }
  .btn:active { transform: scale(0.96); }
  .btn.active { background: #0277BD; border-color: #29B6F6; color: white; }
  .btn.mode-active { background: #009A3E; border-color: #69F0AE; color: white; }
  .btn.mcs-active { background: #1565C0; border-color: #00E5FF; color: white; }

  #tm-view {
    display: flex; flex-direction: column; flex: 1;
    overflow: hidden; position: relative;
  }
  .tr-banner {
    margin: 6px 10px 0 10px; padding: 7px 10px; border-radius: 6px; font-size: 13px;
    background: #311B92; color: #EDE7F6; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  }
  .tr-banner.wait { background: #E65100; color: #fff; }
  .tr-banner.err { background: #B71C1C; color: #fff; }
  .dials {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 6px; padding: 8px 10px 4px 10px; flex-shrink: 0;
  }
  .dial {
    background: #1E1E1E; border: 2px solid #444; border-radius: 8px;
    padding: 6px 4px; text-align: center; font-weight: bold; font-size: 14px;
  }

  .tm-scroll-area {
    flex: 1; overflow-y: auto; padding: 6px 10px 90px 10px;
    display: grid; grid-template-columns: 1fr 1.6fr; gap: 10px;
    -webkit-overflow-scrolling: touch;
  }
  .box {
    background: #1E1E1E; border-radius: 10px; padding: 12px 14px;
    border: 1px solid #333; overflow-y: visible;
  }
  .step-box {
    border: 2px solid #009A3E; font-size: 20px; line-height: 1.5;
    background: #1B231E;
  }
  .step-box.mcs-mode {
    border-color: #00E5FF;
    background: #141C2B;
  }
  .ing-active {
    color: #00E676; font-weight: bold; background: #1B5E20;
    padding: 6px 10px; border-radius: 6px; margin-bottom: 6px; list-style: none;
  }
  .ing-idle { color: #CCCCCC; margin-bottom: 5px; padding: 2px 4px; }

  .bottom-nav {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: #141414; border-top: 2px solid #2E7D32;
    padding: 8px 12px; display: flex; gap: 10px; z-index: 90;
    box-shadow: 0 -4px 12px rgba(0,0,0,0.6);
  }
  .btn-nav {
    background: #009A3E; color: white; border: none;
    padding: 14px 10px; font-size: 16px; border-radius: 8px;
    font-weight: bold; cursor: pointer; flex: 1; text-align: center;
  }
  .btn-nav.mcs-nav { background: #0277BD; }
  .btn-nav:active { transform: scale(0.98); }
  .btn-nav:disabled { opacity: 0.3; cursor: default; }
  .btn-prev { background: #373737 !important; }

  #card-view {
    display: none; flex: 1; overflow: hidden; background: #121212; flex-direction: column;
  }
  .card-switch { display: flex; gap: 6px; padding: 6px 8px; background: #1A1A1A; }
  .card-switch .btn { flex: 1; }
  #card-iframe { width: 100%; flex: 1; border: none; background: #121212; }

  @media(max-width: 850px) {
    #sidebar {
      position: fixed; top: 0; left: 0; right: 0; bottom: 0;
      width: 100%; height: 100dvh;
    }
    .tm-scroll-area {
      grid-template-columns: 1fr;
      display: flex; flex-direction: column;
    }
    .step-box { order: 1; font-size: 19px; }
    #ings { order: 2; }
  }
</style>
</head>
<body>

<div id="sidebar" class="hidden">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
    <h3 style="margin:0; color:#00E676;" data-i18n="📚 Offline Kuchařka">📚 Offline Kuchařka</h3>
    <div style="display:flex; gap:6px;">
      <button class="btn" id="btn-ui-lang" onclick="toggleUiLang()" title="UI">🇬🇧 EN</button>
      <button class="btn" id="btn-icon-style" onclick="toggleIconStyle()">Ikony: 🟢/🔵</button>
      <button class="btn" style="background:#C62828; color:white;" onclick="toggleSidebar()" data-i18n="✖ Zavřít">✖ Zavřít</button>
    </div>
  </div>
  <select id="plat-filter" onchange="renderTree()">
    <option value="all" data-i18n="🔄 Všechny stroje (Cookidoo + Monsieur Cuisine)">🔄 Všechny stroje (Cookidoo + Monsieur Cuisine)</option>
    <option value="tm6" data-i18n="🟢 Jen Cookidoo (Thermomix TM6)">🟢 Jen Cookidoo (Thermomix TM6)</option>
    <option value="mcs" data-i18n="🔵 Jen Monsieur Cuisine Smart">🔵 Jen Monsieur Cuisine Smart</option>
    <option value="other" data-i18n="⚫ Jen ostatní weby">⚫ Jen ostatní weby</option>
  </select>
  <input type="text" id="search" placeholder="🔍 Hledat recept..." data-i18n-ph="🔍 Hledat recept..." oninput="renderTree()">
  <button class="btn" style="margin:4px 0 8px; background:#2E7D32; color:white;" onclick="location.href='/search?ui=' + UI + '&q=' + encodeURIComponent(document.getElementById('search').value)" data-i18n="🔎 Hledat na webech">🔎 Hledat na webech</button>
  <div id="tree" style="overflow-y:auto; flex:1;"></div>
</div>

<div id="main">
  <div class="top-bar">
    <div class="top-row-title">
      <button class="btn" style="background:#009A3E; color:white; font-size:14px;" onclick="toggleSidebar()" data-i18n="☰ Recepty">☰ Recepty</button>
      <h2 id="title" style="margin:0; color:#00E676; font-size:16px; flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" data-i18n="Vyber recept">Vyber recept</h2>
      <span id="step-badge" style="background:#2E7D32; color:white; padding:4px 8px; border-radius:6px; font-weight:bold; font-size:13px;" data-i18n="Krok 0/0">Krok 0/0</span>
    </div>
    <div class="btn-group">
      <button class="btn mode-active" id="btn-mode-tm" onclick="setViewMode('tm')">🍲 TM6</button>
      <button class="btn" id="btn-mode-mcs" onclick="setViewMode('mcs')">🤖 Monsieur Cuisine</button>
      <button class="btn" id="btn-mode-card" onclick="setViewMode('card')" data-i18n="📄 Karta">📄 Karta</button>
      <span style="color:#444;">|</span>
      <button class="btn sc-btn" id="sc-0.5" onclick="setScale(0.5)">0.5x</button>
      <button class="btn sc-btn active" id="sc-1" onclick="setScale(1.0)">1x</button>
      <button class="btn sc-btn" id="sc-1.5" onclick="setScale(1.5)">1.5x</button>
      <button class="btn sc-btn" id="sc-2" onclick="setScale(2.0)">2x</button>
      <span style="color:#444;">|</span>
      <button class="btn lang-btn active" id="lang-orig" onclick="setLang('orig')">🌐 Orig</button>
      <button class="btn lang-btn" id="lang-en" onclick="setLang('en')">🇬🇧 EN</button>
      <button class="btn lang-btn" id="lang-cs" onclick="setLang('cs')">🇨🇿 CZ</button>
      <span style="color:#444;">|</span>
      <button class="btn active" id="btn-fine" onclick="toggleFine()" data-i18n="🔍 Jemné kroky">🔍 Jemné kroky</button>
    </div>
  </div>

  <div id="tm-view">
    <div id="tr-banner" class="tr-banner" style="display:none;"></div>
    <div class="dials">
      <div class="dial" style="border-color:#00B0FF;" id="d-time">⏱️ ČAS<br>—</div>
      <div class="dial" style="border-color:#FF5252;" id="d-temp">🌡️ TEPLOTA<br>—</div>
      <div class="dial" style="border-color:#FFD740;" id="d-speed">🔪 OTÁČKY<br>—</div>
    </div>

    <div class="tm-scroll-area" id="scroll-container">
      <div class="box" id="ings" data-i18n="Vyber recept ze seznamu...">Vyber recept ze seznamu...</div>
      <div class="box step-box" id="step-txt" data-i18n="Klikni na zelené tlačítko &lt;b&gt;☰ Recepty&lt;/b&gt; vlevo nahoře a vyber si recept.">Klikni na zelené tlačítko <b>☰ Recepty</b> vlevo nahoře a vyber si recept.</div>
    </div>

    <div class="bottom-nav" id="bottom-nav-bar">
      <button class="btn-nav btn-prev" id="btn-prev" onclick="moveStep(-1)" data-i18n="◀ PŘEDCHOZÍ KROK">◀ PŘEDCHOZÍ KROK</button>
      <button class="btn-nav" id="btn-next" onclick="moveStep(1)" data-i18n="DALŠÍ KROK ▶">DALŠÍ KROK ▶</button>
    </div>
  </div>

  <div id="card-view">
    <div class="card-switch">
      <button class="btn active" id="card-kind-sheet" onclick="setCardKind('sheet')" data-i18n="📱 Pro mobil">📱 Pro mobil</button>
      <button class="btn" id="card-kind-orig" onclick="setCardKind('orig')" data-i18n="📄 Karta receptu">📄 Karta receptu</button>
    </div>
    <iframe id="card-iframe" src="about:blank"></iframe>
  </div>
</div>

<script>
let catalog = [], currentRecipe = null, currentId = null, stepIdx = 0, scale = 1.0, lang = 'orig', viewMode = 'tm', iconStyle = 'dots';
let fine = true, pendingMap = null;

let trPollTimer = null;
let cardKind = 'sheet';
let UI_SAVED = null;
try { UI_SAVED = localStorage.getItem('cc_ui'); } catch(e) {}
let UI = UI_SAVED || 'cs';
const I18N_EN = {
  '📚 Offline Kuchařka': '📚 Offline Cookbook', '✖ Zavřít': '✖ Close',
  'Ikony: 🟢/🔵': 'Icons: 🟢/🔵', 'Ikony: 🍲/🤖': 'Icons: 🍲/🤖',
  '🔄 Všechny stroje (Cookidoo + Monsieur Cuisine)': '🔄 All machines (Cookidoo + Monsieur Cuisine)',
  '🟢 Jen Cookidoo (Thermomix TM6)': '🟢 Cookidoo only (Thermomix TM6)', '🔵 Jen Monsieur Cuisine Smart': '🔵 Monsieur Cuisine Smart only',
  '🔍 Hledat recept...': '🔍 Search recipes...', '☰ Recepty': '☰ Recipes', 'Vyber recept': 'Select a recipe',
  '📄 Karta receptu': '📄 Recipe card', '🔍 Jemné kroky': '🔍 Detailed steps',
  '⏱️ ČAS': '⏱️ TIME', '🌡️ TEPLOTA': '🌡️ TEMP', '🔪 OTÁČKY': '🔪 SPEED', '🔪 RYCHLOST / PRG': '🔪 SPEED / PRG',
  'Vyber recept ze seznamu...': 'Pick a recipe from the list...',
  'Klikni na zelené tlačítko <b>☰ Recepty</b> vlevo nahoře a vyber si recept.': 'Tap the green <b>☰ Recipes</b> button at the top left and pick a recipe.',
  '◀ PŘEDCHOZÍ KROK': '◀ PREVIOUS STEP', 'DALŠÍ KROK ▶': 'NEXT STEP ▶',
  '⏳ Připravuji MCS verzi...': '⏳ Preparing the MCS version...', '⏳ Načítám...': '⏳ Loading...', '❌ Chyba načtení': '❌ Loading failed',
  'Zdroj': 'Source', 'KROK': 'STEP', 'Krok': 'Step', 'hl.': 'main', 'Z': 'OF', 'Žádné kroky.': 'No steps.',
  '🛒 Suroviny': '🛒 Ingredients', '🔄 Přeložit znovu': '🔄 Translate again',
  'Krok 0/0': 'Step 0/0', '📄 Karta': '📄 Card', '📱 Pro mobil': '📱 Phone view', '📄 Karta receptu': '📄 Recipe card',
  'Nic nenalezeno': 'Nothing found', '⚫ Jen ostatní weby': '⚫ Other sites only', '🔎 Hledat na webech': '🔎 Search the web'
};
function T(s){ return UI === 'en' ? (I18N_EN[s] || s) : s; }
function normKey(s){ return String(s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase(); }
function toggleUiLang(){
  UI = (UI === 'en') ? 'cs' : 'en';
  try { localStorage.setItem('cc_ui', UI); } catch(e) {}
  applyUiLang();
  renderTree();
  if(currentId) openRecipe(currentId, true);
}
function setCardKind(k){
  cardKind = k;
  document.getElementById('card-kind-sheet').classList.toggle('active', k === 'sheet');
  document.getElementById('card-kind-orig').classList.toggle('active', k === 'orig');
  loadCardIframe();
}
function recTitle(rec){
  const tl = (lang === 'orig') ? UI : lang;      // názvy podle jazyka rozhraní, nebo podle zvoleného jazyka receptu
  if(tl === 'en' && rec.title_en) return rec.title_en;
  if(tl === 'cs' && rec.title_cs) return rec.title_cs;
  return rec.title;
}
function applyUiLang(){
  document.documentElement.lang = UI;
  document.getElementById('btn-ui-lang').textContent = (UI === 'en') ? '🇨🇿 CZ' : '🇬🇧 EN';
  document.querySelectorAll('[data-i18n]').forEach(el => { el.innerHTML = T(el.getAttribute('data-i18n')); });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => { el.placeholder = T(el.getAttribute('data-i18n-ph')); });
  if(!currentRecipe){
    document.getElementById('d-time').innerHTML = T('⏱️ ČAS') + '<br>—';
    document.getElementById('d-temp').innerHTML = T('🌡️ TEPLOTA') + '<br>—';
    document.getElementById('d-speed').innerHTML = T('🔪 OTÁČKY') + '<br>—';
  }
  updateIconBtnLabel();
  if(currentRecipe) renderStep();
}
function escapeHtml(s){ return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

function handleTranslation(id){
  const b = document.getElementById('tr-banner');
  const t = (currentRecipe && currentRecipe.translation) || {status:'orig'};
  if(trPollTimer){ clearTimeout(trPollTimer); trPollTimer = null; }
  if(lang === 'orig' || t.status === 'orig'){ b.style.display = 'none'; return; }
  b.style.display = 'flex';
  b.className = 'tr-banner' + ((t.status === 'failed' || t.status === 'unavailable') ? ' err' : (t.status === 'pending' ? ' wait' : ''));
  let html = '<span>' + escapeHtml(t.message || '') + '</span>';
  if(t.status === 'done' || t.status === 'failed') html += '<button class="btn" onclick="retranslate()">' + T('🔄 Přeložit znovu') + '</button>';
  b.innerHTML = html;
  if(t.status === 'pending'){
    const myLang = lang, myMode = viewMode;
    trPollTimer = setTimeout(() => { if(currentId === id && lang === myLang && viewMode === myMode) openRecipe(id, true); }, 3000);
  }
}

async function retranslate(){
  if(!currentId || lang === 'orig') return;
  const dev = (viewMode === 'mcs') ? 'mcs' : 'tm6';
  try { await fetch(`/api/retranslate?id=${encodeURIComponent(currentId)}&lang=${lang}&device=${dev}`); } catch(e) {}
  if(viewMode === 'card') loadCardIframe(); else openRecipe(currentId, true);
}

function toggleFine(){
  const steps = (currentRecipe && currentRecipe.steps) || [];
  const cur = steps[stepIdx] || {};
  pendingMap = fine ? {toFine:false, parent: cur.parent} : {toFine:true, from: stepIdx};
  fine = !fine;
  document.getElementById('btn-fine').classList.toggle('active', fine);
  if(currentId) openRecipe(currentId, true);
}

function toggleSidebar(){
  document.getElementById('sidebar').classList.toggle('hidden');
}

function toggleIconStyle(){
  iconStyle = (iconStyle === 'dots') ? 'bots' : 'dots';
  updateIconBtnLabel();
  renderTree();
}

function updateIconBtnLabel(){
  document.getElementById('btn-icon-style').textContent = (iconStyle === 'bots') ? T('Ikony: 🍲/🤖') : T('Ikony: 🟢/🔵');
}

function getIconPrefix(plat, isFav){
  const p = (plat || 'tm6').toLowerCase();
  const pIc = (iconStyle === 'bots') ? ({mcs: '🤖', other: '🍽️'}[p] || '🍲') : ({mcs: '🔵', other: '⚫'}[p] || '🟢');
  return (isFav ? '⭐ ' : '') + pIc + ' ';
}

async function loadCatalog(){
  try {
    const r = await fetch('/api/recipes');
    const data = await r.json();
    catalog = data.items || [];
    if(data.icon_style) { iconStyle = data.icon_style; updateIconBtnLabel(); }
    if(!UI_SAVED && data.ui_lang && data.ui_lang !== UI) { UI = data.ui_lang; }
    applyUiLang();
    renderTree();
    const hashOpen = (location.hash.match(/^#open=(.+)$/) || [])[1];
    if(hashOpen){ openRecipe(decodeURIComponent(hashOpen)); history.replaceState(null, '', '/'); }
    else if(!currentId && catalog.length > 0){
      openRecipe(catalog[0].recipe_id);
    }
  } catch(e) { console.error(e); }
}

function renderTree(){
  const words = normKey(document.getElementById('search').value).split(/\\s+/).filter(Boolean);
  const pf = document.getElementById('plat-filter').value;
  const groups = {};
  catalog.forEach(item => {
    const itemPlat = (item.source_platform || 'tm6').toLowerCase();
    if(pf !== 'all' && itemPlat !== pf) return;
    const catName = (UI === 'en') ? (item.category_en || item.category) : item.category;
    const blob = (item.search || normKey(item.title)) + ' ' + normKey(catName);
    if(words.length && !words.every(w => blob.includes(w))) return;
    groups[catName] = groups[catName] || [];
    groups[catName].push(item);
  });
  const container = document.getElementById('tree');
  container.innerHTML = '';
  const cats = Object.keys(groups).sort((a, b) => normKey(a).localeCompare(normKey(b)));
  if(!cats.length && words.length){
    container.innerHTML = '<div style="padding:12px; color:#FFB74D;">' + T('Nic nenalezeno') + '</div>';
    return;
  }
  cats.forEach(cat => {
    const h = document.createElement('div');
    h.className = 'cat-header';
    h.textContent = `📁 ${cat} (${groups[cat].length})`;
    container.appendChild(h);
    groups[cat].sort((a, b) => (b.is_favorite - a.is_favorite) || normKey(recTitle(a)).localeCompare(normKey(recTitle(b))));
    groups[cat].forEach(rec => {
      const d = document.createElement('div');
      d.className = 'rec-item' + (rec.recipe_id === currentId ? ' active' : '');
      d.textContent = getIconPrefix(rec.source_platform, rec.is_favorite) + recTitle(rec);
      d.onclick = () => {
        openRecipe(rec.recipe_id);
        document.getElementById('sidebar').classList.add('hidden');
      };
      container.appendChild(d);
    });
  });
}

async function openRecipe(id, keepStep = false){
  currentId = id;
  renderTree();
  const deviceParam = (viewMode === 'mcs') ? 'mcs' : 'tm6';
  document.getElementById('title').textContent = (viewMode === 'mcs') ? T('⏳ Připravuji MCS verzi...') : T('⏳ Načítám...');
  try {
    const r = await fetch(`/api/recipe?id=${encodeURIComponent(id)}&lang=${lang}&scale=${scale}&device=${deviceParam}&fine=${fine ? 1 : 0}&ui=${UI}`);
    currentRecipe = await r.json();
    handleTranslation(id);
    if(!keepStep) stepIdx = 0;
    if(pendingMap){
      const st = currentRecipe.steps || [];
      if(pendingMap.toFine){
        const i = st.findIndex(s => s.parent === pendingMap.from);
        stepIdx = i >= 0 ? i : 0;
      } else if(pendingMap.parent !== null && pendingMap.parent !== undefined){
        stepIdx = Math.min(pendingMap.parent, Math.max(0, st.length - 1));
      }
      pendingMap = null;
    }
    renderStep();
    if(viewMode === 'card') loadCardIframe();
  } catch(e) {
    document.getElementById('title').textContent = T('❌ Chyba načtení');
  }
}

function setViewMode(m){
  const prevDevice = (viewMode === 'mcs') ? 'mcs' : 'tm6';
  viewMode = m;
  const newDevice = (viewMode === 'mcs') ? 'mcs' : 'tm6';

  document.getElementById('btn-mode-tm').className = 'btn' + (m === 'tm' ? ' mode-active' : '');
  document.getElementById('btn-mode-mcs').className = 'btn' + (m === 'mcs' ? ' mcs-active' : '');
  document.getElementById('btn-mode-card').className = 'btn' + (m === 'card' ? ' active' : '');

  document.getElementById('tm-view').style.display = (m === 'tm' || m === 'mcs') ? 'flex' : 'none';
  document.getElementById('card-view').style.display = (m === 'card') ? 'flex' : 'none';

  document.getElementById('step-txt').classList.toggle('mcs-mode', m === 'mcs');
  document.getElementById('btn-next').classList.toggle('mcs-nav', m === 'mcs');
  document.getElementById('title').style.color = (m === 'mcs') ? '#00E5FF' : '#00E676';

  if(m === 'card' && currentId) {
    loadCardIframe();
  } else if(currentId && prevDevice !== newDevice) {
    openRecipe(currentId, true);
  } else {
    renderStep();
  }
}

function loadCardIframe(){
  if(!currentId) return;
  const base = (cardKind === 'orig') ? '/api/card' : '/api/sheet';
  document.getElementById('card-iframe').src = `${base}?id=${encodeURIComponent(currentId)}&lang=${lang}&scale=${scale}&ui=${UI}&t=${Date.now()}`;
}

function setLang(l){
  lang = l;
  document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('lang-' + l).classList.add('active');
  renderTree();
  if(currentId) openRecipe(currentId, true);
}

function setScale(s){
  scale = s;
  document.querySelectorAll('.sc-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('sc-' + s);
  if(btn) btn.classList.add('active');
  if(currentId) openRecipe(currentId, true);
}

function moveStep(dir){
  if(!currentRecipe || !currentRecipe.steps || !currentRecipe.steps.length) return;
  const next = stepIdx + dir;
  if(next >= 0 && next < currentRecipe.steps.length){
    stepIdx = next;
    renderStep();
    const sc = document.getElementById('scroll-container');
    if(sc) sc.scrollTop = 0;
  }
}

function renderStep(){
  if(!currentRecipe) return;
  const steps = currentRecipe.steps || [];
  const total = steps.length;
  if(stepIdx >= total) stepIdx = Math.max(0, total - 1);

  const isMcs = (viewMode === 'mcs');
  const origPlat = (currentRecipe.source_platform || 'tm6').toUpperCase();
  const devLabel = isMcs ? `🤖 MONSIEUR CUISINE (${T('Zdroj')}: ${origPlat}) — ${T('KROK')}` : `🍲 THERMOMIX TM6 (${T('Zdroj')}: ${origPlat}) — ${T('KROK')}`;
  const hdrColor = isMcs ? '#00E5FF' : '#00E676';

  document.getElementById('title').textContent = `${currentRecipe.title} (${scale}x)`;
  const par = (steps[stepIdx] && steps[stepIdx].parent !== null && steps[stepIdx].parent !== undefined && fine) ? ` (${T('hl.')} ${steps[stepIdx].parent + 1})` : '';
  document.getElementById('step-badge').textContent = `${T('Krok')} ${total ? stepIdx+1 : 0}/${total}${par}`;
  document.getElementById('step-badge').style.background = isMcs ? '#1565C0' : '#2E7D32';

  const st = steps[stepIdx] || {text:T('Žádné kroky.'), html:T('Žádné kroky.'), dials:{}, matched_ings:[]};
  const dials = st.dials || {};

  document.getElementById('d-time').innerHTML = T('⏱️ ČAS') + '<br>' + (dials.time || '—');
  document.getElementById('d-temp').innerHTML = T('🌡️ TEPLOTA') + '<br>' + (dials.temp || '—');
  document.getElementById('d-speed').innerHTML = (isMcs ? T('🔪 RYCHLOST / PRG') : T('🔪 OTÁČKY')) + '<br>' + (dials.speed || '—');
  document.getElementById('step-txt').innerHTML = `<div style="color:${hdrColor}; font-size:13px; font-weight:bold; margin-bottom:6px;">${devLabel} ${total ? stepIdx+1 : 0} ${T('Z')} ${total}</div>` + (st.formatted_html || st.html || st.text);

  const ingsList = st.matched_ings || (currentRecipe.ingredients || []).map(x => ({text:x, active:false}));
  document.getElementById('ings').innerHTML = `<h4 style="margin:0 0 8px 0; color:${hdrColor};">${T('🛒 Suroviny')} (${scale}x)</h4><ul style="padding-left:16px; margin:0;">` +
    ingsList.map(i => i.active
      ? `<li class="ing-active">👉 ${i.text}</li>`
      : `<li class="ing-idle">${i.text}</li>`
    ).join('') + '</ul>';

  document.getElementById('btn-prev').disabled = (stepIdx <= 0);
  document.getElementById('btn-next').disabled = (stepIdx >= total - 1);
}

document.addEventListener('keydown', e => {
  if(viewMode === 'card') return;
  if(e.key === 'ArrowRight') moveStep(1);
  if(e.key === 'ArrowLeft') moveStep(-1);
});

loadCatalog();
</script>
</body>
</html>
"""


# ==========================================
# SDÍLENÉ STYLY, PÍSMA A OBRÁZKY KARET RECEPTU (localchef_data/web_assets)
# Každý soubor je uložený jen jednou – pod otiskem obsahu (hash), index.json mapuje adresu z webu → soubor.
# ==========================================
WEB_ASSETS_DIR = BASE_DIR / "web_assets"
ASSET_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
CSS_URL_RE = re.compile(r'url\(\s*([\'"]?)([^\'")]+)\1\s*\)', re.IGNORECASE)
CSS_IMPORT_RE = re.compile(r'@import\s+([\'"])([^\'"]+)\1', re.IGNORECASE)
ASSET_MAX_BYTES = 15 * 1024 * 1024
_ASSET_LOCK = threading.Lock()
_ASSET_INDEX: dict = {"loaded": False, "map": {}}
_ASSET_FAILED: dict = {}                  # adresa → kdy naposledy selhala (nezkoušet znovu hned)
_ASSET_BUSY: set = set()                  # složky receptů, které se právě doplňují
_FONT_EXT = (".woff", ".woff2", ".ttf", ".otf", ".eot")
_IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg", ".ico", ".bmp")


def _asset_site(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(k in host for k in ("cookidoo", "tmecosys", "vorwerk", "thermomix")):
        return "cookidoo"
    if any(k in host for k in ("monsieur-cuisine", "tecpal", "lidl")):
        return "monsieur_cuisine"
    return "other"


def _asset_kind_ext(url: str, ctype: str) -> tuple[str, str]:
    path_ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
    ctype = (ctype or "").split(";")[0].strip().lower()
    if ctype == "text/css" or path_ext == ".css":
        return "css", ".css"
    if path_ext in _FONT_EXT or ctype.startswith("font/") or "font" in ctype:
        return "fonts", path_ext if path_ext in _FONT_EXT else (mimetypes.guess_extension(ctype) or ".font")
    if path_ext in _IMG_EXT or ctype.startswith("image/"):
        ext = path_ext if path_ext in _IMG_EXT else (mimetypes.guess_extension(ctype) or ".img")
        return "images", ".jpg" if ext == ".jpe" else ext
    return "other", path_ext if 0 < len(path_ext) <= 6 else ".bin"


def _asset_map() -> dict:
    with _ASSET_LOCK:
        if not _ASSET_INDEX["loaded"]:
            try:
                _ASSET_INDEX["map"] = json.loads((WEB_ASSETS_DIR / "index.json").read_text(encoding="utf-8"))
            except Exception:
                _ASSET_INDEX["map"] = {}
            _ASSET_INDEX["loaded"] = True
        return _ASSET_INDEX["map"]


def _asset_save_index():
    WEB_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = WEB_ASSETS_DIR / "index.json.tmp"
    tmp.write_text(json.dumps(_ASSET_INDEX["map"], ensure_ascii=False, indent=0), encoding="utf-8")
    os.replace(tmp, WEB_ASSETS_DIR / "index.json")


def asset_lookup(url: str) -> str | None:
    entry = _asset_map().get(url)
    if entry and (WEB_ASSETS_DIR / entry["file"]).exists():
        return entry["file"]
    return None


def _asset_fetch(url: str, referer: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": ASSET_UA, "Referer": referer or url, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read(ASSET_MAX_BYTES + 1)
        if len(data) > ASSET_MAX_BYTES:
            raise ValueError("soubor je příliš velký")
        return data, resp.headers.get("Content-Type", "")


def _css_absolutize(text: str, css_url: str) -> tuple[str, list[str]]:
    subs = []

    def fix(m):
        ref = m.group(2).strip()
        if ref.startswith(("data:", "#", "about:")):
            return m.group(0)
        absu = urllib.parse.urljoin(css_url, ref)
        subs.append(absu)
        return f"url({m.group(1)}{absu}{m.group(1)})"

    text = CSS_URL_RE.sub(fix, text)

    def fix_imp(m):
        absu = urllib.parse.urljoin(css_url, m.group(2))
        subs.append(absu)
        return f"@import {m.group(1)}{absu}{m.group(1)}"

    return CSS_IMPORT_RE.sub(fix_imp, text), subs


def cache_asset(url: str, referer: str = "", depth: int = 0, force: bool = False) -> str | None:
    """Uloží soubor do web_assets (jen jednou podle obsahu) a vrátí jeho relativní cestu.
    force=True: stáhne znovu i už uložený soubor (kontrola stylů při startu)."""
    if not url.startswith(("http://", "https://")):
        return None
    have = asset_lookup(url)
    if have and not force:
        return have
    if time.time() - _ASSET_FAILED.get(url, 0) < 3600:
        return have
    try:
        data, ctype = _asset_fetch(url, referer)
    except Exception:
        _ASSET_FAILED[url] = time.time()
        return have                           # bez internetu zůstává, co už je uložené
    kind, ext = _asset_kind_ext(url, ctype)
    subs: list[str] = []
    if kind == "css":
        text, subs = _css_absolutize(data.decode("utf-8", "replace"), url)
        data = text.encode("utf-8")
    rel = f"{_asset_site(url)}/{kind}/{hashlib.sha1(data).hexdigest()[:24]}{ext}"
    target = WEB_ASSETS_DIR / rel
    if not target.exists():                   # stejný obsah = stejný soubor → žádné duplicity
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    with _ASSET_LOCK:
        _ASSET_INDEX["map"][url] = {"file": rel, "kind": kind, "checked": time.time()}
        _asset_save_index()
    if kind == "css" and depth < 2:
        for sub in dict.fromkeys(subs):
            cache_asset(sub, url, depth + 1)
    return rel


def refresh_web_assets() -> dict:
    """Při startu: znovu ověří všechny uložené styly (CSS). Změněný styl se uloží jako nový soubor a index
    se přepne na něj – všechny recepty, které ho používají, ho tím dostanou hned, nic se u nich nestahuje.
    Nové písma/obrázky, na které nový styl odkazuje, se doplní. Soubory, na které už nic neodkazuje, se smažou."""
    stats = {"checked": 0, "changed": 0, "removed": 0}
    css = [(u, e) for u, e in list(_asset_map().items()) if e.get("kind") == "css"]
    for url, entry in css:
        old = entry.get("file")
        new = cache_asset(url, url, force=True)
        stats["checked"] += 1
        if new and new != old:
            stats["changed"] += 1
    with _ASSET_LOCK:
        used = {e.get("file") for e in _ASSET_INDEX["map"].values()}
    if WEB_ASSETS_DIR.exists():
        for f in WEB_ASSETS_DIR.rglob("*"):
            if f.is_file() and f.name not in ("index.json", "index.json.tmp"):
                rel = f.relative_to(WEB_ASSETS_DIR).as_posix()
                if rel not in used and time.time() - f.stat().st_mtime > 600:   # čerstvé soubory nechat (právě se ukládá recept)
                    try:
                        f.unlink()
                        stats["removed"] += 1
                    except OSError:
                        pass
    return stats


def start_web_assets_check():
    def run():
        try:
            st = refresh_web_assets()
            if st["checked"]:
                log(f"Kontrola stylů karet: ověřeno {st['checked']}, změněno {st['changed']}, odstraněno starých souborů {st['removed']}")
        except Exception:
            log("Kontrola stylů karet selhala:\n" + traceback.format_exc())
    threading.Thread(target=run, daemon=True).start()


def _page_base(soup, page_url: str) -> str:
    b = soup.find("base", href=True)
    return urllib.parse.urljoin(page_url or "", b["href"]) if b else (page_url or "")


def _srcset_urls(value: str) -> list[str]:
    return [c.strip().split()[0] for c in (value or "").split(",") if c.strip()]


def html_asset_urls(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    base = _page_base(soup, page_url)
    found = []
    for link in soup.find_all("link", href=True):
        rels = " ".join(link.get("rel") or []).lower()
        if "stylesheet" in rels or "icon" in rels:
            found.append(link["href"])
    for tag in soup.find_all(["img", "source"]):
        if tag.get("src"):
            found.append(tag["src"])
        found.extend(_srcset_urls(tag.get("srcset", "")))
    for tag in soup.find_all(style=True):
        found.extend(m.group(2) for m in CSS_URL_RE.finditer(tag["style"]))
    for st in soup.find_all("style"):
        found.extend(m.group(2) for m in CSS_URL_RE.finditer(st.get_text()))
    out = []
    for u in found:
        u = (u or "").strip()
        if not u or u.startswith(("data:", "#", "javascript:")):
            continue
        absu = urllib.parse.urljoin(base, u)
        if absu.startswith(("http://", "https://")) and absu not in out:
            out.append(absu)
    return out[:250]


def _recipe_page_url(folder: Path) -> str:
    try:
        return json.loads((folder / "recipe.json").read_text(encoding="utf-8")).get("url", "")
    except Exception:
        return ""


def cache_page_assets(folder: Path) -> int:
    page_url = _recipe_page_url(folder)
    snap = folder / "page_snapshot.html"
    if not snap.exists():
        return 0
    n = 0
    for u in html_asset_urls(snap.read_text(encoding="utf-8", errors="ignore"), page_url):
        if cache_asset(u, page_url):
            n += 1
    return n


def schedule_page_assets(folder: Path):
    """Doplní styly, písma a obrázky karty na pozadí (po uložení receptu a u starších receptů při zobrazení)."""
    key = str(Path(folder).resolve())
    with _ASSET_LOCK:
        if key in _ASSET_BUSY:
            return
        _ASSET_BUSY.add(key)

    def run():
        try:
            n = cache_page_assets(Path(folder))
            log(f"Karta {Path(folder).name}: uloženo {n} sdílených souborů (styly, písma, obrázky)")
        except Exception:
            log("Ukládání stylů karty selhalo:\n" + traceback.format_exc())
        finally:
            with _ASSET_LOCK:
                _ASSET_BUSY.discard(key)

    threading.Thread(target=run, daemon=True).start()


def rewrite_card_html(html: str, page_url: str, host: str) -> tuple[str, int]:
    """Odkazy na styly a obrázky webu nahradí uloženými kopiemi z web_assets. Vrátí i počet chybějících."""
    soup = BeautifulSoup(html, "html.parser")
    base = _page_base(soup, page_url)
    prefix = f"http://{host}/assets/"
    missing = 0

    def local(u: str) -> str | None:
        nonlocal missing
        u = (u or "").strip()
        if not u or u.startswith(("data:", "#", "javascript:")):
            return None
        absu = urllib.parse.urljoin(base, u)
        if not absu.startswith(("http://", "https://")):
            return None
        rel = asset_lookup(absu)
        if rel:
            return prefix + rel
        missing += 1
        return None

    def css_fix(text: str) -> str:
        return CSS_URL_RE.sub(lambda m: f"url({m.group(1)}{local(m.group(2)) or m.group(2)}{m.group(1)})", text)

    for link in soup.find_all("link", href=True):
        rels = " ".join(link.get("rel") or []).lower()
        if "stylesheet" in rels or "icon" in rels:
            loc = local(link["href"])
            if loc:
                link["href"] = loc
                if link.get("integrity"):
                    del link["integrity"]
    for tag in soup.find_all(["img", "source"]):
        if tag.get("src"):
            loc = local(tag["src"])
            if loc:
                tag["src"] = loc
        if tag.get("srcset"):
            parts = []
            for cand in [c.strip() for c in tag["srcset"].split(",") if c.strip()]:
                bits = cand.split()
                loc = local(bits[0])
                parts.append(" ".join([loc or bits[0]] + bits[1:]))
            tag["srcset"] = ", ".join(parts)
    for tag in soup.find_all(style=True):
        tag["style"] = css_fix(tag["style"])
    for st in soup.find_all("style"):
        if st.string:
            st.string.replace_with(css_fix(st.string))
    return str(soup), missing


def localize_css(text: str, host: str) -> str:
    prefix = f"http://{host}/assets/"

    def sub(m):
        rel = asset_lookup(m.group(2).strip())
        return f"url({m.group(1)}{prefix + rel}{m.group(1)})" if rel else m.group(0)

    def sub_imp(m):
        rel = asset_lookup(m.group(2))
        return f"@import {m.group(1)}{prefix + rel}{m.group(1)}" if rel else m.group(0)

    return CSS_IMPORT_RE.sub(sub_imp, CSS_URL_RE.sub(sub, text))


def serve_asset_path(rel: str) -> Path | None:
    try:
        target = (WEB_ASSETS_DIR / urllib.parse.unquote(rel)).resolve()
        target.relative_to(WEB_ASSETS_DIR.resolve())          # nic mimo web_assets
    except Exception:
        return None
    return target if target.is_file() else None


# ==========================================
# DOPLŇKY RECEPTU: obrázek, nutriční hodnoty, tipy, časy  +  ČISTÝ LIST RECEPTU (PDF a mobil)
# ==========================================
NUTRI_LABELS = {
    "calories": ("Energie", "Energy"),
    "protein": ("Bílkoviny", "Protein"),
    "carbs": ("Sacharidy", "Carbohydrates"),
    "sugar": ("z toho cukry", "of which sugars"),
    "fat": ("Tuky", "Fat"),
    "satfat": ("z toho nasycené", "of which saturated"),
    "fiber": ("Vláknina", "Fibre"),
    "salt": ("Sůl", "Salt"),
    "sodium": ("Sodík", "Sodium"),
    "cholesterol": ("Cholesterol", "Cholesterol"),
}
_LD_NUTRI = {"calories": "calories", "proteinContent": "protein", "carbohydrateContent": "carbs",
             "sugarContent": "sugar", "fatContent": "fat", "saturatedFatContent": "satfat",
             "fiberContent": "fiber", "sodiumContent": "sodium", "cholesterolContent": "cholesterol"}
_NUTRI_NAME_RE = [
    ("kj", r'\bkj\b|kilojoule'), ("kcal", r'kcal|kalori|calor'), ("calories", r'energ'),
    ("protein", r'prot|bílkov|eiwei|białk'), ("sugar", r'sugar|cukr|zucker|cukier'),
    ("satfat", r'satur|nasycen|gesättig|nasyc'), ("fat", r'fat|tuk|fett|tłuszcz'),
    ("carbs", r'carb|sachar|kohlenhyd|węglow'), ("fiber", r'fib|vlákn|ballast|błonnik'),
    ("salt", r'salt|sůl|salz|sól'), ("sodium", r'sodium|sodík|natrium|sód'), ("cholesterol", r'cholest'),
]
TIPS_TITLES = {"tipy", "tip", "užitečné tipy", "uzitecne tipy", "rady", "tips", "useful tips", "hints", "tipps",
               "hilfreiche tipps", "tipp", "wskazówki", "porady", "astuces", "consejos", "consigli"}


def _iso_duration(v) -> str:
    m = re.match(r'^P(?:T)?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$', str(v or "").strip().upper().replace("PT", "P"))
    if not m or not any(m.groups()):
        return str(v or "").strip()
    h, mi, _ = (int(x or 0) for x in m.groups())
    h, mi = h + mi // 60, mi % 60
    return " ".join(x for x in (f"{h} h" if h else "", f"{mi} min" if mi else "") if x) or ""


def _plain(s) -> str:
    return re.sub(r'\s+', ' ', BeautifulSoup(str(s or ""), "html.parser").get_text(" ")).strip()


def _walk(o, depth=0):
    if depth > 12:
        return
    if isinstance(o, dict):
        for k, v in o.items():
            yield k, v
            yield from _walk(v, depth + 1)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v, depth + 1)


def _all_dicts(o, depth=0):
    if depth > 12:
        return
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _all_dicts(v, depth + 1)
    elif isinstance(o, list):
        for v in o:
            yield from _all_dicts(v, depth + 1)


def _nutri_from_entries(entries) -> dict:
    out = {}
    for d in entries:
        if not isinstance(d, dict):
            continue
        name = next((str(d[k]) for k in ("type", "name", "nutritionType", "key", "label", "title", "unitType") if d.get(k)), "")
        qty = next((d[k] for k in ("quantity", "value", "amount", "qty", "number") if d.get(k) not in (None, "")), None)
        unit = next((str(d[k]) for k in ("unitNotation", "unit", "unittype", "unitType", "unitName", "unitSymbol") if d.get(k)), "")
        if not name or qty is None:
            continue
        low = name.lower() + " " + unit.lower()
        key = next((k for k, rx in _NUTRI_NAME_RE if re.search(rx, low)), None)
        if key:
            q = _format_num(float(qty)) if isinstance(qty, (int, float)) else str(qty)
            out.setdefault(key, f"{q} {unit}".strip())
    if "kj" in out or "kcal" in out:
        out["calories"] = " / ".join(x for x in (out.pop("kj", ""), out.pop("kcal", "")) if x)
    return out


def _extract_extras(folder: Path) -> dict:
    snap = folder / "page_snapshot.html"
    html = snap.read_text(encoding="utf-8", errors="ignore") if snap.exists() else ""
    soup = BeautifulSoup(html, "html.parser") if html else None
    ld = find_recipe_ld(soup) if soup else {}
    if not ld:
        try:
            ld = json.loads((folder / "_debug_ld.json").read_text(encoding="utf-8")) or {}
        except Exception:
            ld = {}
    api = {}
    try:
        api = json.loads((folder / "_debug_api.json").read_text(encoding="utf-8") or "{}")
    except Exception:
        pass
    ex = {"v": 1, "image": "", "nutrition": {}, "nutrition_per": "", "tips": [], "prep": "", "total": "", "yield": ""}

    # obrázek
    img = ld.get("image")
    if isinstance(img, list):
        img = img[0] if img else ""
    if isinstance(img, dict):
        img = img.get("url") or img.get("contentUrl") or ""
    if not img and soup:
        og = soup.find("meta", attrs={"property": "og:image"}) or soup.find("meta", attrs={"name": "og:image"})
        img = og.get("content", "") if og else ""
    if not img:
        for k, v in _walk(api):
            if isinstance(v, str) and "image" in str(k).lower() and re.match(r'https?://', v):
                img = v
                break
    ex["image"] = str(img or "").replace("{transformation}/", "").replace("{transformation}", "")

    # nutriční hodnoty
    nut = ld.get("nutrition") if isinstance(ld.get("nutrition"), dict) else {}
    for k, key in _LD_NUTRI.items():
        if nut.get(k):
            ex["nutrition"][key] = str(nut[k]).strip()
    ex["nutrition_per"] = str(nut.get("servingSize") or "").strip()
    if not ex["nutrition"]:
        for k, v in _walk(api):
            if "nutri" in str(k).lower() and isinstance(v, (list, dict)):
                entries = []
                for sub in _all_dicts(v):
                    if isinstance(sub, dict):
                        entries.append(sub)
                        if not any(sub.get(f) for f in ("type", "name", "nutritionType", "key", "label", "title")):
                            entries.extend({"name": kk, "quantity": vv} for kk, vv in sub.items()
                                           if isinstance(vv, (int, float, str)) and not isinstance(vv, bool))
                found = _nutri_from_entries(entries)
                if found:
                    ex["nutrition"] = found
                    break

    # tipy (přednost mají tipy, které našlo už ukládání receptu – recipe.json → "tips")
    tips = []
    try:
        tips = [t for t in json.loads((folder / "recipe.json").read_text(encoding="utf-8")).get("tips") or [] if t]
    except Exception:
        tips = []
    for k, v in ([] if tips else _walk(api)):
        kl = str(k).lower()
        if kl.endswith(("tip", "tips", "hint", "hints")) or (kl.startswith(("tip", "hint")) and not kl.startswith("tipo")):
            vals = v if isinstance(v, list) else [v]
            for x in vals:
                t = x if isinstance(x, str) else (next((x[f] for f in ("formattedText", "text", "description", "content", "title") if isinstance(x, dict) and x.get(f)), "") if isinstance(x, dict) else "")
                t = _plain(t)
                if len(t) > 8 and t not in tips:
                    tips.append(t)
    if not tips and soup:
        for h in soup.find_all(["h2", "h3", "h4", "h5", "strong", "b", "span", "div", "p"]):
            txt = _plain(h.get_text(" "))
            if search_key(txt).strip(" :") not in {search_key(x) for x in TIPS_TITLES} or len(txt) > 30:
                continue
            nxt = h.find_next(["ul", "ol", "p", "div"])
            if nxt is None:
                continue
            items = [_plain(li.get_text(" ")) for li in nxt.find_all("li")] or [_plain(nxt.get_text(" "))]
            items = [t for t in items if len(t) < 600]
            tips = [t for t in items if len(t) > 8][:10]
            if tips:
                break
    ex["tips"] = tips[:10]

    ex["prep"] = _iso_duration(ld.get("prepTime"))
    ex["total"] = _iso_duration(ld.get("totalTime"))
    y = ld.get("recipeYield")
    ex["yield"] = str(y[0] if isinstance(y, list) and y else (y or "")).strip()
    return ex


def recipe_extras(folder: Path) -> dict:
    """Obrázek, nutriční hodnoty, tipy a časy receptu (z uložené stránky). Výsledek se pamatuje v extras.json."""
    folder = Path(folder)
    cache = folder / "extras.json"
    snap = folder / "page_snapshot.html"
    mtime = snap.stat().st_mtime if snap.exists() else 0
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        if data.get("v") == 1 and data.get("src_mtime") == mtime:
            return data
    except Exception:
        pass
    try:
        data = _extract_extras(folder)
    except Exception as e:
        log(f"Doplňky receptu {folder.name} se nepodařilo načíst: {e}")
        data = {"v": 1, "image": "", "nutrition": {}, "nutrition_per": "", "tips": [], "prep": "", "total": "", "yield": ""}
    data["src_mtime"] = mtime
    try:
        cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return data


def load_recipe_view(folder: Path, lang: str = "orig", device: str | None = None) -> tuple[dict, str]:
    """Data receptu pro list/PDF: přeložená verze, když existuje, jinak originál. Vrací (data, skutečný jazyk)."""
    folder = Path(folder)
    base = json.loads((folder / "recipe.json").read_text(encoding="utf-8"))
    device = device or (base.get("source_platform") or "tm6").lower()
    if lang in ("en", "cs"):
        f = folder / f"{get_base_prefix_for_device(folder, device)}_{lang}.json"
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8")), lang
            except Exception:
                pass
    f = ensure_device_recipe_file(folder, device) or (folder / "recipe.json")
    return json.loads(Path(f).read_text(encoding="utf-8")), "orig"


SHEET_TXT = {
    "ingredients": ("Suroviny", "Ingredients"), "steps": ("Postup", "Method"), "tips": ("Tipy", "Tips"),
    "nutrition": ("Nutriční hodnoty", "Nutrition"), "per": ("na", "per"), "portions": ("Porce", "Servings"),
    "prep": ("Příprava", "Prep"), "total": ("Celkem", "Total"), "scale": ("Dávka", "Batch"),
    "orig_card": ("Karta receptu", "Recipe card"), "no_steps": ("Kroky nebyly nalezeny.", "No steps found."),
    "source": ("Zdroj", "Source"),
}


# barevné emoji se v PDF (Qt) často vykreslí jako prázdné čtverečky → do PDF je nedáváme (šipky ↺ ↻ zůstávají)
_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]+ ?")


def _st(key: str, ui: str) -> str:
    cs, en = SHEET_TXT[key]
    return en if ui == "en" else cs


def _step_html_plain(st: dict, is_mcs: bool, ui: str = "cs") -> str:
    h = st.get("html") or html_mod.escape(st.get("text", ""))
    h = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', '', h)
    h = re.sub(r'(?i)<(?!/?(b|strong|i|em|br|span|sup|sub)\b)[^>]+>', ' ', h)
    return format_tm_icons_html(h, is_mcs=is_mcs, ui=ui)


def render_recipe_sheet(folder: Path, lang: str = "orig", device: str | None = None, ui: str = "cs",
                        mode: str = "web", scale: float = 1.0, metric: bool = True, image_src: str = "",
                        card_url: str = "") -> str:
    """Čistý list receptu: obrázek, suroviny, nutriční hodnoty, postup a tipy.
    mode='pdf' → jednoduché HTML pro tisk do PDF, mode='web' → stránka pro mobil."""
    folder = Path(folder)
    data, real_lang = load_recipe_view(folder, lang, device)
    ex = recipe_extras(folder)
    is_mcs = (device or data.get("device") or data.get("source_platform") or "tm6").lower() == "mcs"
    title = html_mod.escape(data.get("title") or folder.name)
    ings = []
    for i in data.get("ingredients", []):
        line = scale_ingredient_line(i, scale)
        line = convert_text_to_metric(html_mod.escape(line), html_highlight=False) if metric else html_mod.escape(line)
        ings.append(line)
    steps = []
    for s in data.get("steps", []):
        h = _step_html_plain(s, is_mcs, ui)
        h = scale_step_text(h, scale)
        if metric:
            h = convert_text_to_metric(h, html_highlight=False)
        steps.append(h)
    tips = data.get("tips") if real_lang != "orig" and data.get("tips") else ex.get("tips", [])
    nut = [(NUTRI_LABELS[k][1 if ui == "en" else 0], ex["nutrition"][k]) for k in NUTRI_LABELS if k in ex.get("nutrition", {})]
    meta = []
    portions = data.get("portions") or ex.get("yield")
    if portions:
        meta.append(f"{_st('portions', ui)}: {html_mod.escape(str(portions))}")
    if ex.get("prep"):
        meta.append(f"{_st('prep', ui)}: {html_mod.escape(ex['prep'])}")
    if ex.get("total") or data.get("total_time"):
        meta.append(f"{_st('total', ui)}: {html_mod.escape(ex.get('total') or _iso_duration(data.get('total_time')))}")
    if abs(scale - 1) > 0.01:
        meta.append(f"{_st('scale', ui)}: {scale:g}×")
    accent = "#0277BD" if is_mcs else "#009A3E"
    per = f" ({_st('per', ui)} {html_mod.escape(ex['nutrition_per'])})" if ex.get("nutrition_per") else ""

    if mode == "pdf":
        h3 = f"style='color:{accent}; font-size:12.5pt; margin-top:0; margin-bottom:4px;'"
        ul = "style='margin-top:0; margin-bottom:0; -qt-list-indent:1;'"
        img = f"<img src='{image_src}' width='390'>" if image_src else ""
        ing_html = "".join(f"<li style='margin-bottom:2px;'>{x}</li>" for x in ings) or "<li>—</li>"
        nut_html = ""
        if nut:
            rows = "".join(f"<tr><td style='color:#555;'>{html_mod.escape(k)}</td><td align='right'><b>{html_mod.escape(v)}</b></td></tr>" for k, v in nut)
            nut_html = (f"<h3 {h3}>{_st('nutrition', ui)}</h3>"
                        + (f"<p style='color:#777; margin:0 0 4px 0;'>{_st('per', ui)} {html_mod.escape(ex['nutrition_per'])}</p>" if ex.get("nutrition_per") else "")
                        + f"<table width='100%' cellspacing='0' cellpadding='3' style='border:1px solid #ccc;'>{rows}</table>")
        if img and nut_html:
            top = f"<table width='100%' cellspacing='0' cellpadding='0'><tr><td width='54%' valign='top'>{img}</td><td width='4%'></td><td width='42%' valign='top'>{nut_html}</td></tr></table>"
        elif img:
            top = f"<p align='center' style='margin:0;'>{img}</p>"
        else:
            top = nut_html
        steps = [re.sub(r"background-color:[^;']+;\s*color:[^;']+;", f"color:{accent};", x) for x in steps]   # ikony stroje v PDF jen barevným písmem
        step_html = "".join(f"<li style='margin-bottom:5px;'>{x}</li>" for x in steps) or f"<li>{_st('no_steps', ui)}</li>"
        tips_html = (f"<h3 {h3}>{_st('tips', ui)}</h3><ul {ul}>" + "".join(f"<li style='margin-bottom:2px;'>{html_mod.escape(t)}</li>" for t in tips) + "</ul>") if tips else ""
        return _EMOJI_RE.sub("", f"""<html><body style="font-family:'Segoe UI',Arial,sans-serif; font-size:10pt; color:#222;">
<h1 style="color:{accent}; font-size:19pt; margin-top:0; margin-bottom:0;">{title}</h1>
<p style="color:#666; margin-top:2px; margin-bottom:8px;">{' &nbsp;·&nbsp; '.join(meta)}</p>
{top}
<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:10px;"><tr>
<td width="36%" valign="top"><h3 {h3}>{_st('ingredients', ui)}</h3><ul {ul}>{ing_html}</ul></td>
<td width="3%"></td>
<td width="61%" valign="top"><h3 {h3}>{_st('steps', ui)}</h3><ol {ul}>{step_html}</ol></td>
</tr></table>
<div style="margin-top:8px;">{tips_html}</div>
</body></html>""")

    # mobil
    img = f"<img class='hero' src='{html_mod.escape(image_src)}' alt=''>" if image_src else ""
    nut_html = ""
    if nut:
        cells = "".join(f"<div class='nut'><span>{html_mod.escape(k)}</span><b>{html_mod.escape(v)}</b></div>" for k, v in nut)
        nut_html = f"<section><h2>📊 {_st('nutrition', ui)}<small>{per}</small></h2><div class='nuts'>{cells}</div></section>"
    tips_html = ("<section><h2>💡 " + _st('tips', ui) + "</h2><ul>" + "".join(f"<li>{html_mod.escape(t)}</li>" for t in tips) + "</ul></section>") if tips else ""
    card_link = f"<a class='orig' href='{html_mod.escape(card_url)}'>📄 {_st('orig_card', ui)}</a>" if card_url else ""
    return f"""<!DOCTYPE html><html lang="{ui}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
 body {{ margin:0; background:#121212; color:#ECECEC; font:16px/1.5 -apple-system,'Segoe UI',Roboto,sans-serif; }}
 .wrap {{ max-width:760px; margin:0 auto; padding:12px 14px 40px; }}
 h1 {{ color:{'#00E5FF' if is_mcs else '#00E676'}; font-size:22px; margin:6px 0 4px; }}
 .meta {{ color:#9E9E9E; font-size:14px; margin-bottom:10px; }}
 .hero {{ width:100%; border-radius:12px; display:block; margin:6px 0 12px; }}
 section {{ background:#1E1E1E; border-radius:12px; padding:12px 14px; margin:12px 0; }}
 h2 {{ margin:0 0 8px; font-size:17px; color:{'#80D8FF' if is_mcs else '#69F0AE'}; }}
 h2 small {{ color:#9E9E9E; font-weight:normal; font-size:13px; }}
 ul, ol {{ margin:0; padding-left:20px; }} li {{ margin:4px 0; }}
 ol li {{ margin:8px 0; }}
 ol li span {{ white-space:normal; display:inline; padding:0 4px !important; }}
 .nuts {{ display:grid; grid-template-columns:1fr 1fr; gap:6px; }}
 .nut {{ background:#262626; border-radius:8px; padding:6px 8px; display:flex; justify-content:space-between; gap:6px; font-size:14px; }}
 .nut span {{ color:#BDBDBD; }}
 a.orig {{ display:inline-block; margin-top:6px; color:#B39DDB; font-weight:bold; text-decoration:none; }}
</style></head><body><div class="wrap">
<h1>{title}</h1><div class="meta">{' · '.join(meta)}</div>
{img}
<section><h2>🛒 {_st('ingredients', ui)}</h2><ul>{''.join(f'<li>{x}</li>' for x in ings) or '<li>—</li>'}</ul></section>
{nut_html}
<section><h2>📋 {_st('steps', ui)}</h2><ol>{''.join(f'<li>{x}</li>' for x in steps) or '<li>' + _st('no_steps', ui) + '</li>'}</ol></section>
{tips_html}
{card_link}
</div></body></html>"""


# ==========================================
# HROMADNÝ PŘEKLAD (všechny recepty do EN i CZ, na pozadí)
# ==========================================
BULK_TR = {"running": False, "stop": False, "done": 0, "total": 0, "failed": 0, "current": "", "errors": []}


def bulk_translation_todo(langs=("en", "cs")) -> list[tuple[Path, str, str, str]]:
    """Seznam (složka, jazyk, stroj, název), které ještě nemají překlad."""
    todo = []
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT title, folder_path, source_platform FROM recipes ORDER BY title").fetchall()
    conn.close()
    for title, fp, plat in rows:
        folder = resolve_recipe_folder(fp)
        if not (folder / "recipe.json").exists():
            continue
        dev = (plat or "tm6").lower()
        prefix = get_base_prefix_for_device(folder, dev)
        for lang in langs:
            if not (folder / f"{prefix}_{lang}.json").exists() or not (folder / f"page_snapshot_{lang}.html").exists():
                todo.append((folder, lang, dev, title))
    return todo


def run_bulk_translation(todo: list):
    BULK_TR.update(running=True, stop=False, done=0, total=len(todo), failed=0, current="", errors=[])
    try:
        for folder, lang, dev, title in todo:
            if BULK_TR["stop"]:
                break
            BULK_TR["current"] = f"{title} → {lang.upper()}"
            lock = _FOLDER_LOCKS.setdefault(str(Path(folder).resolve()), threading.Lock())
            try:
                with lock:
                    res, _ = generate_translated_files(folder, lang, target_device=dev)
                if not res:
                    BULK_TR["failed"] += 1
            except Exception as e:
                BULK_TR["failed"] += 1
                BULK_TR["errors"].append(f"{title} ({lang}): {e}")
                log(f"Hromadný překlad {title} → {lang} selhal: {e}")
            BULK_TR["done"] += 1
    finally:
        BULK_TR["running"] = False
        BULK_TR["current"] = ""


# ==========================================
# RECEPTY Z DALŠÍCH WEBŮ (knihovna recipe-scrapers – volitelná: py -m pip install recipe-scrapers)
# ==========================================
_RS = {"loaded": False, "fn": None}


def has_recipe_scrapers() -> bool:
    try:
        return importlib.util.find_spec("recipe_scrapers") is not None
    except Exception:
        return False


def scrape_other_recipe(html: str, url: str) -> dict | None:
    """Název, suroviny, kroky, porce, časy a obrázek z libovolné stránky s receptem. Bez knihovny → None."""
    if not _RS["loaded"]:
        _RS["loaded"] = True
        try:
            from recipe_scrapers import scrape_html
            _RS["fn"] = scrape_html
        except Exception as e:
            log(f"recipe-scrapers není k dispozici: {e}")
    if not _RS["fn"]:
        return None
    try:
        sc = _RS["fn"](html, org_url=url, supported_only=False)
    except Exception as e:
        log(f"recipe-scrapers nerozpoznal recept na {url}: {e}")
        return None

    def get(name, default=None):
        try:
            v = getattr(sc, name)()
            return v if v not in (None, "", []) else default
        except Exception:
            return default

    steps = [s.strip() for s in (get("instructions_list", []) or []) if s and s.strip()]
    if not steps and get("instructions"):
        steps = [s.strip() for s in str(get("instructions")).split("\n") if s.strip()]
    ings = []
    groups = get("ingredient_groups", []) or []
    if len(groups) > 1:
        for gr in groups:
            if getattr(gr, "purpose", None):
                ings.append(f"▸ {gr.purpose}")
            ings.extend(getattr(gr, "ingredients", []) or [])
    else:
        ings = list(get("ingredients", []) or [])
    total = get("total_time")
    return {
        "title": get("title", ""), "ingredients": [str(x).strip() for x in ings if str(x).strip()], "steps": steps,
        "yields": str(get("yields", "") or ""), "total_time": f"{total} min" if isinstance(total, (int, float)) else str(total or ""),
        "image": get("image", ""), "site": get("site_name", "") or urllib.parse.urlparse(url).netloc,
        "language": get("language", ""), "nutrients": get("nutrients", {}) or {},
    }


def other_recipe_id(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower().replace("www.", "").split(".")[0]
    return f"web_{re.sub(r'[^a-z0-9]', '', host)[:12]}_{hashlib.sha1(url.split('#')[0].encode('utf-8')).hexdigest()[:10]}"


# ==========================================
# VYHLEDÁVÁNÍ RECEPTŮ NA WEBECH + VE VLASTNÍ KUCHAŘCE
# Webové hledání běží v aplikaci na počítači (skryté stránky prohlížeče, i s přihlášením do Cookidoo);
# stránka s výsledky (/search) se průběžně obnovuje. Zdroje jdou upravit v config.json → "search_sources".
# ==========================================
DEFAULT_SEARCH_SOURCES = [
    {"id": "cookidoo", "name": "Cookidoo", "color": "#00A651", "url": "https://cookidoo.cz/search/cs-CZ?query={q}",
     "home": "https://cookidoo.cz/foundation/cs-CZ", "icon": "🟢",
     "link": r"cookidoo\.[a-z.]+/recipes/recipe/[a-zA-Z-]+/r\d+", "enabled": True},
    {"id": "mcs", "name": "Monsieur Cuisine", "color": "#1565C0", "url": "https://www.monsieur-cuisine.com/cs/vyhledavani?q={q}",
     "home": "https://www.monsieur-cuisine.com/cs/recepty", "icon": "🔵",
     "link": r"monsieur-cuisine\.com/[a-z]{2}/recipe/[^/?#]+", "enabled": True},
    {"id": "iprima", "name": "Prima FRESH", "color": "#D81B60", "url": "https://fresh.iprima.cz/vyhledat/{q}",
     "home": "https://fresh.iprima.cz/recepty", "icon": "🍅",
     "link": r"fresh\.iprima\.cz/(?!videa/)[^#?]+", "scope": ".search-articles-list", "enabled": True},
    {"id": "chefkoch", "name": "Chefkoch", "color": "#E2001A", "url": "https://www.chefkoch.de/rs/s0/{q}/Rezepte.html",
     "home": "https://www.chefkoch.de/", "icon": "🇩🇪",
     "link": r"chefkoch\.de/rezepte/\d+/", "scope": ".recipe-list", "enabled": True},
    {"id": "allrecipes", "name": "Allrecipes", "color": "#F37021", "url": "https://www.allrecipes.com/search?q={q}",
     "home": "https://www.allrecipes.com/", "icon": "🇺🇸",
     "link": r"allrecipes\.com/(?:recipe/\d+/|[a-z0-9-]+-recipe-\d+)", "enabled": True},
    {"id": "bbcgoodfood", "name": "BBC Good Food", "color": "#7B1FA2", "url": "https://www.bbcgoodfood.com/search?q={q}",
     "home": "https://www.bbcgoodfood.com/", "icon": "🇬🇧",
     "link": r"bbcgoodfood\.com/recipes/(?!collection/|category/)[a-z0-9-]+/?$", "enabled": True},
]
SEARCH_STATE: dict = {}
_SEARCH_QUEUE: list = []
_SEARCH_LOCK = threading.Lock()
_LOCAL_ING_CACHE: dict = {}


def search_sources() -> list[dict]:
    cfg = load_config().get("search_sources")
    if isinstance(cfg, list) and cfg:
        return [s for s in cfg if isinstance(s, dict) and s.get("url") and s.get("link")]
    return DEFAULT_SEARCH_SOURCES


def search_key_of(q: str, mode: str) -> str:
    return f"{mode}|{search_key(q).strip()}"


def request_web_search(q: str, mode: str) -> dict:
    """Založí (nebo vrátí běžící) hledání; aplikace na počítači si ho vyzvedne a spustí."""
    key = search_key_of(q, mode)
    with _SEARCH_LOCK:
        st = SEARCH_STATE.get(key)
        if st is None or time.time() - st["started"] > 1800:
            st = {"q": q, "mode": mode, "started": time.time(), "sources": {
                s["id"]: {"name": s["name"], "color": s.get("color", "#555"), "state": "pending", "results": [],
                          "search_url": s["url"].replace("{q}", urllib.parse.quote(q))}
                for s in search_sources() if s.get("enabled", True)}}
            SEARCH_STATE[key] = st
            _SEARCH_QUEUE.append(key)
        return json.loads(json.dumps(st))


def _og_image(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ASSET_UA, "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            head = resp.read(400_000).decode("utf-8", "ignore")
    except Exception:
        return ""
    for pat in (r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)', r'"image"\s*:\s*(?:\[\s*)?(?:\{[^}]*"url"\s*:\s*)?"(https?://[^"]+)"'):
        m = re.search(pat, head, re.IGNORECASE)
        if m:
            return html_mod.unescape(m.group(1)).replace("{transformation}/", "")
    return ""


def fill_missing_images(key: str, source_id: str, limit: int = 16):
    """Výsledkům bez obrázku doplní obrázek z náhledu stránky receptu (og:image) – na pozadí, stránka se sama obnoví."""
    with _SEARCH_LOCK:
        s = SEARCH_STATE.get(key, {}).get("sources", {}).get(source_id)
        if not s:
            return
        todo = [r for r in s["results"] if not r.get("image")][:limit]
        s["img_pending"] = len(todo)
    for r in todo:
        img = _og_image(r["url"])
        with _SEARCH_LOCK:
            if img:
                r["image"] = img
            s["img_pending"] = max(0, s.get("img_pending", 1) - 1)


_SEARCH_STOP = {"a", "s", "se", "na", "v", "ve", "z", "ze", "do", "k", "ke", "o", "po", "pro", "bez", "and", "with",
                "the", "of", "und", "mit", "der", "die", "das"}


def rank_search_results(results: list[dict], q: str, mode: str) -> list[dict]:
    """Hledání podle názvu: výsledky, které hledané slovo opravdu obsahují (v názvu nebo adrese), dopředu.
    Slovo se porovnává bez diakritiky a podle kmene („zelňačka“ najde i „Zelná polévka“)."""
    if mode != "title":
        return results
    stems = [w[:max(4, len(w) - 3)] for w in re.findall(r'\w+', search_key(q)) if w not in _SEARCH_STOP and len(w) > 2]
    if not stems:
        return results

    def hit(r):
        blob = search_key(f"{r.get('title', '')} {urllib.parse.unquote(r.get('url', ''))}")
        return sum(1 for s in stems if s in blob)

    return sorted(results, key=lambda r: -hit(r))           # stabilní řazení: jinak pořadí webu


def local_search(q: str, mode: str, limit: int = 30) -> list[dict]:
    words = search_key(q).split()
    if not words:
        return []
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT recipe_id, title, title_en, title_cs, folder_path, source_platform, category FROM recipes").fetchall()
    conn.close()
    out = []
    for rid, title, t_en, t_cs, fp, plat, cat in rows:
        if mode == "ingredient":
            folder = resolve_recipe_folder(fp)
            rj = folder / "recipe.json"
            try:
                mt = rj.stat().st_mtime
                cached = _LOCAL_ING_CACHE.get(str(rj))
                if not cached or cached[0] != mt:
                    ings = json.loads(rj.read_text(encoding="utf-8")).get("ingredients", [])
                    cached = (mt, search_key(" ".join(ings)))
                    _LOCAL_ING_CACHE[str(rj)] = cached
                blob = cached[1]
            except Exception:
                continue
        else:
            blob = search_key(" ".join(x or "" for x in (title, t_en, t_cs)))
        if all(w in blob for w in words):
            out.append({"recipe_id": rid, "title": title, "title_en": t_en or "", "title_cs": t_cs or "", "folder": fp,
                        "platform": (plat or "tm6").lower(), "category": cat or "Nezařazené"})
    out.sort(key=lambda r: search_key(r["title"]))
    for r in out[:limit]:
        try:
            img = recipe_extras(resolve_recipe_folder(r["folder"])).get("image", "")
            rel = asset_lookup(img) if img else None
            r["image"] = ("/assets/" + rel) if rel else img
        except Exception:
            r["image"] = ""
        r.pop("folder", None)
    return out[:limit]


SEARCH_EXTRACT_JS = r"""
(() => {
  try { window.scrollBy(0, Math.max(900, window.innerHeight || 900)); } catch (e) {}   // líně načítané obrázky
  const re = new RegExp(%PATTERN%, 'i');
  const bad = /icon|logo|device-pic|avatar|sprite|placeholder|blank|spacer|\.svg/i;
  const imgSrc = el => {
    if (!el) return '';
    const vm = el.__vue__;                                 // Vue komponenty (Monsieur Cuisine) mají obrázek jen v datech
    const vsrc = vm ? (typeof vm.src === 'string' ? vm.src : (vm.src && vm.src.src) || '') : '';
    const cand = [el.currentSrc, el.getAttribute && el.getAttribute('src'), el.dataset && (el.dataset.src || el.dataset.lazySrc || el.dataset.original), vsrc];
    const ss = (el.getAttribute && (el.getAttribute('srcset') || el.getAttribute('data-srcset') || el.getAttribute('data-lazy-srcset'))) || '';
    if (ss) cand.push(ss.split(',').pop().trim().split(' ')[0]);
    if (el.attributes) for (const at of el.attributes) {
      const v = (at.value || '').trim();
      if (/^(https?:)?\/\/|^\//.test(v) && /\.(jpe?g|png|webp|avif)(\?|$|\s)|\/image|\/img|images?\//i.test(v)) cand.push(v.split(/[\s,]/)[0]);
    }
    for (const c of cand) { if (c && !c.startsWith('data:') && !bad.test(c)) { try { return new URL(c, location.href).href; } catch (e) {} } }
    return '';
  };
  const bgSrc = el => { const m = (el.getAttribute('style') || '').match(/url\(['"]?([^'")]+)/); return m && !bad.test(m[1]) ? new URL(m[1], location.href).href : ''; };
  const clean = s => (s || '').replace(/\s+/g, ' ').replace(/^(Zum Rezept|Rezept|Recipe|Recept)\s*:?\s*/i, '').trim();
  // Web nic nenašel a místo výsledků ukazuje „populární recepty“ (MCS, Allrecipes…) → žádné výsledky
  const pageText = (document.body && document.body.innerText) || '';
  if (/(^|[^\d])0\s+(recept|rezept|recipe|result|ergebnis|treffer)|nebyly nalezeny žádné|nenašli jsme žádn|žádné výsledky|keine (rezepte|ergebnisse|treffer)|no results|nothing found|no recipes found/i.test(pageText))
    return JSON.stringify({none: true});
  const out = new Map();
  const scopeSel = %SCOPE%;
  const root = scopeSel ? document.querySelector(scopeSel) : document;
  if (!root) return JSON.stringify([]);
  for (const a of root.querySelectorAll('a[href]')) {
    const href = a.href.split('#')[0];
    if (!re.test(href)) continue;
    const e = out.get(href) || {url: href, title: '', image: '', meta: ''};
    let card = a;
    for (let i = 0; i < 7 && card; i++) {
      const links = new Set([...card.querySelectorAll('a[href]')].map(x => x.href.split('#')[0]).filter(h => re.test(h)));
      if (links.size > 1) break;
      if (!e.image) { for (const im of card.querySelectorAll('img, source, .v-image, [class*="image" i]')) { const s = imgSrc(im); if (s) { e.image = s; break; } } }
      if (!e.image) { for (const el of [card, ...card.querySelectorAll('[style*="url("]')]) { const s = bgSrc(el); if (s) { e.image = s; break; } } }
      if (!e.image) { for (const ns of card.querySelectorAll('noscript')) { const m = (ns.textContent || '').match(/src=["']([^"']+\.(?:jpe?g|png|webp)[^"']*)/i); if (m) { e.image = new URL(m[1], location.href).href; break; } } }
      if (!e.title) { const h = card.querySelector('h1,h2,h3,h4,h5,[class*="title" i],[class*="name" i]'); if (h && clean(h.innerText).length > 2) e.title = clean(h.innerText); }
      if (!e.meta) { const m = (card.innerText || '').match(/\d+\s*(min|hod|h|Std|Min)\.?(?:\s*\d+\s*min\.?)?/); if (m) e.meta = m[0]; }
      if (e.image && e.title) break;
      card = card.parentElement;
    }
    if (!e.title) e.title = clean(a.getAttribute('aria-label') || a.title || (a.querySelector('img') || {}).alt || '');
    if (!e.title) e.title = clean((a.innerText || '').split('\n').find(x => x.trim().length > 3) || '');
    if (!e.title) { try { e.title = decodeURIComponent(href.split('/').filter(Boolean).pop().replace(/\.html?$/, '').replace(/[-_]+/g, ' ').replace(/^\d+\s*/, '')); } catch (err) {} }
    out.set(href, e);
  }
  return JSON.stringify([...out.values()].filter(x => x.title && x.title.length > 2).slice(0, 24));
})()
"""


SEARCH_PAGE_HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recipe search</title>
<style>
 :root { --bg:#141414; --card:#1F1F1F; --muted:#9E9E9E; --txt:#EDEDED; --accent:#00E676; }
 * { box-sizing:border-box; }
 body { margin:0; background:var(--bg); color:var(--txt); font:15px/1.45 'Segoe UI',Roboto,sans-serif; }
 .wrap { max-width:1280px; margin:0 auto; padding:22px 18px 60px; }
 h1 { font-size:26px; margin:6px 0 4px; } .sub { color:var(--muted); margin-bottom:16px; }
 form { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px; }
 input[type=text] { flex:1; min-width:220px; font-size:18px; padding:12px 14px; border-radius:10px; border:1px solid #3A3A3A; background:#202020; color:var(--txt); }
 .seg { display:flex; border:1px solid #3A3A3A; border-radius:10px; overflow:hidden; }
 .seg label { padding:11px 14px; cursor:pointer; color:#CFCFCF; user-select:none; } .seg input { display:none; }
 .seg input:checked + span { color:#fff; font-weight:bold; } .seg label:has(input:checked) { background:#2E7D32; }
 button.go { font-size:17px; padding:11px 22px; border-radius:10px; border:0; background:#E65100; color:#fff; font-weight:bold; cursor:pointer; }
 .hint { color:#FFB74D; margin:6px 0 18px; font-size:14px; }
 .chips { display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 18px; }
 .chip { padding:6px 12px; border-radius:20px; background:#262626; color:#DDD; text-decoration:none; font-size:14px; border:1px solid #333; }
 .sites { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:-6px 0 18px; }
 .sl { color:var(--muted); font-size:14px; margin-right:4px; }
 a.site { display:inline-flex; align-items:center; gap:6px; padding:7px 14px; border-radius:8px; color:#fff; text-decoration:none; font-weight:bold; font-size:14px; border:1px solid rgba(255,255,255,.12); }
 a.site:hover { filter:brightness(1.15); }
 section { margin:22px 0; }
 .sh { display:flex; align-items:center; gap:10px; margin-bottom:10px; }
 .badge { padding:3px 10px; border-radius:20px; font-weight:bold; font-size:13px; color:#fff; }
 .state { color:var(--muted); font-size:14px; } .state a { color:#B39DDB; }
 .grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(210px, 1fr)); gap:14px; }
 a.card { display:flex; flex-direction:column; background:var(--card); border-radius:12px; overflow:hidden; text-decoration:none; color:var(--txt); border:1px solid #2A2A2A; transition:transform .12s, border-color .12s; }
 a.card:hover { transform:translateY(-2px); border-color:#555; }
 .img { aspect-ratio:4/3; background:#2A2A2A center/cover no-repeat; position:relative; }
 .img.noimg::after { content:'🍽️'; position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:46px; opacity:.35; }
 .img .src { position:absolute; left:8px; top:8px; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:bold; color:#fff; }
 .ok { color:#69F0AE; font-weight:bold; margin-left:6px; }
 .t { padding:10px 12px 4px; font-weight:600; line-height:1.3; } .m { padding:0 12px 10px; color:var(--muted); font-size:13px; }
 .spin { display:inline-block; width:12px; height:12px; border:2px solid #666; border-top-color:#fff; border-radius:50%; animation:s 0.8s linear infinite; vertical-align:-1px; }
 @keyframes s { to { transform:rotate(360deg); } }
 .empty { color:var(--muted); padding:30px 0; text-align:center; }
</style></head><body><div class="wrap">
<h1 id="h"></h1><div class="sub" id="sub"></div>
<form id="f" action="/search" method="get">
 <input type="text" name="q" id="q" autocomplete="off">
 <div class="seg"><label><input type="radio" name="mode" value="title"><span id="m1"></span></label><label><input type="radio" name="mode" value="ingredient"><span id="m2"></span></label></div>
 <input type="hidden" name="ui" id="ui"><input type="hidden" name="desk" id="desk">
 <button class="go" id="go" type="submit"></button>
</form>
<div class="hint" id="hint"></div>
<div class="chips" id="chips"></div>
<div class="sites"><span class="sl" id="sl"></span><span id="sites"></span></div>
<div id="res"></div>
</div>
<script>
const P = new URLSearchParams(location.search);
const UI = P.get('ui') || 'cs', DESK = P.get('desk') === '1', Q = (P.get('q') || '').trim(), MODE = P.get('mode') === 'ingredient' ? 'ingredient' : 'title';
const TT = {cs: {h:'🔎 Hledat recepty', sub:'Ve vlastní kuchařce i na webech s recepty – podle názvu nebo suroviny.', m1:'Název', m2:'Surovina', go:'Hledat',
  ph:'např. kulajda, svíčková, cuketa…', hint:'Otevři recept z webu a klikni nahoře na ⬇️ ULOŽIT RECEPT – uloží se do offline kuchařky.',
  mine:'📚 Moje kuchařka', wait:'hledám…', none:'nic nenalezeno', fail:'nepodařilo se načíst', open:'otevřít hledání na webu', found:'nalezeno',
  saved:'v kuchařce', sites:'Procházet weby:', start:'Zadej název receptu nebo surovinu.', mobile:'Na mobilu se otevře původní web; uložit recept jde v aplikaci na počítači.'},
 en: {h:'🔎 Search recipes', sub:'In your own cookbook and on recipe websites – by name or ingredient.', m1:'Name', m2:'Ingredient', go:'Search',
  ph:'e.g. goulash, risotto, zucchini…', hint:'Open a recipe from a website and click ⬇️ SAVE RECIPE at the top – it is saved to your offline cookbook.',
  mine:'📚 My cookbook', wait:'searching…', none:'nothing found', fail:'could not be loaded', open:'open the search on the website', found:'found',
  saved:'in cookbook', sites:'Browse websites:', start:'Enter a recipe name or an ingredient.', mobile:'On a phone the original website opens; saving works in the desktop app.'}}[UI === 'en' ? 'en' : 'cs'];
for (const k of ['h','sub','m1','m2','go']) document.getElementById(k).textContent = TT[k];
const qi = document.getElementById('q'); qi.placeholder = TT.ph; qi.value = Q;
document.querySelector(`input[name=mode][value=${MODE}]`).checked = true;
document.getElementById('ui').value = UI; document.getElementById('desk').value = DESK ? '1' : '0';
document.getElementById('hint').textContent = DESK ? TT.hint : TT.mobile;
const esc = s => String(s || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const PLAT = {tm6: ['Cookidoo', '#00A651'], mcs: ['Monsieur Cuisine', '#1565C0'], other: ['Web', '#424242']};
function card(r, srcName, color, local){
  const title = local ? ((UI === 'en' && r.title_en) || (UI === 'cs' && r.title_cs) || r.title) : r.title;
  const href = local ? (DESK ? '/open?id=' + encodeURIComponent(r.recipe_id) : '/#open=' + encodeURIComponent(r.recipe_id)) : r.url;
  const tgt = (!local && !DESK) ? ' target="_blank" rel="noopener"' : '';
  const img = r.image ? `style="background-image:url('${esc(r.image)}')"` : '';
  return `<a class="card" href="${esc(href)}"${tgt}><div class="img${r.image ? '' : ' noimg'}" ${img}><span class="src" style="background:${color}">${esc(srcName)}</span></div>
    <div class="t">${esc(title)}</div><div class="m">${esc(r.meta || r.category || '')}${r.saved ? ` <span class="ok">✓ ${TT.saved}</span>` : ''}</div></a>`;
}
async function poll(){
  if (!Q) { document.getElementById('res').innerHTML = `<div class="empty">${TT.start}</div>`; return; }
  let d; try { d = await (await fetch(`/api/search?q=${encodeURIComponent(Q)}&mode=${MODE}&ui=${UI}`)).json(); } catch (e) { setTimeout(poll, 1500); return; }
  let html = '';
  const loc = d.local || [];
  if (loc.length) html += `<section><div class="sh"><span class="badge" style="background:#2E7D32">${TT.mine}</span><span class="state">${TT.found}: ${loc.length}</span></div><div class="grid">` +
      loc.map(r => card(r, (PLAT[r.platform] || PLAT.other)[0], (PLAT[r.platform] || PLAT.other)[1], true)).join('') + '</div></section>';
  let pending = false;
  for (const [id, s] of Object.entries(d.sources || {})) {
    if (s.img_pending) pending = true;
    let st;
    if (s.state === 'pending') { pending = true; st = `<span class="spin"></span> ${TT.wait}`; }
    else if (s.results.length) st = `${TT.found}: ${s.results.length}`;
    else st = `${s.state === 'error' ? TT.fail : TT.none} – <a href="${esc(s.search_url)}"${DESK ? '' : ' target="_blank"'}>${TT.open}</a>`;
    html += `<section><div class="sh"><span class="badge" style="background:${s.color}">${esc(s.name)}</span><span class="state">${st}</span></div>` +
      (s.results.length ? `<div class="grid">${s.results.map(r => card(r, s.name, s.color, false)).join('')}</div>` : '') + '</section>';
  }
  document.getElementById('res').innerHTML = html;
  if (pending) setTimeout(poll, 900);
}
const CH = UI === 'en' ? ['pancakes', 'goulash', 'risotto', 'bread', 'chocolate cake'] : ['kulajda', 'svíčková', 'guláš', 'chléb', 'bábovka', 'rizoto'];
document.getElementById('chips').innerHTML = CH.map(c => `<a class="chip" href="/search?q=${encodeURIComponent(c)}&mode=title&ui=${UI}&desk=${DESK ? 1 : 0}">${c}</a>`).join('');
document.getElementById('sl').textContent = TT.sites;
fetch('/api/sources').then(r => r.json()).then(list => {
  document.getElementById('sites').innerHTML = list.map(s => `<a class="site" style="background:${esc(s.color)}" href="${esc(s.home)}"${DESK ? '' : ' target="_blank" rel="noopener"'}>${esc(s.icon || '')} ${esc(s.name)}</a>`).join(' ');
}).catch(() => {});
poll();
</script></body></html>"""


class LanCookidooHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_html(self, html: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(LAN_WEB_APP_HTML.encode("utf-8"))
            return

        if parsed.path == "/api/recipes":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT recipe_id, title, category, is_favorite, source_platform, title_en, title_cs FROM recipes ORDER BY category, is_favorite DESC, title")
            items = [{
                "recipe_id": r[0],
                "title": r[1],
                "category": r[2] or "Nezařazené",
                "category_en": CATEGORY_EN.get(r[2] or "Nezařazené", r[2] or "Nezařazené"),
                "is_favorite": bool(r[3]),
                "source_platform": r[4] or "tm6",
                "title_en": r[5] or "",
                "title_cs": r[6] or "",
                "search": search_key(" ".join(x or "" for x in (r[1], r[5], r[6], r[2]))),
            } for r in c.fetchall()]
            conn.close()
            resp_obj = {"icon_style": load_icon_style(), "ui_lang": ui_lang(), "items": items}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(resp_obj, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/api/recipe":
            qs = urllib.parse.parse_qs(parsed.query)
            r_id = qs.get("id", [""])[0]
            lang = qs.get("lang", ["orig"])[0]
            device = qs.get("device", ["tm6"])[0].lower()
            is_mcs = (device == "mcs")
            use_fine = qs.get("fine", ["1"])[0] == "1"
            ui = qs.get("ui", [ui_lang()])[0]
            try:
                scale = float(qs.get("scale", ["1.0"])[0])
            except ValueError:
                scale = 1.0

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT folder_path, source_platform FROM recipes WHERE recipe_id = ?", (r_id,))
            row = c.fetchone()
            conn.close()

            if not row:
                self.send_error(404)
                return

            folder = resolve_recipe_folder(row[0])
            source_plat = (row[1] or "tm6").lower()

            ensure_device_recipe_file(folder, device)
            prefix = get_base_prefix_for_device(folder, device)

            json_file = folder / (f"{prefix}.json" if lang == "orig" else f"{prefix}_{lang}.json")
            tr_info = {"status": "orig"}
            if lang in ("en", "cs"):
                if json_file.exists():
                    tr_info = {"status": "done"}
                elif not translation_available():
                    tr_info = {"status": "unavailable",
                               "message": txl("⚠️ Překladač není nastaven – v desktopové aplikaci zadej ✨ Gemini klíč nebo nainstaluj argostranslate. Zobrazuji originál.", ui)}
                    json_file = folder / f"{prefix}.json"
                else:
                    job = start_translation_job(folder, lang, device)
                    if job["state"] == "failed":
                        tr_info = {"status": "failed", "message": txl("❌ Překlad selhal: {err} – zobrazuji originál.", ui, err=job.get('error') or txl('neznámá chyba', ui))}
                    else:
                        tr_info = {"status": "pending", "message": txl("⏳ Překládám… zatím zobrazuji originál, stránka se sama obnoví.", ui)}
                    json_file = folder / f"{prefix}.json"

            if not json_file.exists():
                json_file = folder / "recipe.json"

            if not json_file.exists():
                self.send_error(404)
                return

            data = json.loads(json_file.read_text(encoding="utf-8"))
            if tr_info.get("status") == "done":
                tr_info["message"] = describe_translation(data, ui)
            plain_ings = [scale_ingredient_line(i, scale) for i in data.get("ingredients", [])]
            scaled_ings = [convert_text_to_metric(i, html_highlight=True) for i in plain_ings]

            enriched_steps = []
            step_list = get_fine_steps(data) if use_fine else data.get("steps", [])
            all_matches = match_recipe_ingredients([s.get("text", "") or _plain(s.get("html")) for s in step_list], list(data.get("ingredients", [])))
            for si, st in enumerate(step_list):
                raw_step_html = st.get("html") or st.get("text", "")
                formatted_html = convert_text_to_metric(scale_step_text(format_tm_icons_html(raw_step_html, is_mcs=is_mcs, ui=ui), scale), html_highlight=True)
                matched = all_matches[si]
                for mi, m_item in enumerate(matched):
                    part = m_item.pop("part", "")
                    m_item["text"] = scaled_ings[mi] + (f" <span style='color:#FFB74D;'>({txl('teď', ui)} {scale_ingredient_line(part, scale)})</span>" if part and m_item["active"] else "")
                dials = dict(st.get("dials") or extract_tm_dials(st.get("text", "")))
                dials["time"] = normalize_dial_time(dials.get("time"))
                enriched_steps.append({
                    "text": st.get("text", ""),
                    "html": raw_step_html,
                    "formatted_html": formatted_html,
                    "dials": dials,
                    "parent": st.get("parent"),
                    "matched_ings": matched
                })

            resp = {
                "recipe_id": r_id,
                "title": data.get("title", r_id),
                "source_platform": source_plat,
                "device": device,
                "ingredients": scaled_ings,
                "steps": enriched_steps,
                "fine": use_fine,
                "translation": tr_info
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(resp, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/api/card":
            qs = urllib.parse.parse_qs(parsed.query)
            r_id = qs.get("id", [""])[0]
            lang = qs.get("lang", ["orig"])[0]

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT folder_path, source_platform FROM recipes WHERE recipe_id = ?", (r_id,))
            row = c.fetchone()
            conn.close()

            if not row:
                self.send_error(404)
                return

            folder = resolve_recipe_folder(row[0])
            card_dev = (row[1] or "tm6").lower()
            ensure_clean_html_snapshot(folder)
            is_translated_card = False

            if lang in ("en", "cs"):
                target_html = folder / f"page_snapshot_{lang}.html"
                retry = qs.get("retry", ["0"])[0] == "1"
                if retry:
                    clear_translation(folder, lang)
                if target_html.exists():
                    html_file, is_translated_card = target_html, True
                elif not translation_available():
                    html_file = folder / "page_snapshot.html"
                else:
                    job = start_translation_job(folder, lang, card_dev, force=retry)
                    self._send_html(_card_wait_page(job, r_id, lang))
                    return
            else:
                html_file = folder / "page_snapshot.html"

            if not html_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h3>{tx('Karta receptu není pro tento recept k dispozici.')}</h3>".encode("utf-8"))
                return

            raw_html = html_file.read_text(encoding="utf-8", errors="ignore")
            try:
                raw_html, missing_assets = rewrite_card_html(raw_html, _recipe_page_url(folder), self.headers.get("Host") or f"127.0.0.1:{LAN_PORT}")
                if missing_assets:
                    schedule_page_assets(folder)
            except Exception as e:
                log(f"Přepis karty na uložené styly selhal: {e}")
            clean_css = """
            <style>
              header, core-header, .page-header, .l-header, nav,
              [class*="header__"], [class*="Header"], .core-nav,
              core-transclusion, footer, .cookie-banner, #onetrust-consent-sdk {
                  display: none !important; height: 0 !important; visibility: hidden !important;
              }
              *[style*="position: fixed"], *[style*="position: sticky"] { position: static !important; }
              body, main, .recipe-card, #recipe-content { padding-top: 15px !important; margin-top: 0 !important; }
            </style>
            """
            if "</head>" in raw_html:
                raw_html = raw_html.replace("</head>", clean_css + "</head>", 1)
            else:
                raw_html = clean_css + raw_html
            if is_translated_card:
                retry_link = (f"<div style='background:#1A1A2E;padding:6px 14px;font:14px Segoe UI,sans-serif;'>"
                              f"<a href='/api/card?id={urllib.parse.quote(r_id)}&lang={lang}&retry=1' "
                              f"style='color:#B39DDB;font-weight:bold;'>{tx('🔄 Přeložit znovu')}</a></div>")
                raw_html = re.sub(r"(<div id='cc-tr-banner'[^>]*>.*?</div>)", lambda m: m.group(1) + retry_link, raw_html, count=1, flags=re.S)

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(raw_html.encode("utf-8"))
            return

        if parsed.path == "/search":
            self._send_html(SEARCH_PAGE_HTML)
            return

        if parsed.path == "/api/search":
            qs = urllib.parse.parse_qs(parsed.query)
            q = qs.get("q", [""])[0].strip()
            mode = "ingredient" if qs.get("mode", ["title"])[0] == "ingredient" else "title"
            resp = {"q": q, "mode": mode, "local": [], "sources": {}}
            if q:
                try:
                    resp["local"] = local_search(q, mode)
                    if qs.get("ui", ["cs"])[0] == "en":
                        for r in resp["local"]:
                            r["category"] = CATEGORY_EN.get(r["category"], r["category"])
                except Exception as e:
                    log(f"Hledání v kuchařce selhalo: {e}")
                resp["sources"] = request_web_search(q, mode)["sources"]
                conn = sqlite3.connect(DB_PATH)
                have = {r[0] for r in conn.execute("SELECT recipe_id FROM recipes")}
                conn.close()
                for srcd in resp["sources"].values():
                    for res in srcd["results"]:
                        u = res.get("url", "")
                        m_ck = re.search(r"cookidoo\.[^/]+/recipes/recipe/[^/]+/(r\d+)", u)
                        m_mc = re.search(r"monsieur-cuisine\.com/[a-z]{2}/recipe/([^/?#]+)", u)
                        mc_slug = re.sub(r'[^\w-]', '', m_mc.group(1))[:36] if m_mc else ""
                        cand = m_ck.group(1) if m_ck else ("mcs_" + mc_slug if m_mc else other_recipe_id(u))
                        res["saved"] = cand in have
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(resp, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/api/sources":
            lst = [{"id": s["id"], "name": s["name"], "color": s.get("color", "#555"), "icon": s.get("icon", ""),
                    "home": s.get("home") or "https://" + urllib.parse.urlparse(s["url"]).netloc + "/"}
                   for s in search_sources() if s.get("enabled", True)]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(lst, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/open":
            r_id = urllib.parse.parse_qs(parsed.query).get("id", [""])[0]
            self._send_html(f"<meta http-equiv='refresh' content='0;url=/api/card?id={urllib.parse.quote(r_id)}'>")
            return

        if parsed.path == "/api/sheet":
            qs = urllib.parse.parse_qs(parsed.query)
            r_id = qs.get("id", [""])[0]
            lang = qs.get("lang", ["orig"])[0]
            ui = qs.get("ui", [ui_lang()])[0]
            dev = qs.get("device", [""])[0].lower() or None
            try:
                scale = float(qs.get("scale", ["1"])[0])
            except ValueError:
                scale = 1.0
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute("SELECT folder_path FROM recipes WHERE recipe_id = ?", (r_id,)).fetchone()
            conn.close()
            if not row:
                self.send_error(404)
                return
            folder = resolve_recipe_folder(row[0])
            try:
                img_url = recipe_extras(folder).get("image", "")
                img_src = ""
                if img_url:
                    rel = asset_lookup(img_url)
                    if rel:
                        img_src = "/assets/" + rel
                    else:
                        img_src = img_url
                        threading.Thread(target=cache_asset, args=(img_url, img_url), daemon=True).start()
                card_url = f"/api/card?id={urllib.parse.quote(r_id)}&lang={lang}"
                self._send_html(render_recipe_sheet(folder, lang, dev, ui, "web", scale, True, img_src, card_url))
            except Exception as e:
                log("List receptu selhal:\n" + traceback.format_exc())
                self._send_html(f"<h3>{html_mod.escape(str(e))}</h3>")
            return

        if parsed.path.startswith("/assets/"):
            target = serve_asset_path(parsed.path[len("/assets/"):])
            if not target:
                self.send_error(404)
                return
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if target.suffix == ".css":
                ctype = "text/css; charset=utf-8"
            elif target.suffix == ".woff2":
                ctype = "font/woff2"
            elif target.suffix == ".woff":
                ctype = "font/woff"
            data = target.read_bytes()
            if target.suffix == ".css":                # písma a obrázky uvnitř stylů taky z uložených kopií
                data = localize_css(data.decode("utf-8", "replace"), self.headers.get("Host") or f"127.0.0.1:{LAN_PORT}").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
            return

        if parsed.path == "/api/retranslate":
            qs = urllib.parse.parse_qs(parsed.query)
            r_id = qs.get("id", [""])[0]
            lang = qs.get("lang", ["en"])[0]
            device = qs.get("device", ["tm6"])[0].lower()
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute("SELECT folder_path FROM recipes WHERE recipe_id = ?", (r_id,)).fetchone()
            conn.close()
            if not row or lang not in ("en", "cs"):
                self.send_error(404)
                return
            folder = resolve_recipe_folder(row[0])
            clear_translation(folder, lang)
            state = start_translation_job(folder, lang, device, force=True)["state"] if translation_available() else "unavailable"
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "state": state}).encode("utf-8"))
            return

        self.send_error(404)


def _card_wait_page(job: dict, r_id: str, lang: str) -> str:
    style = "body{background:#121212;color:#eee;font-family:Segoe UI,sans-serif;display:flex;align-items:center;justify-content:center;height:90vh;text-align:center;} a{color:#B39DDB;font-weight:bold;}"
    if job.get("state") == "failed":
        retry = f"/api/card?id={urllib.parse.quote(r_id)}&lang={lang}&retry=1"
        body = (f"<div><h3>{tx('❌ Překlad karty se nepodařil')}</h3><p>{job.get('error') or tx('neznámá chyba')}</p>"
                f"<p><a href='{retry}'>{tx('🔄 Zkusit znovu')}</a></p></div>")
        return f"<!doctype html><html><head><meta charset='utf-8'><style>{style}</style></head><body>{body}</body></html>"
    secs = int(time.time() - job.get("started", time.time()))
    return (f"<!doctype html><html><head><meta charset='utf-8'><meta http-equiv='refresh' content='3'><style>{style}</style></head>"
            f"<body><div><h3>{tx('⏳ Překládám kartu do {lang}…', lang=lang.upper())}</h3><p>{tx('Stránka se obnoví sama ({s} s).', s=secs)}</p></div></body></html>")


LAN_STATE = {"ok": False}


def start_lan_http_server():
    try:
        server = ThreadingHTTPServer(("0.0.0.0", LAN_PORT), LanCookidooHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        LAN_STATE["ok"] = True
    except Exception as e:
        log(f"LAN server error: {e}")


def local_card_url(recipe_id: str, lang: str = "orig") -> str:
    return f"http://127.0.0.1:{LAN_PORT}/api/card?id={urllib.parse.quote(recipe_id)}&lang={lang}"


def is_offline_card_url(url_str: str) -> bool:
    return url_str.startswith("file://") or url_str.startswith(f"http://127.0.0.1:{LAN_PORT}/api/card")


# ==========================================
# ZÁLOHA RECEPTŮ (.7z): export vybraných receptů a jejich import – i na jiném počítači
# Archiv: manifest.json + recipes/<složka receptu>/… + web_assets/<styly, písma, obrázky karet>
#         + web_assets/index.part.json (adresa z webu → soubor), aby karta receptu fungovala i bez internetu.
# ==========================================
try:
    import py7zr
except Exception:                         # volitelné – bez knihovny jsou export a import jen vypnuté
    py7zr = None

EXPORT_DIR = BASE_DIR / "exported_recipes"
BACKUP_FORMAT = "localchef-recipes"
BACKUP_VERSION = 1
_ASSET_REL_RE = re.compile(r'^[a-z_]+/[a-z]+/[0-9a-f]{24}\.[A-Za-z0-9]{1,6}$')


def has_py7zr() -> bool:
    return py7zr is not None


def _card_asset_entries(folder: Path) -> dict:
    """Soubory z web_assets, které karta receptu potřebuje – i písma a obrázky, na které odkazují styly."""
    page_url = _recipe_page_url(folder)
    amap = _asset_map()
    todo: list[str] = []
    for snap in folder.glob("page_snapshot*.html"):
        try:
            todo += html_asset_urls(snap.read_text(encoding="utf-8", errors="ignore"), page_url)
        except Exception:
            pass
    try:
        img = recipe_extras(folder).get("image")            # obrázek pro PDF a mobil
        if img:
            todo.append(img)
    except Exception:
        pass
    out: dict = {}
    while todo:
        u = todo.pop()
        if u in out:
            continue
        e = amap.get(u)
        if not e or not _ASSET_REL_RE.match(str(e.get("file", ""))) or not (WEB_ASSETS_DIR / e["file"]).exists():
            continue
        out[u] = {"file": e["file"], "kind": e.get("kind", "")}
        if e["file"].endswith(".css"):
            css = (WEB_ASSETS_DIR / e["file"]).read_text(encoding="utf-8", errors="ignore")
            todo += [m.group(2).strip() for m in CSS_URL_RE.finditer(css)] + [m.group(2) for m in CSS_IMPORT_RE.finditer(css)]
    return out


def backup_file_name(titles: list[str]) -> str:
    stamp = time.strftime("%Y-%m-%d_%H%M")
    if len(titles) == 1:
        safe = re.sub(r'[\\/:*?"<>|]+', "_", titles[0]).strip()[:80] or "recept"
        return f"{safe}.7z"
    return f"recepty_{len(titles)}_{stamp}.7z"


def export_recipes_backup(folders: list, target: Path) -> dict:
    """Zabalí vybrané recepty (celé složky: kroky, překlady, převody, karta, doplňky) do jednoho .7z."""
    if py7zr is None:
        raise RuntimeError(tx("Chybí knihovna py7zr (py -m pip install py7zr)."))
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    recipes, assets, n_files = [], {}, 0
    tmp = target.with_name(target.name + ".tmp")
    with py7zr.SevenZipFile(tmp, "w") as z:
        for folder in [Path(f) for f in folders]:
            rj = folder / "recipe.json"
            if not rj.exists() or (folder / DELETED_MARK).exists():
                continue
            data = json.loads(rj.read_text(encoding="utf-8"))
            for f in sorted(folder.rglob("*")):
                if f.is_file():
                    z.write(f, f"recipes/{folder.name}/{f.relative_to(folder).as_posix()}")
                    n_files += 1
            recipes.append({"folder": folder.name, "recipe_id": data.get("recipe_id", ""), "title": data.get("title", ""),
                            "category": data.get("category", ""), "platform": data.get("source_platform", "")})
            assets.update(_card_asset_entries(folder))
        files = {}
        for e in assets.values():
            files[e["file"]] = WEB_ASSETS_DIR / e["file"]
        for rel, path in sorted(files.items()):
            z.write(path, f"web_assets/{rel}")
        z.writestr(json.dumps(assets, ensure_ascii=False, indent=0).encode("utf-8"), "web_assets/index.part.json")
        manifest = {"format": BACKUP_FORMAT, "version": BACKUP_VERSION, "app": APP_NAME, "app_version": APP_VERSION,
                    "created": time.strftime("%Y-%m-%d %H:%M:%S"), "recipes": recipes}
        z.writestr(json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"), "manifest.json")
    if not recipes:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(tx("Žádný z vybraných receptů nejde exportovat."))
    os.replace(tmp, target)
    log(f"Export receptů: {len(recipes)} receptů, {len(files)} souborů karet → {target}")
    return {"path": str(target), "recipes": len(recipes), "files": n_files, "assets": len(files),
            "size": target.stat().st_size}


def _backup_name_ok(name: str) -> bool:
    """Do zálohy smí jen manifest, složky receptů a soubory karet – nic mimo ně (žádné ../, absolutní cesty)."""
    parts = name.replace("\\", "/").split("/")
    if not name or name.startswith(("/", "\\")) or ":" in name or any(p in ("", ".", "..") for p in parts):
        return False
    if parts in (["manifest.json"], ["recipes"], ["web_assets"]):
        return True
    if parts[0] == "recipes":
        return len(parts) >= 2 and not parts[1].startswith(".")
    if parts[0] == "web_assets":
        rest = "/".join(parts[1:])
        return rest == "index.part.json" or len(parts) <= 3 or bool(_ASSET_REL_RE.match(rest))
    return False


def stage_recipe_backups(paths: list) -> dict:
    """1. krok importu: rozbalí zálohy do dočasné složky, zkontroluje je a zjistí, které recepty už v kuchařce jsou."""
    if py7zr is None:
        raise RuntimeError(tx("Chybí knihovna py7zr (py -m pip install py7zr)."))
    tmp = Path(tempfile.mkdtemp(prefix="localchef_import_"))
    conn = sqlite3.connect(DB_PATH)
    known = {r[0] for r in conn.execute("SELECT recipe_id FROM recipes")}
    conn.close()
    stage = {"tmp": str(tmp), "items": [], "asset_dirs": [], "errors": []}
    seen = set()
    for i, p in enumerate(paths):
        p = Path(p)
        out = tmp / f"a{i}"
        try:
            with py7zr.SevenZipFile(p, "r") as z:
                names = z.getnames()
                bad = [n for n in names if not _backup_name_ok(n)]
                if bad or "manifest.json" not in names:
                    raise ValueError(tx("není to záloha receptů z této aplikace") + (f" ({bad[0]})" if bad else ""))
                z.extractall(path=out)
            man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            if man.get("format") != BACKUP_FORMAT:
                raise ValueError(tx("není to záloha receptů z této aplikace"))
        except Exception as e:
            stage["errors"].append(f"{p.name}: {e}")
            continue
        stage["asset_dirs"].append(str(out / "web_assets"))
        rdir = out / "recipes"
        for folder in sorted(rdir.iterdir()) if rdir.is_dir() else []:
            try:
                data = json.loads((folder / "recipe.json").read_text(encoding="utf-8"))
            except Exception:
                stage["errors"].append(f"{p.name}: {folder.name} – " + tx("chybí recipe.json"))
                continue
            rid = str(data.get("recipe_id") or "").strip()
            if not rid or rid in seen:
                continue
            seen.add(rid)
            stage["items"].append({"src": str(folder), "folder": folder.name, "recipe_id": rid,
                                   "title": data.get("title") or folder.name,
                                   "exists": rid in known or (RECIPES_DIR / folder.name).exists()})
    return stage


def apply_recipe_backups(stage: dict, overwrite: bool) -> dict:
    """2. krok importu: zkopíruje recepty do kuchařky a doplní soubory karet. Přepisovaný recept jde do koše
    (recipes_smazane), takže nic nezmizí natrvalo. Dočasnou složku nakonec smaže."""
    res = {"imported": 0, "replaced": 0, "skipped": 0, "assets": 0, "errors": list(stage.get("errors", []))}
    try:
        for it in stage["items"]:
            src = Path(it["src"])
            if it["exists"]:
                if not overwrite:
                    res["skipped"] += 1
                    continue
                conn = sqlite3.connect(DB_PATH)
                rows = conn.execute("SELECT folder_path FROM recipes WHERE recipe_id = ?", (it["recipe_id"],)).fetchall()
                for (fp,) in rows:
                    move_recipe_to_trash(resolve_recipe_folder(fp))
                conn.execute("DELETE FROM recipes WHERE recipe_id = ?", (it["recipe_id"],))
                conn.commit()
                conn.close()
                if (RECIPES_DIR / src.name).exists():
                    move_recipe_to_trash(RECIPES_DIR / src.name)
            target = RECIPES_DIR / src.name
            if target.exists():                       # nešlo přesunout do koše (otevřený soubor…)
                res["errors"].append(f"{it['title']}: " + tx("složku receptu nejde nahradit"))
                continue
            shutil.copytree(src, target)
            res["replaced" if it["exists"] else "imported"] += 1
        # soubory karet: stejný název = stejný obsah, takže jen doplnit chybějící
        added = {}
        for d in stage.get("asset_dirs", []):
            d = Path(d)
            try:
                part = json.loads((d / "index.part.json").read_text(encoding="utf-8"))
            except Exception:
                continue
            for url, e in part.items():
                rel = str((e or {}).get("file", ""))
                src = d / rel
                if not _ASSET_REL_RE.match(rel) or not src.is_file():
                    continue
                dst = WEB_ASSETS_DIR / rel
                if not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    res["assets"] += 1
                added[url] = {"file": rel, "kind": e.get("kind", ""), "checked": time.time()}
        if added:
            amap = _asset_map()
            with _ASSET_LOCK:
                for url, e in added.items():
                    if not (amap.get(url) and (WEB_ASSETS_DIR / amap[url]["file"]).exists()):
                        amap[url] = e
                _asset_save_index()
    finally:
        shutil.rmtree(stage.get("tmp", ""), ignore_errors=True)
    sync_catalog_from_folders()
    try:
        backfill_translated_titles()
    except Exception:
        pass
    log(f"Import receptů: nové {res['imported']}, nahrazené {res['replaced']}, přeskočené {res['skipped']}, "
        f"soubory karet {res['assets']}, chyby {len(res['errors'])}")
    return res


# ==========================================
# VERZE, CO JE NOVÉHO, PODMÍNKY POUŽITÍ
# ==========================================
WHATS_NEW = {
    "1.5": {
        "cs": [
            "💛 Nové tlačítko Podpořit vývoj: pokud se vám aplikace líbí, můžete autora podpořit přes Ko-fi, PayPal nebo "
            "Revolut (i naskenováním QR kódu). Podpora je zcela dobrovolná, aplikace zůstává zdarma.",
            "📦 Hromadné stahování celých kolekcí a seznamů receptů bylo odstraněno. Hromadné vytěžování obsahu webů jde proti "
            "pravidlům EU na ochranu databází (směrnice 96/9/ES) i proti podmínkám webů. Recepty se dál ukládají jednotlivě "
            "tlačítkem ⬇️ ULOŽIT RECEPT.",
        ],
        "en": [
            "💛 New Donation button: if you like the app, you can support the author via Ko-fi, PayPal or Revolut (also by "
            "scanning a QR code). Support is entirely voluntary, the app stays free.",
            "📦 Bulk download of whole recipe collections and lists has been removed. Bulk extraction of website content goes "
            "against the EU database protection rules (Directive 96/9/EC) and against the websites' terms. Recipes are still "
            "saved one at a time with the ⬇️ SAVE RECIPE button.",
        ],
    },
    "1.4": {
        "cs": [
            "🌍 Při startu aplikace zkontroluje offline překladač. Když chybí, nabídne stažení (ANO / NE) s volbou "
            "„Příště se již neptat“. Kdykoli později ho stáhneš v ⚙️ Nastavení → 📥 Stáhnout offline překladač.",
            "📄 Dokumentace a návod v PDF jsou aktualizované pro LocalChef Studio (složka docs).",
        ],
        "en": [
            "🌍 At start the app checks the offline translator. If it is missing, it offers to download it (YES / NO) with a "
            "“Don’t ask again” option. You can download it any time later in ⚙️ Settings → 📥 Download offline translator.",
            "📄 The PDF documentation and user guide are updated for LocalChef Studio (docs folder).",
        ],
    },
    "1.3": {
        "cs": [
            "🥄 Nový název: LocalChef Studio – offline kuchařka a průvodce vařením s robotem. Aplikace už neumí jen Cookidoo, proto "
            "nese vlastní jméno bez cizích ochranných známek. Datová složka se jmenuje localchef_data; data ze starší verze "
            "se při prvním startu převezmou samy – recepty, nastavení i přihlášení zůstávají.",
            "📦 Záloha receptů: označ recepty (Ctrl/Shift + klik, nebo celou kategorii), pravé tlačítko → Exportovat zálohu. "
            "Uloží se do jednoho souboru .7z ve složce exported_recipes – i s překlady, převody a kartou receptu.",
            "📥 Import receptů: tlačítko vlevo nahraje jednu nebo víc záloh .7z najednou, už není potřeba kopírovat složky. "
            "Recepty, které už máš, můžeš přepsat (stará verze jde do koše), nebo ponechat.",
            "❓ Vestavěný návod k použití (česky i anglicky): co kde je, jak funguje offline překlad a proč a jak zdarma "
            "získat klíče Gemini a DeepL.",
            "🔎 Hledání na webech už neukazuje nesouvisející recepty: když web nic nenajde a nabídne „populární recepty“, "
            "aplikace je nebere. Výsledky s hledaným slovem jsou první.",
            "🧹 Recepty z ostatních webů (třeba Prima FRESH) se ukládají bez balastu: jen skutečné kroky, tipy zvlášť a karta "
            "receptu očištěná od reklam a článků, autor receptu zůstává.",
            "🤖 Komunitní recepty Monsieur Cuisine mají čisté kroky „Název: postup“ a správně načtenou teplotu (℃) i rychlost.",
            "◀ Tlačítko Zpět je teď první, 🏠 Domů hned za ním.",
            "🐳 Docker verze (build_docker.bat) – aplikace v prohlížeči na http://localhost:6080/.",
        ],
        "en": [
            "🥄 New name: LocalChef Studio – Offline Cookbook & Kitchen Robot Guide. The app does far more than Cookidoo now, so it "
            "has its own name without other companies' trademarks. The data folder is now localchef_data; data from an older version "
            "are taken over automatically on first start – recipes, settings and logins stay.",
            "📦 Recipe backup: select recipes (Ctrl/Shift + click, or a whole category), right-click → Export backup. They are "
            "saved into one .7z file in the exported_recipes folder – with translations, conversions and the recipe card.",
            "📥 Recipe import: the button on the left loads one or more .7z backups at once – no more copying folders. Recipes you "
            "already have can be replaced (the old version goes to the trash) or kept.",
            "❓ Built-in user guide (Czech and English): what is where, how offline translation works and why and how to get "
            "free Gemini and DeepL keys.",
            "🔎 Web search no longer shows unrelated recipes: when a site finds nothing and offers “popular recipes”, the app "
            "ignores them. Results containing the search word come first.",
            "🧹 Recipes from other sites (e.g. Prima FRESH) are saved without clutter: only real steps, tips kept separately "
            "and a recipe card cleaned of ads and articles, with the recipe's author kept.",
            "🤖 Monsieur Cuisine community recipes get clean “Name: method” steps and correctly read temperature (℃) and speed.",
            "◀ The Back button now comes first, 🏠 Home right after it.",
            "🐳 Docker version (build_docker.bat) – the app in your browser at http://localhost:6080/.",
        ],
    },
    "1.1": {
        "cs": [
            "🔎 Vyhledávání receptů na webech (Cookidoo, Monsieur Cuisine, Prima FRESH, Chefkoch, Allrecipes, BBC Good Food) i ve vlastní kuchařce – podle názvu nebo suroviny. Výsledky jsou přehledně na úvodní stránce i se zdrojem.",
            "⚫ Ukládání receptů i z dalších webů (stovky podporovaných webů přes knihovnu recipe-scrapers, ostatní přes standardní značení receptů). Mají černou ikonku a vlastní filtr „Jen ostatní weby“.",
            "🤖 Recepty z ostatních webů jdou vařit v režimu TM6 i Monsieur Cuisine: s klíčem Gemini je převede umělá inteligence, bez klíče je převede offline asistent (navrhne čas, teplotu a rychlost u kroků, které jde dělat v robotu, a ostatní označí jako ruční).",
            "Když později zadáš klíč Gemini, převody udělané offline asistentem se při dalším otevření samy vylepší přes Gemini.",
        ],
        "en": [
            "🔎 Recipe search across websites (Cookidoo, Monsieur Cuisine, Prima FRESH, Chefkoch, Allrecipes, BBC Good Food) and your own cookbook – by name or ingredient. Results appear on the start page together with their source.",
            "⚫ Save recipes from other websites too (hundreds of supported sites via the recipe-scrapers library, others via standard recipe markup). They have a black icon and their own filter “Other sites only”.",
            "🤖 Recipes from other websites can be cooked in TM6 and Monsieur Cuisine mode: with a Gemini key the AI converts them, without a key the offline assistant does (it suggests time, temperature and speed for steps that can be done in the machine and marks the others as manual).",
            "If you add a Gemini key later, conversions made by the offline assistant are upgraded via Gemini the next time you open them.",
        ],
    },
    "1.0": {
        "cs": [
            "První očíslovaná verze aplikace.",
            "Ukládání receptů z Cookidoo (Thermomix) a Monsieur Cuisine do offline kuchařky.",
            "Režim vaření krok po kroku pro TM6 i Monsieur Cuisine, s jemnými kroky a automatickým převodem mezi stroji.",
            "Karta receptu – uložená stránka receptu funguje i bez internetu; styly a obrázky se ukládají jen jednou.",
            "Překlad receptů do češtiny a angličtiny: DeepL → Gemini → offline překladač; hromadný překlad celé kuchařky.",
            "Správné jednotky v překladu (lžička, lžíce, balíček…) a jednotné nastavení stroje (rychlost, sek, °C).",
            "Chytřejší zvýraznění surovin v kroku – i když se surovina v receptu opakuje nebo se použije jen část.",
            "Přehledné PDF receptu na jednu stránku: fotka, nutriční hodnoty, suroviny, postup a tipy.",
            "Mobilní aplikace přes Wi-Fi (QR kód) – vlastní volba jazyka a karta upravená pro telefon.",
            "Kategorie (i vlastní), oblíbené, hledání bez ohledu na diakritiku, menu na pravém tlačítku.",
            "Přenos receptů: stačí zkopírovat jejich složky; smazané recepty jdou do koše recipes_smazane.",
        ],
        "en": [
            "First numbered version of the app.",
            "Save recipes from Cookidoo (Thermomix) and Monsieur Cuisine into an offline cookbook.",
            "Step-by-step cooking mode for TM6 and Monsieur Cuisine, with detailed steps and automatic conversion between machines.",
            "Recipe card – the saved recipe page works offline; styles and images are stored only once.",
            "Recipe translation into Czech and English: DeepL → Gemini → offline translator; bulk translation of the whole cookbook.",
            "Correct units in translations (tsp, tbsp, pack…) and consistent machine settings (speed, sec, °C).",
            "Smarter ingredient highlighting in each step – even when an ingredient repeats or only part of it is used.",
            "Clean one-page recipe PDF: photo, nutrition, ingredients, method and tips.",
            "Mobile app over Wi-Fi (QR code) – its own language switch and a card made for phones.",
            "Categories (including your own), favorites, accent-insensitive search, right-click menu.",
            "Sharing recipes: just copy their folders; deleted recipes go to the recipes_smazane trash folder.",
        ],
    },
}

DISCLAIMER_TEXT = {
    "cs": [
        ("Vzdělávací a osobní účel",
         "Tento nástroj byl vyvinut pro vzdělávací účely (zpracování dat z webu, překlad, převod receptů mezi kuchyňskými "
         "roboty) a pro osobní potřebu. Neslouží k pirátství, k obcházení předplatného, placeného obsahu ani jiných omezení "
         "přístupu a nesmí se k nim používat."),
        ("Nezávislý projekt",
         "Aplikace LocalChef Studio není spojena se společnostmi Vorwerk (Thermomix, Cookidoo) ani Lidl / Hoyer Handel (Monsieur Cuisine), "
         "není jimi schválena ani podporována. Uvedené názvy jsou ochranné známky svých vlastníků a aplikace je používá "
         "jen k označení webů a zařízení, se kterými spolupracuje."),
        ("Autorská práva",
         "Recepty, texty, fotografie a grafika patří jejich autorům a provozovatelům webů. Ukládejte jen recepty, ke kterým "
         "máte legální přístup (např. vlastní předplatné), a nezveřejňujte, neprodávejte ani hromadně nešiřte je. "
         "Za předání receptů jiným osobám odpovídáte sami."),
        ("Podmínky webů",
         "Ukládání stránek může omezovat podmínky použití daného webu. Uživatel je povinen je dodržovat; za jejich porušení "
         "nebo zablokování účtu odpovídá uživatel, ne autor aplikace."),
        ("Bez záruky",
         "Aplikace se poskytuje „tak, jak je“, bez jakékoli záruky. Autor neodpovídá za ztrátu dat ani jiné škody."),
        ("Vaření a bezpečnost",
         "Převody mezi stroji, přepočty a překlady jsou strojové a mohou být chybné. Před vařením zkontrolujte teploty, "
         "časy, rychlosti, množství a alergeny a řiďte se návodem ke svému zařízení."),
        ("Překlady a klíče",
         "Při překladu přes DeepL nebo Gemini se texty receptů odesílají těmto službám. API klíče zůstávají jen ve vašem "
         "počítači (config.json) – nikomu je nedávejte."),
    ],
    "en": [
        ("Educational and personal use",
         "This tool was developed for educational purposes (processing web data, translating and converting recipes between "
         "kitchen machines) and for personal use. It is not meant for piracy or for getting around subscriptions, paid "
         "content or any other access restrictions, and must not be used for that."),
        ("Independent project",
         "LocalChef Studio is not affiliated with, endorsed or supported by Vorwerk (Thermomix, Cookidoo) or Lidl / Hoyer Handel "
         "(Monsieur Cuisine). The names mentioned are trademarks of their owners and are used only to identify the "
         "websites and appliances the app works with."),
        ("Copyright",
         "Recipes, texts, photos and graphics belong to their authors and the website operators. Save only recipes you have "
         "legitimate access to (e.g. your own subscription) and do not publish, sell or mass-distribute them. You alone are "
         "responsible for sharing recipes with others."),
        ("Website terms",
         "Saving pages may be restricted by a website's terms of use. Users must follow them; the user, not the author of the "
         "app, is responsible for any breach of terms or account suspension."),
        ("No warranty",
         "The app is provided “as is”, without warranty of any kind. The author is not liable for data loss or other damage."),
        ("Cooking and safety",
         "Conversions between machines, recalculations and translations are machine-made and may contain mistakes. Check "
         "temperatures, times, speeds, quantities and allergens before cooking and follow your appliance's manual."),
        ("Translations and keys",
         "When translating with DeepL or Gemini, recipe texts are sent to those services. API keys stay only on your "
         "computer (config.json) – never share them."),
    ],
}


# Vestavěný návod (❓ Návod). Kapitoly = (nadpis, HTML). Odkazy se otevřou v prohlížeči počítače.
GEMINI_KEY_URL = "https://aistudio.google.com/app/apikey"
DEEPL_KEY_URL = "https://www.deepl.com/pro-api"
HOW_TO_GUIDE = {
    "cs": [
        ("Co LocalChef Studio umí",
         "<p><b>LocalChef Studio</b> je offline kuchařka. Recepty z webu (Cookidoo pro Thermomix, Monsieur Cuisine a stovky dalších "
         "webů s recepty) si uložíš do počítače a pak je máš i bez internetu: jako kartu receptu, jako PDF, v telefonu "
         "přes Wi-Fi a hlavně v <b>režimu vaření krok po kroku</b> pro Thermomix TM6 i Monsieur Cuisine. Recepty umí převést "
         "mezi oběma roboty, přeložit do češtiny a angličtiny a přepočítat na jiný počet porcí.</p>"),
        ("Rychlý start",
         "<ol><li>Klikni na <b>🏠 Domů</b> a napiš, co chceš vařit (název nebo surovinu). Uvidíš recepty ze své kuchařky i z webů.</li>"
         "<li>Otevři recept, který se ti líbí, a klikni na <b>⬇️ ULOŽIT RECEPT</b>. Vyber kategorii.</li>"
         "<li>Recept se objeví v seznamu vlevo. Klikni na něj a vyber zobrazení: <b>📄 Karta</b>, <b>🍲 TM6</b> nebo <b>🤖 MCS</b>.</li>"
         "<li>Vař podle kroků, šipkami <b>◀ / ▶</b> se posouváš.</li></ol>"),
        ("Horní lišta",
         "<ul><li><b>◀ Zpět</b> – předchozí stránka ve vestavěném prohlížeči.</li>"
         "<li><b>🏠 Domů</b> – úvodní stránka s hledáním v tvé kuchařce i na webech (Cookidoo, Monsieur Cuisine, Prima FRESH, "
         "Chefkoch, Allrecipes, BBC Good Food). Hledat jde podle názvu nebo podle suroviny.</li>"
         "<li><b>🟢 Cookidoo.cz</b> a <b>🔵 Monsieur-Cuisine</b> – otevřou web daného robota.</li>"
         "<li><b>⬇️ ULOŽIT RECEPT</b> – uloží právě otevřený recept.</li>"
         "<li><b>❓ Návod</b> – tenhle návod. <b>⚙️ Nastavení</b> – překladače, klíče, jazyk a vzhled (viz níže).</li></ul>"),
        ("Ukládání receptů",
         "<ul><li><b>Cookidoo</b> (Thermomix) potřebuje tvé předplatné: přihlas se jednou ve vestavěném prohlížeči "
         "(🟢 Cookidoo.cz), přihlášení vydrží i po restartu.</li>"
         "<li><b>Monsieur Cuisine</b> recepty jsou veřejné, ukládají se bez účtu.</li>"
         "<li><b>Ostatní weby</b> – najdi recept přes 🏠 Domů a ulož ho stejně. Aplikace z něj vezme jen recept: suroviny, "
         "postup a tipy, karta receptu je očištěná od reklam a souvisejících článků (autor receptu zůstává). Stránky jen "
         "s videem uložit nejde.</li>"
         "<li>Uložení stejného receptu znovu ho přepíše a smaže jeho staré převody a překlady – hodí se, když se něco "
         "uložilo špatně.</li></ul>"),
        ("Kuchařka vlevo",
         "<ul><li>Recepty jsou podle kategorií; <b>➕ Nová kategorie</b> založí vlastní. Pravé tlačítko na receptu otevře "
         "menu (přesun do kategorie, oblíbené, smazání).</li>"
         "<li>Filtry: všechny stroje / 🟢 jen Cookidoo / 🔵 jen Monsieur Cuisine / ⚫ jen ostatní weby, ⭐ oblíbené.</li>"
         "<li>Hledání nedbá na diakritiku (<i>kulajda</i> najde <i>Kulajda</i>).</li>"
         "<li>„Názvy“ přepíná, jestli seznam ukazuje původní, nebo přeložené názvy.</li>"
         "<li><b>🗑️ Smazat</b> přesune recept do koše <code>recipes_smazane</code> – nic se nemaže natrvalo.</li>"
         "<li>Víc receptů označíš <b>Ctrl + klik</b> (jednotlivě) nebo <b>Shift + klik</b> (rozsah); kliknutím na kategorii "
         "označíš všechny její recepty.</li></ul>"),
        ("Recept a režim vaření",
         "<ul><li><b>📄 Karta receptu</b> – uložená stránka receptu, funguje bez internetu.</li>"
         "<li><b>🍲 Režim Thermomix (TM6)</b> a <b>🤖 Monsieur Cuisine Smart (MCS)</b> – kroky s časem, teplotou a "
         "rychlostí. Recept z jednoho robota se pro druhý převede sám (s klíčem Gemini přes umělou inteligenci, jinak "
         "offline pravidly). Recepty z ostatních webů převede offline asistent: kroky, které jdou dělat v robotu, dostanou "
         "nastavení, ostatní jsou označené jako ruční.</li>"
         "<li><b>🔍 Jemné kroky</b> rozdělí postup na drobné úkony, <b>📏 Metrické</b> převede unce a šálky na gramy a "
         "mililitry, <b>⚖️ Dávka</b> přepočítá množství. Suroviny k aktuálnímu kroku jsou zvýrazněné.</li>"
         "<li><b>🌐 Originál / 🇬🇧 English / 🇨🇿 Čeština</b> přepne jazyk receptu, <b>🔄 Přeložit znovu</b> udělá překlad "
         "znovu, <b>🖨️ Export do PDF</b> uloží přehledný list na jednu stránku.</li>"
         "<li>⚠️ Převody a překlady dělá stroj. Před vařením zkontroluj teploty, časy a rychlosti.</li></ul>"),
        ("Překlady a offline překladač",
         "<p>Aplikace zkouší překladače v pořadí <b>DeepL → Gemini → offline překladač</b>. Když jeden nemá klíč, "
         "vyčerpá limit nebo nefunguje internet, použije další. Hotový překlad se uloží k receptu, takže se překládá jen jednou.</p>"
         "<p><b>Offline překladač</b> (Argos Translate) funguje bez internetu a bez klíčů:</p>"
         "<ol><li>V sestavené aplikaci (exe) už je. Při spuštění z Pythonu ho nainstaluj: <code>py -m pip install argostranslate</code>.</li>"
         "<li>Jednou otevři <b>⚙️ → 📥 Stáhnout offline překladač</b> a nech stáhnout jazykové modely (čeština, angličtina, němčina). "
         "Na to je potřeba internet, každý model má desítky až stovky MB.</li>"
         "<li>Potom překládá i úplně offline. Běží v samostatném procesu, takže první překlad po startu chvíli trvá "
         "(načítá modely). Kvalita je slabší než u DeepL a Gemini, ale pro recepty stačí.</li></ol>"
         "<p><b>⚙️ → 🌍 Přeložit všechny recepty</b> přeloží celou kuchařku na pozadí.</p>"),
        ("Proč zadat API klíče a jak je získat (zdarma)",
         "<p>Klíče nejsou povinné – aplikace funguje i bez nich. S nimi je ale výrazně lepší:</p>"
         "<ul><li><b>Gemini</b> (Google AI) dělá nejlepší <b>převody mezi TM6 a Monsieur Cuisine</b> a převody receptů "
         "z ostatních webů na kroky robota a umí kvalitně překládat. Převody udělané bez klíče se po jeho zadání samy "
         "vylepší.</li>"
         "<li><b>DeepL</b> je nejpřesnější <b>překladač</b> – přirozená čeština, správné jednotky.</li></ul>"
         f"<p><b>Gemini klíč</b> – zdarma, bez platební karty:</p><ol><li>Otevři <a href='{GEMINI_KEY_URL}'>{GEMINI_KEY_URL}</a> "
         "a přihlas se Google účtem.</li><li>Klikni na <b>Create API key</b> (Vytvořit klíč) a klíč zkopíruj "
         "(začíná <code>AIza</code>).</li><li>V aplikaci <b>⚙️ → ✨ Gemini AI klíč</b> ho vlož.</li></ol>"
         "<p>Bezplatná úroveň má limity na počet dotazů za minutu a za den. Když se vyčerpají, aplikace použije další "
         "překladač. Do bezplatné úrovně neposílej citlivé osobní údaje – Google s nimi zachází jinak než u placené. "
         "Recepty jsou v pořádku.</p>"
         f"<p><b>DeepL klíč</b> – tarif <b>DeepL API Free</b> je zdarma a dá 500 000 znaků měsíčně (stovky receptů):</p>"
         f"<ol><li>Otevři <a href='{DEEPL_KEY_URL}'>{DEEPL_KEY_URL}</a> a zaregistruj se do <b>DeepL API Free</b>.</li>"
         "<li>DeepL může chtít platební kartu jen pro ověření totožnosti; tarif Free se nestrhává.</li>"
         "<li>V účtu v části <b>API Keys</b> zkopíruj klíč (končí <code>:fx</code>) a vlož ho do <b>⚙️ → 🔑 DeepL</b>.</li></ol>"
         "<p>🔒 Klíče zůstávají jen v tvém počítači v souboru <code>localchef_data/config.json</code>. Nikomu je nedávej. "
         "Při překladu se text receptu odešle zvolené službě.</p>"),
        ("Mobil přes Wi-Fi",
         "<p>Klikni na <b>📱 QR kód</b> a naskenuj ho telefonem. Telefon musí být na stejné Wi-Fi jako počítač a aplikace "
         "musí běžet. V telefonu je seznam receptů, režim vaření, karta upravená pro mobil, hledání a vlastní přepínač "
         "čeština/angličtina. Když se telefon nepřipojí, povol aplikaci ve firewallu Windows (port 3665).</p>"),
        ("⚙️ Nastavení",
         "<ul><li><b>Překlad</b>: přeložit všechny recepty, ✨ Gemini AI klíč, 📥 Stáhnout offline překladač (stav a stažení), "
         "🔑 DeepL klíč.</li><li><b>Vzhled</b>: jazyk aplikace (čeština/angličtina), tmavý/světlý režim, styl ikon "
         "receptů (🟢/🔵 nebo 🍲/🤖).</li><li><b>Aplikace</b>: co je nového a podmínky použití.</li></ul>"),
        ("Data a záloha",
         "<p>Vše je ve složce <code>localchef_data</code> vedle programu: <code>catalog.db</code> (seznam), "
         "<code>recipes/</code> (recepty, každý ve vlastní složce), <code>recipes_smazane/</code> (koš), "
         "<code>config.json</code> (nastavení a klíče), <code>browser_profile/</code> (přihlášení), <code>app.log</code> (záznam činnosti).</p>"
         "<ul><li><b>Celá záloha</b> = zkopíruj celou složku <code>localchef_data</code>.</li>"
         "<li><b>Přenos receptů</b> = složky receptů můžeš zkopírovat i ručně do <code>recipes/</code>, aplikace je při startu "
         "sama přidá. Pohodlnější je záloha .7z (další kapitola).</li>"
         "<li><code>config.json</code> a <code>browser_profile</code> nikomu nedávej (klíče a přihlášení).</li></ul>"),
        ("Záloha a import receptů (.7z)",
         "<p>Recepty jde přenést na jiný počítač nebo poslat kamarádovi jako jeden soubor:</p>"
         "<ol><li>V seznamu vlevo označ recepty – <b>Ctrl + klik</b>, <b>Shift + klik</b> nebo klikni na celou kategorii.</li>"
         "<li>Pravé tlačítko → <b>📦 Exportovat zálohu (.7z)</b>, nebo tlačítko <b>📦 Exportovat označené</b> pod seznamem.</li>"
         "<li>Vyber, kam soubor uložit – výchozí je složka <code>localchef_data/exported_recipes</code>. Záloha obsahuje vše: "
         "suroviny a kroky, překlady, převody pro TM6 i MCS a kartu receptu i s jejími styly a obrázky.</li></ol>"
         "<p><b>Import:</b> tlačítko <b>📥 Importovat recepty (.7z)</b> vlevo – vyber jeden nebo víc souborů .7z. Kategorie a "
         "oblíbené se zachovají. Když některý recept už v kuchařce máš, aplikace se zeptá: <b>Ano</b> = přepsat verzí ze "
         "zálohy (současná jde do koše <code>recipes_smazane</code>), <b>Ne</b> = ponechat současnou.</p>"
         "<p>⚠️ Recepty jsou chráněné autorským právem – zálohy jsou pro tvou vlastní potřebu, nešiř je hromadně.</p>"),
        ("Docker verze",
         "<p><b>Experimentální:</b> aplikace je psaná hlavně pro Windows, verze pro Docker nebyla otestovaná v běžném provozu.</p>"
         "<p>LocalChef Studio jde spustit i v Dockeru (potřebuješ Docker Desktop). Dvojklik na <code>build_docker.bat</code> sestaví "
         "obraz (poprvé i desítky minut) a spustí ho. Aplikace se pak ovládá v prohlížeči na "
         "<a href='http://localhost:6080/'>http://localhost:6080/</a>, telefon se připojí přes QR kód jako obvykle (port 3665).</p>"
         "<ul><li><code>build_docker.bat noargos</code> vynechá offline překladač – obraz je o zhruba 2 GB menší.</li>"
         "<li>Data kontejneru jsou ve složce <code>docker_data\\localchef_data</code>, oddělená od Windows verze (dvě "
         "aplikace nad jednou kuchařkou by si přepisovaly data). Recepty přeneseš zkopírováním jejich složek do "
         "<code>docker_data\\localchef_data\\recipes</code>.</li>"
         "<li>Do Cookidoo se v Dockeru přihlásíš zvlášť a klíče zadáš znovu v ⚙️.</li>"
         "<li>Zastavení: <code>docker stop localchef</code>, znovu: <code>docker start localchef</code>.</li></ul>"),
        ("Když něco nejde",
         "<ul><li><b>Recept nerozpoznán</b> – zkus stejný recept z jiného webu přes 🏠 Domů nebo nainstaluj "
         "<code>recipe-scrapers</code>.</li><li><b>Překlad trvá dlouho</b> – offline překladač napoprvé načítá modely; "
         "s klíčem DeepL nebo Gemini je to rychlejší.</li><li><b>Divné kroky</b> – recept ulož znovu.</li>"
         "<li>Podrobnosti o tom, co aplikace dělala, jsou v <code>localchef_data/app.log</code>.</li></ul>"),
    ],
    "en": [
        ("What LocalChef Studio does",
         "<p><b>LocalChef Studio</b> is an offline cookbook. Save recipes from the web (Cookidoo for Thermomix, Monsieur Cuisine and "
         "hundreds of other recipe sites) to your computer and keep them without internet: as a recipe card, as a PDF, on "
         "your phone over Wi-Fi and above all in a <b>step-by-step cooking mode</b> for Thermomix TM6 and Monsieur Cuisine. "
         "It converts recipes between the two machines, translates them into Czech and English and scales them to other "
         "portions.</p>"),
        ("Quick start",
         "<ol><li>Click <b>🏠 Home</b> and type what you want to cook (a name or an ingredient). You will see recipes from "
         "your cookbook and from websites.</li>"
         "<li>Open a recipe you like and click <b>⬇️ SAVE RECIPE</b>. Pick a category.</li>"
         "<li>The recipe appears in the list on the left. Click it and choose a view: <b>📄 Card</b>, <b>🍲 TM6</b> or <b>🤖 MCS</b>.</li>"
         "<li>Cook along the steps; <b>◀ / ▶</b> moves between them.</li></ol>"),
        ("Top bar",
         "<ul><li><b>◀ Back</b> – previous page in the built-in browser.</li>"
         "<li><b>🏠 Home</b> – start page that searches your cookbook and websites (Cookidoo, Monsieur Cuisine, Prima FRESH, "
         "Chefkoch, Allrecipes, BBC Good Food) by name or by ingredient.</li>"
         "<li><b>🟢 Cookidoo.cz</b> and <b>🔵 Monsieur-Cuisine</b> – open the machine's website.</li>"
         "<li><b>⬇️ SAVE RECIPE</b> – saves the recipe that is open.</li>"
         "<li><b>❓ How to use</b> – this guide. <b>⚙️ Settings</b> – translators, keys, language and appearance (see below).</li></ul>"),
        ("Saving recipes",
         "<ul><li><b>Cookidoo</b> (Thermomix) needs your subscription: log in once in the built-in browser "
         "(🟢 Cookidoo.cz); the login survives restarts.</li>"
         "<li><b>Monsieur Cuisine</b> recipes are public and save without an account.</li>"
         "<li><b>Other sites</b> – find a recipe via 🏠 Home and save it the same way. Only the recipe is kept: ingredients, "
         "method and tips; the recipe card is cleaned of ads and related articles (the recipe's author stays). Video-only "
         "pages cannot be saved.</li>"
         "<li>Saving the same recipe again replaces it and removes its old conversions and translations – useful when "
         "something was saved wrong.</li></ul>"),
        ("Cookbook on the left",
         "<ul><li>Recipes are sorted into categories; <b>➕ New category</b> adds your own. Right-click a recipe for a "
         "menu (move to category, favorite, delete).</li>"
         "<li>Filters: all machines / 🟢 Cookidoo only / 🔵 Monsieur Cuisine only / ⚫ other sites only, ⭐ favorites.</li>"
         "<li>Search ignores accents (<i>kulajda</i> finds <i>Kulajda</i>).</li>"
         "<li>“Names” switches the list between original and translated recipe names.</li>"
         "<li><b>🗑️ Delete</b> moves a recipe to the <code>recipes_smazane</code> trash folder – nothing is deleted for good.</li>"
         "<li>Select several recipes with <b>Ctrl + click</b> (one by one) or <b>Shift + click</b> (a range); clicking a category "
         "selects all its recipes.</li></ul>"),
        ("Recipe and cooking mode",
         "<ul><li><b>📄 Recipe card</b> – the saved recipe page, works offline.</li>"
         "<li><b>🍲 Thermomix mode (TM6)</b> and <b>🤖 Monsieur Cuisine Smart (MCS)</b> – steps with time, temperature and "
         "speed. A recipe for one machine is converted for the other automatically (with a Gemini key by AI, otherwise by "
         "offline rules). Recipes from other sites are converted by the offline assistant: steps that can be done in the "
         "machine get settings, the rest are marked as manual.</li>"
         "<li><b>🔍 Detailed steps</b> splits the method into small actions, <b>📏 Metric</b> converts ounces and cups to "
         "grams and millilitres, <b>⚖️ Batch</b> scales the amounts. Ingredients for the current step are highlighted.</li>"
         "<li><b>🌐 Original / 🇬🇧 English / 🇨🇿 Čeština</b> switches the recipe language, <b>🔄 Translate again</b> redoes "
         "the translation, <b>🖨️ Export to PDF</b> saves a clean one-page sheet.</li>"
         "<li>⚠️ Conversions and translations are machine-made. Check temperatures, times and speeds before cooking.</li></ul>"),
        ("Translations and the offline translator",
         "<p>The app tries translators in this order: <b>DeepL → Gemini → offline translator</b>. When one has no key, runs "
         "out of quota or there is no internet, it uses the next one. A finished translation is stored with the recipe, so "
         "each recipe is translated only once.</p>"
         "<p>The <b>offline translator</b> (Argos Translate) works without internet and without keys:</p>"
         "<ol><li>The built app (exe) already includes it. When running from Python, install it: "
         "<code>py -m pip install argostranslate</code>.</li>"
         "<li>Open <b>⚙️ → 📥 Download offline translator</b> once and let it download the language models (Czech, English, German). "
         "This needs internet; each model is tens to hundreds of MB.</li>"
         "<li>After that it translates fully offline. It runs in a separate process, so the first translation after start "
         "takes a moment (loading models). Quality is below DeepL and Gemini but fine for recipes.</li></ol>"
         "<p><b>⚙️ → 🌍 Translate all recipes</b> translates the whole cookbook in the background.</p>"),
        ("Why add API keys and how to get them (free)",
         "<p>Keys are optional – the app works without them. With them it is much better:</p>"
         "<ul><li><b>Gemini</b> (Google AI) gives the best <b>conversions between TM6 and Monsieur Cuisine</b> and from "
         "other sites' recipes to machine steps, and translates well. Conversions made without a key are upgraded "
         "automatically once you add one.</li>"
         "<li><b>DeepL</b> is the most accurate <b>translator</b> – natural wording, correct units.</li></ul>"
         f"<p><b>Gemini key</b> – free, no payment card:</p><ol><li>Open <a href='{GEMINI_KEY_URL}'>{GEMINI_KEY_URL}</a> "
         "and sign in with a Google account.</li><li>Click <b>Create API key</b> and copy the key (it starts with "
         "<code>AIza</code>).</li><li>Paste it in the app under <b>⚙️ → ✨ Gemini AI key</b>.</li></ol>"
         "<p>The free tier has limits per minute and per day. When they run out, the app uses the next translator. Don't "
         "send sensitive personal data to the free tier – Google handles it differently from the paid tier. Recipes are fine.</p>"
         f"<p><b>DeepL key</b> – the <b>DeepL API Free</b> plan costs nothing and gives 500,000 characters a month (hundreds of recipes):</p>"
         f"<ol><li>Open <a href='{DEEPL_KEY_URL}'>{DEEPL_KEY_URL}</a> and sign up for <b>DeepL API Free</b>.</li>"
         "<li>DeepL may ask for a payment card for identity verification only; the Free plan is not charged.</li>"
         "<li>In your account under <b>API Keys</b>, copy the key (it ends with <code>:fx</code>) and paste it under "
         "<b>⚙️ → 🔑 DeepL</b>.</li></ol>"
         "<p>🔒 Keys stay only on your computer in <code>localchef_data/config.json</code>. Never share them. When "
         "translating, the recipe text is sent to the chosen service.</p>"),
        ("Phone over Wi-Fi",
         "<p>Click <b>📱 QR code</b> and scan it with your phone. The phone must be on the same Wi-Fi as the computer and "
         "the app must be running. The phone gets the recipe list, cooking mode, a card made for phones, search and its own "
         "Czech/English switch. If the phone can't connect, allow the app in Windows Firewall (port 3665).</p>"),
        ("⚙️ Settings",
         "<ul><li><b>Translation</b>: translate all recipes, ✨ Gemini AI key, 📥 Download offline translator (status and "
         "download), 🔑 DeepL key.</li><li><b>Appearance</b>: app language (Czech/English), dark/light mode, recipe icon "
         "style (🟢/🔵 or 🍲/🤖).</li><li><b>App</b>: what's new and terms of use.</li></ul>"),
        ("Data and backup",
         "<p>Everything is in the <code>localchef_data</code> folder next to the program: <code>catalog.db</code> (the "
         "list), <code>recipes/</code> (one folder per recipe), <code>recipes_smazane/</code> (trash), <code>config.json</code> "
         "(settings and keys), <code>browser_profile/</code> (logins), <code>app.log</code> (activity log).</p>"
         "<ul><li><b>Full backup</b> = copy the whole <code>localchef_data</code> folder.</li>"
         "<li><b>Moving recipes</b> = you can still copy recipe folders into <code>recipes/</code> by hand; the app adds them at "
         "start. A .7z backup is easier (next chapter).</li>"
         "<li>Never give anyone <code>config.json</code> or <code>browser_profile</code> (keys and logins).</li></ul>"),
        ("Recipe backup and import (.7z)",
         "<p>Recipes can be moved to another computer or sent to a friend as a single file:</p>"
         "<ol><li>Select recipes in the list on the left – <b>Ctrl + click</b>, <b>Shift + click</b> or click a whole category.</li>"
         "<li>Right-click → <b>📦 Export backup (.7z)</b>, or the <b>📦 Export selected</b> button below the list.</li>"
         "<li>Choose where to save the file – by default <code>localchef_data/exported_recipes</code>. The backup contains "
         "everything: ingredients and steps, translations, TM6 and MCS conversions and the recipe card with its styles and images.</li></ol>"
         "<p><b>Import:</b> the <b>📥 Import recipes (.7z)</b> button on the left – pick one or more .7z files. Categories and "
         "favourites are kept. If a recipe is already in your cookbook, the app asks: <b>Yes</b> = replace it with the backup "
         "version (the current one goes to the <code>recipes_smazane</code> trash), <b>No</b> = keep the current one.</p>"
         "<p>⚠️ Recipes are protected by copyright – backups are for your own use, do not distribute them widely.</p>"),
        ("Docker version",
         "<p><b>Experimental:</b> the app is written mainly for Windows; the Docker version has not been tested in everyday use.</p>"
         "<p>LocalChef Studio can also run in Docker (you need Docker Desktop). Double-click <code>build_docker.bat</code>: it builds "
         "the image (the first time can take tens of minutes) and starts it. You then use the app in your browser at "
         "<a href='http://localhost:6080/'>http://localhost:6080/</a>; the phone connects via the QR code as usual (port 3665).</p>"
         "<ul><li><code>build_docker.bat noargos</code> leaves out the offline translator – the image is about 2 GB smaller.</li>"
         "<li>The container's data live in <code>docker_data\\localchef_data</code>, separate from the Windows version (two "
         "apps on one cookbook would overwrite each other's data). Move recipes by copying their folders into "
         "<code>docker_data\\localchef_data\\recipes</code>.</li>"
         "<li>In Docker you log in to Cookidoo separately and enter your keys again in ⚙️.</li>"
         "<li>Stop: <code>docker stop localchef</code>, start again: <code>docker start localchef</code>.</li></ul>"),
        ("When something goes wrong",
         "<ul><li><b>Recipe not recognised</b> – try the same recipe from another site via 🏠 Home, or install "
         "<code>recipe-scrapers</code>.</li><li><b>Translation is slow</b> – the offline translator loads its models the "
         "first time; DeepL or Gemini keys are faster.</li><li><b>Odd steps</b> – save the recipe again.</li>"
         "<li>Details of what the app did are in <code>localchef_data/app.log</code>.</li></ul>"),
    ],
}


def how_to_html(lang: str) -> str:
    en = lang == "en"
    parts = HOW_TO_GUIDE["en" if en else "cs"]
    out = [f"<h2 style='margin:0 0 4px 0;'>{APP_NAME} – {'How to use' if en else 'Návod k použití'}</h2>",
           f"<p style='color:#9E9E9E; margin:0 0 8px 0;'>{APP_TAGLINE['en' if en else 'cs']} · {'version' if en else 'verze'} {APP_VERSION}</p>",
           "<p>" + " · ".join(f"<a href='#s{i}'>{html_mod.escape(t)}</a>" for i, (t, _) in enumerate(parts)) + "</p>"]
    for i, (title, body) in enumerate(parts):
        out.append(f"<h3 id='s{i}'><a name='s{i}'></a>{html_mod.escape(title)}</h3>{body}")
    return "".join(out)


class HowToDialog(QDialog):
    """❓ Návod k použití – CZ/EN, odkazy na registraci klíčů se otevřou v prohlížeči počítače."""

    def __init__(self, lang: str, parent=None):
        super().__init__(parent)
        self.resize(860, 720)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addStretch(1)
        self.btn_cs = QPushButton("🇨🇿 Čeština")
        self.btn_en = QPushButton("🇬🇧 English")
        for b_, code in ((self.btn_cs, "cs"), (self.btn_en, "en")):
            b_.clicked.connect(lambda _, c=code: self._set_lang(c))
            top.addWidget(b_)
        lay.addLayout(top)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        lay.addWidget(self.view, stretch=1)
        self.btn_close = QPushButton("OK")
        self.btn_close.setMinimumWidth(160)
        self.btn_close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.btn_close)
        lay.addLayout(row)
        self._set_lang("en" if lang == "en" else "cs")

    def _set_lang(self, lang: str):
        self.lang = lang
        en = lang == "en"
        self.setWindowTitle(f"{APP_NAME} – " + ("How to use" if en else "Návod k použití"))
        active = "background-color: #6A1B9A; color: white; font-weight: bold;"
        self.btn_cs.setStyleSheet(active if not en else "")
        self.btn_en.setStyleSheet(active if en else "")
        self.view.setHtml(how_to_html(lang))


def whats_new_html(lang: str) -> str:
    en = lang == "en"
    out = [donate_banner_html(lang), f"<h2 style='margin:0 0 6px 0;'>{'What’s new' if en else 'Co je nového'}</h2>"]
    for ver in sorted(WHATS_NEW, key=lambda v: [int(x) for x in v.split(".")], reverse=True):
        cur = ver == APP_VERSION
        out.append(f"<h3 style='margin:10px 0 4px 0; color:{'#00E676' if cur else '#9E9E9E'};'>{'Version' if en else 'Verze'} {ver}"
                   f"{(' – ' + ('current' if en else 'aktuální')) if cur else ''}</h3><ul>")
        out += [f"<li style='margin-bottom:4px;{'' if cur else ' color:#BDBDBD;'}'>{html_mod.escape(x)}</li>" for x in WHATS_NEW[ver]["en" if en else "cs"]]
        out.append("</ul>")
    out.append("<hr>")
    out.append(f"<h3 style='margin:8px 0 4px 0;'>{'Disclaimer and terms of use' if en else 'Upozornění a podmínky použití'}</h3>")
    for title, body in DISCLAIMER_TEXT["en" if en else "cs"]:
        out.append(f"<p style='margin:0 0 6px 0;'><b>{html_mod.escape(title)}.</b> {html_mod.escape(body)}</p>")
    out.append(f"<p style='color:#9E9E9E;'>{'By using the app you agree to these terms.' if en else 'Používáním aplikace s těmito podmínkami souhlasíte.'}</p>")
    return "".join(out)


class WhatsNewDialog(QDialog):
    """Novinky a podmínky použití. OK (i zavření okna) jde až po sjetí na konec textu, aby si lidi upozornění přečetli."""

    def __init__(self, lang: str, show_checkbox: bool = True, parent=None):
        super().__init__(parent)
        self.lang = "en" if lang == "en" else "cs"
        self.read_all = False
        self._shown = False
        self.resize(780, 660)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color: #FFB74D; font-weight: bold;")
        top.addWidget(self.lbl_info, stretch=1)
        self.btn_cs = QPushButton("🇨🇿 Čeština")
        self.btn_en = QPushButton("🇬🇧 English")
        for b_, code in ((self.btn_cs, "cs"), (self.btn_en, "en")):
            b_.clicked.connect(lambda _, c=code: self._set_lang(c))
            top.addWidget(b_)
        lay.addLayout(top)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        self.view.verticalScrollBar().valueChanged.connect(self._check_read)
        self.view.verticalScrollBar().rangeChanged.connect(lambda *_: self._check_read())
        lay.addWidget(self.view, stretch=1)
        row = QHBoxLayout()
        self.chk_hide = QCheckBox("")
        self.chk_hide.setVisible(show_checkbox)
        row.addWidget(self.chk_hide, stretch=1)
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setMinimumWidth(130)
        self.btn_ok.setMinimumWidth(190)
        self.btn_ok.clicked.connect(self.accept)
        row.addWidget(self.btn_ok)
        lay.addLayout(row)
        self._set_lang(self.lang)

    def _set_lang(self, lang: str):
        self.lang = lang
        en = lang == "en"
        self.setWindowTitle(("What’s new" if en else "Co je nového") + f" – {APP_NAME} {APP_VERSION}")
        self.chk_hide.setText("Don’t show again until the next version" if en else "Příště nezobrazovat (až do nové verze)")
        active = "background-color: #6A1B9A; color: white; font-weight: bold;"
        self.btn_cs.setStyleSheet(active if not en else "")
        self.btn_en.setStyleSheet(active if en else "")
        pos = self.view.verticalScrollBar().value()
        self.view.setHtml(whats_new_html(lang))
        self.view.verticalScrollBar().setValue(pos)
        self._check_read()

    def showEvent(self, event):
        super().showEvent(event)
        # až teď je text rozložený a posuvník má skutečný rozsah
        QTimer.singleShot(300, self._after_shown)

    def _after_shown(self):
        self._shown = True
        self._check_read()

    def _check_read(self, *_):
        sb = self.view.verticalScrollBar()
        if self._shown and (sb.maximum() <= 0 or sb.value() >= sb.maximum() - 4):
            self.read_all = True
        en = self.lang == "en"
        self.btn_ok.setEnabled(self.read_all)
        self.chk_hide.setEnabled(self.read_all)
        if self.read_all:
            self.btn_ok.setText("✔ OK, I understand" if en else "✔ Rozumím")
            self.btn_ok.setStyleSheet("background-color: #009A3E; color: white; font-weight: bold; padding: 7px 14px; border: 1px solid #00E676;")
        else:
            self.btn_ok.setText("⬇ Read to the end first" if en else "⬇ Nejdřív dočti až dolů")
            self.btn_ok.setStyleSheet("background-color: #424242; color: #9E9E9E; padding: 7px 14px; border: 1px dashed #757575;")
        self.lbl_info.setText("" if self.read_all else ("Please read to the end – the terms of use are at the bottom."
                                                         if en else "Dočti prosím až dolů – na konci jsou podmínky použití."))

    def reject(self):
        if self.read_all:
            super().reject()

    def closeEvent(self, event):
        if self.read_all:
            super().closeEvent(event)
        else:
            event.ignore()


# 💛 Donation – dobrovolná podpora autora. Odkazy se otevřou v prohlížeči počítače.
DONATE_LINKS = (
    ("☕ Ko-fi", "https://ko-fi.com/johnpreclik"),
    ("🅿️ PayPal", "https://paypal.me/johnpreclik"),
    ("💳 Revolut", "https://revolut.me/preca"),
)
# QR kód pro https://revolut.me/preca (PNG, vygenerováno knihovnou segno) – vložený, aby šel ukázat i offline
DONATE_REVOLUT_QR_PNG = "iVBORw0KGgoAAAANSUhEUgAAAK4AAACuAQAAAACHdwtDAAAA9klEQVR42u2X0QkDMQxDTTNARsrqGSkDBFTZSlso91tUaMNx5PwlnCfFF7haO367vIKrrcFNA/Ijxr7F5fpkmUoGFTVMCqAeimHFpUQaos/d0Vb2x6kEE/gWJTvfZiUoASLWysnxjh6nd86aJWMcc5tOJ2OkI2XwXBJa2+nwEa6ppye6Vk6CGtgWvm09YZI82pKbDBYfJ2WZA4nRxZlpoqUs3GHkJHGtaI3siZGTsm2Ik6GKzTt0jSyjgO1wZmzlm9piv3eePsIyz2zACXxjnoSiPtycvGY2VN6ml61zbChMZGcrJ9DkphHFfBcfXKfv3vn/jb6V7wt4N+IecV1aAAAAAElFTkSuQmCC"
DONATE_TEXT = {
    "cs": ("Líbí se vám LocalChef Studio?",
           "Aplikaci vyvíjím ve volném čase a je zdarma. Pokud vám šetří čas v kuchyni a chcete podpořit její další vývoj "
           "a práci autora, budu rád za jakýkoli příspěvek – třeba na kafe. Díky, že ji používáte! 🙂",
           "Revolut můžete poslat i naskenováním QR kódu mobilem:"),
    "en": ("Do you like LocalChef Studio?",
           "I build this app in my free time and it is free. If it saves you time in the kitchen and you would like to support "
           "its further development and the author's work, any contribution is welcome – a coffee is plenty. Thank you for using it! 🙂",
           "You can also send money via Revolut by scanning the QR code with your phone:"),
}


def donate_banner_html(lang: str) -> str:
    """Krátká výzva k podpoře – hlavička okna novinek a podmínek."""
    head, body, _ = DONATE_TEXT["en" if lang == "en" else "cs"]
    links = " · ".join(f"<a style='color:#FFD54F;' href='{url}'>{html_mod.escape(name)}</a>" for name, url in DONATE_LINKS)
    return ("<table width='100%' cellpadding='8' style='background-color:#3E2723; border:1px solid #FFB300; margin-bottom:8px;'>"
            f"<tr><td style='color:#FFF8E1;'><b style='color:#FFD54F;'>💛 {html_mod.escape(head)}</b><br>{html_mod.escape(body)}<br>"
            f"<b>{links}</b></td></tr></table>")


class DonateDialog(QDialog):
    """💛 Donation: proč podpořit, odkazy Ko-fi / PayPal / Revolut a QR kód pro Revolut. CZ/EN."""

    def __init__(self, lang: str, parent=None):
        super().__init__(parent)
        self.resize(560, 600)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addStretch(1)
        self.btn_cs = QPushButton("🇨🇿 Čeština")
        self.btn_en = QPushButton("🇬🇧 English")
        for b_, code in ((self.btn_cs, "cs"), (self.btn_en, "en")):
            b_.clicked.connect(lambda _, c=code: self._set_lang(c))
            top.addWidget(b_)
        lay.addLayout(top)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        lay.addWidget(self.view, stretch=1)
        self.lbl_qr_info = QLabel("")
        self.lbl_qr_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr_info.setWordWrap(True)
        lay.addWidget(self.lbl_qr_info)
        self.lbl_qr = QLabel()
        self.lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        try:
            import base64
            self.lbl_qr.setPixmap(QPixmap.fromImage(QImage.fromData(base64.b64decode(DONATE_REVOLUT_QR_PNG))))
        except Exception:
            self.lbl_qr.setText("https://revolut.me/preca")
        lay.addWidget(self.lbl_qr)
        self.btn_close = QPushButton("OK")
        self.btn_close.setMinimumWidth(160)
        self.btn_close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.btn_close)
        lay.addLayout(row)
        self._set_lang("en" if lang == "en" else "cs")

    def _set_lang(self, lang: str):
        self.lang = lang
        en = lang == "en"
        head, body, qr_info = DONATE_TEXT["en" if en else "cs"]
        self.setWindowTitle(f"{APP_NAME} – " + ("Donation" if en else "Podpořit vývoj"))
        active = "background-color: #6A1B9A; color: white; font-weight: bold;"
        self.btn_cs.setStyleSheet(active if not en else "")
        self.btn_en.setStyleSheet(active if en else "")
        links = "".join(f"<p style='font-size:15px; margin:6px 0;'><b><a href='{url}'>{html_mod.escape(name)}</a></b> &nbsp; "
                        f"<span style='color:#9E9E9E;'>{url}</span></p>" for name, url in DONATE_LINKS)
        self.view.setHtml(f"<h2 style='color:#FFD54F;'>💛 {html_mod.escape(head)}</h2><p>{html_mod.escape(body)}</p>{links}")
        self.lbl_qr_info.setText(qr_info)


class QrDialog(QDialog):
    def __init__(self, url_str: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tx("QR kód pro přístup z mobilu / tabletu"))
        self.resize(380, 420)
        layout = QVBoxLayout(self)

        lbl_info = QLabel(tx("Naskenuj QR kód fotoaparátem v mobilu:") + f"\n<b>{url_str}</b>")
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)

        self.lbl_qr = QLabel()
        self.lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_qr, stretch=1)

        qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(url_str)}"
        try:
            req = urllib.request.urlopen(qr_api_url, timeout=3)
            img_data = req.read()
            qimg = QImage.fromData(img_data)
            self.lbl_qr.setPixmap(QPixmap.fromImage(qimg))
        except Exception:
            self.lbl_qr.setText(tx("Nelze stáhnout QR kód (chybí internet pro API).\nOpiš adresu ručně."))


WIDGET_TOOLTIPS = {
    "btn_expand_all": ("Rozbalí všechny kategorie v seznamu receptů", "Expands all categories in the recipe list"),
    "btn_collapse_all": ("Sbalí všechny kategorie – v seznamu zůstanou jen jejich názvy", "Collapses all categories – only their names stay visible"),
    "search_input": ("Hledá v názvech receptů (původních i přeložených) a kategoriích. Nezáleží na diakritice ani velkých písmenech, můžeš zadat víc slov.",
                     "Searches recipe names (original and translated) and categories. Accents and capitals don't matter, several words are allowed."),
    "combo_category_filter": ("Zobrazí jen recepty z vybrané kategorie", "Shows only recipes from the selected category"),
    "btn_new_cat": ("Založí novou kategorii. Recept do ní přetáhneš myší, nebo přes pravé tlačítko na receptu.",
                    "Creates a new category. Drag a recipe into it, or use the right-click menu on a recipe."),
    "combo_platform_filter": ("Zobrazí recepty ze všech webů, nebo jen z Cookidoo (Thermomix), nebo jen z Monsieur Cuisine",
                              "Shows recipes from all sites, only Cookidoo (Thermomix) or only Monsieur Cuisine"),
    "combo_title_lang": ("Jazyk názvů v seznamu. „Podle jazyka aplikace“ ukáže přeložený název, pokud recept už je přeložený, jinak původní.",
                         "Language of the names in the list. “Same as app language” shows the translated name when the recipe is translated, otherwise the original."),
    "chk_only_favorites": ("Zobrazí jen recepty označené hvězdičkou", "Shows only recipes marked with a star"),
    "recipe_tree": ("Kliknutím recept otevřeš, pravým tlačítkem nabídka (oblíbené, kategorie, PDF, smazání). Recept jde přetáhnout do jiné kategorie.",
                    "Click to open a recipe, right-click for a menu (favorites, category, PDF, delete). Drag a recipe to move it to another category."),
    "btn_toggle_fav": ("Přidá vybraný recept do oblíbených, nebo ho z nich odebere", "Adds the selected recipe to favorites or removes it"),
    "btn_change_cat": ("Přesune vybraný recept do jiné (i nové) kategorie", "Moves the selected recipe to another (or new) category"),
    "btn_delete": ("Odebere vybraný recept z kuchařky. Jeho složka se přesune do koše localchef_data\\recipes_smazane.",
                   "Removes the selected recipe from the cookbook. Its folder moves to the trash folder localchef_data\\recipes_smazane."),
    "lbl_wifi": ("Adresa kuchařky pro mobil nebo tablet ve stejné Wi-Fi", "Cookbook address for a phone or tablet on the same Wi-Fi"),
    "btn_qr": ("Ukáže QR kód – naskenuj ho mobilem a kuchařka se otevře v telefonu", "Shows a QR code – scan it with your phone to open the cookbook there"),
    "btn_back": ("Zpět na předchozí stránku v prohlížeči", "Back to the previous page in the browser"),
    "btn_home_tm": ("Otevře web Cookidoo (Thermomix) – tam se přihlas a ukládej recepty", "Opens the Cookidoo (Thermomix) website – log in there and save recipes"),
    "btn_home_mcs": ("Otevře web Monsieur Cuisine – tam ukládej recepty", "Opens the Monsieur Cuisine website – save recipes there"),
    "url_bar": ("Adresa právě zobrazené stránky", "Address of the page shown"),
    "btn_donate": ("Dobrovolná podpora autora – Ko-fi, PayPal nebo Revolut (i QR kód)", "Voluntary support for the author – Ko-fi, PayPal or Revolut (QR code too)"),
    "btn_save_single": ("Uloží recept, který máš právě otevřený na webu, do offline kuchařky (i s verzí pro druhý stroj)",
                        "Saves the recipe open on the website to the offline cookbook (including a version for the other machine)"),
    "btn_settings": ("Překladače a klíče, hromadný překlad, jazyk aplikace, vzhled", "Translators and keys, bulk translation, app language, appearance"),
    "btn_import_backup": ("Nahraje recepty ze záloh .7z (jednu nebo víc najednou) – i se styly a obrázky karet.",
                          "Loads recipes from .7z backups (one or more at once) – including card styles and images."),
    "btn_export_backup": ("Zabalí označené recepty (Ctrl/Shift + klik, nebo celou kategorii) do jednoho .7z ve složce exported_recipes.",
                          "Packs the selected recipes (Ctrl/Shift + click, or a whole category) into one .7z in the exported_recipes folder."),
    "btn_help": ("Návod k použití: co kde je, překlady, offline překladač, jak získat klíče zdarma",
                 "How to use: what is where, translations, the offline translator, how to get free keys"),
    "btn_translate_all": ("Na pozadí přeloží všechny recepty do angličtiny i češtiny (recept i kartu). Už hotové přeskočí.",
                          "Translates all recipes into English and Czech in the background (recipe and card). Finished ones are skipped."),
    "btn_deepl_key": ("Klíč k DeepL – nejkvalitnější překlad, použije se jako první (volitelné, deepl.com/pro-api)",
                      "DeepL key – best quality, used first (optional, deepl.com/pro-api)"),
    "btn_gemini_key": ("Klíč ke Google Gemini – použije se, když DeepL není nebo selže, a pro převod TM6 ↔ Monsieur Cuisine (zdarma z aistudio.google.com)",
                       "Google Gemini key – used when DeepL is missing or fails, and for TM6 ↔ Monsieur Cuisine conversion (free at aistudio.google.com)"),
    "btn_offline_tr": ("Offline překladač bez internetu a bez klíčů – použije se až jako poslední. Tady stáhneš jazykové modely.",
                       "Offline translator without internet or keys – used last. Download the language models here."),
    "act_ui_cs": ("Rozhraní aplikace v češtině", "App interface in Czech"),
    "act_ui_en": ("Rozhraní aplikace v angličtině", "App interface in English"),
    "btn_theme_toggle": ("Přepíná tmavý a světlý vzhled aplikace i karty receptu", "Switches between the dark and light look of the app and the recipe card"),
    "btn_icon_style": ("Styl ikon před recepty: barevné tečky, nebo hrnec/robot", "Icon style in front of recipes: coloured dots or pot/robot"),
    "btn_view_card": ("Karta receptu – uložená stránka receptu, jak vypadá na webu (funguje i offline)", "Recipe card – the saved recipe page as it looks on the website (works offline)"),
    "btn_view_tm": ("Režim vaření pro Thermomix TM6 – krok po kroku s časem, teplotou a rychlostí", "Cooking mode for Thermomix TM6 – step by step with time, temperature and speed"),
    "btn_view_mcs": ("Režim vaření pro Monsieur Cuisine – recept se případně převede z TM6", "Cooking mode for Monsieur Cuisine – the recipe is converted from TM6 if needed"),
    "btn_card_orig": ("Zobrazí recept v původním jazyce", "Shows the recipe in its original language"),
    "btn_card_en": ("Zobrazí recept v angličtině (poprvé ho přeloží)", "Shows the recipe in English (translates it the first time)"),
    "btn_card_cs": ("Zobrazí recept v češtině (poprvé ho přeloží)", "Shows the recipe in Czech (translates it the first time)"),
    "btn_card_retranslate": ("Přeložit znovu – smaže uložený překlad zobrazeného jazyka a přeloží recept i kartu znovu",
                             "Translate again – deletes the saved translation of the shown language and translates the recipe and card again"),
    "btn_export_pdf": ("Uloží vybraný recept jako přehledné PDF: fotka, nutriční hodnoty, suroviny, postup a tipy (v zobrazeném jazyce a dávce)",
                       "Saves the selected recipe as a clean PDF: photo, nutrition, ingredients, method and tips (in the shown language and batch)"),
    "btn_cancel_batch": ("Zastaví hromadné ukládání nebo hromadný překlad (rozpracovaný recept se dokončí)", "Stops batch saving or bulk translation (the current recipe is finished)"),
    "btn_lang_orig": ("Recept v původním jazyce", "Recipe in its original language"),
    "btn_lang_en": ("Recept v angličtině", "Recipe in English"),
    "btn_lang_cs": ("Recept v češtině", "Recipe in Czech"),
    "btn_unit_toggle": ("Převede americké jednotky (cup, oz, lb, °F…) na gramy, mililitry a °C. Původní hodnota zůstane v závorce.",
                        "Converts US units (cup, oz, lb, °F…) to grams, millilitres and °C. The original value stays in brackets."),
    "btn_fine_toggle": ("Jemné kroky: každé navážení a každé nastavení stroje jako samostatný krok", "Detailed steps: every weighing and every machine setting as a separate step"),
    "btn_retranslate": ("Smaže uložený překlad tohoto jazyka a přeloží recept znovu", "Deletes the saved translation for this language and translates the recipe again"),
    "btn_prev_step": ("Předchozí krok (šipka vlevo)", "Previous step (left arrow)"),
    "btn_whats_new": ("Novinky této verze a podmínky použití aplikace", "What's new in this version and the terms of use"),
    "btn_home": ("Úvodní stránka s hledáním receptů ve tvé kuchařce i na webech", "Start page with recipe search in your cookbook and on websites"),
    "btn_next_step": ("Další krok (šipka vpravo)", "Next step (right arrow)"),
}


class LocalChefStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui_lang = "en" if load_config().get("ui_lang") == "en" else "cs"
        set_ui_lang(self.ui_lang)
        self.icon_style = load_icon_style()
        self.setWindowTitle(UI_TEXTS[self.ui_lang]["window_title"])
        self.resize(1680, 960)
        for note in _DATA_NOTES:            # přejmenování datové složky (do 1.2 cookidoo_data) – až teď jde do app.log
            log(note)
        init_db()
        sync_catalog_from_folders()        # recepty zkopírované do localchef_data/recipes se samy objeví v kuchařce
        repair_fragmented_steps()          # recepty uložené s rozsekanými kroky → opravit z dat Cookidoo
        backfill_translated_titles()       # názvy z hotových překladů → seznam receptů
        start_lan_http_server()

        self.current_offline_data = None
        self.current_recipe_folder: Path | None = None
        self.current_recipe_id = None
        self.current_source_platform = "tm6"
        self.current_step_index = 0
        self.use_metric_conversion = True
        self.portion_scale = 1.0
        self.display_lang = "orig"
        self.device_mode = "tm6"
        self.fine_mode = True
        self.is_dark_mode = True
        self.translation_worker: TranslationWorker | None = None
        self.conv_worker: DeviceConversionWorker | None = None
        self._workers: list = []
        self._tr_timer: QTimer | None = None
        self._tr_poll: dict | None = None

        self._build_ui()
        self._apply_theme()
        self._refresh_categories_combo()
        self._load_catalog()

    def closeEvent(self, event):
        try:
            self.webview.setPage(None)
            self.webpage.deleteLater()
        except Exception:
            pass
        super().closeEvent(event)

    def t(self, key: str) -> str:
        return UI_TEXTS[self.ui_lang].get(key, key)

    def _build_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(6)

        lan_ip = get_local_ip()
        self.lan_url_str = f"http://{lan_ip}:{LAN_PORT}"

        header_left = QHBoxLayout()
        self.lbl_cat_title = QLabel(tx("📚 Moje Offline Kuchařka"))
        self.lbl_cat_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        header_left.addWidget(self.lbl_cat_title, stretch=1)
        self.btn_expand_all = QPushButton(self.t('expand_btn'))
        self.btn_expand_all.setToolTip(tx("Rozbalit všechny kategorie"))
        self.btn_expand_all.clicked.connect(lambda: self.recipe_tree.expandAll())
        self.btn_collapse_all = QPushButton(self.t('collapse_btn'))
        self.btn_collapse_all.setToolTip(tx("Sbalit všechny kategorie"))
        self.btn_collapse_all.clicked.connect(lambda: self.recipe_tree.collapseAll())
        header_left.addWidget(self.btn_expand_all)
        header_left.addWidget(self.btn_collapse_all)
        left_layout.addLayout(header_left)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.t('search_ph'))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter_catalog)
        left_layout.addWidget(self.search_input)

        filter_row = QHBoxLayout()
        self.combo_category_filter = QComboBox()
        self.combo_category_filter.currentIndexChanged.connect(lambda _: self._load_catalog())
        filter_row.addWidget(self.combo_category_filter, stretch=1)
        self.btn_new_cat = QPushButton(tx("➕ Nová kategorie"))
        self.btn_new_cat.setToolTip(tx("Založit novou kategorii (vybraný recept do ní můžeš rovnou přesunout)"))
        self.btn_new_cat.clicked.connect(self._new_category)
        filter_row.addWidget(self.btn_new_cat)
        left_layout.addLayout(filter_row)

        plat_row = QHBoxLayout()
        self.combo_platform_filter = QComboBox()
        self.combo_platform_filter.addItem(self.t("plat_all"), "all")
        self.combo_platform_filter.addItem(self.t("plat_tm6"), "tm6")
        self.combo_platform_filter.addItem(self.t("plat_mcs"), "mcs")
        self.combo_platform_filter.addItem(self.t("plat_other"), "other")
        self.combo_platform_filter.currentIndexChanged.connect(lambda _: self._load_catalog())
        plat_row.addWidget(self.combo_platform_filter, stretch=1)

        self.combo_title_lang = QComboBox()
        self.combo_title_lang.setToolTip(tx("V jakém jazyce ukazovat názvy receptů (přeložený název je k dispozici po překladu receptu)"))
        for code in ("auto", "orig", "en", "cs"):
            self.combo_title_lang.addItem("", code)
        self._fill_title_lang_combo()
        saved_tl = load_config().get("title_lang", "auto")
        self.combo_title_lang.setCurrentIndex({"auto": 0, "orig": 1, "en": 2, "cs": 3}.get(saved_tl, 0))
        self.combo_title_lang.currentIndexChanged.connect(self._on_title_lang_changed)
        plat_row.addWidget(self.combo_title_lang)

        self.chk_only_favorites = QCheckBox(self.t('only_fav'))
        self.chk_only_favorites.setStyleSheet("font-weight: bold; color: #FFB300;")
        self.chk_only_favorites.toggled.connect(lambda _: self._load_catalog())
        plat_row.addWidget(self.chk_only_favorites)
        left_layout.addLayout(plat_row)

        self.lbl_search_info = QLabel("")
        self.lbl_search_info.setStyleSheet("color: #FFB74D;")
        self.lbl_search_info.setVisible(False)
        left_layout.addWidget(self.lbl_search_info)

        self.recipe_tree = RecipeTreeWidget()
        self.recipe_tree.itemClicked.connect(self._on_tree_item_clicked)
        self.recipe_tree.recipe_moved.connect(self._on_recipe_drag_dropped)
        self.recipe_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.recipe_tree.customContextMenuRequested.connect(self._recipe_context_menu)
        left_layout.addWidget(self.recipe_tree, stretch=1)

        org_row = QHBoxLayout()
        self.btn_toggle_fav = QPushButton(self.t('fav_btn'))
        self.btn_toggle_fav.setStyleSheet("padding: 6px; font-weight: bold;")
        self.btn_toggle_fav.clicked.connect(self._toggle_favorite_selected)
        self.btn_change_cat = QPushButton(self.t('cat_btn'))
        self.btn_change_cat.setStyleSheet("padding: 6px;")
        self.btn_change_cat.clicked.connect(self._change_category_selected)
        self.btn_delete = QPushButton(self.t('del_btn'))
        self.btn_delete.setStyleSheet("padding: 6px;")
        self.btn_delete.clicked.connect(self._delete_selected_recipe)
        org_row.addWidget(self.btn_toggle_fav)
        org_row.addWidget(self.btn_change_cat)
        org_row.addWidget(self.btn_delete)
        left_layout.addLayout(org_row)

        backup_row = QHBoxLayout()
        self.btn_import_backup = QPushButton(tx("📥 Importovat recepty (.7z)…"))
        self.btn_import_backup.setStyleSheet("padding: 6px; font-weight: bold;")
        self.btn_import_backup.clicked.connect(lambda *_: self._import_backup())
        self.btn_export_backup = QPushButton(tx("📦 Exportovat označené (.7z)…"))
        self.btn_export_backup.setStyleSheet("padding: 6px;")
        self.btn_export_backup.clicked.connect(lambda *_: self._export_backup())
        backup_row.addWidget(self.btn_import_backup)
        backup_row.addWidget(self.btn_export_backup)
        left_layout.addLayout(backup_row)

        lan_layout = QHBoxLayout()
        self.lbl_wifi = QLabel(f"{self.t('wifi_label')}{self.lan_url_str}")
        self.lbl_wifi.setStyleSheet("background-color: #1B5E20; color: #A5D6A7; padding: 6px; border-radius: 5px; font-weight: bold;")
        self.lbl_wifi.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.btn_qr = QPushButton(self.t('qr_btn'))
        self.btn_qr.setMinimumWidth(85)
        self.btn_qr.setStyleSheet("background-color: #0277BD; color: white; font-weight: bold;")
        self.btn_qr.clicked.connect(self._show_qr_dialog)
        lan_layout.addWidget(self.lbl_wifi, stretch=1)
        lan_layout.addWidget(self.btn_qr)
        left_layout.addLayout(lan_layout)

        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # ---- lišta 1: web (prohlížení a ukládání receptů) + nastavení
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 8, 8, 4)
        self.btn_back = QPushButton(self.t('back_btn'))
        self.btn_back.clicked.connect(lambda: self.webview.back())
        toolbar.addWidget(self.btn_back)
        self.btn_home_tm = QPushButton(self.t('home_tm_btn'))
        self.btn_home_tm.setStyleSheet("background-color: #1B5E20; color: white; font-weight: bold; padding: 6px 10px;")
        self.btn_home_tm.clicked.connect(self._go_online_cookidoo)
        toolbar.addWidget(self.btn_home_tm)
        self.btn_home_mcs = QPushButton(self.t('home_mcs_btn'))
        self.btn_home_mcs.setStyleSheet("background-color: #0D47A1; color: white; font-weight: bold; padding: 6px 10px;")
        self.btn_home_mcs.clicked.connect(self._go_online_mcs)
        toolbar.addWidget(self.btn_home_mcs)
        self.btn_home = QPushButton(tx("🏠 Domů"))
        self.btn_home.setStyleSheet("background-color: #E65100; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_home.clicked.connect(self._go_home)
        toolbar.insertWidget(1, self.btn_home)          # pořadí: ← Zpět, 🏠 Domů, Cookidoo, MCS
        self.url_bar = QLineEdit()
        self.url_bar.setReadOnly(True)
        toolbar.addWidget(self.url_bar, stretch=1)
        self.btn_save_single = QPushButton(self.t('save_single'))
        self.btn_save_single.setStyleSheet("background-color: #E65100; color: white; font-weight: bold; padding: 7px 12px; border-radius: 4px;")
        self.btn_save_single.clicked.connect(lambda: self._save_current_recipe(silent=False))
        toolbar.addWidget(self.btn_save_single)
        self.btn_donate = QPushButton(self.t('donate_btn'))
        self.btn_donate.setStyleSheet("background-color: #F9A825; color: #3E2723; font-weight: bold; padding: 7px 12px; border-radius: 4px;")
        self.btn_donate.clicked.connect(self._show_donate)
        toolbar.addWidget(self.btn_donate)

        self.btn_settings = QToolButton()
        self.btn_settings.setText(tx("⚙️ Nastavení"))
        self.btn_settings.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_settings.setStyleSheet("font-weight: bold; padding: 7px 12px;")
        menu = QMenu(self)
        self.menu_translate_section = menu.addSection(tx("Překlad"))
        self.btn_translate_all = QAction(tx("🌍 Přeložit všechny recepty (EN + CZ)…"), self)
        self.btn_translate_all.triggered.connect(self._bulk_translate)
        menu.addAction(self.btn_translate_all)
        self.btn_gemini_key = QAction(self.t('ai_key_btn'), self)
        self.btn_gemini_key.triggered.connect(self._prompt_gemini_key)
        menu.addAction(self.btn_gemini_key)
        self.btn_offline_tr = QAction(tx("📥 Stáhnout offline překladač"), self)
        self.btn_offline_tr.setToolTip(tx("Stav offline překladače (Argos Translate) a stažení jazykových modelů pro překlad bez internetu a bez klíčů"))
        self.btn_offline_tr.triggered.connect(self._offline_translator_dialog)
        menu.addAction(self.btn_offline_tr)
        self.btn_deepl_key = QAction(self.t('key_btn'), self)
        self.btn_deepl_key.triggered.connect(self._prompt_api_key)
        menu.addAction(self.btn_deepl_key)
        self.menu_view_section = menu.addSection(tx("Vzhled"))
        self.menu_ui_lang = menu.addMenu(self.t('ui_lang_label') + " " + ("English" if self.ui_lang == "en" else "Čeština"))
        self.ui_lang_group = QActionGroup(self)
        self.act_ui_cs = QAction("🇨🇿 Čeština", self, checkable=True)
        self.act_ui_en = QAction("🇬🇧 English", self, checkable=True)
        for i, act in enumerate((self.act_ui_cs, self.act_ui_en)):
            self.ui_lang_group.addAction(act)
            self.menu_ui_lang.addAction(act)
            act.triggered.connect(lambda _, ix=i: self._change_ui_language(ix))
        (self.act_ui_en if self.ui_lang == "en" else self.act_ui_cs).setChecked(True)
        self.btn_theme_toggle = QAction(self.t('dark_on'), self, checkable=True)
        self.btn_theme_toggle.setChecked(True)
        self.btn_theme_toggle.triggered.connect(self._toggle_theme)
        menu.addAction(self.btn_theme_toggle)
        self.btn_icon_style = QAction(self.t("icon_bots" if self.icon_style == "bots" else "icon_dots"), self)
        self.btn_icon_style.setToolTip(tx("Přepnout styl ikon před recepty"))
        self.btn_icon_style.triggered.connect(self._toggle_icon_style)
        menu.addAction(self.btn_icon_style)
        self.menu_about_section = menu.addSection(tx("Aplikace"))
        self.act_how_to = QAction(tx("❓ Návod k použití"), self)
        self.act_how_to.triggered.connect(lambda *_: self._show_how_to())
        menu.addAction(self.act_how_to)
        self.btn_whats_new = QAction(tx("ℹ️ Co je nového a podmínky použití (verze {v})", v=APP_VERSION), self)
        self.btn_whats_new.triggered.connect(lambda *_: self._show_whats_new(False))
        menu.addAction(self.btn_whats_new)
        self.btn_settings.setMenu(menu)
        self.settings_menu = menu
        menu.setToolTipsVisible(True)
        self.btn_help = QPushButton(tx("❓ Návod"))
        self.btn_help.setStyleSheet("font-weight: bold; padding: 7px 12px;")
        self.btn_help.clicked.connect(lambda *_: self._show_how_to())
        toolbar.addWidget(self.btn_help)
        toolbar.addWidget(self.btn_settings)
        right_layout.addLayout(toolbar)

        # ---- lišta 2: vybraný recept (zobrazení, jazyk, PDF)
        self.recipe_bar = QFrame()
        self.recipe_bar.setStyleSheet("QFrame#recipeBar { background-color: #252526; border-top: 1px solid #333; border-bottom: 1px solid #333; }")
        self.recipe_bar.setObjectName("recipeBar")
        rbar = QHBoxLayout(self.recipe_bar)
        rbar.setContentsMargins(8, 4, 8, 4)
        self.lbl_view = QLabel(tx("Zobrazit:"))
        self.lbl_view.setStyleSheet("font-weight: bold; color: #BDBDBD;")
        rbar.addWidget(self.lbl_view)
        self.btn_view_card = QPushButton(self.t('card_btn'))
        self.btn_view_card.clicked.connect(self._switch_to_card_view)
        self.btn_view_tm = QPushButton(self.t('tm_btn'))
        self.btn_view_tm.clicked.connect(self._open_tm_player)
        self.btn_view_mcs = QPushButton(self.t('mcs_btn'))
        self.btn_view_mcs.clicked.connect(self._open_mcs_player)
        for b_, col in ((self.btn_view_card, "#37474F"), (self.btn_view_tm, "#009A3E"), (self.btn_view_mcs, "#1565C0")):
            b_.setStyleSheet(f"background-color: {col}; color: white; font-weight: bold; padding: 5px 10px;")
            rbar.addWidget(b_)
        rbar.addSpacing(14)
        self.lbl_card_lang = QLabel(tx("Jazyk:"))
        self.lbl_card_lang.setStyleSheet("font-weight: bold; color: #BDBDBD;")
        rbar.addWidget(self.lbl_card_lang)
        self.btn_card_orig = QPushButton("🌐 Orig")
        self.btn_card_en = QPushButton("🇬🇧 EN")
        self.btn_card_cs = QPushButton("🇨🇿 CZ")
        for b_, code in ((self.btn_card_orig, "orig"), (self.btn_card_en, "en"), (self.btn_card_cs, "cs")):
            b_.setMinimumWidth(62)
            b_.clicked.connect(lambda _, c=code: self._switch_any_language(c))
            rbar.addWidget(b_)
        self.btn_card_retranslate = QPushButton("🔄")
        self.btn_card_retranslate.setFixedWidth(36)
        self.btn_card_retranslate.setToolTip(tx("Přeložit znovu – smaže uložený překlad tohoto jazyka a přeloží recept i kartu znovu"))
        self.btn_card_retranslate.clicked.connect(self._retranslate_current)
        rbar.addWidget(self.btn_card_retranslate)
        rbar.addStretch(1)
        self.btn_export_pdf = QPushButton(self.t('pdf_btn'))
        self.btn_export_pdf.setStyleSheet("background-color: #5D4037; color: white; font-weight: bold; padding: 5px 12px;")
        self.btn_export_pdf.clicked.connect(self._export_current_to_pdf)
        rbar.addWidget(self.btn_export_pdf)
        right_layout.addWidget(self.recipe_bar)

        self.batch_bar_frame = QFrame()
        self.batch_bar_frame.setStyleSheet("background-color: #0D47A1; color: white; padding: 4px;")
        batch_layout = QHBoxLayout(self.batch_bar_frame)
        self.lbl_batch_status = QLabel(self.t('batch_lbl'))
        self.progress_batch = QProgressBar()
        self.progress_batch.setStyleSheet("color: black;")
        self.btn_cancel_batch = QPushButton(self.t('cancel_btn'))
        self.btn_cancel_batch.clicked.connect(self._stop_batch)
        batch_layout.addWidget(self.lbl_batch_status)
        batch_layout.addWidget(self.progress_batch, stretch=1)
        batch_layout.addWidget(self.btn_cancel_batch)
        self.batch_bar_frame.setVisible(False)
        right_layout.addWidget(self.batch_bar_frame)

        self.right_stack = QStackedWidget()
        right_layout.addWidget(self.right_stack)

        self.profile = QWebEngineProfile("cookidoo_persistent", self)
        self.profile.setPersistentStoragePath(str(SESSION_DIR.resolve()))
        self.profile.setCachePath(str(CACHE_DIR.resolve()))
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        
        settings = self.profile.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)

        self.webview = QWebEngineView()
        self.webpage = QWebEnginePage(self.profile, self.webview)
        
        page_settings = self.webpage.settings()
        page_settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        page_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        page_settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        page_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        self.webview.setPage(self.webpage)
        self.webview.urlChanged.connect(self._on_url_changed)
        self.webview.loadFinished.connect(self._on_page_load_finished)
        if LAN_STATE["ok"]:
            self.webview.setUrl(QUrl(f"http://127.0.0.1:{LAN_PORT}/search?ui={self.ui_lang}&desk=1"))
        else:
            self.webview.setUrl(QUrl("https://cookidoo.cz/foundation/cs-CZ"))
        self._search_pages = {}
        self._search_timer = QTimer(self)
        self._search_timer.setInterval(400)
        self._search_timer.timeout.connect(self._process_search_queue)
        self._search_timer.start()
        self.right_stack.addWidget(self.webview)

        self.tm_screen = self._build_tm_player_widget()
        self.right_stack.addWidget(self.tm_screen)

        splitter.addWidget(right_panel)
        splitter.setSizes([440, 1240])
        self._apply_tooltips()

    def _toggle_icon_style(self):
        self.icon_style = "bots" if self.icon_style == "dots" else "dots"
        save_icon_style(self.icon_style)
        self.btn_icon_style.setText(self.t("icon_bots" if self.icon_style == "bots" else "icon_dots"))
        self._load_catalog()

    def _prompt_api_key(self):
        current_key = load_api_key()
        key, ok = QInputDialog.getText(self, tx("DeepL API klíč"), tx("Zadej svůj DeepL API klíč (volitelná záloha pro překlady):"), QLineEdit.EchoMode.Normal, current_key)
        if ok:
            save_api_key(key)
            QMessageBox.information(self, tx("Uloženo"), tx("DeepL API klíč byl uložen."))

    def _run_bg(self, label: str, fn, on_done):
        """Spustí pomalou práci ve vlákně; okno zůstává živé, výsledek přijde do on_done(box)."""
        box = {"done": False}

        def worker():
            try:
                box["result"] = fn()
            except Exception as e:
                box["error"] = str(e) or e.__class__.__name__
                log("Chyba na pozadí:\n" + traceback.format_exc())
            box["done"] = True

        threading.Thread(target=worker, daemon=True).start()
        timer = QTimer(self)
        timer.setInterval(400)
        t0 = time.time()

        def tick():
            if not box["done"]:
                self.url_bar.setText(f"{label} {int(time.time() - t0)} s")
                return
            timer.stop()
            self.url_bar.setText(self.webview.url().toString())
            on_done(box)

        timer.timeout.connect(tick)
        timer.start()
        self.url_bar.setText(label)

    def _offline_translator_dialog(self):
        if not has_argos():
            if getattr(sys, "frozen", False):
                QMessageBox.information(self, tx("Offline překladač"),
                                        tx("V této verzi programu offline překladač chybí – stáhni novou verzi aplikace."))
                return
            ans = QMessageBox.question(self, tx("Offline překladač"), tx(
                "Offline překladač (Argos Translate) není nainstalovaný.\n\nNainstalovat ho teď i s jazykovými modely? "
                "Jednorázově se stáhnou knihovny a modely (zhruba 1–2 GB), potřebuje to internet a pár minut."))
            if ans == QMessageBox.StandardButton.Yes:
                self._run_bg(tx("📥 Stahuji offline překladač…"), install_offline_translator, self._on_argos_installed)
            return
        self._run_bg(tx("🌍 Zjišťuji stav offline překladače…"), lambda: argos_call({"action": "status"}, 600), self._on_argos_status)

    def _on_argos_status(self, box: dict):
        if "error" in box:
            QMessageBox.warning(self, tx("Offline překladač"),
                                tx("Offline překladač je nainstalovaný, ale nejde spustit:\n\n{err}\n\nPodrobnosti: {log}",
                                   err=box['error'], log=APP_LOG.resolve()))
            return
        st = box["result"]
        pairs = [tuple(x) for x in st.get("pairs", [])]
        have = ", ".join(f"{a}→{b}" for a, b in pairs) or tx("žádné")
        missing = [pr for pr in OFFLINE_PAIRS if pr not in pairs]
        msg = tx("Argos Translate {ver} funguje.\n\nStažené jazykové modely: {have}", ver=st.get('version', '?'), have=have)
        if not missing:
            QMessageBox.information(self, tx("Offline překladač"),
                                    msg + tx("\n\n✅ Čeština a angličtina jsou stažené – překlad funguje i bez internetu a bez klíčů."))
            return
        ans = QMessageBox.question(
            self, tx("Offline překladač"),
            msg + tx("\n\nChybí: {missing}\n\nStáhnout je teď? (jednorázově, potřebuje internet, každý model má desítky až stovky MB)",
                     missing=", ".join(f"{a}→{b}" for a, b in missing)))
        if ans == QMessageBox.StandardButton.Yes:
            self._run_bg(tx("📥 Stahuji jazykové modely…"),
                         lambda: argos_call({"action": "install", "pairs": [list(x) for x in missing]}, 3600),
                         self._on_argos_installed)

    def _ask_offline_download(self, text: str) -> tuple:
        """ANO / NE + „Příště se již neptat“ + kde jde překladač stáhnout později. Vrací (ano, už se neptat)."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tx("Offline překladač"))
        box.setText(text)
        box.setInformativeText(tx("Překladač je vždy možné stáhnout v ⚙️ Nastavení → 📥 Stáhnout offline překladač."))
        b_yes = box.addButton(tx("ANO"), QMessageBox.ButtonRole.YesRole)
        box.addButton(tx("NE"), QMessageBox.ButtonRole.NoRole)
        chk = QCheckBox(tx("Příště se již neptat"))
        box.setCheckBox(chk)
        box.setDefaultButton(b_yes)
        box.exec()
        return box.clickedButton() is b_yes, chk.isChecked()

    def _startup_offline_check(self):
        """Při startu: chybí offline překladač nebo jeho jazyky? Zeptá se (dokud uživatel nezvolí „už se neptat“)."""
        if load_config().get("offline_tr_never_ask"):
            return

        def checked(box):
            if "error" in box:
                log(f"Kontrola offline překladače při startu selhala: {box['error']}")
                return
            st = box["result"]
            if st["installed"] and not st["missing"]:
                return
            if not st["installed"] and getattr(sys, "frozen", False):
                return                                  # exe bez překladače – nic se nedá doinstalovat
            text = (tx("Offline překladač (Argos Translate) není nainstalovaný.") if not st["installed"] else
                    tx("Offline překladači chybí jazykové modely: {missing}.",
                       missing=", ".join(f"{a}→{b}" for a, b in st["missing"])))
            text += "\n\n" + tx("Stáhnout ho teď? Překlad receptů pak funguje i bez internetu a bez API klíčů. "
                                 "Stahuje se jednou (stovky MB, bez Pythonu knihoven až 1–2 GB).")
            yes, never = self._ask_offline_download(text)
            if never and not yes:
                save_config({"offline_tr_never_ask": True})
            if yes:
                self._run_bg(tx("📥 Stahuji offline překladač…"), install_offline_translator, self._on_argos_installed)

        self._run_bg(tx("🌍 Zjišťuji stav offline překladače…"), offline_translator_state, checked)

    def _on_argos_installed(self, box: dict):
        if "error" in box:
            QMessageBox.warning(self, tx("Offline překladač"), tx("Stažení se nepodařilo:\n\n{err}", err=box['error']))
            return
        have = ", ".join(f"{a}→{b}" for a, b in box["result"].get("pairs", []))
        QMessageBox.information(self, tx("Offline překladač"), tx("✅ Hotovo. Stažené modely: {have}\n\nPřeklad teď funguje i bez internetu.", have=have))

    def _translator_label(self) -> str:
        if HAS_DEEPL and load_api_key():
            return "DeepL"
        if load_gemini_key():
            return "Gemini"
        return tx("offline překladač")

    def _ensure_translator(self) -> bool:
        if translation_available():
            return True
        QMessageBox.information(
            self, tx("Překlad"),
            tx("Pro překlad je potřeba jedna z možností:\n\n"
               "• ✨ Gemini AI klíč (zdarma z aistudio.google.com) – nejlepší kvalita\n"
               "• offline překladač: py -m pip install argostranslate – pak v ⚙️ → 📥 Stáhnout offline překladač stáhni jazyky\n"
               "  (potom funguje bez klíče i bez internetu)"))
        self._prompt_gemini_key()
        return translation_available()

    def _prompt_gemini_key(self):
        current_key = load_gemini_key()
        key, ok = QInputDialog.getText(
            self,
            tx("Google Gemini API klíč (volitelný)"),
            tx("Zadej bezplatný Gemini API klíč (z aistudio.google.com) pro překlady receptů\n"
               "a obousměrnou AI konverzi TM6 <-> Monsieur Cuisine.\n"
               "Pokud necháš prázdné, použije se offline překladač (je-li nainstalován) a vestavěný konvertor:"),
            QLineEdit.EchoMode.Normal,
            current_key
        )
        if ok:
            save_gemini_key(key)
            QMessageBox.information(self, tx("Uloženo"), tx("Nastavení Gemini klíče bylo uloženo."))

    def _switch_any_language(self, target_lang: str):
        """Tlačítka Orig / EN / CZ v liště receptu: přepnou kartu i režim vaření (podle toho, co je zobrazené)."""
        if self.right_stack.currentIndex() == 1:
            self._switch_recipe_language(target_lang)
        else:
            self._switch_card_language(target_lang)

    def _switch_card_language(self, target_lang: str):
        if not self.current_recipe_folder:
            QMessageBox.warning(self, tx("Vyber recept"), tx("Nejprve vyber recept v seznamu vlevo."))
            return
        folder = self.current_recipe_folder

        if target_lang == "orig":
            self.display_lang = "orig"
            orig_json = ensure_device_recipe_file(folder, self.device_mode)
            if orig_json and orig_json.exists():
                self.current_offline_data = json.loads(orig_json.read_text(encoding="utf-8"))
            self._update_lang_and_scale_buttons()
            self._render_tm_step()
            html_orig = ensure_clean_html_snapshot(folder)
            if html_orig and html_orig.exists() and self.right_stack.currentIndex() == 0:
                self._show_card(html_orig, "orig")
            return

        if (folder / f"page_snapshot_{target_lang}.html").exists() and self._load_translated_json(target_lang):
            self._show_translated_card(target_lang)
            return

        if not self._ensure_translator():
            return
        self._start_translation(target_lang, lambda: self._show_translated_card(target_lang, reload_json=True))

    def _show_translated_card(self, target_lang: str, reload_json: bool = False):
        folder = self.current_recipe_folder
        if not folder:
            return
        if reload_json:
            self._load_translated_json(target_lang)
        self.display_lang = target_lang
        self._update_lang_and_scale_buttons()
        self._render_tm_step()
        lang_html = folder / f"page_snapshot_{target_lang}.html"
        if lang_html.exists() and self.right_stack.currentIndex() == 0:
            self._show_card(lang_html, target_lang)

    def _load_translated_json(self, target_lang: str) -> bool:
        folder = self.current_recipe_folder
        if not folder:
            return False
        prefix = get_base_prefix_for_device(folder, self.device_mode)
        f = folder / f"{prefix}_{target_lang}.json"
        if not f.exists():
            return False
        try:
            self.current_offline_data = json.loads(f.read_text(encoding="utf-8"))
            return True
        except Exception as e:
            log(f"Nelze načíst překlad {f}: {e}")
            return False

    def _start_translation(self, target_lang: str, on_done, force: bool = False):
        folder, device = self.current_recipe_folder, self.device_mode
        start_translation_job(folder, target_lang, device, force=force)
        self._tr_poll = {"folder": folder, "lang": target_lang, "device": device, "on_done": on_done, "t0": time.time()}
        if self._tr_timer is None:
            self._tr_timer = QTimer(self)
            self._tr_timer.setInterval(500)
            self._tr_timer.timeout.connect(self._poll_translation)
        self._tr_timer.start()
        self._set_tr_status(tx("⏳ Překládám do {lang} – {engine}…", lang=target_lang.upper(), engine=self._translator_label()))

    def _poll_translation(self):
        pj = self._tr_poll
        if not pj:
            self._tr_timer.stop()
            return
        st = translation_job_status(pj["folder"], pj["lang"], pj["device"])
        if st.get("state") == "running":
            self._set_tr_status(tx("⏳ Překládám do {lang} – {engine}… {s} s", lang=pj['lang'].upper(), engine=self._translator_label(), s=int(time.time() - pj['t0'])))
            return
        self._tr_timer.stop()
        self._tr_poll = None
        if pj["folder"] != self.current_recipe_folder:
            return                                   # mezitím byl vybrán jiný recept; překlad zůstal uložený
        if st.get("state") == "done":
            pj["on_done"]()
            if self.combo_title_lang.currentData() != "orig":
                self._load_catalog()             # přeložený název hned i v seznamu vlevo
        else:
            if self.display_lang == pj["lang"] and not self._load_translated_json(pj["lang"]):
                # starý překlad byl smazán (Přeložit znovu) a nový se nepovedl → zpět na originál
                if self.right_stack.currentIndex() == 0:
                    self._switch_card_language("orig")
                else:
                    self._switch_recipe_language("orig")
            self._update_tr_info()
            QMessageBox.warning(self, tx("Překlad"),
                                tx("Překlad se nepodařilo vytvořit:\n\n{err}\n\nZůstává zobrazen originál. Zkusit to můžeš znovu (🔄 Přeložit znovu).",
                                   err=st.get('error') or tx('neznámá chyba')))

    def _set_tr_status(self, text: str):
        self.lbl_tr_info.setText(text)
        self.lbl_tr_info.setVisible(True)
        if self.right_stack.currentIndex() == 0:
            self.url_bar.setText(text)

    def _update_tr_info(self):
        if not hasattr(self, "lbl_tr_info"):
            return
        data = self.current_offline_data or {}
        translated = self.display_lang != "orig" and (data.get("translated_by") or data.get("translation_same_language") or data.get("language"))
        if self._tr_poll:
            return                                   # běží překlad – nechá se zobrazený průběh
        self.lbl_tr_info.setVisible(bool(translated))
        self.btn_retranslate.setVisible(bool(translated))
        if translated:
            self.lbl_tr_info.setText(describe_translation(data, self.ui_lang))

    def _retranslate_current(self):
        folder = self.current_recipe_folder
        if not folder:
            QMessageBox.information(self, tx("Přeložit znovu"), tx("Nejprve vyber recept."))
            return
        lang = self.display_lang
        if lang == "orig":
            QMessageBox.information(self, tx("Přeložit znovu"), tx("Nejprve přepni jazyk na 🇬🇧 EN nebo 🇨🇿 CZ – přeloží se znovu ten zobrazený."))
            return
        if not self._ensure_translator():
            return
        clear_translation(folder, lang)
        if self.right_stack.currentIndex() == 0:
            self._start_translation(lang, lambda: self._show_translated_card(lang, reload_json=True), force=True)
        else:
            self._start_translation(lang, lambda: self._after_recipe_translation(lang), force=True)

    def _after_recipe_translation(self, target_lang: str):
        if self._load_translated_json(target_lang):
            self.display_lang = target_lang
        self._update_lang_and_scale_buttons()
        self._render_tm_step()

    def _change_ui_language(self, index: int):
        self.ui_lang = ("cs", "en")[index]
        set_ui_lang(self.ui_lang)
        save_config({"ui_lang": self.ui_lang})
        self.setWindowTitle(self.t('window_title'))
        self.btn_expand_all.setToolTip(tx("Rozbalit všechny kategorie"))
        self.btn_collapse_all.setToolTip(tx("Sbalit všechny kategorie"))
        self.btn_icon_style.setToolTip(tx("Přepnout styl ikon před recepty"))
        self.btn_card_retranslate.setToolTip(tx("Přeložit znovu – smaže uložený překlad tohoto jazyka a přeloží recept i kartu znovu"))
        self.btn_offline_tr.setText(tx("📥 Stáhnout offline překladač"))
        self.btn_translate_all.setText(tx("🌍 Přeložit všechny recepty (EN + CZ)…"))
        self.btn_whats_new.setText(tx("ℹ️ Co je nového a podmínky použití (verze {v})", v=APP_VERSION))
        self.act_how_to.setText(tx("❓ Návod k použití"))
        self.btn_import_backup.setText(tx("📥 Importovat recepty (.7z)…"))
        self.btn_export_backup.setText(tx("📦 Exportovat označené (.7z)…"))
        self.btn_help.setText(tx("❓ Návod"))
        self.menu_about_section.setText(tx("Aplikace"))
        self.btn_settings.setText(tx("⚙️ Nastavení"))
        self.menu_translate_section.setText(tx("Překlad"))
        self.menu_view_section.setText(tx("Vzhled"))
        self.menu_ui_lang.setTitle(self.t('ui_lang_label') + " " + ("English" if self.ui_lang == "en" else "Čeština"))
        self.btn_new_cat.setText(tx("➕ Nová kategorie"))
        self.btn_new_cat.setToolTip(tx("Založit novou kategorii (vybraný recept do ní můžeš rovnou přesunout)"))
        self.combo_title_lang.setToolTip(tx("V jakém jazyce ukazovat názvy receptů (přeložený název je k dispozici po překladu receptu)"))
        self._fill_title_lang_combo()
        self.lbl_view.setText(tx("Zobrazit:"))
        self._apply_tooltips()
        self.lbl_card_lang.setText(tx("Jazyk:"))
        self.btn_offline_tr.setToolTip(tx("Stav offline překladače (Argos Translate) a stažení jazykových modelů pro překlad bez internetu a bez klíčů"))
        self.lbl_recipe_lang.setText(tx("🌍 Jazyk receptu:"))
        self.lbl_scale.setText(tx("⚖️ Dávka:"))
        self.btn_unit_toggle.setText(self.t('metric_on' if self.use_metric_conversion else 'metric_off'))
        self.btn_fine_toggle.setToolTip(tx("Jemné kroky: každé navážení a každé nastavení stroje jako samostatný krok"))
        self.btn_retranslate.setText(tx("🔄 Přeložit znovu"))
        self.btn_retranslate.setToolTip(tx("Smaže uložený překlad tohoto jazyka a přeloží recept znovu"))
        sel = self._get_selected_recipe_item()
        if sel is not None:
            self.btn_toggle_fav.setText(self.t('fav_btn_on' if sel.data(0, Qt.ItemDataRole.UserRole + 2) else 'fav_btn_off'))
        if not self.current_offline_data:
            self.tm_title.setText(tx("Název receptu"))
            self.tm_step_counter.setText(tx("KROK 1 Z X"))
            self.lbl_dial_time.setText(tx("⏱️ ČAS") + ": —")
            self.lbl_dial_temp.setText(tx("🌡️ TEPLOTA") + ": —")
            self.lbl_dial_speed.setText(tx("🔪 OTÁČKY") + ": —")
        self._update_tr_info()
        self.lbl_wifi.setText(f"{self.t('wifi_label')}{self.lan_url_str}")
        self.btn_qr.setText(self.t('qr_btn'))
        self.lbl_cat_title.setText(tx("📚 Moje Offline Kuchařka"))
        self.btn_expand_all.setText(self.t('expand_btn'))
        self.btn_collapse_all.setText(self.t('collapse_btn'))
        self.chk_only_favorites.setText(self.t('only_fav'))
        self.btn_icon_style.setText(self.t("icon_bots" if self.icon_style == "bots" else "icon_dots"))
        self.btn_theme_toggle.setText(self.t('dark_on' if self.is_dark_mode else 'light_on'))
        self.combo_platform_filter.setItemText(0, self.t("plat_all"))
        self.combo_platform_filter.setItemText(1, self.t("plat_tm6"))
        self.combo_platform_filter.setItemText(2, self.t("plat_mcs"))
        self.combo_platform_filter.setItemText(3, self.t("plat_other"))
        self.btn_home.setText(tx("🏠 Domů"))
        self.search_input.setPlaceholderText(self.t('search_ph'))
        self.btn_toggle_fav.setText(self.t('fav_btn'))
        self.btn_change_cat.setText(self.t('cat_btn'))
        self.btn_view_card.setText(self.t('card_btn'))
        self.btn_view_tm.setText(self.t('tm_btn'))
        self.btn_view_mcs.setText(self.t('mcs_btn'))
        self.btn_export_pdf.setText(self.t('pdf_btn'))
        self.btn_delete.setText(self.t('del_btn'))
        self.btn_home_tm.setText(self.t('home_tm_btn'))
        self.btn_home_mcs.setText(self.t('home_mcs_btn'))
        self.btn_back.setText(self.t('back_btn'))
        self.btn_deepl_key.setText(self.t('key_btn'))
        self.btn_gemini_key.setText(self.t('ai_key_btn'))
        self.btn_save_single.setText(self.t('save_single'))
        self.btn_donate.setText(self.t('donate_btn'))
        self.btn_cancel_batch.setText(self.t('cancel_btn'))
        self.btn_fine_toggle.setText(self.t('fine_on' if self.fine_mode else 'fine_off'))
        self.btn_lang_orig.setText(self.t('lang_orig'))
        self.btn_lang_en.setText(self.t('lang_en'))
        self.btn_lang_cs.setText(self.t('lang_cs'))
        
        self.btn_prev_step.setText(self.t('prev_btn'))
        self.btn_next_step.setText(self.t('next_btn'))

        self._refresh_categories_combo()
        self._load_catalog()
        if self.current_offline_data:
            self._render_tm_step()

    def _show_qr_dialog(self):
        dlg = QrDialog(self.lan_url_str, self)
        dlg.exec()

    def _build_tm_player_widget(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background-color: #181818; color: #F5F5F5;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(25, 16, 25, 16)

        header_layout = QHBoxLayout()
        self.tm_title = QLabel(tx("Název receptu"))
        self.tm_title.setFont(QFont("Segoe UI", 19, QFont.Weight.Bold))
        self.tm_title.setStyleSheet("color: #00E676;")

        self.tm_step_counter = QLabel(tx("KROK 1 Z X"))
        self.tm_step_counter.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.tm_step_counter.setStyleSheet("background-color: #2E7D32; color: white; padding: 6px 14px; border-radius: 6px;")
        header_layout.addWidget(self.tm_title, stretch=1)
        header_layout.addWidget(self.tm_step_counter)
        layout.addLayout(header_layout)

        controls_bar = QHBoxLayout()
        self.lbl_recipe_lang = QLabel(tx("🌍 Jazyk receptu:"))
        self.lbl_recipe_lang.setStyleSheet("font-weight: bold; color: #BDBDBD;")
        controls_bar.addWidget(self.lbl_recipe_lang)

        self.btn_lang_orig = QPushButton(self.t('lang_orig'))
        self.btn_lang_en = QPushButton(self.t('lang_en'))
        self.btn_lang_cs = QPushButton(self.t('lang_cs'))

        for b, code in ((self.btn_lang_orig, "orig"), (self.btn_lang_en, "en"), (self.btn_lang_cs, "cs")):
            b.clicked.connect(lambda _, c=code: self._switch_recipe_language(c))
            controls_bar.addWidget(b)

        controls_bar.addSpacing(20)
        self.lbl_scale = QLabel(tx("⚖️ Dávka:"))
        self.lbl_scale.setStyleSheet("font-weight: bold; color: #BDBDBD;")
        controls_bar.addWidget(self.lbl_scale)

        self.scale_buttons = {}
        for sc in (0.5, 1.0, 1.5, 2.0, 3.0):
            btn_sc = QPushButton(f"{sc:g}x")
            btn_sc.setFixedWidth(48)
            btn_sc.clicked.connect(lambda _, s=sc: self._set_portion_scale(s))
            self.scale_buttons[sc] = btn_sc
            controls_bar.addWidget(btn_sc)

        controls_bar.addStretch(1)
        self.btn_unit_toggle = QPushButton(self.t('metric_on'))
        self.btn_unit_toggle.setCheckable(True)
        self.btn_unit_toggle.setChecked(True)
        self.btn_unit_toggle.setStyleSheet("background-color: #0277BD; color: white; font-weight: bold; padding: 6px 12px; border-radius: 6px;")
        self.btn_unit_toggle.clicked.connect(self._toggle_metric_units)
        controls_bar.addWidget(self.btn_unit_toggle)

        self.btn_fine_toggle = QPushButton(self.t('fine_on'))
        self.btn_fine_toggle.setCheckable(True)
        self.btn_fine_toggle.setChecked(True)
        self.btn_fine_toggle.setToolTip(tx("Jemné kroky: každé navážení a každé nastavení stroje jako samostatný krok"))
        self.btn_fine_toggle.setStyleSheet("background-color: #6A1B9A; color: white; font-weight: bold; padding: 6px 12px; border-radius: 6px;")
        self.btn_fine_toggle.clicked.connect(self._toggle_fine_steps)
        controls_bar.addWidget(self.btn_fine_toggle)

        layout.addLayout(controls_bar)

        tr_bar = QHBoxLayout()
        self.lbl_tr_info = QLabel("")
        self.lbl_tr_info.setWordWrap(True)
        self.lbl_tr_info.setStyleSheet("background-color: #311B92; color: #EDE7F6; padding: 5px 10px; border-radius: 6px;")
        self.btn_retranslate = QPushButton(tx("🔄 Přeložit znovu"))
        self.btn_retranslate.setToolTip(tx("Smaže uložený překlad tohoto jazyka a přeloží recept znovu"))
        self.btn_retranslate.setStyleSheet("background-color: #4527A0; color: white; font-weight: bold; padding: 5px 10px; border-radius: 6px;")
        self.btn_retranslate.clicked.connect(self._retranslate_current)
        tr_bar.addWidget(self.lbl_tr_info, stretch=1)
        tr_bar.addWidget(self.btn_retranslate)
        self.lbl_tr_info.setVisible(False)
        self.btn_retranslate.setVisible(False)
        layout.addLayout(tr_bar)
        self._update_lang_and_scale_buttons()

        dials_layout = QHBoxLayout()
        self.lbl_dial_time = QLabel(tx("⏱️ ČAS") + ": —")
        self.lbl_dial_temp = QLabel(tx("🌡️ TEPLOTA") + ": —")
        self.lbl_dial_speed = QLabel(tx("🔪 OTÁČKY") + ": —")

        for lbl, border_col in ((self.lbl_dial_time, "#00B0FF"), (self.lbl_dial_temp, "#FF5252"), (self.lbl_dial_speed, "#FFD740")):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
            lbl.setMinimumHeight(62)
            lbl.setStyleSheet(f"background-color: #242424; border: 2px solid {border_col}; border-radius: 10px; padding: 8px; color: white;")
            dials_layout.addWidget(lbl)

        layout.addLayout(dials_layout)

        content_split = QSplitter(Qt.Orientation.Horizontal)
        self.tm_ingredients_box = QTextBrowser()
        self.tm_ingredients_box.setStyleSheet("background-color: #222222; border-radius: 10px; padding: 14px; font-size: 15px;")
        content_split.addWidget(self.tm_ingredients_box)

        self.tm_step_box = QTextBrowser()
        self.tm_step_box.setStyleSheet("background-color: #252526; border: 2px solid #009A3E; border-radius: 12px; padding: 24px;")
        content_split.addWidget(self.tm_step_box)
        content_split.setSizes([410, 760])
        layout.addWidget(content_split, stretch=1)

        nav = QHBoxLayout()
        self.btn_prev_step = QPushButton(self.t('prev_btn'))
        self.btn_prev_step.setMinimumHeight(52)
        self.btn_prev_step.setStyleSheet("background-color: #373737; color: white; font-size: 16px; font-weight: bold; border-radius: 6px;")
        self.btn_prev_step.clicked.connect(self._prev_tm_step)

        self.btn_next_step = QPushButton(self.t('next_btn'))
        self.btn_next_step.setMinimumHeight(52)
        self.btn_next_step.setStyleSheet("background-color: #009A3E; color: white; font-size: 16px; font-weight: bold; border-radius: 6px;")
        self.btn_next_step.clicked.connect(self._next_tm_step)

        nav.addWidget(self.btn_prev_step)
        nav.addWidget(self.btn_next_step)
        layout.addLayout(nav)

        return w

    def _update_lang_and_scale_buttons(self):
        active_style = "background-color: #6A1B9A; color: white; font-weight: bold; border: 1px solid #CE93D8;"
        idle_style = "background-color: #2D2D30; color: #CCCCCC;"

        self.btn_lang_orig.setStyleSheet(active_style if self.display_lang == "orig" else idle_style)
        self.btn_lang_en.setStyleSheet(active_style if self.display_lang == "en" else idle_style)
        self.btn_lang_cs.setStyleSheet(active_style if self.display_lang == "cs" else idle_style)
        if hasattr(self, "btn_card_orig"):
            for b_, code in ((self.btn_card_orig, "orig"), (self.btn_card_en, "en"), (self.btn_card_cs, "cs")):
                b_.setStyleSheet((active_style if self.display_lang == code else idle_style) + " padding: 5px 8px;")

        sc_active = "background-color: #00897B; color: white; font-weight: bold; border: 1px solid #80CBC4;"
        for sc, btn in self.scale_buttons.items():
            btn.setStyleSheet(sc_active if abs(self.portion_scale - sc) < 0.01 else idle_style)
        self._update_tr_info()

    def _set_portion_scale(self, scale_val: float):
        self.portion_scale = scale_val
        self._update_lang_and_scale_buttons()
        self._render_tm_step()

    def _switch_recipe_language(self, target_lang: str):
        if not self.current_recipe_folder:
            return

        if target_lang == "orig":
            self.display_lang = "orig"
            orig_file = ensure_device_recipe_file(self.current_recipe_folder, self.device_mode)
            if orig_file and orig_file.exists():
                self.current_offline_data = json.loads(orig_file.read_text(encoding="utf-8"))
            self._update_lang_and_scale_buttons()
            self._render_tm_step()
            return

        if self._load_translated_json(target_lang):
            self.display_lang = target_lang
            self._update_lang_and_scale_buttons()
            self._render_tm_step()
            return

        if not self._ensure_translator():
            return
        self._start_translation(target_lang, lambda: self._after_recipe_translation(target_lang))

    def _toggle_theme(self):
        self.is_dark_mode = self.btn_theme_toggle.isChecked()
        self._apply_theme()
        self._inject_offline_page_fixes()

    def _apply_theme(self):
        app = QApplication.instance()
        if self.is_dark_mode:
            app.setStyleSheet(DARK_THEME_QSS)
            self.btn_theme_toggle.setText(self.t('dark_on'))
        else:
            app.setStyleSheet(LIGHT_THEME_QSS)
            self.btn_theme_toggle.setText(self.t('light_on'))

    def _inject_offline_page_fixes(self):
        url_str = self.webview.url().toString()
        if not is_offline_card_url(url_str) or url_str.endswith(".mhtml"):
            return

        dark_flag = "true" if self.is_dark_mode else "false"
        js_fix = f"""
        (() => {{
            let fixStyle = document.getElementById('cookidoo-offline-fix');
            if (!fixStyle) {{
                fixStyle = document.createElement('style');
                fixStyle.id = 'cookidoo-offline-fix';
                document.head.appendChild(fixStyle);
            }}
            let css = `
                header, core-header, .page-header, .l-header, nav,
                [class*="header__"], [class*="Header"], .core-nav,
                core-transclusion, footer, .cookie-banner, #onetrust-consent-sdk {{
                    display: none !important; height: 0 !important; visibility: hidden !important;
                }}
                *[style*="position: fixed"], *[style*="position: sticky"] {{ position: static !important; }}
                body, main, .recipe-card, #recipe-content {{ padding-top: 20px !important; margin-top: 0 !important; }}
            `;
            if ({dark_flag}) {{
                css += `
                    html {{ filter: invert(0.90) hue-rotate(180deg) !important; background-color: #121212 !important; }}
                    img, video, picture, svg, [style*="background-image"] {{ filter: invert(1) hue-rotate(180deg) !important; }}
                `;
            }}
            fixStyle.innerHTML = css;
        }})();
        """
        self.webpage.runJavaScript(js_fix)

    def _show_card(self, html_file: Path | None, lang: str = "orig"):
        """Karta receptu přes vestavěný server (http://127.0.0.1) – styly a obrázky z webu se tak načtou
        v každé verzi Qt WebEngine (u file:// je to blokované). Server neběží → záložně soubor."""
        if LAN_STATE["ok"] and self.current_recipe_id:
            self.webview.setUrl(QUrl(local_card_url(self.current_recipe_id, lang)))
        elif html_file and html_file.exists():
            self.webview.setUrl(QUrl.fromLocalFile(str(html_file.resolve())))

    def _switch_to_card_view(self):
        self.right_stack.setCurrentIndex(0)
        if self.current_recipe_folder:
            html_file = ensure_clean_html_snapshot(self.current_recipe_folder)
            lang = "orig"
            if self.display_lang in ("en", "cs"):
                tr_html = self.current_recipe_folder / f"page_snapshot_{self.display_lang}.html"
                if tr_html.exists():
                    html_file, lang = tr_html, self.display_lang
            self._show_card(html_file, lang)

    def _current_steps(self, data: dict | None) -> list[dict]:
        if not data:
            return []
        return get_fine_steps(data) if self.fine_mode else (data.get("steps") or [])

    def _toggle_fine_steps(self):
        data = self.current_offline_data
        old_steps = self._current_steps(data)
        old_idx = self.current_step_index
        self.fine_mode = self.btn_fine_toggle.isChecked()
        self.btn_fine_toggle.setText(self.t('fine_on' if self.fine_mode else 'fine_off'))
        if data:
            self.current_step_index = map_step_index(old_steps, self._current_steps(data), old_idx, to_fine=self.fine_mode)
        self._render_tm_step()

    def _toggle_metric_units(self):
        self.use_metric_conversion = self.btn_unit_toggle.isChecked()
        self.btn_unit_toggle.setText(self.t('metric_on' if self.use_metric_conversion else 'metric_off'))
        self._render_tm_step()

    def _go_online_cookidoo(self):
        self.right_stack.setCurrentIndex(0)
        self.webview.setUrl(QUrl("https://cookidoo.cz/foundation/cs-CZ"))

    def _go_online_mcs(self):
        self.right_stack.setCurrentIndex(0)
        saved_mcs_url = load_config().get("mcs_home_url", "https://www.monsieur-cuisine.com/cs/recipes")
        self.webview.setUrl(QUrl(saved_mcs_url))

    def _on_url_changed(self, qurl: QUrl):
        u_str = qurl.toString()
        self.url_bar.setText(u_str)
        if u_str.startswith(f"http://127.0.0.1:{LAN_PORT}/open?"):
            r_id = urllib.parse.parse_qs(urllib.parse.urlparse(u_str).query).get("id", [""])[0]
            QTimer.singleShot(0, lambda: self._open_recipe_by_id(r_id))
            return
        m = re.match(r"^(https://www\.monsieur-cuisine\.com/[a-z]{2}/(?:recipes|recepty|rezepte|przepisy|recettes|recetas|ricette))", u_str, re.IGNORECASE)
        if m:
            save_config({"mcs_home_url": m.group(1)})

    def _open_recipe_by_id(self, r_id: str):
        root = self.recipe_tree.invisibleRootItem()
        for i in range(root.childCount()):
            cat = root.child(i)
            for j in range(cat.childCount()):
                it = cat.child(j)
                if it.data(0, Qt.ItemDataRole.UserRole + 1) == r_id:
                    cat.setHidden(False)
                    it.setHidden(False)
                    cat.setExpanded(True)
                    self.recipe_tree.setCurrentItem(it)
                    self.recipe_tree.scrollToItem(it)
                    self.right_stack.setCurrentIndex(0)
                    self._on_tree_item_clicked(it, 0)
                    return
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT folder_path FROM recipes WHERE recipe_id = ?", (r_id,)).fetchone()
        conn.close()
        if row:            # recept je skrytý filtrem → zobrazit aspoň kartu
            self.current_recipe_folder = resolve_recipe_folder(row[0])
            self.current_recipe_id = r_id
            self._show_card(ensure_clean_html_snapshot(self.current_recipe_folder), "orig")

    # ---------------------------------------------------------------- hledání receptů na webech
    def _go_home(self):
        """🏠 Domů: úvodní stránka s hledáním (ve vestavěném prohlížeči)."""
        self.right_stack.setCurrentIndex(0)
        if LAN_STATE["ok"]:
            self.webview.setUrl(QUrl(f"http://127.0.0.1:{LAN_PORT}/search?ui={self.ui_lang}&desk=1"))
        else:
            self._go_online_cookidoo()

    def _process_search_queue(self):
        """Hledání zadaná na stránce /search (z počítače i z mobilu) spustí ve skrytých stránkách prohlížeče."""
        with _SEARCH_LOCK:
            keys, _SEARCH_QUEUE[:] = list(_SEARCH_QUEUE), []
        for key in keys:
            st = SEARCH_STATE.get(key)
            if not st:
                continue
            for src_cfg in search_sources():
                if src_cfg["id"] in st["sources"]:
                    self._start_source_search(key, src_cfg, st["q"])

    def _start_source_search(self, key: str, cfg: dict, q: str):
        # Stránka se opravdu vykreslí (mimo obrazovku) – jinak weby nenačtou líné obrázky a některé ani výsledky.
        view = QWebEngineView()
        page = QWebEnginePage(self.profile, view)
        view.setPage(page)
        try:
            view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            view.resize(1366, 2400)
            view.show()
            page.setAudioMuted(True)
        except Exception:
            pass
        pid = f"{key}::{cfg['id']}"
        self._search_pages[pid] = view
        js = SEARCH_EXTRACT_JS.replace("%PATTERN%", json.dumps(cfg["link"])).replace("%SCOPE%", json.dumps(cfg.get("scope") or ""))
        state = {"tries": 0, "done": False, "best": []}

        def finish(results, status):
            if state["done"]:
                return
            state["done"] = True
            with _SEARCH_LOCK:
                s = SEARCH_STATE.get(key, {}).get("sources", {}).get(cfg["id"])
                if s is not None:
                    s["results"] = results
                    s["state"] = status
            pg = self._search_pages.pop(pid, None)
            if pg is not None:
                pg.deleteLater()
            missing = [r for r in results if not r.get("image")]
            if missing:
                threading.Thread(target=fill_missing_images, args=(key, cfg["id"]), daemon=True).start()

        def got(raw):
            if state["done"]:
                return
            try:
                res = json.loads(raw) if isinstance(raw, str) else []
            except Exception:
                res = []
            if isinstance(res, dict) and res.get("none"):
                finish([], "done")                        # web výslovně píše, že nic nenašel
                return
            res = rank_search_results(res if isinstance(res, list) else [], q, key.split("|", 1)[0])
            state["tries"] += 1
            # obrázky z předchozích pokusů zůstanou (stránka je načítá postupně při posouvání)
            prev = {r["url"]: r for r in state["best"]}
            for r in res:
                if not r.get("image") and prev.get(r["url"], {}).get("image"):
                    r["image"] = prev[r["url"]]["image"]
            if len(res) >= len(state["best"]):
                state["best"] = res
            best = state["best"]
            with_img = sum(1 for r in best if r.get("image"))
            if (best and (with_img >= 0.8 * len(best) or state["tries"] >= 5)) or state["tries"] >= 7:
                finish(best, "done")
            else:
                QTimer.singleShot(1300, extract)          # výsledky / obrázky se dotahují JavaScriptem → zkusit znovu

        def extract():
            if not state["done"] and pid in self._search_pages:
                try:
                    page.runJavaScript(js, got)
                except RuntimeError:
                    finish(state["best"], "done" if state["best"] else "error")

        started = {"x": False}

        def kick(*_):
            if not started["x"]:
                started["x"] = True
                extract()

        # i když se stránka „nedonačte“ (reklamy, přesměrování souhlasu s cookies), výsledky už obvykle v ní jsou
        page.loadFinished.connect(lambda ok: QTimer.singleShot(1500, kick))
        QTimer.singleShot(7000, kick)
        QTimer.singleShot(30000, lambda: finish(state["best"], "done" if state["best"] else "error"))
        page.setUrl(QUrl(cfg["url"].replace("{q}", urllib.parse.quote(q))))

    def _get_all_existing_categories(self) -> list[str]:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT DISTINCT category FROM recipes WHERE category IS NOT NULL AND category != '' ORDER BY category")
        cats = [r[0] for r in c.fetchall()]
        conn.close()
        for default_cat in ["Nezařazené", "Hlavní jídla", "Polévky", "Pečení & Dezerty", "Omáčky", "Monsieur Cuisine", "Cizojazyčné"] + self._custom_categories():
            if default_cat not in cats: cats.append(default_cat)
        return cats

    def _pick_category(self, title: str, prompt: str, current_raw: str | None) -> str | None:
        cats = self._get_all_existing_categories()
        labels = [cat_label(c) for c in cats]
        idx = cats.index(current_raw) if current_raw in cats else 0
        picked, ok = QInputDialog.getItem(self, title, prompt, labels, idx, True)
        if not ok:
            return None
        picked = picked.strip()
        if picked in labels:
            return cats[labels.index(picked)]
        return cat_from_label(picked) if picked else ""

    def _save_current_recipe(self, silent: bool = False):
        url_str = self.webview.url().toString()
        if is_offline_card_url(url_str):
            if not silent:
                QMessageBox.information(self, tx("Otevři detail"), tx("Teď je zobrazená už uložená karta receptu. Pro uložení otevři recept na webu Cookidoo nebo Monsieur Cuisine."))
            return
        is_mcs_site = "monsieur-cuisine.com" in url_str.lower()
        is_cookidoo_site = "cookidoo" in url_str.lower()

        if is_cookidoo_site and "/recipes/recipe/" not in url_str:
            if not silent:
                QMessageBox.information(self, tx("Otevři detail"), tx("Nejprve na Cookidoo rozklikni konkrétní recept."))
            return

        if is_mcs_site:
            slug = url_str.rstrip("/").split("/")[-1].split("?")[0]
            if "/recipe/" not in url_str or not slug or slug in ("rezepte", "recipes", "recepty", "przepisy", "recettes", "recetas", "ricette", "de", "en", "pl", "fr", "es", "it", "cs"):
                if not silent:
                    QMessageBox.information(self, tx("Otevři detail"), tx("Nejprve na Monsieur-Cuisine.com rozklikni konkrétní recept."))
                return
            clean_id = re.sub(r'[^\w-]', '', slug)[:36]
            recipe_id = f"mcs_{clean_id}"
            source_platform = "mcs"
        elif is_cookidoo_site:
            match = re.search(r"/(r\d+)", url_str)
            recipe_id = match.group(1) if match else f"r_{int(threading.get_ident())}"
            source_platform = "tm6"
        else:
            if not url_str.startswith(("http://", "https://")) or url_str.startswith(f"http://127.0.0.1:{LAN_PORT}"):
                if not silent:
                    QMessageBox.information(self, tx("Otevři detail"), tx("Nejprve otevři stránku s receptem (Cookidoo, Monsieur Cuisine nebo jiný web s recepty)."))
                return
            recipe_id = other_recipe_id(url_str)
            source_platform = "other"

        QTimer.singleShot(1500, lambda: self._trigger_actual_save(recipe_id, url_str, silent, source_platform))

    def _trigger_actual_save(self, recipe_id: str, url_str: str, silent: bool, source_platform: str, attempt: int = 0):
        # Monsieur-cuisine.com dotahuje obsah JavaScriptem – počkáme, až jsou kroky opravdu v DOM.
        js_ready = r"""(() => {
            try { window.scrollTo(0, document.body.scrollHeight); } catch (e) {}
            const ld = Array.from(document.querySelectorAll('script[type*="ld+json"]'))
                .some(s => /recipeInstructions/.test(s.textContent || ''));
            const t = document.body ? document.body.innerText : '';
            const hdr = /\n\s*(Příprava|Postup|Postup přípravy|Zubereitung|Preparation|Instructions|Przygotowanie)\s*:?\s*\n/i.test(t);
            const mcs = document.querySelector('.recipe-detail-live-note .text-pre-line');
            const mcsOk = !!(mcs && (mcs.textContent || '').trim().length > 30 && document.querySelector('.ingredient-group-view .v-list-item__title'));
            // Strukturovaná data receptu (jemné kroky): MCS → mc-api.tecpal.com, Cookidoo → JSON verze stránky
            if (window.__ccApi === undefined) {
                window.__ccApi = null;
                const done = t => { window.__ccApi = t || ''; };
                try {
                    const sc = window.siteConfig;
                    if (location.hostname.includes('monsieur-cuisine') && sc && sc.recipeId) {
                        const loc = (((sc.siteLanguages || {})[sc.viewerLang] || {}).default_locale || (sc.viewerLang + '_' + (sc.viewerCountry || ''))).replace('_', '-');
                        fetch('https://mc-api.tecpal.com/api/v2/recipes/' + sc.recipeId, {headers: {'Accept': 'application/json', 'Accept-Language': loc}})
                            .then(r => r.ok ? r.text() : '').then(done).catch(() => done(''));
                    } else if (location.pathname.includes('/recipes/recipe/')) {
                        const opt = {headers: {'Accept': 'application/json'}, credentials: 'include'};
                        fetch(location.pathname, opt)
                            .then(r => r.ok ? r.text() : fetch(location.pathname.replace(/\/([a-z]{2})-[A-Za-z]{2}\//, '/$1/'), opt).then(r2 => r2.ok ? r2.text() : ''))
                            .then(done).catch(() => done(''));
                    } else { done(''); }
                } catch (e) { done(''); }
            }
            const apiDone = window.__ccApi !== null;
            return (ld || hdr || mcsOk) && apiDone;
        })()"""

        def on_ready(ready):
            if ready or attempt >= 12:
                self._extract_page_now(recipe_id, url_str, silent, source_platform)
            else:
                QTimer.singleShot(700, lambda: self._trigger_actual_save(recipe_id, url_str, silent, source_platform, attempt + 1))

        self.webpage.runJavaScript(js_ready, on_ready)

    def _extract_page_now(self, recipe_id: str, url_str: str, silent: bool, source_platform: str):
        # innerText vynechává skrytý obsah → rozbalíme <details>/akordeony a vrátíme se nahoru
        js_extract_visible = r"""(() => {
            try {
                document.querySelectorAll('details').forEach(d => d.open = true);
                document.querySelectorAll('[aria-expanded="false"]').forEach(b => {
                    const txt = (b.innerText || '').toLowerCase();
                    if (/příprav|postup|zubereitung|preparation|instruction|krok|step/.test(txt)) { try { b.click(); } catch (e) {} }
                });
                window.scrollTo(0, 0);
            } catch (e) {}
            return JSON.stringify({text: document.body ? document.body.innerText : '', api: window.__ccApi || ''});
        })()"""

        def got_payload(payload):
            try:
                obj = json.loads(payload) if isinstance(payload, str) else {}
            except Exception:
                obj = {"text": payload or "", "api": ""}
            vt, api_raw = obj.get("text") or "", obj.get("api") or ""
            self.webpage.toHtml(
                lambda html: self._process_and_store_recipe(recipe_id, url_str, html, silent, source_platform, vt, api_raw)
            )

        self.webpage.runJavaScript(js_extract_visible, got_payload)

    def _process_and_store_recipe(self, recipe_id: str, url_str: str, html: str, silent: bool, source_platform: str, visible_text: str = "", api_raw: str = ""):
        soup = BeautifulSoup(html, "html.parser")

        extracted = extract_recipe_content(soup, visible_text, recipe_id)
        recipe_ld = extracted["recipe_ld"]
        title = extracted["title"]
        ingredients = extracted["ingredients"]
        steps_structured = extracted["steps"]
        tips = extracted.get("tips") or []

        # Strukturovaná data z API → jemné kroky (+ záloha pro kroky/suroviny)
        fine_steps, fine_src = [], "fallback"
        api_obj = {}
        try:
            api_obj = json.loads(api_raw) if api_raw else {}
        except Exception:
            api_obj = {}
        if isinstance(api_obj, dict) and api_obj:
            if source_platform == "mcs" and (api_obj.get("data") or {}).get("recipe"):
                fine_steps, fine_src = fine_steps_from_mcs_api(api_obj), "mcs-api"
                if not steps_structured:
                    steps_structured = mcs_api_to_basic(api_obj)
                    extracted["steps_source"] = "mcs-api"
            elif api_obj.get("recipeStepGroups"):
                fine_steps, fine_src = fine_steps_from_cookidoo_json(api_obj), "cookidoo-json"
                j_ings, j_steps = cookidoo_json_to_basic(api_obj)
                if j_steps:
                    steps_structured, extracted["steps_source"] = j_steps, "cookidoo-json"
                if not ingredients:
                    ingredients, extracted["ingredients_source"] = j_ings, "cookidoo-json"
        if not fine_steps:
            fine_steps = fine_steps_from_steps(steps_structured)

        if source_platform == "other":
            sc = scrape_other_recipe(html, url_str)
            if sc:
                title = sc["title"] or title
                if sc["ingredients"]:
                    ingredients, extracted["ingredients_source"] = sc["ingredients"], "recipe-scrapers"
                if sc["steps"]:
                    steps_structured = [{"html": html_mod.escape(s), "text": s, "dials": extract_tm_dials(s)} for s in sc["steps"]]
                    extracted["steps_source"] = "recipe-scrapers"
                    tips = []
                    fine_steps, fine_src = [], "fallback"
                recipe_ld = dict(recipe_ld or {})
                if sc["yields"] and not recipe_ld.get("recipeYield"):
                    recipe_ld["recipeYield"] = sc["yields"]
                if sc["image"] and not recipe_ld.get("image"):
                    recipe_ld["image"] = sc["image"]
            is_video = (not steps_structured and not ingredients and (
                "/video" in url_str.lower() or re.search(r'"@type"\s*:\s*"VideoObject"', html) is not None or soup.find("video") is not None))
            if is_video:
                if not silent:
                    QMessageBox.information(self, tx("Jen video"),
                                            tx("Tahle stránka obsahuje jen video – nejsou na ní suroviny ani postup, takže recept nejde uložit.\n\n"
                                               "Zkus najít stejný recept jako textový (např. přes 🏠 Domů a hledání)."))
                return
            if not steps_structured or not ingredients:
                if not silent:
                    QMessageBox.warning(self, tx("Recept nerozpoznán"),
                                        tx("Na této stránce se nepodařilo najít suroviny nebo postup receptu.\n\n"
                                           "Tip: nainstaluj knihovnu recipe-scrapers (py -m pip install recipe-scrapers), "
                                           "ta zná stovky webů s recepty."))
                if not steps_structured and not ingredients:
                    return
            fine_steps = fine_steps or fine_steps_from_steps(steps_structured)
        default_cat = "Monsieur Cuisine" if source_platform == "mcs" else "Nezařazené"
        chosen_category = default_cat
        if not silent:
            picked = self._pick_category(tx("Kategorie"), tx("Vyber kategorii:"), default_cat)
            if picked: chosen_category = picked

        safe_slug = re.sub(r'[^\w\s-]', '', title.lower()).strip().replace(" ", "_")[:50]
        folder = RECIPES_DIR / f"{recipe_id}_{safe_slug}"
        folder.mkdir(parents=True, exist_ok=True)

        for sc_tag in soup.find_all("script"):
            if sc_tag.get("type") != "application/ld+json":
                sc_tag.decompose()

        for bad_el in soup.select(".search-overlay, .modal, #sliding-popup, .eu-cookie-compliance-banner, [role='alert'], [class*='toast'], [class*='notification']"):
            bad_el.decompose()

        # Ostatní weby: karta receptu jen s receptem (bez menu, reklam, souvisejících článků a diskuze).
        # Cookidoo a MCS mají stránku receptu bez balastu a karta s ní počítá – tam se nic neořezává.
        if source_platform == "other":
            try:
                if trim_recipe_page(soup, recipe_ld, ingredients, [s.get("text", "") for s in steps_structured]):
                    log(f"Karta {recipe_id}: stránka oříznutá na recept")
                else:
                    log(f"Karta {recipe_id}: recept na stránce nenalezen, ukládám ji celou")
            except Exception:
                log(f"Ořezání karty {recipe_id} selhalo, ukládám celou stránku:\n" + traceback.format_exc())

        for img in soup.find_all("img"):
            for attr in ("data-src", "data-lazy-src", "data-original"):
                if img.get(attr) and (not img.get("src") or "data:image" in img.get("src", "")):
                    img["src"] = img[attr]

        parsed_u = urllib.parse.urlparse(url_str)
        base_origin = f"{parsed_u.scheme}://{parsed_u.netloc}/"
        if soup.head and not soup.head.find("base"):
            base_tag = soup.new_tag("base", href=base_origin)
            soup.head.insert(0, base_tag)

        # Po novém uložení musí zmizet staré konverze/překlady, jinak se dál zobrazují staré (rozbité) kroky.
        for stale in list(folder.glob("recipe_*.json")) + list(folder.glob("page_snapshot_*.html")):
            try:
                stale.unlink()
            except Exception:
                pass

        # Ladicí výpis – co aplikace ze stránky skutečně dostala
        try:
            (folder / "_debug_visible_text.txt").write_text(visible_text or "", encoding="utf-8")
            (folder / "_debug_ld.json").write_text(json.dumps(recipe_ld, ensure_ascii=False, indent=2), encoding="utf-8")
            (folder / "_debug_api.json").write_text(api_raw or "", encoding="utf-8")
        except Exception:
            pass

        html_path = folder / "page_snapshot.html"
        html_path.write_text(str(soup), encoding="utf-8")

        recipe_payload = {
            "recipe_id": recipe_id,
            "title": title,
            "url": url_str,
            "category": chosen_category,
            "portions": str(recipe_ld.get("recipeYield", "")),
            "total_time": str(recipe_ld.get("totalTime", "")),
            "source_platform": source_platform,
            "device": source_platform,
            "ingredients": ingredients,
            "steps": steps_structured,
            "fine_steps": fine_steps,
            "extraction": {"ingredients": extracted["ingredients_source"], "steps": extracted["steps_source"], "fine_steps": fine_src}
        }
        if tips:
            recipe_payload["tips"] = tips
        if source_platform == "other":
            recipe_payload["source_site"] = urllib.parse.urlparse(url_str).netloc.replace("www.", "")
        (folder / "recipe.json").write_text(json.dumps(recipe_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        schedule_page_assets(folder)          # styly, písma a obrázky karty receptu → sdílená složka web_assets

        opposite_device = "tm6" if source_platform == "mcs" else "mcs"
        ensure_device_recipe_file(folder, opposite_device)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT is_favorite FROM recipes WHERE recipe_id = ?", (recipe_id,))
        row = c.fetchone()
        fav_val = row[0] if row else 0
        (folder / DELETED_MARK).unlink(missing_ok=True)      # znovu uložený recept už není smazaný
        if fav_val:
            set_recipe_json_field(folder, "is_favorite", True)
        c.execute("""
            INSERT OR REPLACE INTO recipes
            (recipe_id, title, url, portions, total_time, folder_path, category, is_favorite, source_platform)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (recipe_id, title, url_str, recipe_payload["portions"], recipe_payload["total_time"], str(folder.resolve()), chosen_category, fav_val, source_platform))
        conn.commit()
        conn.close()

        self._refresh_categories_combo()
        self._load_catalog()

        if not silent:
            plat_name = {"mcs": "Monsieur Cuisine", "other": urllib.parse.urlparse(url_str).netloc.replace("www.", "")}.get(source_platform, "Cookidoo TM6")
            QMessageBox.information(self, tx("Uloženo"), tx("Recept '{title}' ({plat}) byl uložen včetně konverze pro druhý stroj!", title=title, plat=plat_name))

    def _on_page_load_finished(self, ok: bool):
        if not ok: return
        if is_offline_card_url(self.webview.url().toString()):
            self._inject_offline_page_fixes()

    def _stop_batch(self):
        if getattr(self, "_bulk_active", False):
            BULK_TR["stop"] = True
            self.lbl_batch_status.setText(tx("⏹ Zastavuji po dokončení aktuálního receptu…"))
            return
        self.batch_bar_frame.setVisible(False)

    def _open_tm_player(self):
        self._open_device_player("tm6")

    def _open_mcs_player(self):
        self._open_device_player("mcs")

    def _open_device_player(self, target_device: str):
        if not self.current_recipe_folder:
            QMessageBox.warning(self, tx("Vyber recept"), tx("Nejprve vyber recept ze stromu vlevo."))
            return
        self.device_mode = target_device
        self.right_stack.setCurrentIndex(1)

        prefix = get_base_prefix_for_device(self.current_recipe_folder, target_device)
        expected_file = self.current_recipe_folder / f"{prefix}.json"

        if expected_file.exists():
            self._load_active_device_json()
            self._render_tm_step()
        else:
            dev_label = "Monsieur Cuisine Smart" if target_device == "mcs" else "Thermomix TM6"
            self.tm_title.setText(tx("⏳ Připravuji konverzi pro {dev}...", dev=dev_label))
            self.conv_worker = DeviceConversionWorker(self.current_recipe_folder, target_device)
            self.conv_worker.finished_ok.connect(self._on_device_conversion_done)
            self.conv_worker.failed_err.connect(lambda err: QMessageBox.warning(self, tx("Chyba konverze"), err))
            self._workers.append(self.conv_worker)
            self.conv_worker.finished.connect(lambda w=self.conv_worker: self._workers.remove(w) if w in self._workers else None)
            self.conv_worker.start()

    def _on_device_conversion_done(self, conv_path: Path):
        if self.display_lang in ("en", "cs"):
            self._switch_recipe_language(self.display_lang)
        else:
            self._load_active_device_json()
            self._render_tm_step()

    def _load_active_device_json(self):
        if not self.current_recipe_folder:
            return
        prefix = get_base_prefix_for_device(self.current_recipe_folder, self.device_mode)
        if (self.current_recipe_folder / f"{prefix}.json").exists() or prefix == "recipe":
            ensure_device_recipe_file(self.current_recipe_folder, self.device_mode)
        target = self.current_recipe_folder / (f"{prefix}.json" if self.display_lang == "orig" else f"{prefix}_{self.display_lang}.json")
        if not target.exists():
            target = self.current_recipe_folder / f"{prefix}.json"
        if not target.exists():
            target = self.current_recipe_folder / "recipe.json"
        if target.exists():
            self.current_offline_data = json.loads(target.read_text(encoding="utf-8"))

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        folder_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not folder_str:
            item.setExpanded(not item.isExpanded())
            return

        folder = resolve_recipe_folder(folder_str)
        self.current_recipe_folder = folder
        self.current_recipe_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        is_fav = item.data(0, Qt.ItemDataRole.UserRole + 2)
        self.current_source_platform = item.data(0, Qt.ItemDataRole.UserRole + 4) or "tm6"

        self.btn_toggle_fav.setText(self.t('fav_btn_on' if is_fav else 'fav_btn_off'))

        self.display_lang = "orig"
        self.current_step_index = 0
        self._update_lang_and_scale_buttons()
        self._load_active_device_json()

        if self.right_stack.currentIndex() == 1:
            self._render_tm_step()
        else:
            html_file = ensure_clean_html_snapshot(folder)
            self._show_card(html_file, "orig")

    def _toggle_favorite_selected(self):
        item = self._get_selected_recipe_item()
        if not item: return
        r_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        cur_fav = item.data(0, Qt.ItemDataRole.UserRole + 2)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE recipes SET is_favorite = ? WHERE recipe_id = ?", (0 if cur_fav else 1, r_id))
        conn.commit()
        conn.close()
        try:
            set_recipe_json_field(resolve_recipe_folder(item.data(0, Qt.ItemDataRole.UserRole)), "is_favorite", not cur_fav)
        except Exception as e:
            log(f"Oblíbené se nepodařilo zapsat do recipe.json: {e}")
        self._load_catalog()

    def _change_category_selected(self):
        item = self._get_selected_recipe_item()
        if not item: return
        r_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        cur_cat = item.data(0, Qt.ItemDataRole.UserRole + 3) or "Nezařazené"
        new_cat = self._pick_category(tx("Změnit kategorii"), tx("Nová kategorie:"), cur_cat)
        if new_cat:
            self._on_recipe_drag_dropped(r_id, item.data(0, Qt.ItemDataRole.UserRole), new_cat)

    def _export_current_to_pdf(self):
        """Hezký list receptu do PDF: obrázek, suroviny, nutriční hodnoty, postup a tipy (bez reklam a menu webu)."""
        folder = self.current_recipe_folder
        if not folder or not (Path(folder) / "recipe.json").exists():
            QMessageBox.information(self, tx("Export do PDF"), tx("Nejprve vyber recept v seznamu vlevo."))
            return
        folder = Path(folder)
        lang = self.display_lang if self.display_lang in ("en", "cs") else "orig"
        device = self.device_mode if self.right_stack.currentIndex() == 1 else None
        try:
            title = load_recipe_view(folder, lang, device)[0].get("title") or folder.name
        except Exception:
            title = folder.name
        safe = re.sub(r'[\\/:*?"<>|]+', "_", title).strip() or "recept"
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        target_path, _ = QFileDialog.getSaveFileName(self, tx("Export do PDF"), str(PDF_DIR / f"{safe}.pdf"), "PDF (*.pdf)")
        if not target_path:
            return
        if not target_path.lower().endswith(".pdf"):
            target_path += ".pdf"

        def prepare():
            ex = recipe_extras(folder)
            img_path = ""
            if ex.get("image"):
                rel = cache_asset(ex["image"], ex["image"])         # obrázek ze sdílené mezipaměti (stáhne se jen jednou)
                if rel and (WEB_ASSETS_DIR / rel).exists():
                    img_path = str(WEB_ASSETS_DIR / rel)
            return img_path

        def done(box):
            img_path = box.get("result") or ""
            try:
                html = render_recipe_sheet(folder, lang, device, self.ui_lang, "pdf", self.portion_scale,
                                           self.use_metric_conversion, "cc-hero" if img_path else "")
                doc = QTextDocument()
                doc.setDocumentMargin(0)
                doc.setDefaultFont(QFont("Segoe UI", 10))
                if img_path:
                    img = QImage(img_path)
                    if not img.isNull():
                        if img.width() > 1200:
                            img = img.scaledToWidth(1200, Qt.TransformationMode.SmoothTransformation)
                        doc.addResource(QTextDocument.ResourceType.ImageResource.value, QUrl("cc-hero"), img)
                doc.setHtml(html)
                writer = QPdfWriter(target_path)
                writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
                writer.setPageMargins(QMarginsF(12, 10, 12, 10), QPageLayout.Unit.Millimeter)
                writer.setResolution(110)
                writer.setTitle(title)
                writer.setCreator(APP_NAME)
                doc.print(writer)
                del writer
                ok = Path(target_path).exists() and Path(target_path).stat().st_size > 500
            except Exception as e:
                log("Export do PDF selhal:\n" + traceback.format_exc())
                QMessageBox.warning(self, tx("Export do PDF"), tx("PDF se nepodařilo vytvořit:\n\n{err}", err=e))
                return
            if ok:
                QMessageBox.information(self, tx("Export do PDF"), tx("Uloženo do:\n{path}", path=target_path))
            else:
                QMessageBox.warning(self, tx("Export do PDF"), tx("PDF se nepodařilo uložit do:\n{path}\n\nZkus jinou složku (např. Dokumenty).", path=target_path))

        self._run_bg(tx("🖨️ Připravuji PDF…"), prepare, done)

    def _bulk_translate(self):
        if BULK_TR["running"]:
            QMessageBox.information(self, tx("Hromadný překlad"), tx("Hromadný překlad už běží – průběh vidíš v modré liště nahoře."))
            return
        if not self._ensure_translator():
            return
        todo = bulk_translation_todo()
        if not todo:
            ans = QMessageBox.question(self, tx("Hromadný překlad"),
                                       tx("Všechny recepty už jsou přeložené do angličtiny i češtiny. 👍\n\n"
                                          "Chceš je přeložit všechny znovu (např. po změně překladače nebo kvůli lepší kvalitě)?\n"
                                          "Stávající překlady se smažou."))
            if ans != QMessageBox.StandardButton.Yes:
                return
            conn = sqlite3.connect(DB_PATH)
            for (fp,) in conn.execute("SELECT folder_path FROM recipes").fetchall():
                for lang in ("en", "cs"):
                    try:
                        clear_translation(resolve_recipe_folder(fp), lang)
                    except Exception as e:
                        log(f"Smazání překladu selhalo: {e}")
            conn.close()
            todo = bulk_translation_todo()
            if not todo:
                return
        n_rec = len({str(t[0]) for t in todo})
        engine = self._translator_label()
        ans = QMessageBox.question(
            self, tx("Hromadný překlad"),
            tx("Přeložit {n} receptů ({k} překladů: EN a CZ, recept i karta)?\n\nPřekladač: {engine}\n"
               "Běží to na pozadí, aplikaci můžeš dál používat. Už hotové překlady se přeskočí.", n=n_rec, k=len(todo), engine=engine))
        if ans != QMessageBox.StandardButton.Yes:
            return
        threading.Thread(target=run_bulk_translation, args=(todo,), daemon=True).start()
        self.batch_bar_frame.setVisible(True)
        self.progress_batch.setMaximum(len(todo))
        self.progress_batch.setValue(0)
        self._bulk_timer = QTimer(self)
        self._bulk_timer.setInterval(700)
        self._bulk_timer.timeout.connect(self._poll_bulk_translation)
        self._bulk_timer.start()
        self._bulk_active = True

    def _poll_bulk_translation(self):
        st = BULK_TR
        self.progress_batch.setValue(st["done"])
        self.lbl_batch_status.setText(tx("🌍 Překládám {d}/{t}: {cur}", d=st["done"], t=st["total"], cur=st["current"]))
        if st["running"]:
            return
        self._bulk_timer.stop()
        self._bulk_active = False
        self.batch_bar_frame.setVisible(False)
        self.lbl_batch_status.setText(self.t('batch_lbl'))
        self._load_catalog()
        msg = tx("Hotovo: přeloženo {ok} z {t}.", ok=st["done"] - st["failed"], t=st["total"])
        if st["failed"]:
            msg += "\n" + tx("Nepovedlo se: {f} (podrobnosti v app.log). Spusť hromadný překlad znovu – hotové se přeskočí.", f=st["failed"])
        if st["stop"]:
            msg = tx("Hromadný překlad zastaven.") + "\n" + msg
        QMessageBox.information(self, tx("Hromadný překlad"), msg)

    def _delete_selected_recipe(self):
        item = self._get_selected_recipe_item()
        if not item: return
        r_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM recipes WHERE recipe_id = ?", (r_id,))
        conn.commit()
        conn.close()
        try:
            folder = resolve_recipe_folder(item.data(0, Qt.ItemDataRole.UserRole))
            if self.current_recipe_folder and Path(self.current_recipe_folder).resolve() == folder.resolve():
                self.webview.setHtml("")          # zobrazený recept uvolnit, ať jde složka přesunout
            move_recipe_to_trash(folder)
        except Exception as e:
            log(f"Smazaný recept se nepodařilo přesunout do koše: {e}")
        self._refresh_categories_combo()
        self._load_catalog()

    def _custom_categories(self) -> list[str]:
        return [c for c in load_config().get("custom_categories", []) if c]

    def _refresh_categories_combo(self):
        current_sel = self.combo_category_filter.currentData()
        self.combo_category_filter.blockSignals(True)
        self.combo_category_filter.clear()
        self.combo_category_filter.addItem(self.t('all_categories'), None)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT category, COUNT(*) FROM recipes GROUP BY category ORDER BY category")
        counts = {}
        for cat, count in c.fetchall():
            cat_name = cat if cat else "Nezařazené"
            counts[cat_name] = counts.get(cat_name, 0) + count
        conn.close()
        for cat in self._custom_categories():
            counts.setdefault(cat, 0)
        for cat_name in sorted(counts, key=lambda x: search_key(cat_label(x))):
            self.combo_category_filter.addItem(f"🏷️ {cat_label(cat_name)} ({counts[cat_name]})", userData=cat_name)

        idx = self.combo_category_filter.findData(current_sel) if current_sel else 0
        self.combo_category_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_category_filter.blockSignals(False)

    def _fill_title_lang_combo(self):
        labels = (tx("Názvy: podle jazyka aplikace"), tx("Názvy: originál"), tx("Názvy: English"), tx("Názvy: čeština"))
        for i, lab in enumerate(labels):
            self.combo_title_lang.setItemText(i, lab)

    def _on_title_lang_changed(self, _index: int):
        save_config({"title_lang": self.combo_title_lang.currentData()})
        self._load_catalog()

    def _ask_new_category(self) -> str | None:
        name, ok = QInputDialog.getText(self, tx("Nová kategorie"), tx("Název nové kategorie:"))
        name = (name or "").strip()
        if not ok or not name:
            return None
        raw = cat_from_label(name)
        cats = self._custom_categories()
        if raw not in cats and raw not in self._get_all_existing_categories():
            cats.append(raw)
            save_config({"custom_categories": cats})
        return raw

    def _move_item_to_category(self, item, raw_cat: str):
        self._on_recipe_drag_dropped(item.data(0, Qt.ItemDataRole.UserRole + 1), item.data(0, Qt.ItemDataRole.UserRole), raw_cat)

    def _recipe_context_menu(self, pos):
        """Pravé tlačítko na receptu: oblíbené, přesun do kategorie (i do nové), zobrazení, PDF, smazání."""
        item = self.recipe_tree.itemAt(pos)
        if item is None or item.data(0, Qt.ItemDataRole.UserRole) is None:
            return
        if not item.isSelected():                 # klik mimo označené → pracuje se jen s tímto receptem
            self.recipe_tree.setCurrentItem(item)
        n_sel = len(self._selected_recipe_items())
        cur_cat = item.data(0, Qt.ItemDataRole.UserRole + 3) or "Nezařazené"
        is_fav = bool(item.data(0, Qt.ItemDataRole.UserRole + 2))
        menu = QMenu(self)
        menu.setToolTipsVisible(True)

        def opened(fn):
            def run(*_):
                if self.current_recipe_id != item.data(0, Qt.ItemDataRole.UserRole + 1):
                    self._on_tree_item_clicked(item, 0)
                fn()
            return run

        a = menu.addAction(self.t('fav_btn_on' if is_fav else 'fav_btn_off'))
        a.triggered.connect(lambda *_: self._toggle_favorite_selected())
        sub = menu.addMenu(tx("🏷️ Přesunout do kategorie"))
        sub.setToolTipsVisible(True)
        a_new = sub.addAction(tx("➕ Nová…"))
        a_new.setToolTip(tx("Založí novou kategorii a recept do ní rovnou přesune"))
        a_new.triggered.connect(lambda *_: (lambda raw: raw and self._move_item_to_category(item, raw))(self._ask_new_category()))
        sub.addSeparator()
        for cat in sorted(self._get_all_existing_categories(), key=lambda c: search_key(cat_label(c))):
            act = sub.addAction(f"📁 {cat_label(cat)}")
            if cat == cur_cat:
                act.setCheckable(True)
                act.setChecked(True)
                act.setEnabled(False)
            else:
                act.triggered.connect(lambda *_, c=cat: self._move_item_to_category(item, c))
        menu.addSeparator()
        for text, fn in ((self.t('card_btn'), self._switch_to_card_view), (self.t('tm_btn'), self._open_tm_player),
                         (self.t('mcs_btn'), self._open_mcs_player), (self.t('pdf_btn'), self._export_current_to_pdf)):
            menu.addAction(text).triggered.connect(opened(fn))
        menu.addSeparator()
        a_exp = menu.addAction(tx("📦 Exportovat zálohu (.7z)…") if n_sel <= 1
                               else tx("📦 Exportovat zálohu – {n} receptů (.7z)…", n=n_sel))
        a_exp.setToolTip(tx("Zabalí označené recepty do jednoho souboru .7z (do složky exported_recipes). "
                            "Na jiném počítači je nahraješ tlačítkem 📥 Importovat recepty."))
        a_exp.triggered.connect(lambda *_: self._export_backup())
        menu.addSeparator()
        menu.addAction(self.t('del_btn')).triggered.connect(lambda *_: self._delete_selected_recipe())
        menu.exec(self.recipe_tree.viewport().mapToGlobal(pos))

    def _selected_recipe_items(self) -> list:
        """Označené recepty v seznamu (Ctrl/Shift + klik). Označená kategorie = všechny její viditelné recepty."""
        out, seen = [], set()

        def add(it):
            rid = it.data(0, Qt.ItemDataRole.UserRole + 1)
            if it.data(0, Qt.ItemDataRole.UserRole) is not None and rid not in seen and not it.isHidden():
                seen.add(rid)
                out.append(it)

        for it in self.recipe_tree.selectedItems():
            if it.data(0, Qt.ItemDataRole.UserRole) is not None:
                add(it)
            else:
                for i in range(it.childCount()):
                    add(it.child(i))
        cur = self.recipe_tree.currentItem()
        if not out and cur is not None and cur.data(0, Qt.ItemDataRole.UserRole) is not None:
            add(cur)
        return out

    def _export_backup(self):
        """📦 Export zálohy: označené recepty → jeden .7z (výchozí složka localchef_data/exported_recipes)."""
        title = tx("Export receptů")
        if not has_py7zr():
            QMessageBox.warning(self, title, tx("Export potřebuje knihovnu py7zr:\n\n    py -m pip install py7zr\n\nPotom aplikaci restartuj."))
            return
        items = self._selected_recipe_items()
        if not items:
            QMessageBox.information(self, title, tx("Nejdřív v seznamu vlevo označ recepty (Ctrl/Shift + klik, nebo celou kategorii)."))
            return
        folders = [resolve_recipe_folder(it.data(0, Qt.ItemDataRole.UserRole)) for it in items]
        titles = [re.sub(r'^\W+', '', it.text(0)).strip() or Path(f).name for it, f in zip(items, folders)]
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        target, _ = QFileDialog.getSaveFileName(self, title, str(EXPORT_DIR / backup_file_name(titles)), "7-Zip (*.7z)")
        if not target:
            return
        if not target.lower().endswith(".7z"):
            target += ".7z"

        def done(box):
            if "error" in box:
                QMessageBox.warning(self, title, tx("Export se nepodařil:\n\n{err}", err=box["error"]))
                return
            r = box["result"]
            QMessageBox.information(self, title, tx("Exportováno receptů: {n} ({mb} MB)\n\nUloženo do:\n{path}",
                                                    n=r["recipes"], mb=f"{r['size'] / 1048576:.1f}", path=r["path"]))

        self._run_bg(tx("📦 Balím recepty do .7z…"), lambda: export_recipes_backup(folders, Path(target)), done)

    def _import_backup(self):
        """📥 Import: jedna nebo víc záloh .7z → recepty do kuchařky (i se styly a obrázky karet)."""
        title = tx("Import receptů")
        if not has_py7zr():
            QMessageBox.warning(self, title, tx("Import potřebuje knihovnu py7zr:\n\n    py -m pip install py7zr\n\nPotom aplikaci restartuj."))
            return
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        paths, _ = QFileDialog.getOpenFileNames(self, title, str(EXPORT_DIR), "7-Zip (*.7z)")
        if not paths:
            return

        def applied(box):
            if "error" in box:
                QMessageBox.warning(self, title, tx("Import se nepodařil:\n\n{err}", err=box["error"]))
                return
            r = box["result"]
            self._refresh_categories_combo()
            self._load_catalog()
            msg = tx("Nové recepty: {a}\nNahrazené: {b}\nPřeskočené (už v kuchařce): {c}",
                     a=r["imported"], b=r["replaced"], c=r["skipped"])
            if r["errors"]:
                msg += "\n\n" + tx("Problémy:") + "\n" + "\n".join(r["errors"][:10])
            (QMessageBox.warning if r["errors"] and not (r["imported"] or r["replaced"]) else QMessageBox.information)(self, title, msg)

        def staged(box):
            if "error" in box:
                QMessageBox.warning(self, title, tx("Import se nepodařil:\n\n{err}", err=box["error"]))
                return
            stage = box["result"]
            if not stage["items"]:
                shutil.rmtree(stage["tmp"], ignore_errors=True)
                QMessageBox.warning(self, title, tx("V souborech nejsou žádné recepty k importu.") +
                                    ("\n\n" + "\n".join(stage["errors"][:10]) if stage["errors"] else ""))
                return
            dup = [it for it in stage["items"] if it["exists"]]
            overwrite = False
            if dup:
                names = "\n".join("• " + it["title"] for it in dup[:12]) + ("\n…" if len(dup) > 12 else "")
                ans = QMessageBox.question(self, title, tx(
                    "{n} z {total} receptů už v kuchařce je:\n\n{names}\n\nPřepsat je verzí ze zálohy?\n"
                    "Ano = přepsat (současná verze půjde do koše recipes_smazane), Ne = ponechat současnou.",
                    n=len(dup), total=len(stage["items"]), names=names))
                overwrite = ans == QMessageBox.StandardButton.Yes
            self._run_bg(tx("📥 Importuji recepty…"), lambda: apply_recipe_backups(stage, overwrite), applied)

        self._run_bg(tx("📥 Rozbaluji zálohy…"), lambda: stage_recipe_backups(paths), staged)

    def _show_donate(self):
        DonateDialog(self.ui_lang, parent=self).exec()

    def _show_how_to(self):
        HowToDialog(self.ui_lang, parent=self).exec()

    def _show_whats_new(self, on_start: bool = True):
        """Při startu (dokud si to uživatel u této verze nevypne) a z menu ⚙️."""
        if on_start and load_config().get("whats_new_hidden") == APP_VERSION:
            return
        dlg = WhatsNewDialog(self.ui_lang, show_checkbox=on_start, parent=self)
        dlg.exec()
        if on_start and dlg.chk_hide.isChecked():
            save_config({"whats_new_hidden": APP_VERSION})

    def _apply_tooltips(self):
        """Ke každému tlačítku a volbě nápověda po najetí myší (v jazyce aplikace)."""
        en = self.ui_lang == "en"
        for attr, (cs_txt, en_txt) in WIDGET_TOOLTIPS.items():
            w = getattr(self, attr, None)
            if w is not None:
                w.setToolTip(en_txt if en else cs_txt)
        for sc, btn in getattr(self, "scale_buttons", {}).items():
            btn.setToolTip(f"Ingredients and amounts in the steps × {sc:g}" if en else f"Suroviny a množství v krocích × {sc:g}")

    def _new_category(self):
        raw = self._ask_new_category()
        if not raw:
            return
        name = cat_label(raw)
        item = self._get_selected_recipe_item()
        if item is not None:
            ans = QMessageBox.question(self, tx("Nová kategorie"),
                                       tx("Přesunout vybraný recept „{t}“ do kategorie „{c}“?", t=item.data(0, Qt.ItemDataRole.UserRole + 6) or "", c=name))
            if ans == QMessageBox.StandardButton.Yes:
                self._on_recipe_drag_dropped(item.data(0, Qt.ItemDataRole.UserRole + 1), item.data(0, Qt.ItemDataRole.UserRole), raw)
                return
        self._refresh_categories_combo()
        self._load_catalog()

    def _load_catalog(self):
        self.recipe_tree.clear()
        selected_cat_data = self.combo_category_filter.currentData()
        selected_plat = self.combo_platform_filter.currentData()
        only_fav = self.chk_only_favorites.isChecked()
        title_lang = self.combo_title_lang.currentData() or "auto"
        if title_lang == "auto":
            title_lang = self.ui_lang

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        query = "SELECT recipe_id, title, folder_path, category, is_favorite, source_platform, title_en, title_cs FROM recipes WHERE 1=1"
        params = []
        if selected_cat_data:
            query += " AND category = ?"
            params.append(selected_cat_data)
        if selected_plat and selected_plat != "all":
            query += " AND LOWER( COALESCE(source_platform, 'tm6') ) = ?"
            params.append(selected_plat)
        if only_fav:
            query += " AND is_favorite = 1"
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        def shown_title(r):
            t = {"en": r[6], "cs": r[7]}.get(title_lang) or r[1]
            return t or r[0]

        rows.sort(key=lambda r: (search_key(cat_label(r[3] or "Nezařazené")), -int(r[4] or 0), search_key(shown_title(r))))

        cat_nodes = {}
        cat_counts = {}

        def cat_node(cat_name):
            if cat_name not in cat_nodes:
                parent_item = QTreeWidgetItem(self.recipe_tree)
                parent_item.setData(0, Qt.ItemDataRole.UserRole, None)
                parent_item.setData(0, Qt.ItemDataRole.UserRole + 3, cat_name)
                parent_item.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
                cat_nodes[cat_name] = parent_item
                cat_counts[cat_name] = 0
            return cat_nodes[cat_name]

        for r in rows:
            r_id, title, folder_path, category, is_fav, source_plat, t_en, t_cs = r
            cat_name = category if category else "Nezařazené"
            parent = cat_node(cat_name)
            cat_counts[cat_name] += 1
            plat_code = (source_plat or "tm6").lower()
            prefix_icons = get_recipe_icon_prefix(plat_code, bool(is_fav), self.icon_style)
            child = QTreeWidgetItem(parent)
            shown = shown_title(r)
            child.setText(0, f"{prefix_icons}{shown}")
            if title_lang != "orig" and shown == title:
                child.setToolTip(0, tx("Recept zatím není přeložený – zobrazuji původní název"))
            child.setData(0, Qt.ItemDataRole.UserRole, folder_path)
            child.setData(0, Qt.ItemDataRole.UserRole + 1, r_id)
            child.setData(0, Qt.ItemDataRole.UserRole + 2, is_fav)
            child.setData(0, Qt.ItemDataRole.UserRole + 3, cat_name)
            child.setData(0, Qt.ItemDataRole.UserRole + 4, plat_code)
            child.setData(0, Qt.ItemDataRole.UserRole + 5, search_key(" ".join(x or "" for x in (title, t_en, t_cs))))
            child.setData(0, Qt.ItemDataRole.UserRole + 6, shown)

        # prázdné vlastní kategorie – aby šlo recepty přetáhnout i do nich
        if not selected_plat or selected_plat == "all":
            if not only_fav:
                for cat in self._custom_categories():
                    if (not selected_cat_data or selected_cat_data == cat) and cat not in cat_nodes:
                        cat_node(cat)

        for cat_name, node in cat_nodes.items():
            node.setText(0, f"📁 {cat_label(cat_name)} ({cat_counts[cat_name]})")
            node.setExpanded(True)
            if getattr(self, "current_recipe_id", None):
                for j in range(node.childCount()):
                    if node.child(j).data(0, Qt.ItemDataRole.UserRole + 1) == self.current_recipe_id:
                        self.recipe_tree.setCurrentItem(node.child(j))

        self._filter_catalog(self.search_input.text())

    def _filter_catalog(self, query: str):
        q = search_key(query).strip()
        words = q.split()
        root = self.recipe_tree.invisibleRootItem()
        total = 0
        for i in range(root.childCount()):
            cat_item = root.child(i)
            cat_hit = bool(words) and all(w in search_key(cat_label(cat_item.data(0, Qt.ItemDataRole.UserRole + 3) or "")) for w in words)
            visible_children = 0
            for j in range(cat_item.childCount()):
                rec_item = cat_item.child(j)
                blob = rec_item.data(0, Qt.ItemDataRole.UserRole + 5) or search_key(rec_item.text(0))
                match = (not words) or cat_hit or all(w in blob for w in words)
                rec_item.setHidden(not match)
                if match:
                    visible_children += 1
            total += visible_children
            cat_item.setHidden(bool(words) and visible_children == 0)
            if words and visible_children:
                cat_item.setExpanded(True)
        if words:
            self.lbl_search_info.setText(tx("Nalezeno: {n}", n=total) if total else tx("Nic nenalezeno – zkus jiné slovo nebo zruš filtry nahoře."))
        self.lbl_search_info.setVisible(bool(words))

    def _get_selected_recipe_item(self) -> QTreeWidgetItem | None:
        item = self.recipe_tree.currentItem()
        if not item or item.data(0, Qt.ItemDataRole.UserRole) is None: return None
        return item

    def _on_recipe_drag_dropped(self, r_id: str, folder_str: str, new_cat: str):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE recipes SET category = ? WHERE recipe_id = ?", (new_cat, r_id))
        conn.commit()
        conn.close()

        folder = resolve_recipe_folder(folder_str)
        for json_file in folder.glob("recipe*.json"):
            if json_file.exists():
                data = json.loads(json_file.read_text(encoding="utf-8"))
                data["category"] = new_cat
                json_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        self._refresh_categories_combo()
        self._load_catalog()

    def _render_tm_step(self):
        data = self.current_offline_data
        if not data: return

        is_mcs = (self.device_mode == "mcs")
        accent_col = "#00E5FF" if is_mcs else "#00E676"
        badge_bg = "#1565C0" if is_mcs else "#2E7D32"
        orig_plat = (data.get("source_platform") or self.current_source_platform or "tm6").upper()
        if orig_plat == "OTHER":
            orig_plat = (data.get("source_site") or "WEB").upper()
        dev_badge = tx("🤖 MONSIEUR CUISINE (Zdroj: {p})", p=orig_plat) if is_mcs else tx("🍲 THERMOMIX TM6 (Zdroj: {p})", p=orig_plat)

        title_txt = data.get("title", "Recept")
        self.tm_title.setText(f"{title_txt} ({self.portion_scale:g}x)")
        self.tm_title.setStyleSheet(f"color: {accent_col};")

        steps = self._current_steps(data)

        if not steps:
            steps = [{
                "html": tx("⚠️ U tohoto receptu se nepodařilo automaticky rozpoznat jednotlivé kroky. Otevři recept na webu, počkej na plné načtení textu a klikni znovu na <b>⬇️ ULOŽIT RECEPT</b>."),
                "text": tx("Kroky nenalezeny."),
                "dials": {"time": "—", "temp": "—", "speed": "—"}
            }]

        total = len(steps)
        idx = max(0, min(self.current_step_index, total - 1))
        self.current_step_index = idx
        step_obj = steps[idx]

        step_word = "STEP" if self.ui_lang == "en" else "KROK"
        parent_info = ""
        if self.fine_mode and step_obj.get("parent") is not None:
            parent_info = f"  ({tx('hlavní')} {step_obj['parent'] + 1})"
        self.tm_step_counter.setText(f"{dev_badge} — {step_word} {idx + 1} / {total}{parent_info}")
        self.tm_step_counter.setStyleSheet(f"background-color: {badge_bg}; color: white; padding: 6px 14px; border-radius: 6px;")

        dials = step_obj.get("dials", {"time": "—", "temp": "—", "speed": "—"})

        time_hdr = "⏱️ TIME" if self.ui_lang == "en" else "⏱️ ČAS"
        temp_hdr = "🌡️ TEMP" if self.ui_lang == "en" else "🌡️ TEPLOTA"
        speed_hdr = tx("🔪 RYCHLOST / PROGRAM") if is_mcs else tx("🔪 OTÁČKY")

        self.lbl_dial_time.setText(f"{time_hdr}\n{normalize_dial_time(dials.get('time', '—'))}")
        self.lbl_dial_temp.setText(f"{temp_hdr}\n{dials.get('temp', '—')}")
        self.lbl_dial_speed.setText(f"{speed_hdr}\n{dials.get('speed', '—')}")

        raw_ings = data.get("ingredients", [])
        scaled_ings = [scale_ingredient_line(i, self.portion_scale) for i in raw_ings]
        mkey = (id(data), self.fine_mode, self.portion_scale, len(steps))
        if getattr(self, "_match_key", None) != mkey:
            self._match_key = mkey
            self._match_all = match_recipe_ingredients([s.get("text", "") or _plain(s.get("html")) for s in steps], raw_ings)
        matched_ings = [dict(m, text=scaled_ings[i]) for i, m in enumerate(self._match_all[idx])] if idx < len(self._match_all) \
            else match_step_ingredients(step_obj.get("text", ""), scaled_ings)

        ings_title = "🛒 Ingredients" if self.ui_lang == "en" else "🛒 Suroviny"
        ing_html = f"<h3 style='color:{accent_col}; margin-top:0;'>{ings_title} ({self.portion_scale:g}x)</h3><ul style='padding-left:18px;'>"
        for item in matched_ings:
            ing_display = convert_text_to_metric(item["text"], html_highlight=True) if self.use_metric_conversion else item["text"]
            if item["active"]:
                part = f" <span style='color:#FFB74D;'>({tx('teď')} {scale_ingredient_line(item['part'], self.portion_scale)})</span>" if item.get("part") else ""
                ing_html += f"<li style='margin-bottom:8px; color:{accent_col}; font-weight:bold; background-color:#1B5E20; padding:5px 8px; border-radius:4px;'>👉 {ing_display}{part}</li>"
            else:
                ing_html += f"<li style='margin-bottom:6px; color:#B0B0B0;'>{ing_display}</li>"
        ing_html += "</ul>"
        ing_html += self._extras_html(accent_col)
        self.tm_ingredients_box.setHtml(ing_html)

        formatted_step = format_tm_icons_html(step_obj.get("html") or step_obj.get("text", ""), is_mcs=is_mcs)
        formatted_step = scale_step_text(formatted_step, self.portion_scale)
        if self.use_metric_conversion:
            formatted_step = convert_text_to_metric(formatted_step, html_highlight=True)

        self.tm_step_box.setStyleSheet(f"background-color: #252526; border: 2px solid {accent_col}; border-radius: 12px; padding: 24px;")
        self.tm_step_box.setHtml(f"<div style='font-size:24px; color:#FFFFFF; line-height:1.6;'>{formatted_step}</div>")
        self.btn_next_step.setStyleSheet(f"background-color: {badge_bg}; color: white; font-size: 16px; font-weight: bold; border-radius: 6px;")

        self.btn_prev_step.setEnabled(idx > 0)
        self.btn_next_step.setEnabled(idx < total - 1)

    def _extras_html(self, accent_col: str) -> str:
        """Nutriční hodnoty a tipy pod surovinami (popisky v jazyce aplikace, tipy v jazyce receptu)."""
        folder = self.current_recipe_folder
        if not folder:
            return ""
        try:
            ex = recipe_extras(Path(folder))
        except Exception:
            return ""
        out = ""
        ui = self.ui_lang
        nut = [(NUTRI_LABELS[k][1 if ui == "en" else 0], ex["nutrition"][k]) for k in NUTRI_LABELS if k in ex.get("nutrition", {})]
        if nut:
            per = f" <span style='color:#9E9E9E; font-weight:normal;'>({_st('per', ui)} {html_mod.escape(ex['nutrition_per'])})</span>" if ex.get("nutrition_per") else ""
            rows = "".join(f"<tr><td style='color:#BDBDBD; padding-right:12px;'>{html_mod.escape(k)}</td><td><b>{html_mod.escape(v)}</b></td></tr>" for k, v in nut)
            out += f"<h3 style='color:{accent_col};'>📊 {_st('nutrition', ui)}{per}</h3><table>{rows}</table>"
        data = self.current_offline_data or {}
        tips = data.get("tips") if self.display_lang != "orig" and data.get("tips") else ex.get("tips", [])
        if tips:
            out += f"<h3 style='color:{accent_col};'>💡 {_st('tips', ui)}</h3><ul style='padding-left:18px;'>" + \
                   "".join(f"<li style='margin-bottom:6px; color:#D0D0D0;'>{html_mod.escape(t)}</li>" for t in tips) + "</ul>"
        return out

    def _prev_tm_step(self):
        if self.current_step_index > 0:
            self.current_step_index -= 1
            self._render_tm_step()

    def _next_tm_step(self):
        steps = self._current_steps(self.current_offline_data)
        if self.current_step_index < len(steps) - 1:
            self.current_step_index += 1
            self._render_tm_step()


def _install_crash_guard():
    """PyQt6 při neošetřené výjimce v obsluze tlačítka celou aplikaci ukončí – tohle ji jen zaloguje a ukáže."""
    def hook(etype, value, tb):
        txt = "".join(traceback.format_exception(etype, value, tb))
        log("NEOŠETŘENÁ CHYBA:\n" + txt)
        try:
            QMessageBox.critical(None, tx("Chyba"), tx("Nastala chyba, aplikace ale běží dál:\n\n{err}\n\nPodrobnosti: {log}", err=value, log=APP_LOG.resolve()))
        except Exception:
            pass
    sys.excepthook = hook
    threading.excepthook = lambda a: log("Chyba ve vlákně:\n" + "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))


if __name__ == "__main__":
    _install_crash_guard()
    start_web_assets_check()          # při startu ověří, jestli weby nezměnily styly karet receptu
    app = QApplication(sys.argv)
    window = LocalChefStudio()
    window.show()
    # „Co je nového“ + podmínky použití, potom kontrola offline překladače (dialogy jdou po sobě)
    QTimer.singleShot(400, lambda: (window._show_whats_new(), window._startup_offline_check()))
    sys.exit(app.exec())