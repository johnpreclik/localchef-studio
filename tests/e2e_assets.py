import sys, types, json, io, sqlite3, time
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
# fake internet
WEB = {
 "https://cookidoo.cz/assets/main.css": (b"@import 'extra.css'; body{background:url(../img/bg.png)} @font-face{src:url('/fonts/a.woff2')}", "text/css"),
 "https://cookidoo.cz/assets/extra.css": (b".x{color:red}", "text/css"),
 "https://cookidoo.cz/img/bg.png": (b"PNGDATA", "image/png"),
 "https://cookidoo.cz/fonts/a.woff2": (b"FONT", "font/woff2"),
 "https://assets.tmecosys.com/r1.jpg": (b"JPG1", "image/jpeg"),
 "https://assets.tmecosys.com/r2.jpg": (b"JPG1", "image/jpeg"),   # same content → one file
}
calls = []
class Resp:
    def __init__(s, d, t): s.d, s.headers = d, {"Content-Type": t}
    def read(s, n=-1): return s.d
    def __enter__(s): return s
    def __exit__(s, *a): pass
def urlopen(req, timeout=0):
    u = req.full_url; calls.append(u)
    if u not in WEB: raise OSError("404")
    return Resp(*WEB[u])
g["urllib"].request.urlopen = urlopen
def mk(rid, img):
    f = g["RECIPES_DIR"] / rid; f.mkdir(parents=True)
    (f/"recipe.json").write_text(json.dumps({"recipe_id": rid, "url": f"https://cookidoo.cz/recipes/recipe/cs-CZ/{rid}", "source_platform": "tm6"}), encoding="utf-8")
    (f/"page_snapshot.html").write_text(f"<html><head><base href='https://cookidoo.cz/'><link rel='stylesheet' href='/assets/main.css' integrity='sha-x'></head><body><img src='{img}' srcset='{img} 1x, /missing.jpg 2x'><div style=\"background:url('/img/bg.png')\"></div></body></html>", encoding="utf-8")
    con = sqlite3.connect(g["DB_PATH"]); con.execute("INSERT INTO recipes (recipe_id,title,folder_path,source_platform) VALUES (?,?,?,'tm6')", (rid, rid, str(f.resolve()))); con.commit(); con.close()
    return f
f1 = mk("r1", "https://assets.tmecosys.com/r1.jpg"); f2 = mk("r2", "https://assets.tmecosys.com/r2.jpg")
print("recept 1:", g["cache_page_assets"](f1), "souborů; stažení:", len(calls))
n0 = len(calls)
print("recept 2:", g["cache_page_assets"](f2), "souborů; nová stažení:", calls[n0:])
W = g["WEB_ASSETS_DIR"]
files = sorted(str(p.relative_to(W)) for p in W.rglob("*") if p.is_file())
print("web_assets:", files)
css = [p for p in W.rglob("*.css")]
print("CSS absolutní:", all("https://cookidoo.cz/" in p.read_text(encoding="utf-8") for p in css if "url(" in p.read_text(encoding="utf-8") or "@import" in p.read_text(encoding="utf-8")))
# card
H = g["LanCookidooHandler"]
def get(path, host="192.168.1.5:3665"):
    h = H.__new__(H); h.path = path; h.wfile = io.BytesIO(); h.headers = {"Host": host}; h.st = []
    h.send_response = lambda c: h.st.append(c); h.send_header = lambda *a: h.st.append(a); h.end_headers = lambda: None; h.send_error = lambda c: h.st.append(("ERR", c))
    h.do_GET(); return h
h = get("/api/card?id=r1"); html = h.wfile.getvalue().decode()
import re
print("odkazy na /assets/:", re.findall(r"http://192\.168\.1\.5:3665/assets/[^'\" )]+", html))
print("integrity odstraněno:", "integrity" not in html, "| chybějící zůstal z webu:", "/missing.jpg" in html)
rel = re.search(r"/assets/([^'\" )]+\.css)", html).group(1)
h = get("/assets/" + rel); print("server /assets:", h.st[0], [a for a in h.st if isinstance(a, tuple) and a[0]=="Content-Type"], h.wfile.getvalue().decode())
h = get("/assets/../index.json"); print("path traversal:", h.st)
h = get("/assets/%2e%2e/%2e%2e/cookidoo.db"); print("path traversal 2:", h.st)
time.sleep(0.5)
# offline: again – nothing is downloaded, it stays
g["urllib"].request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
print("offline cache:", g["cache_asset"]("https://cookidoo.cz/assets/main.css"))
