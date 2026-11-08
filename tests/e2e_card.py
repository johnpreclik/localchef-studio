import sys, types, json, io, sqlite3
from pathlib import Path
class Dummy:
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return Dummy()
    def __getattr__(self, n): return Dummy()
def fake(name):
    m = types.ModuleType(name); m.__getattr__ = lambda n: Dummy; return m
for n in ["PyQt6","PyQt6.QtCore","PyQt6.QtGui","PyQt6.QtWidgets","PyQt6.QtWebEngineWidgets","PyQt6.QtWebEngineCore"]:
    sys.modules[n] = fake(n)
sys.modules["PyQt6.QtCore"].pyqtSignal = lambda *a, **k: Dummy()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["init_db"]()
folder = g["RECIPES_DIR"] / "mcs_rajcatova-omacka_rajčatová_omáčka"; folder.mkdir(parents=True)
(folder / "recipe.json").write_text(json.dumps({"recipe_id": "mcs_rajcatova-omacka", "title": "Rajčatová omáčka", "source_platform": "mcs", "steps": []}, ensure_ascii=False), encoding="utf-8")
(folder / "page_snapshot.html").write_text("<html><head><base href='https://www.monsieur-cuisine.com/'><link rel='stylesheet' href='/wp-content/themes/mc3/style.css'></head><body><header>menu</header><h1>Rajčatová omáčka</h1><img src='https://mc-web-content-cdn.tecpal.com/x.jpg'></body></html>", encoding="utf-8")
con = sqlite3.connect(g["DB_PATH"]); con.execute("INSERT INTO recipes (recipe_id,title,folder_path,source_platform) VALUES ('mcs_rajcatova-omacka','Rajčatová omáčka',?, 'mcs')", (str(folder.resolve()),)); con.commit(); con.close()
url = g["local_card_url"]("mcs_rajcatova-omacka")
print("URL karty:", url, "| rozpoznána jako karta:", g["is_offline_card_url"](url), "| web Cookidoo jako karta:", g["is_offline_card_url"]("https://cookidoo.cz/recipes/recipe/cs/r1"))
H = g["LanCookidooHandler"]; h = H.__new__(H); h.path = url.split(":3665")[1]; h.wfile = io.BytesIO()
h.send_response = lambda *a: None; h.send_header = lambda *a: None; h.end_headers = lambda: None; h.send_error = lambda c: print("ERR", c)
h.do_GET(); html = h.wfile.getvalue().decode()
print("base href na web:", "base href='https://www.monsieur-cuisine.com/'" in html, "| styly webu:", "style.css" in html, "| skrytí hlavičky:", "display: none !important" in html, "| obrázek:", "x.jpg" in html)
