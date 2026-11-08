"""1.6 phase 2: saving a recipe as a state machine (one save at a time, done / skipped / failed, watchdog) and the
recipe view as one object (RecipeView)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None; g["init_db"]()

timers = []


class Timer(fakeqt.W):
    @staticmethod
    def singleShot(ms, fn): timers.append((ms, fn))


g["QTimer"] = Timer
win = g["LocalChefStudio"]()
URL = "https://www.chefkoch.de/rezepte/123/gulasch.html"
win.webview.url = lambda: fakeqt.Url(URL)
js_answers = []
win.webpage.runJavaScript = lambda js, cb: cb(js_answers.pop(0) if js_answers else True)
win.webpage.toHtml = lambda cb: cb("<html></html>")
result = {"v": True}
stored = []


def fake_store(rid, url, html, silent, plat, vt="", api=""):
    stored.append(rid)
    if isinstance(result["v"], Exception):
        raise result["v"]
    return result["v"]


win._process_and_store_recipe = fake_store
F = win.save_flow


def run_timers(max_ms=5000):
    """Fires the queued short timers (the 1.5 s start, 0.7 s retries); the 90 s watchdog stays queued."""
    while any(ms <= max_ms for ms, _ in timers):
        i = next(k for k, (ms, _) in enumerate(timers) if ms <= max_ms)
        timers.pop(i)[1]()


# 1) a normal save: waiting → extracting → storing → done, the url bar shows progress and comes back
fakeqt.msgs.clear()
win._save_current_recipe()
print("after click:", F.state, "| url bar:", win.url_bar.text())
assert F.state == "waiting" and win.url_bar.text() == "⏳ Ukládám recept…"
# 2) a second click while saving: nothing starts, a message says why
win._save_current_recipe()
assert F.state == "waiting" and fakeqt.msgs[-1][1].startswith("Recept se právě ukládá")
js_answers[:] = [False, False, True, '{"text": "x", "api": ""}']       # the page needs two retries
run_timers()
print("done:", F.state, [h["to"] for h in F.snapshot()["history"]][-4:], "| waited:", F.data.get("waited"), "| url bar:", win.url_bar.text())
assert F.state == "done" and stored == [g["other_recipe_id"](URL)] and F.data["waited"] == 2 and win.url_bar.text() == URL

# 3) a page without a recipe → skipped; the next save works again
result["v"] = False
win._save_current_recipe(); js_answers[:] = [True, "{}"]; run_timers()
assert F.state == "skipped"
# 4) an error while storing → failed with the message, re-raised for the crash guard
result["v"] = RuntimeError("disk full")
win._save_current_recipe(); js_answers[:] = [True, "{}"]
try:
    run_timers(); raise SystemExit("must re-raise")
except RuntimeError:
    pass
print("failed:", F.state, F.data["error"])
assert F.state == "failed" and F.data["error"] == "disk full" and win.url_bar.text() == URL

# 5) watchdog: the page never answers → after 90 s the flow is free again; an old watchdog does nothing
result["v"] = True
win.webpage.runJavaScript = lambda js, cb: None                          # no callback ever
timers.clear()
win._save_current_recipe(); run_timers()
assert F.state == "waiting"
dog = [fn for ms, fn in timers if ms == 90000]
assert len(dog) == 1
dog[0]()
print("watchdog:", F.state, F.data["error"])
assert F.state == "failed" and F.data["error"] == "timeout" and not F.running()
dog[0]()                                                                  # a late duplicate changes nothing
assert F.state == "failed"
print("diagram:", F.to_mermaid().splitlines()[1:3])
# ---- recipe view: one object, old attribute names map onto it, select() resets what belongs to one recipe
import json
V = win.view
win.display_lang = "en"; win.current_step_index = 4; win.portion_scale = 2.0; win.device_mode = "mcs"
assert (V.lang, V.step, V.scale, V.device) == ("en", 4, 2.0, "mcs") and win.display_lang == "en"
win.display_lang = "de"; win.device_mode = "kenwood"                     # typos are logged and ignored
assert V.lang == "en" and V.device == "mcs"
R = g["RECIPES_DIR"]
for rid, title in (("r1", "Kulajda"), ("r2", "Guláš")):
    d = R / f"{rid}_{title}"; d.mkdir(parents=True)
    (d / "recipe.json").write_text(json.dumps({"recipe_id": rid, "title": title, "ingredients": ["voda"],
        "steps": [{"text": f"{title} krok 1"}, {"text": "krok 2"}], "source_platform": "tm6"}, ensure_ascii=False), encoding="utf-8")
g["sync_catalog_from_folders"]()
win.view.data = {"title": "OLD"}
class EmptyRoot:
    def childCount(self): return 0
win.recipe_tree.invisibleRootItem = lambda: EmptyRoot()                   # the recipe is hidden by a filter
win._show_card = lambda *a, **k: None
win._open_recipe_by_id("r2")
snap = V.snapshot()
print("view after opening a hidden recipe:", {k: snap[k] for k in ("recipe_id", "lang", "step", "device", "scale", "data_title")})
assert V.recipe_id == "r2" and V.folder.name == "r2_Guláš" and V.lang == "orig" and V.step == 0
assert V.scale == 2.0 and V.device == "mcs", "machine and batch are preferences and stay"
assert V.data and V.data.get("title") != "OLD", "data are loaded for the new recipe, not left from the old one"
print("OK")
