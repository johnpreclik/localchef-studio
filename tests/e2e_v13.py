import sys, os, json, sqlite3
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None
R = g["RECIPES_DIR"]
f = R / "r45604_apfel"; f.mkdir(parents=True)
(f/"recipe.json").write_text(json.dumps({"recipe_id": "r45604", "title": "Apfel-Zimt-Pudding", "category": "German Recipes Collection", "source_platform": "tm6",
  "ingredients": ["450 g Apfelsaft", "1 Pck. Vanillepuddingpulver"],
  "steps": [{"text": "x", "html": "Apfelsaft, Puddingpulver und Zimtzucker in den Mixtopf geben, <nobr>3 Sek./Stufe 5</nobr> verrühren und <nobr>5 Min./100°C/Stufe 2</nobr> aufkochen."}]}), encoding="utf-8")
(f/"page_snapshot.html").write_text("<html><body><h2>Suroviny</h2><p>Apfelsaft</p><h2>Tipy</h2><p>Dazu passt Sahne.</p></body></html>", encoding="utf-8")
g["init_db"]()
win = g["LocalChefStudio"]()
# --- jednotky překladu: <nobr> už větu nerozseká
units = [u for tr, u in g["RecipeTranslator"]._units('Apfelsaft in den Mixtopf geben, <nobr>3 Sek./Stufe 5</nobr> verrühren und <nobr>5 Min./100°C/Stufe 2</nobr> aufkochen.') if tr]
print("units:", units)
# --- jazyk po větách
for t in ["Suroviny", "Tipy", "Počet porcí", "Apfelsaft in den Mixtopf geben", "Dazu passt Sahne.", "4 portions"]:
    print(f"  {t!r} ->", g["detect_unit_lang"](t, "de"))
# --- pořadí překladačů
calls = []
g["HAS_DEEPL"] = True; g["load_api_key"] = lambda: "dk"; g["load_gemini_key"] = lambda: "gk"; g["has_argos"] = lambda: True
g["_deepl_translate"] = lambda xs, t: (calls.append("deepl"), [f"D:{x}" for x in xs])[1]
g["_gemini_translate"] = lambda xs, t, k: (calls.append("gemini"), [f"G:{x}" for x in xs])[1]
g["_argos_translate"] = lambda xs, s_, t: (calls.append("argos"), [f"A:{x}" for x in xs])[1]
print("order 1:", g["translate_strings"](["Hallo"], "en", "de"), calls)
def boom(*a): calls.append("deepl-fail"); raise RuntimeError("quota")
g["_deepl_translate"] = boom; calls.clear()
print("order 2:", g["translate_strings"](["Hallo"], "en", "de"), calls)
g["_gemini_translate"] = lambda *a: (calls.append("gemini-fail"), (_ for _ in ()).throw(RuntimeError("429")))[1]; calls.clear()
print("order 3:", g["translate_strings"](["Hallo"], "en", "de"), calls)
print("label:", (g["load_api_key"](), win._translator_label()))
# --- překlad karty: české nadpisy z cs, německý text z de, do cs se české nepřekládají
g["_deepl_translate"] = lambda xs, t: [f"[{t}]{x}" for x in xs]
sent = []
orig_ts = g["translate_strings"]
def spy(strings, tgt, src_): sent.append((src_, tgt, list(strings))); return orig_ts(strings, tgt, src_)
g["translate_strings"] = spy
g["translation_available"] = lambda: True
g["generate_translated_files"](f, "en", target_device="tm6")
for x in sent: print("  sent:", x[0], "->", x[1], x[2][:4])
d = json.loads((f/"recipe_en.json").read_text(encoding="utf-8")); print("EN step:", d["steps"][0]["html"])
sent.clear(); g["generate_translated_files"](f, "cs", target_device="tm6")
for x in sent: print("  sent cs:", x[0], "->", x[1], x[2][:4])
print("CS card has Suroviny untouched:", "<h2>Suroviny</h2>" in (f/"page_snapshot_cs.html").read_text(encoding="utf-8"))
# --- názvy podle UI
print("title combo:", [i[0] for i in win.combo_title_lang._items], "| current:", win.combo_title_lang.currentData())
def names():
    root = win.recipe_tree.invisibleRootItem(); return [root.child(i).child(j).text(0) for i in range(root.childCount()) for j in range(root.child(i).childCount())]
g["backfill_translated_titles"]()
win._load_catalog(); print("UI cs:", names())
win._change_ui_language(1); print("UI en:", names(), "| tooltip search:", win.search_input._tooltip[:40])
win.combo_title_lang.setCurrentIndex(1); print("orig:", names())
win.combo_title_lang.setCurrentIndex(0)
# --- kontextové menu
root = win.recipe_tree.invisibleRootItem(); item = root.child(0).child(0)
captured = {}
orig_menu = g["QMenu"]
class M(fakeqt.W):
    def exec(self, *a): captured["m"] = self
g["QMenu"] = M
win._recipe_context_menu(item)
m = captured["m"]
print("menu:", [a.text() for a in m._acts])
sub = [a for a in m._acts if "Move to category" in a.text()][0]
print("submenu:", [(a.text(), a.isEnabled()) for a in sub._acts])
target = [a for a in sub._acts if "Soups" in a.text()][0]
target.triggered.emit(False)
print("po přesunu:", json.loads((f/"recipe.json").read_text(encoding="utf-8"))["category"])
fakeqt.Inp.text_answer = ("Dezerty z Německa", True)
win._recipe_context_menu(win.recipe_tree.invisibleRootItem().child(0).child(0)); m = captured["m"]
sub = [a for a in m._acts if "Move to category" in a.text()][0]
sub._acts[0].triggered.emit(False)
print("nová z menu:", json.loads((f/"recipe.json").read_text(encoding="utf-8"))["category"])
fav = m._acts[0]; fav.triggered.emit(False)
print("fav:", sqlite3.connect(g["DB_PATH"]).execute("select is_favorite from recipes").fetchone())
# --- PDF HTML
html = g["render_recipe_sheet"](f, "en", None, "en", "pdf", 1.0, True, "cc-hero")
print("pdf layout:", "width='54%'" in html or "<td width='54%'" in html, "<td width=\"61%\"" in html, "Ingredients" in html, "Method" in html, "<nobr>" in html)
