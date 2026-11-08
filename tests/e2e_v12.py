import sys, os, json, io, sqlite3, time, re
sys.path.insert(0, os.path.dirname(__file__)); from stub import load
g = load(sys.argv[1])
g["init_db"]()
R = g["RECIPES_DIR"]
# --- simulated Cookidoo recipe (JSON-LD with nutrition + a Tipy section in the HTML)
f1 = R / "r72374_kulajda"; f1.mkdir(parents=True)
ld = {"@context": "https://schema.org", "@type": "Recipe", "name": "Kulajda", "image": ["https://assets.tmecosys.com/image/upload/{transformation}/img/recipe/kulajda.jpg"],
      "prepTime": "PT20M", "totalTime": "PT1H5M", "recipeYield": "4 porce",
      "nutrition": {"@type": "NutritionInformation", "calories": "1449 kJ / 346 kcal", "proteinContent": "11 g", "carbohydrateContent": "30 g", "fatContent": "19 g", "fiberContent": "3 g", "servingSize": "1 porce"}}
(f1/"page_snapshot.html").write_text(f"""<html><head><script type="application/ld+json">{json.dumps(ld)}</script></head><body>
<h1>Kulajda</h1><h3>Užitečné tipy</h3><ul><li>Houby můžete nahradit sušenými, předem je namočte.</li><li>Kopr přidejte až na konci, ať voní.</li></ul></body></html>""", encoding="utf-8")
(f1/"recipe.json").write_text(json.dumps({"recipe_id": "r72374", "title": "Kulajda", "url": "https://cookidoo.cz/r72374", "source_platform": "tm6", "portions": "4 porce",
   "ingredients": ["500 g brambor", "2 lžíce octa", "200 ml smetany"], "steps": [{"text": "Vložte 500 g brambor, 10 min/100 °C/rychlost 1.", "html": "Vložte 500 g brambor, <nobr>10 min/100 °C//rychlost 1</nobr>.", "dials": {"time": "10 minut", "temp": "100 °C", "speed": "Speed 1"}}]}, ensure_ascii=False), encoding="utf-8")
# --- simulated MCS recipe (nutrition and tips only in the API)
f2 = R / "mcs_bacon_bacon-medaillons"; f2.mkdir(parents=True)
(f2/"page_snapshot.html").write_text('<html><head><meta property="og:image" content="https://mc-web-content-cdn.tecpal.com/bacon.jpg"></head><body>x</body></html>', encoding="utf-8")
(f2/"_debug_api.json").write_text(json.dumps({"data": {"nutritions": [{"name": "Kalorien", "value": 520, "unit": "kcal"}, {"name": "Eiweiß", "value": 31, "unit": "g"}, {"name": "Fett", "value": 40, "unit": "g"}, {"name": "Kohlenhydrate", "value": 6, "unit": "g"}],
    "tips": [{"text": "<p>Dazu passt frisches Baguette.</p>"}], "multipleChoice": "nope"}}), encoding="utf-8")
(f2/"recipe.json").write_text(json.dumps({"recipe_id": "mcs_bacon", "title": "Bacon-Medaillons mit Bresso-Soße", "url": "https://www.monsieur-cuisine.com/de/x", "source_platform": "mcs",
   "ingredients": ["200 g Bacon", "1 EL Öl"], "steps": [{"text": "Bacon anbraten 5 Min.", "dials": {"time": "5 Min.", "temp": "120 °C", "speed": "—"}}]}, ensure_ascii=False), encoding="utf-8")
print("sync:", g["sync_catalog_from_folders"]())
for f in (f1, f2):
    ex = g["recipe_extras"](f)
    print(f.name, "| image:", ex["image"], "| nutrition:", ex["nutrition"], "| per:", ex["nutrition_per"], "| tips:", ex["tips"], "| prep/total:", ex["prep"], ex["total"])

# --- translation (fake translator: adds [EN]/[CS]) → title into the catalog, tips translated
g["translation_available"] = lambda: True
def fake_tr(strings, target_lang, source_lang): return [f"[{target_lang.upper()}] {s}" for s in strings], "gemini"
g["translate_strings"] = fake_tr
g["load_gemini_key"] = lambda: "x"
todo = g["bulk_translation_todo"]()
print("bulk todo:", [(t[0].name, t[1]) for t in todo])
g["run_bulk_translation"](todo)
print("bulk state:", {k: g["BULK_TR"].data[k] for k in ("done", "total", "failed")}, g["BULK_TR"].state)
print("bulk todo after:", g["bulk_translation_todo"]())
con = sqlite3.connect(g["DB_PATH"])
print("titles:", con.execute("SELECT recipe_id, title, title_en, title_cs FROM recipes ORDER BY recipe_id").fetchall())
en = json.loads((f1/"recipe_en.json").read_text(encoding="utf-8")); print("EN tips:", en.get("tips"))
# backfill: delete titles and fill them in from finished files
con.execute("UPDATE recipes SET title_en=NULL, title_cs=NULL"); con.commit()
print("backfill:", g["backfill_translated_titles"](), con.execute("SELECT title_en FROM recipes ORDER BY recipe_id").fetchall())

# --- recipe sheet
web = g["render_recipe_sheet"](f1, "en", None, "en", "web", 2.0, True, "/assets/x.jpg", "/api/card?id=r72374")
for needle in ["[EN] Kulajda", "Ingredients", "Nutrition", "Energy", "1449 kJ / 346 kcal", "(per 1 porce)", "Tips", "[EN] Houby", "1000 g", "Servings", "Batch: 2×", "Recipe card", "/assets/x.jpg"]:
    print(f"web has {needle!r}:", needle in web)
pdf = g["render_recipe_sheet"](f2, "orig", None, "cs", "pdf", 1.0, True, "cc-hero")
for needle in ["Bacon-Medaillons", "Suroviny", "Nutriční hodnoty", "Energie", "520 kcal", "Bílkoviny", "Tipy", "Dazu passt", "cc-hero", "<ol>"]:
    print(f"pdf has {needle!r}:", needle in pdf)

# --- server: /api/recipes, /api/recipe, /api/sheet
H = g["LanCookidooHandler"]
def get(path):
    h = H.__new__(H); h.path = path; h.wfile = io.BytesIO(); h.headers = {"Host": "pc:3665"}; h.st = []
    h.send_response = lambda c: h.st.append(c); h.send_header = lambda *a: None; h.end_headers = lambda: None; h.send_error = lambda c: h.st.append(("ERR", c))
    h.do_GET(); return h
r = json.loads(get("/api/recipes").wfile.getvalue())
print("api/recipes:", [(i["title"], i["title_en"], i["category_en"], i["search"]) for i in r["items"]])
r = json.loads(get("/api/recipe?id=r72374&lang=orig&scale=2&device=tm6&fine=0&ui=en").wfile.getvalue())
print("api/recipe dials:", r["steps"][0]["dials"], "| step:", r["steps"][0]["formatted_html"][:60], "| ings:", r["ingredients"])
print("matched:", r["steps"][0]["matched_ings"])
r = json.loads(get("/api/recipe?id=mcs_bacon&lang=orig&device=mcs&fine=0&ui=en").wfile.getvalue())
print("mcs dial time:", r["steps"][0]["dials"]["time"])
h = get("/api/sheet?id=mcs_bacon&lang=en&ui=en")
html = h.wfile.getvalue().decode()
print("api/sheet:", h.st[:1], "Nutrition" in html, "[EN] Bacon" in html, "bacon.jpg" in html, "Recipe card" in html)
print("search_key:", g["search_key"]("Kulajda Svíčková ŘÍZEK"))
