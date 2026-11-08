import sys, types, json, io, sqlite3
class Dummy:
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return Dummy()
    def __getattr__(self, n): return Dummy()
def fake(name):
    m = types.ModuleType(name); m.__getattr__ = lambda n: Dummy; return m
for n in ["PyQt6","PyQt6.QtCore","PyQt6.QtGui","PyQt6.QtWidgets","PyQt6.QtWebEngineWidgets","PyQt6.QtWebEngineCore"]:
    sys.modules[n] = fake(n)
sys.modules["PyQt6.QtCore"].pyqtSignal = lambda *a, **k: Dummy()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["set_ui_lang"]("en")
print("tx:", g["tx"]("Nalezeno {n} receptů. Kategorie:", n=12), "|", g["cat_label"]("Nezařazené"), "|", g["cat_from_label"]("Main dishes"))
g["init_db"](); g["save_gemini_key"]("")
H = g["LanCookidooHandler"]; h = H.__new__(H); h.path = "/api/recipes"; h.wfile = io.BytesIO()
h.send_response = lambda *a: None; h.send_header = lambda *a: None; h.end_headers = lambda: None
h.do_GET(); print("mobil dostane ui_lang:", json.loads(h.wfile.getvalue())["ui_lang"])
print("hláška bez překladače:", g["tx"]("⚠️ Překladač není nastaven – v desktopové aplikaci zadej ✨ Gemini klíč nebo nainstaluj argostranslate. Zobrazuji originál."))
g["set_ui_lang"]("cs"); print("zpět CZ:", g["tx"]("Hotovo"), "|", g["cat_label"]("Nezařazené"))
