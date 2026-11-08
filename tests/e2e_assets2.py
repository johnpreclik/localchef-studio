import sys, os, time
exec(open(os.path.join(os.path.dirname(__file__), "e2e_assets.py"), encoding="utf-8").read().split("# karta")[0])
import re
W = g["WEB_ASSETS_DIR"]
for f in W.rglob("*"):
    if f.is_file(): os.utime(f, (time.time()-3600, time.time()-3600))
calls.clear()
print("start bez změn:", g["refresh_web_assets"](), "stažení:", calls)
WEB["https://cookidoo.cz/assets/main.css"] = (b"body{background:url(../img/bg2.png)}", "text/css")
WEB["https://cookidoo.cz/img/bg2.png"] = (b"PNG2", "image/png")
calls.clear()
print("start po změně webu:", g["refresh_web_assets"](), "stažení:", calls)
print("soubory:", sorted(p.relative_to(W).as_posix() for p in W.rglob("*") if p.is_file()))
# recipes r1 and r2 get the new style without downloading the recipe
H = g["LanCookidooHandler"]
for rid in ("r1","r2"):
    h = H.__new__(H); h.path = f"/api/card?id={rid}"; h.wfile = io.BytesIO(); h.headers = {"Host": "pc:3665"}
    h.send_response = h.send_header = lambda *a: None; h.end_headers = lambda: None; h.send_error = print
    h.do_GET(); print(rid, re.findall(r"assets/(cookidoo/css/[^'\"]+)", h.wfile.getvalue().decode()))
print("nový css:", g["asset_lookup"]("https://cookidoo.cz/assets/main.css"))
g["urllib"].request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
print("start offline:", g["refresh_web_assets"](), "soubory:", len([p for p in W.rglob('*') if p.is_file()]))
