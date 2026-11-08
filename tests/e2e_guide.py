"""Version 1.2: name LocalChef Studio, built-in guide CZ/EN (❓ button and an item in ⚙️), QR address from an environment variable."""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None; g["init_db"]()
win = g["LocalChefStudio"]()

print("název:", g["APP_NAME"], g["APP_VERSION"], "|", g["UI_TEXTS"]["cs"]["window_title"], "|", g["UI_TEXTS"]["en"]["window_title"])
assert g["APP_NAME"] == "LocalChef Studio" and g["APP_VERSION"] in g["WHATS_NEW"]
for lang in ("cs", "en"):
    assert "Cookidoo & Monsieur Cuisine Studio" not in g["UI_TEXTS"][lang]["window_title"]
    assert g["WHATS_NEW"][g["APP_VERSION"]][lang], "chybí Co je nového"

for lang in ("cs", "en"):
    h = g["how_to_html"](lang)
    titles = [t for t, _ in g["HOW_TO_GUIDE"][lang]]
    print(f"návod {lang}: {len(titles)} kapitol, {len(h)} znaků:", " | ".join(titles))
    assert g["GEMINI_KEY_URL"] in h and g["DEEPL_KEY_URL"] in h, "chybí odkazy na registraci klíčů"
    assert "argostranslate" in h and "500" in h and "Docker" in h
    for i in range(len(titles)):
        assert f"href='#s{i}'" in h and f"name='s{i}'" in h
    # balanced tags in the guide HTML
    for tag in ("ul", "ol", "li", "p", "b", "code", "a"):
        assert len(re.findall(f"<{tag}[ >]", h)) == h.count(f"</{tag}>"), (lang, tag)
assert len(g["HOW_TO_GUIDE"]["cs"]) == len(g["HOW_TO_GUIDE"]["en"])

dlg = g["HowToDialog"]("en", parent=win)
print("okno návodu:", dlg.lang)
dlg._set_lang("cs"); assert dlg.lang == "cs"
win._show_how_to()                       # must not crash
print("tlačítko:", win.btn_help.text(), "| menu:", win.act_how_to.text())
assert win.btn_help.text() == "❓ Návod" and win.act_how_to.text() == "❓ Návod k použití"
print("EN:", g["tx"]("❓ Návod") if g.get("_UI_LANG") == "en" else g["EN_UI"]["❓ Návod"])
assert g["EN_UI"]["❓ Návod"] == "❓ How to use"
assert "btn_help" in g["WIDGET_TOOLTIPS"]

os.environ["LOCALCHEF_LAN_HOST"] = "192.168.1.50"
print("IP pro QR (Docker):", g["get_local_ip"]())
assert g["get_local_ip"]() == "192.168.1.50"
del os.environ["LOCALCHEF_LAN_HOST"]
assert g["get_local_ip"]() != "192.168.1.50"
