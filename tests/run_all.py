"""Spustí všechny testy (bez skutečného Qt – Qt je nahrazené atrapou, viz stub.py a fakeqt.py).

Použití (z kořene repozitáře):   python tests/run_all.py
Každý test běží v dočasné složce, kde si vytvoří vlastní localchef_data – skutečná data se nepoužijí.
Test vrací 0 a nesmí vypsat „Traceback“. Výstup testů je čitelný text – projdi ho i očima.
"""
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# aplikace má verzi v názvu souboru (localchef_studio_v1.5.py) → vezme se ta s nejvyšší verzí
APP = max(HERE.parent.glob("localchef_studio_v*.py"),
          key=lambda p: [int(x) for x in re.findall(r"\d+", p.stem.rsplit("_v", 1)[-1])])
TESTS = ["e2e_units", "e2e_v12", "e2e_card", "e2e_i18n", "e2e_assets2", "e2e_trash",
         "e2e_gui", "e2e_v13", "e2e_v15", "e2e_v16", "e2e_v17", "e2e_trim", "e2e_mcs_steps", "e2e_guide", "e2e_backup", "e2e_offline", "e2e_donate"]


def main() -> int:
    # výstup vždy v UTF-8: na Windows je jinak při přesměrování do souboru cp1250 a „→“ shodí výpis
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    # recipe-scrapers potřebuje extruct (těžká knihovna); když chybí, použije se zjednodušená atrapa
    if importlib.util.find_spec("extruct") is None:
        env["PYTHONPATH"] = str(HERE / "fakelibs") + os.pathsep + env.get("PYTHONPATH", "")
    verbose = "-v" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    failed = 0
    for name in (only or TESTS):
        with tempfile.TemporaryDirectory(prefix=f"cc_{name}_") as tmp:
            res = subprocess.run([sys.executable, str(HERE / f"{name}.py"), str(APP)], cwd=tmp, env=env,
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        out = (res.stdout or "") + (res.stderr or "")
        ok = res.returncode == 0 and "Traceback" not in out
        failed += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {name}")
        if verbose or not ok:
            print("    " + "\n    ".join(out.strip().splitlines()[-40:]))
    print(f"\n{len(only or TESTS) - failed}/{len(only or TESTS)} testů prošlo")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
