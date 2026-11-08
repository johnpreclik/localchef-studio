"""1.6: update check against GitHub at start (after the offline translator), download with checksum, silent installer."""
import sys, os, io, json, hashlib
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None; g["init_db"]()
g["tempfile"].tempdir = os.getcwd()        # downloads go to the test folder, not the real %TEMP%

vt = g["version_tuple"]
assert vt("v1.10") > vt("1.9") > vt("1.6") == vt("1.6") > vt("1.5.3") and vt("") == (0,)

PAYLOAD = b"MZ fake installer " * 1000
SHA = hashlib.sha256(PAYLOAD).hexdigest()


def release(tag="v1.7", sha=SHA, size=len(PAYLOAD)):
    return {"tag_name": tag, "name": f"LocalChef Studio {tag[1:]}", "body": "## news", "html_url": "https://github.com/x/releases/tag/" + tag,
            "assets": [{"name": "LocalChef_Studio_1.7_python.zip", "browser_download_url": "https://dl/zip", "size": 5},
                       {"name": f"LocalChef_Studio_{tag[1:]}.exe", "browser_download_url": "https://dl/exe", "size": size,
                        "digest": "sha256:" + sha}]}


class Resp(io.BytesIO):
    def __init__(s, data, headers=None): super().__init__(data); s.headers = headers or {}
    def __enter__(s): return s
    def __exit__(s, *a): return False


state = {"rel": release(), "payload": PAYLOAD}


def fake_urlopen(req, timeout=0):
    url = req.full_url if hasattr(req, "full_url") else req
    if url == g["UPDATE_API"]:
        return Resp(json.dumps(state["rel"]).encode())
    if url == "https://dl/exe":
        return Resp(state["payload"], {"Content-Length": str(len(state["payload"]))})
    raise AssertionError(url)


g["urllib"].request.urlopen = fake_urlopen

rel = g["fetch_latest_release"]()
print("release:", rel["version"], rel["exe_name"], rel["exe_size"], rel["sha256"][:12])
assert rel["version"] == "1.7" and rel["exe_url"] == "https://dl/exe" and rel["sha256"] == SHA
assert g["check_for_update"]("1.6")["version"] == "1.7" and g["check_for_update"]("1.7") is None

# skipped version is not offered again at start
g["save_config"]({"update_skip_version": "1.7"})
assert g["check_for_update"]("1.6") is None
g["save_config"]({"update_skip_version": ""})

# download: progress, checksum, size
seen = []
path = g["download_update"](rel, lambda d, t: seen.append((d, t)))
print("downloaded:", path.name, path.stat().st_size, "| progress calls:", len(seen), seen[-1])
assert path.read_bytes() == PAYLOAD and seen[-1] == (len(PAYLOAD), len(PAYLOAD))
path.unlink()
state["payload"] = PAYLOAD[:-1] + b"X"
try:
    g["download_update"](rel); raise SystemExit("bad checksum must fail")
except RuntimeError as e:
    print("bad checksum:", e); assert "kontrolním součtem" in str(e)
state["payload"] = PAYLOAD[:100]
try:
    g["download_update"](rel); raise SystemExit("short file must fail")
except RuntimeError as e:
    print("short file:", e); assert "neúplný" in str(e)
assert not path.with_suffix(".part").exists() and not path.exists(), "no half-downloaded file may stay"
state["payload"] = PAYLOAD
try:
    g["download_update"](rel, lambda d, t: False); raise SystemExit("cancel must stop")
except RuntimeError as e:
    print("cancel:", e)

# installer command: silent, over this folder, relaunch; never asks for the install mode
cmd = g["installer_command"](g["Path"]("C:/x/setup.exe"), g["Path"](os.getcwd()))
print("command:", cmd)
assert "/SILENT" in cmd and "/CURRENTUSER" in cmd and "/relaunch=1" in cmd and f"/DIR={os.getcwd()}" in cmd

# GUI: start sequence What's new → offline check → update check → question; then download → installer → quit
win = g["LocalChefStudio"]()
win._run_bg = lambda label, fn, done: done({"result": fn()})
g["offline_translator_state"] = lambda: {"installed": True, "missing": [], "pairs": list(g["OFFLINE_PAIRS"])}
offers, installs, opened, quits = [], [], [], []
win._offer_update = lambda r, manual=False: offers.append((r["version"], manual))
steps = []
win.startup.on_change(lambda a, b, m: steps.append(b))
win._show_whats_new = lambda on_start=True: steps.append("(window)")
win._run_startup()
print("offered at start:", offers, "| steps:", steps, "| final:", win.startup.state)
assert offers == [("1.7", False)] and win.startup.state == "ready"
assert steps == ["whats_new", "(window)", "translator", "update", "ready"]
win._run_startup(); win._startup_done("translator"); win._startup_done("update")
assert offers == [("1.7", False)] and win.startup.state == "ready", "only one run; late reports change nothing"

# offline translator missing → update check comes after its download
win2 = g["LocalChefStudio"]()
win2._run_bg = lambda label, fn, done: done({"result": fn()})
order = []
g["offline_translator_state"] = lambda: {"installed": False, "missing": [("cs", "en")]}
g["install_offline_translator"] = lambda progress=None: (order.append("translator"), {"pairs": [["cs", "en"]]})[1]
win2._offer_update = lambda r, manual=False: order.append("update " + r["version"])
win2._show_whats_new = lambda on_start=True: order.append("whats new")
win2._run_startup()
print("order:", order)
assert order == ["whats new", "translator", "update 1.7"] and win2.startup.state == "ready"

# Docker: no check at all
real_mode = g["update_mode"]
g["update_mode"] = lambda: ""
win3 = g["LocalChefStudio"](); win3._run_bg = lambda label, fn, done: done({"result": fn()})
win3._offer_update = lambda r, manual=False: offers.append("docker!")
win3._show_whats_new = lambda on_start=True: None
g["offline_translator_state"] = lambda: {"installed": True, "missing": [], "pairs": []}
win3._run_startup()
assert "docker!" not in offers and win3.startup.state == "ready"
g["update_mode"] = real_mode

# the yes path: download → installer started detached → app quits
popen = []
g["subprocess"].Popen = lambda cmd, **k: popen.append(cmd)
g["QApplication"].quit = staticmethod(lambda: quits.append(1))
win4 = g["LocalChefStudio"](); win4._run_bg = lambda label, fn, done: done({"result": fn()})
win4._download_and_install(rel)
print("installer started:", popen[-1][0].split(os.sep)[-1], popen[-1][1:4], "| quit:", quits)
assert popen and popen[-1][0].endswith("LocalChef_Studio_1.7.exe") and quits == [1]
print("EN:", g["EN_UI"]["Na GitHubu je k dispozici nová verze {new} (máš {cur}).\n\nStáhnout a nainstalovat?"].splitlines()[0])
print("OK")
