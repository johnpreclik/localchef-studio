"""Kontrola offline překladače při startu: dotaz ANO/NE + „Příště se již neptat“, stažení, položka v ⚙️."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None; g["init_db"]()
win = g["LocalChefStudio"]()
win._run_bg = lambda label, fn, done: done({"result": fn()})
orig_state = g["offline_translator_state"]
asked, installs = [], []
win._ask_offline_download = lambda text: (asked.append(text), answer[0])[1]
g["install_offline_translator"] = lambda: (installs.append(1), {"pairs": [["cs", "en"], ["en", "cs"]]})[1]

print("položka v ⚙️:", win.btn_offline_tr.text())
assert win.btn_offline_tr.text() == "📥 Stáhnout offline překladač"
assert g["EN_UI"]["📥 Stáhnout offline překladač"] == "📥 Download offline translator"

# 1) nic není nainstalované, uživatel odmítne a nechce se už ptát
g["offline_translator_state"] = lambda: {"installed": False, "missing": list(g["OFFLINE_PAIRS"])}
answer = [(False, True)]
win._startup_offline_check()
print("dotaz:", asked[-1].replace("\n", " "))
assert len(asked) == 1 and "není nainstalovaný" in asked[-1] and not installs
assert g["load_config"]().get("offline_tr_never_ask") is True
win._startup_offline_check()
assert len(asked) == 1, "po „Příště se již neptat“ se už nesmí ptát"

# 2) chybí jazyky, uživatel řekne ANO → stahuje se
g["save_config"]({"offline_tr_never_ask": False})
g["offline_translator_state"] = lambda: {"installed": True, "missing": [("cs", "en")], "pairs": [("en", "cs")]}
answer = [(True, False)]
win._startup_offline_check()
print("dotaz 2:", asked[-1].replace("\n", " "), "| stahování:", len(installs), "|", fakeqt.msgs[-1])
assert "cs→en" in asked[-1] and installs == [1] and "Hotovo" in fakeqt.msgs[-1][1]
assert not g["load_config"]().get("offline_tr_never_ask")

# 3) NE bez zaškrtnutí → příště se zeptá znovu
answer = [(False, False)]
win._startup_offline_check(); win._startup_offline_check()
assert len(asked) == 4 and not g["load_config"]().get("offline_tr_never_ask")

# 4) všechno staženo → žádný dotaz
g["offline_translator_state"] = lambda: {"installed": True, "missing": [], "pairs": list(g["OFFLINE_PAIRS"])}
win._startup_offline_check()
assert len(asked) == 4

# stav bez knihovny nevolá překladač (proces s Argosem se vůbec nespouští)
g["has_argos"] = lambda: False
calls = []
g["argos_call"] = lambda req, t: calls.append(req) or {}
st = orig_state()
print("bez knihovny:", st["installed"], len(st["missing"]), "| volání překladače:", len(calls))
assert st == {"installed": False, "missing": list(g["OFFLINE_PAIRS"])} and not calls
print("anglicky:", g["EN_UI"]["Příště se již neptat"], "|", g["EN_UI"]["ANO"], "/", g["EN_UI"]["NE"])
