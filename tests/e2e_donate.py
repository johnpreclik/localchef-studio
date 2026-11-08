"""Version 1.5: Donation button (CZ/EN window with Ko-fi, PayPal, Revolut + QR), call to action in the header of
what's new and terms, bulk download of collections is gone."""
import sys, os, base64
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read()
for gone in ("_start_batch_collection_download", "_process_next_in_batch", "save_batch", "STÁHNOUT KOLEKCI",
             "DOWNLOAD COLLECTION", "dev-only", "is_batch_running"):
    assert gone not in src, f"zbytek hromadného stahování: {gone}"
src = src.split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None; g["init_db"]()
win = g["LocalChefStudio"]()

urls = [u for _, u in g["DONATE_LINKS"]]
assert urls == ["https://ko-fi.com/johnpreclik", "https://paypal.me/johnpreclik", "https://revolut.me/preca"], urls
png = base64.b64decode(g["DONATE_REVOLUT_QR_PNG"])
assert png[:8] == b"\x89PNG\r\n\x1a\n", "QR není PNG"
for lang in ("cs", "en"):
    h = g["whats_new_html"](lang)
    assert all(u in h for u in urls), f"hlavička novinek {lang} bez odkazů"
    assert h.index("ko-fi.com") < h.index("<h3"), "výzva má být nahoře"
    assert g["UI_TEXTS"][lang]["donate_btn"]
dlg = g["DonateDialog"]("en", parent=win)
assert dlg.lang == "en"
dlg._set_lang("cs"); assert dlg.lang == "cs"
print("tlačítko:", win.btn_donate.text(), "| QR", len(png), "B")
assert win.btn_donate.text() == g["UI_TEXTS"]["cs"]["donate_btn"]
win._show_donate()
assert "btn_donate" in g["WIDGET_TOOLTIPS"]
print("OK")
