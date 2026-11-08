import sys, os, json, io
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None; g["init_db"]()
class SB:
    def __init__(s): s.v, s.mx = 0, 500; s.valueChanged = fakeqt.Sig(); s.rangeChanged = fakeqt.Sig()
    def value(s): return s.v
    def maximum(s): return s.mx
    def setValue(s, v): s.v = v; s.valueChanged.emit(v)
class TB(fakeqt.W):
    def __init__(s, *a): super().__init__(); s.sb = SB(); s.html = ""
    def verticalScrollBar(s): return s.sb
    def setHtml(s, h): s.html = h
class Btn(fakeqt.W):
    def setEnabled(s, v): s._en = v
    def isEnabled(s): return getattr(s, "_en", True)
g["QTextBrowser"] = TB; g["QPushButton"] = Btn; g["QCheckBox"] = Btn
class Ev:
    ignored = False
    def ignore(s): s.ignored = True
D = g["WhatsNewDialog"]
D.accept = lambda s: setattr(s, "closed", "accept")
d = D("cs", True)
print("before shown, scrolled to bottom:", (d.view.sb.setValue(500), d.btn_ok.isEnabled())[1]); d.view.sb.v = 0
d._after_shown()
print("start:", d.btn_ok.isEnabled(), d.btn_ok.text(), "|", d.lbl_info.text()[:40], "| cz html:", "Co je nového" in d.view.html)
e = Ev(); d.closeEvent(e); print("close before read ignored:", e.ignored)
d._set_lang("en"); print("EN:", "What’s new" in d.view.html, d.chk_hide.text(), d.btn_ok.text())
d.view.sb.setValue(500); print("after scroll:", d.btn_ok.isEnabled(), d.btn_ok.text(), d.chk_hide.isEnabled())
d._set_lang("cs"); print("lang after read stays OK:", d.btn_ok.isEnabled())
d2 = D("cs", False); d2.view.sb.mx = 0; d2._after_shown(); print("short text enabled:", d2.btn_ok.isEnabled())
# sources + page
H = g["LanCookidooHandler"]
def get(path):
    h = H.__new__(H); h.path = path; h.wfile = io.BytesIO(); h.headers = {"Host": "pc"}
    h.send_response = lambda c: None; h.send_header = lambda *a: None; h.end_headers = lambda: None; h.send_error = print
    h.do_GET(); return h.wfile.getvalue()
print("sources:", [(s["name"], s["home"]) for s in json.loads(get("/api/sources"))])
# filling in og:image
g["_og_image"] = lambda u: "https://img/" + u.split("/")[-1] + ".jpg"
st = g["request_web_search"]("gulas", "title"); key = g["search_key_of"]("gulas", "title")
g["SEARCH_STATE"][key]["sources"]["bbcgoodfood"].update(state="done", results=[{"url": "https://www.bbcgoodfood.com/recipes/goulash", "title": "Goulash", "image": ""}])
g["fill_missing_images"](key, "bbcgoodfood")
print("og filled:", g["SEARCH_STATE"][key]["sources"]["bbcgoodfood"])

# video only
win = g["LocalChefStudio"](); win.is_batch_running = False
fakeqt.msgs.clear()
html = '<html><head><script type="application/ld+json">{"@type":"VideoObject","name":"Poctivá zelňačka"}</script></head><body><video src="x.mp4"></video></body></html>'
win._process_and_store_recipe("web_x", "https://fresh.iprima.cz/videa/poctiva-zelnacka-s-klobasou", html, False, "other")
print("video msg:", fakeqt.msgs[-1][1][:60] if fakeqt.msgs else None, "| saved:", list(g["RECIPES_DIR"].iterdir()))
# a video recipe WITH ingredients but no method (Prima FRESH /videorecepty/) is refused too
fakeqt.msgs.clear()
html2 = ('<html><head><script type="application/ld+json">[{"@type":"VideoObject","name":"Kulajda"},'
         '{"@type":"Recipe","name":"Kulajda","recipeIngredient":["500 ml vody","200 g hub","1 brambora"]}]</script></head>'
         '<body><h1>Kulajda</h1><h2>Ingredience</h2><ul><li>500 ml vody</li><li>200 g hub</li><li>1 brambora</li></ul></body></html>')
stored = win._process_and_store_recipe("web_y", "https://fresh.iprima.cz/videorecepty/kulajda", html2, False, "other")
print("video recipe with ingredients:", stored, fakeqt.msgs[-1][1][:50] if fakeqt.msgs else None)
assert stored is False and fakeqt.msgs and "video recept" in fakeqt.msgs[-1][1] and not list(g["RECIPES_DIR"].iterdir())
win._go_home(); print("home ok")
import re
print("iprima regex skips /videa/:", re.search(g["DEFAULT_SEARCH_SOURCES"][2]["link"], "https://fresh.iprima.cz/videa/poctiva-zelnacka") is None, re.search(g["DEFAULT_SEARCH_SOURCES"][2]["link"], "https://fresh.iprima.cz/recky-gulas") is not None)
