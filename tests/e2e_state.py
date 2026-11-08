"""1.6 phase 1: StateMachine – allowed and forbidden transitions, listeners, threads, snapshot, registry, diagram."""
import sys, os, json, threading, enum, gc
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
SM = g["StateMachine"]
logged = []
g["log"] = logged.append          # collect only: the crashing listener below logs a traceback on purpose

T = {"idle": {"checking"}, "checking": {"offer", "idle", "failed"}, "offer": {"downloading", "idle"},
     "downloading": {"installing", "failed", "idle"}, "installing": set(), "failed": {"idle"}}
m = SM("aktualizace", T, "idle")
print(m, "| can checking:", m.can("checking"), "| can offer:", m.can("offer"))
assert m.state == "idle" and m.can("checking") and not m.can("offer")

# allowed path with data
assert m.go("checking") and m.go("offer", version="1.7") and m.go("downloading", done=0)
assert m.go("downloading") is False, "self-transition not in the table is refused"
assert m.state == "downloading" and m.data == {"version": "1.7", "done": 0} and m.is_in("offer", "downloading")
print("log:", [x for x in logged if x.startswith("[stav]")][:3])
assert "[stav] aktualizace: idle → checking" in logged and "[stav] aktualizace: checking → offer" in logged

# forbidden transition: refused, logged, state unchanged, no exception
n = len(logged)
assert m.go("idle") is True and m.go("installing") is False
assert m.state == "idle" and any("nepovolený přechod idle → installing" in x for x in logged[n:])

# final state has no way out
m.go("checking"); m.go("offer"); m.go("downloading"); m.go("installing")
assert m.state == "installing" and not m.go("idle") and m.state == "installing"

# reset: always allowed, data replaced
m.reset(run=2)
assert m.state == "idle" and m.data == {"run": 2}

# listeners: order, arguments; a crashing listener is logged and does not stop the transition or the others
seen = []
m.on_change(lambda a, b, mm: seen.append((a, b, mm.name)))
@m.on_change
def boom(a, b, mm):
    raise RuntimeError("listener bug")
m.on_change(lambda a, b, mm: seen.append(("second", b)))
assert m.go("checking") and m.state == "checking"
print("listeners:", seen, "| crash logged:", any("posluchač přechodu idle → checking spadl" in x for x in logged))
assert seen == [("idle", "checking", "aktualizace"), ("second", "checking")]
assert any("posluchač přechodu idle → checking spadl" in x and "listener bug" in x for x in logged)

# str-based Enum members as states
class S(str, enum.Enum):
    A = "a"
    B = "b"
e = SM("enum", {S.A: {S.B}, S.B: set()}, S.A, log_transitions=False)
n = len(logged)
assert e.state == "a" and e.go(S.B) and e.is_in(S.B) and e.state == "b"
assert not any("[stav] enum:" in x for x in logged[n:]), "log_transitions=False keeps the log quiet"

# table errors are programmer errors → raised at construction
for bad in ({"a": {"x"}}, {"a": set()}):
    try:
        SM("bad", bad, "a" if "x" in str(bad) else "z"); raise SystemExit("must raise")
    except ValueError as ex:
        print("bad table:", ex)

# threads: 8 threads fight over idle → busy → idle; the lock keeps every step legal
r = SM("race", {"idle": {"busy"}, "busy": {"idle"}}, "idle", log_transitions=False, history=100000)
wins = []
def worker():
    for _ in range(2000):
        if r.go("busy"):
            wins.append(1)
            assert r.go("idle")
ths = [threading.Thread(target=worker) for _ in range(8)]
[t.start() for t in ths]; [t.join() for t in ths]
hist = list(r.history)
print("threads:", len(wins), "wins,", len(hist), "transitions, final", r.state)
assert r.state == "idle" and len(hist) == 2 * len(wins)
assert all(a != b for _, a, b in hist) and all(hist[i][2] == hist[i + 1][1] for i in range(len(hist) - 1)), "history is a valid chain"

# snapshot is JSON-safe (data with a Path), registry of live machines, Mermaid diagram
m.data["file"] = g["Path"]("C:/x/setup.exe")
snap = m.snapshot()
json.dumps(snap)
print("snapshot:", snap["name"], snap["state"], snap["data"], len(snap["history"]))
assert snap["state"] == "checking" and snap["data"]["file"].endswith("setup.exe") and snap["history"][-1]["to"] == "checking"
names = [s["name"] for s in g["machines_snapshot"]()]
assert {"aktualizace", "enum", "race"} <= set(names) and names == sorted(names)
del e; gc.collect()
assert "enum" not in [s["name"] for s in g["machines_snapshot"]()], "dead machines leave the registry"
mer = m.to_mermaid()
print(mer.splitlines()[:3])
assert mer.startswith("stateDiagram-v2\n    [*] --> idle") and "    offer --> downloading" in mer and "    installing --> [*]" in mer
# ---- Job: the shared model of long tasks
J = g["Job"]
j = J("job")
assert j.state == "idle" and not j.running and j.start(total=3) and j.running and j.data["total"] == 3
assert j.start() is False, "a running job cannot start twice"
j.progress(done=2); assert j.data["done"] == 2 and j.state == "running"
assert j.finish() == "done" and not j.running and j.data["ended"] > 0
assert j.start() and j.data.get("done") is None, "a new run starts with fresh data"
assert j.finish("boom") == "failed" and j.data["error"] == "boom"
assert j.start() and j.cancel() and j.cancel_requested and j.running
assert j.finish("zrušeno") == "cancelled"
assert j.start() and j.cancel() and j.finish() == "done", "work that finished anyway counts as done"
assert not j.cancel(), "nothing to cancel when idle/done"

# ---- one recipe translation: the phone's state strings stay none / running / done / failed
import time as _t
folder = g["RECIPES_DIR"] / "web_x"; folder.mkdir(parents=True)
ts = g["translation_job_status"]
assert ts(folder, "en", "tm6") == {"state": "none"}
gate = threading.Event(); calls = []
def fake_gen(f, lang, target_device="tm6"):
    calls.append(lang); gate.wait(5)
    if len(calls) == 1:
        raise RuntimeError("no translator")
    out = f / "recipe_tm6_en.json"; out.write_text("{}", encoding="utf-8"); return out, None
g["generate_translated_files"] = fake_gen
st = g["start_translation_job"](folder, "en", "tm6")
assert st["state"] == "running" and g["start_translation_job"](folder, "en", "tm6")["state"] == "running" and len(calls) <= 1
gate.set()
for _ in range(100):
    if ts(folder, "en", "tm6")["state"] != "running": break
    _t.sleep(0.02)
st = ts(folder, "en", "tm6"); print("failed job:", st["state"], st["error"])
assert st["state"] == "failed" and st["error"] == "no translator"
assert g["start_translation_job"](folder, "en", "tm6")["state"] == "failed" and len(calls) == 1, "no retry within 30 s"
g["start_translation_job"](folder, "en", "tm6", force=True)
for _ in range(100):
    if ts(folder, "en", "tm6")["state"] != "running": break
    _t.sleep(0.02)
assert ts(folder, "en", "tm6")["state"] == "done" and len(calls) == 2

# ---- bulk translation: stop request → cancelled, counters in data
B = g["BULK_TR"]
def slow_gen(f, lang, target_device="tm6"):
    if B.data["done"] == 1:
        B.cancel()                       # the user clicks stop while the second recipe is being translated
    return f / "x.json", None
g["generate_translated_files"] = slow_gen
g["run_bulk_translation"]([(folder, "en", "tm6", "A"), (folder, "cs", "tm6", "B"), (folder, "en", "mcs", "C")])
print("bulk:", B.state, {k: B.data[k] for k in ("done", "total", "failed")})
assert B.state == "cancelled" and B.data["done"] == 2 and B.data["total"] == 3 and not B.running
print("OK")
