"""1.6: recipe card in the app's own template (author, source link, machine settings, units), website icons and
default categories, extras from the older .mhtml snapshot."""
import sys, os, io, json, re
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None; g["init_db"]()
g["load_gemini_key"] = lambda: ""

# ---- websites: own icon, colour and default category
si = g["site_info"]
for url, plat, name, icon in [("https://cookidoo.cz/recipes/recipe/cs/r1", "tm6", "Cookidoo", "🟢"),
                              ("https://www.monsieur-cuisine.com/cs/recipe/x", "mcs", "Monsieur Cuisine", "🔵"),
                              ("https://fresh.iprima.cz/recepty/kulajda", "other", "Prima FRESH", "🔴"),
                              ("https://www.allrecipes.com/recipe/1/x/", "other", "Allrecipes", "🟠"),
                              ("https://www.bbcgoodfood.com/recipes/x", "other", "BBC Good Food", "🟣"),
                              ("", "tm6", "Cookidoo", "🟢")]:
    info = si(url, plat)
    assert (info["name"], info["icon"], info["category"]) == (name, icon, name), (url, info)
a, b = si("https://www.toprecepty.cz/recept/1"), si("https://toprecepty.cz/recept/2")
print("unknown site:", a)
assert a == b and a["name"] == "toprecepty.cz" and a["category"] == "Toprecepty.cz" and a["icon"] not in "🟢🔵🔴🟠🟣⚫"
assert g["get_recipe_icon_prefix"]("other", True, "dots", "https://www.bbcgoodfood.com/x") == "⭐ 🟣 "
assert g["get_recipe_icon_prefix"]("other", False, "dots") == "⚫ " and g["get_recipe_icon_prefix"]("other", False, "bots", "https://x.cz") == "🍽️ "

# ---- default categories: meals and drinks, all translated
cats = g["DEFAULT_CATEGORIES"]
print("default categories:", cats)
for c in ("Snídaně", "Svačiny", "Předkrmy", "Polévky", "Obědy", "Večeře", "Pečivo", "Sladkosti a dezerty",
          "Alkoholické koktejly", "Nealkoholické koktejly"):
    assert c in cats and g["CATEGORY_EN"].get(c), c
win = g["LocalChefStudio"]()
assert all(c in win._get_all_existing_categories() for c in cats)

# ---- saving puts a recipe into its website's category
page = ('<html><head><script type="application/ld+json">{"@type":"Recipe","name":"Spaghetti Bolognese",'
        '"author":{"@type":"Person","name":"Good Food team"},"description":"A classic &amp; rich Italian sauce.",'
        '"image":"https://images.example/bolo.jpg","recipeYield":"4","totalTime":"PT1H",'
        '"nutrition":{"@type":"NutritionInformation","calories":"520 kcal","proteinContent":"31 g"},'
        '"recipeIngredient":["1 lb beef mince","2 cups passata","1 (8 ounce) package spaghetti"],'
        '"recipeInstructions":[{"@type":"HowToStep","text":"Fry the beef for 10 minutes."},'
        '{"@type":"HowToStep","text":"Add the passata and simmer for 30 minutes."}]}</script></head>'
        '<body><h1>Spaghetti Bolognese</h1></body></html>')
url = "https://www.bbcgoodfood.com/recipes/best-spaghetti-bolognese-recipe"
rid = g["other_recipe_id"](url)
assert win._process_and_store_recipe(rid, url, page, True, "other") is True
import sqlite3
row = sqlite3.connect(g["DB_PATH"]).execute("SELECT category, folder_path FROM recipes WHERE recipe_id=?", (rid,)).fetchone()
print("saved into:", row[0])
assert row[0] == "BBC Good Food"
folder = g["resolve_recipe_folder"](row[1])

# ---- the card: author, source link, description, units, settings per machine
ex = g["recipe_extras"](folder)
print("extras:", {k: ex[k] for k in ("author", "description", "url", "image")})
assert ex["author"] == "Good Food team" and ex["description"] == "A classic & rich Italian sauce." and ex["url"] == url
R = g["render_recipe_sheet"]
nav = "/api/card?id=x&lang=orig"
orig = R(folder, "orig", "other", "cs", "web", 1.0, True, "/img.jpg", "", "light", nav)
tm6 = R(folder, "orig", "tm6", "cs", "web", 1.0, True, "/img.jpg", "", "dark", nav)
mcs = R(folder, "orig", "mcs", "en", "web", 2.0, True, "", "", "dark", nav)
assert 'data-theme="light"' in orig and 'data-theme="dark"' in tm6
assert "Good Food team" in orig and f"href='{url}'" in orig and "🟣 BBC Good Food ↗" in orig and "Recept pochází z webu" in orig
assert "A classic &amp; rich Italian sauce." in orig
ings = re.search(r"<h2>🛒 Suroviny</h2><ul>(.*?)</ul>", orig, re.S).group(1)
print("ingredients:", re.sub("<[^>]+>", "", ings.replace("</li>", " | ")))
assert "455 g" in ings and "480 ml" in ings and "225 g" in ings and "<small class='orig'>(1 lb)</small>" in ings
assert "class='dev on' href='/api/card?id=x&amp;lang=orig&amp;device=other'" in orig and "device=mcs" in orig
assert "class='dial'>⏱ 10 min" in orig and "🌀" not in orig, "original steps: time only, no machine"
assert "🌡 100 °C" in tm6 and "rychlost" in tm6.lower() and "class='dev on' href='/api/card?id=x&amp;lang=orig&amp;device=tm6'" in tm6
assert "speed" in mcs and "Batch: 2×" in mcs and "<img class='hero'" not in mcs
print("dials tm6:", re.findall(r"<span class='dial'>([^<]+)</span>", tm6)[:4])

# ---- older recipes saved as .mhtml: extras are read from it without changing the folder
old = g["RECIPES_DIR"] / "r9_stary"
old.mkdir()
(old / "recipe.json").write_text(json.dumps({"recipe_id": "r9", "title": "Babiččina polévka", "url": "https://cookidoo.cz/recipes/recipe/cs/r9",
    "source_platform": "tm6", "ingredients": ["voda"], "steps": [{"text": "Vařte 5 min/100°C/rychlost 1.", "dials": {"time": "5 min", "temp": "100°C", "speed": "Speed 1"}}]},
    ensure_ascii=False), encoding="utf-8")
mhtml = ("MIME-Version: 1.0\r\nContent-Type: multipart/related; boundary=\"B\"\r\n\r\n--B\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
         '<html><head><meta property="og:image" content="https://img/stary.jpg"><meta name="description" content="Polévka po babičce"></head><body></body></html>'
         "\r\n--B--\r\n")
(old / "page_snapshot.mhtml").write_bytes(mhtml.encode("utf-8"))
ex_old = g["recipe_extras"](old)
print("mhtml extras:", ex_old["image"], "|", ex_old["description"])
assert ex_old["image"] == "https://img/stary.jpg" and ex_old["description"] == "Polévka po babičce"
assert not (old / "page_snapshot.html").exists(), "reading extras must not convert the snapshot"
# the website's general blurb is not a recipe description
(old / "page_snapshot.mhtml").write_bytes(mhtml.replace("Polévka po babičce", "Svět receptů Thermomix® – Cookidoo® vám přináší vynikající jídla").encode("utf-8"))
os.utime(old / "page_snapshot.mhtml", (1, 1))
assert g["recipe_extras"](old)["description"] == ""
card_old = R(old, "orig", None, "cs", "web", 1.0, True, "", "", "dark", nav)
assert "rychlost 1" in card_old and "Speed" not in re.sub(r"<style>.*?</style>", "", card_old, flags=re.S)

# ---- /api/card serves the template; a recipe without any content falls back to the saved page
H = g["LanCookidooHandler"]
def get(path):
    h = H.__new__(H); h.path = path; h.wfile = io.BytesIO(); h.headers = {"Host": "127.0.0.1"}
    h.send_response = lambda c: None; h.send_header = lambda *a: None; h.end_headers = lambda: None; h.send_error = print
    h.do_GET(); return h.wfile.getvalue().decode("utf-8")
out = get(f"/api/card?id={rid}&lang=orig&theme=light&ui=cs")
assert "<h1>Spaghetti Bolognese</h1>" in out and 'data-theme="light"' in out and "Good Food team" in out
empty = g["RECIPES_DIR"] / "web_x_empty"; empty.mkdir()
(empty / "recipe.json").write_text(json.dumps({"recipe_id": "web_x_empty", "title": "Prázdný", "ingredients": [], "steps": []}), encoding="utf-8")
(empty / "page_snapshot.html").write_text("<html><body><p>PŮVODNÍ STRÁNKA</p></body></html>", encoding="utf-8")
g["sync_catalog_from_folders"]()
assert not g["recipe_has_content"](empty)
assert "PŮVODNÍ STRÁNKA" in get("/api/card?id=web_x_empty&lang=orig")
# ---- PDF: short nutrition values, a small image, muted original units
nv = g["nutri_value_text"]
print("nutrition:", nv("35 grams protein"), "|", nv("624 calories"), "|", nv("1.6 milligram of sodium"), "|", nv("1449 kJ / 346 kcal"))
assert (nv("35 grams protein"), nv("624 calories"), nv("1.6 milligram of sodium"), nv("1449 kJ / 346 kcal"), nv("12 g")) ==        ("35 g", "624 kcal", "1.6 mg", "1449 kJ / 346 kcal", "12 g")
pdf = R(folder, "orig", "other", "en", "pdf", 1.0, True, "cc-hero")
assert "<img src='cc-hero' width='190'>" in pdf and "width='66%'" in pdf and "(1 lb)</span>" in pdf and "[orig:" not in pdf
assert g["PDF_MARGINS_MM"][1] <= 25, "top margin at most like Word (2.5 cm)"
print("OK")
