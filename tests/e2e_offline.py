"""Offline translator at start (1.6): when missing, it downloads itself and shows a window with progress in percent.
“Příště nestahovat automaticky” turns it off, the ⚙️ item downloads through the same window."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None; g["init_db"]()
win = g["LocalChefStudio"]()
win._run_bg = lambda label, fn, done: done({"result": fn()})
orig_state = g["offline_translator_state"]
installs, dialogs = [], []
D = g["OfflineDownloadDialog"]


class Chk(fakeqt.W):
    def __init__(s, *a): super().__init__(); s._c = False
    def isChecked(s): return s._c
    def setChecked(s, v): s._c = v


g["QCheckBox"] = Chk
orig_init = D.__init__


def init(self, *a, **k):
    orig_init(self, *a, **k)
    self.chk_never.setChecked(tick[0])
    dialogs.append(self)


D.__init__ = init


def fake_install(progress=None):
    # progress as from the worker process: 2 models, the second one half downloaded
    assert progress({"i": 1, "n": 2, "pair": "en→cs", "done": 50, "total": 100}) is True
    installs.append(1)
    return {"pairs": [["cs", "en"], ["en", "cs"]]}


g["install_offline_translator"] = fake_install

print("položka v ⚙️:", win.btn_offline_tr.text())
assert win.btn_offline_tr.text() == "📥 Stáhnout offline překladač"

# 1) nothing installed → downloads by itself, no question, the window shows the result
g["offline_translator_state"] = lambda: {"installed": False, "missing": list(g["OFFLINE_PAIRS"])}
tick = [False]
win._startup_offline_check()
d = dialogs[-1]
print("okno:", d.lbl_head.text(), "|", d.lbl_detail.text(), "| stav:", d.job.data.get("pair"), D.percent(d.job.data), "%", d.job.state)
assert installs == [1] and len(dialogs) == 1 and D.percent(d.job.data) == 75 and d.job.state == "done"
assert "připravený" in d.lbl_head.text() and "cs→en" in d.lbl_detail.text()
assert not win.offline_job.running and not g["load_config"]().get("offline_tr_never_ask")

# 2) the user ticks “Příště nestahovat automaticky” → it is saved and nothing is downloaded at the next start
tick = [True]
win._startup_offline_check()
assert installs == [1, 1] and g["load_config"]().get("offline_tr_never_ask") is True
win._startup_offline_check()
assert installs == [1, 1], "po „Příště nestahovat automaticky“ se už nesmí stahovat"

# 3) everything downloaded → nothing
g["save_config"]({"offline_tr_never_ask": False})
g["offline_translator_state"] = lambda: {"installed": True, "missing": [], "pairs": list(g["OFFLINE_PAIRS"])}
win._startup_offline_check()
assert installs == [1, 1]

# 4) cancel: progress returns False, the window shows “cancelled”
job = g["Job"]("test")
job.start()
d = D(job, None, True)
assert d.progress({"i": 0, "n": 1}) is True
d._cancel()
assert d.progress({"i": 0, "n": 1}) is False and job.state == "cancelling"
assert job.finish("Stahování bylo zrušeno.") == "cancelled"
d.finish({"error": "Stahování bylo zrušeno."})
print("zrušeno:", d.lbl_head.text())
assert d.lbl_head.text() == "Stahování bylo zrušeno."

# 5) percent
P = D.percent
print("procenta:", P({}), P({"i": 0, "n": 4, "done": 0, "total": 0}), P({"i": 2, "n": 4, "done": 30, "total": 60}), P({"i": 4, "n": 4}))
assert (P({}), P({"i": 0, "n": 4}), P({"i": 2, "n": 4, "done": 30, "total": 60}), P({"i": 4, "n": 4})) == (0, 0, 62, 100)

# state without the library does not call the translator (the Argos process is not started at all)
g["has_argos"] = lambda: False
calls = []
g["argos_call"] = lambda req, t, progress=None: calls.append(req) or {}
st = orig_state()
print("bez knihovny:", st["installed"], len(st["missing"]), "| volání překladače:", len(calls))
assert st == {"installed": False, "missing": list(g["OFFLINE_PAIRS"])} and not calls
print("anglicky:", g["EN_UI"]["Příště nestahovat automaticky"], "|", g["EN_UI"]["📥 Stahuje se offline překladač… {p} %"])
