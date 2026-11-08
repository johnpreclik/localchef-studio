import sys, os, json, io, sqlite3
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None; g["init_db"]()
win = g["LocalChefStudio"]()
# ---- uložení receptu z Chefkoch
ld = {"@context":"https://schema.org","@type":"Recipe","name":"Einfache Kartoffelsuppe","recipeYield":"4","totalTime":"PT40M",
 "image":"https://img.chefkoch-cdn.de/x.jpg","recipeIngredient":["1 kg Kartoffeln","1 Zwiebel","2 EL Butter","1 l Gemüsebrühe","200 ml Sahne"],
 "nutrition": {"calories": "320 kcal", "fatContent": "14 g"},
 "recipeInstructions":[{"@type":"HowToStep","text":"Kartoffeln schälen und würfeln."},{"@type":"HowToStep","text":"Zwiebel fein hacken und in Butter andünsten."},
   {"@type":"HowToStep","text":"Kartoffeln und Brühe zugeben und alles 20 Minuten köcheln lassen."},{"@type":"HowToStep","text":"Sahne zugeben und pürieren."},
   {"@type":"HowToStep","text":"Mit Croutons aus der Pfanne servieren."}]}
html = f'<html><head><script type="application/ld+json">{json.dumps(ld)}</script></head><body><h1>Einfache Kartoffelsuppe</h1></body></html>'
url = "https://www.chefkoch.de/rezepte/305391110829449/Einfache-Kartoffelsuppe.html"
print("rs available:", g["has_recipe_scrapers"](), "| scrape:", (g["scrape_other_recipe"](html, url) or {}).get("steps"))
rid = g["other_recipe_id"](url); print("id:", rid)
win.is_batch_running = False
win._process_and_store_recipe(rid, url, html, True, "other")
con = sqlite3.connect(g["DB_PATH"]); print("db:", con.execute("select recipe_id, title, source_platform from recipes").fetchall())
folder = g["resolve_recipe_folder"](con.execute("select folder_path from recipes").fetchone()[0])
d = json.loads((folder/"recipe.json").read_text(encoding="utf-8")); print("saved:", d["extraction"], d["source_site"], len(d["steps"]), d["portions"])
print("icon:", g["get_recipe_icon_prefix"]("other", False, "dots"), g["get_recipe_icon_prefix"]("other", True, "bots"))
# ---- offline asistent
g["load_gemini_key"] = lambda: ""
for dev in ("tm6", "mcs"):
    p = g["ensure_device_recipe_file"](folder, dev); c = json.loads(p.read_text(encoding="utf-8"))
    print(f"== {dev} ({c['converted_by']}):", c["title"])
    for s in c["steps"]: print("   ", s["assist"], s["dials"], "|", s["text"][:60])
# ---- s klíčem Gemini se offline převod jednou vylepší
calls = []
def fake_gem(data, key, target_device="mcs"):
    calls.append(target_device)
    return {"title": data["title"] + " [AI]", "steps": [{"html": "AI krok", "text": "AI krok", "dials": {"time": "5 min", "temp": "100 °C", "speed": "1"}}]}
g["convert_recipe_via_gemini_api"] = fake_gem; g["load_gemini_key"] = lambda: "k"
p = g["ensure_device_recipe_file"](folder, "tm6"); print("gemini upgrade:", json.loads(p.read_text(encoding="utf-8"))["converted_by"], calls)
g["ensure_device_recipe_file"](folder, "tm6"); print("no 2nd call:", calls)
# ---- hledání: kuchařka (název i surovina)
print("local title:", [r["title"] for r in g["local_search"]("kartoffel", "title")])
print("local ingr:", [r["title"] for r in g["local_search"]("sahne", "ingredient")], g["local_search"]("xyz", "ingredient"))
# ---- server /api/search + fronta + skryté stránky
H = g["LanCookidooHandler"]
def get(path):
    h = H.__new__(H); h.path = path; h.wfile = io.BytesIO(); h.headers = {"Host": "pc"}
    h.send_response = lambda c: None; h.send_header = lambda *a: None; h.end_headers = lambda: None; h.send_error = print
    h.do_GET(); return h.wfile.getvalue()
r = json.loads(get("/api/search?q=Kartoffelsuppe&mode=title&ui=cs")); print("api:", len(r["local"]), {k: v["state"] for k, v in r["sources"].items()})
pages = []
class Page(fakeqt.W):
    def __init__(self, *a):
        super().__init__(); self.loadFinished = fakeqt.Sig(); self.url = None; pages.append(self); self.js = []
    def setUrl(self, u): self.url = str(u)
    def runJavaScript(self, js, cb): self.js.append(js); cb(json.dumps([{"url": self.url + "#r1", "title": "Výsledek z " + self.url[:30], "image": "https://x/i.jpg", "meta": "30 min"}]))
    def deleteLater(self): pass
g["QWebEnginePage"] = Page
timers = []
class T:
    @staticmethod
    def singleShot(ms, fn): (timers.append(fn) if ms < 30000 else None)
g["QTimer"].singleShot = T.singleShot
win._process_search_queue()
print("pages:", [p.url for p in pages])
for p in pages: p.loadFinished.emit(True)
while timers: timers.pop(0)()
r = json.loads(get("/api/search?q=Kartoffelsuppe&mode=title&ui=cs"))
print("after:", {k: (v["state"], len(v["results"])) for k, v in r["sources"].items()})
print("page html:", b"Hledat recepty" in get("/search?q=x"), "| open:", get("/open?id=abc")[:60])
