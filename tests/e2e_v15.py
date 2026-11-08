import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None; g["init_db"]()
win = g["LocalChefStudio"]()
shown = []
class D(fakeqt.W):
    def __init__(self, lang, show_checkbox=True, parent=None):
        super().__init__(); self.chk_hide = fakeqt.W(); self.chk_hide._checked = True; shown.append((lang, show_checkbox))
    def exec(self): pass
g["WhatsNewDialog"] = D
win._show_whats_new(); win._show_whats_new(); win._show_whats_new(False)
print("shown:", shown, "| config:", g["load_config"]().get("whats_new_hidden"))
print("title:", g["UI_TEXTS"]["cs"]["window_title"], "| menu:", win.btn_whats_new.text())
win._change_ui_language(1); print("EN menu:", win.btn_whats_new.text())
h = g["whats_new_html"]("cs"); print("html:", "verze 1.0" in h, "pirátství" in h, "vzdělávací" in h.lower(), len(h))
