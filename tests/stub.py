import sys, types
class Dummy:
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return Dummy()
    def __getattr__(self, n): return Dummy()
def fake(name):
    m = types.ModuleType(name); m.__getattr__ = lambda n: Dummy; return m
for n in ["PyQt6","PyQt6.QtCore","PyQt6.QtGui","PyQt6.QtWidgets","PyQt6.QtWebEngineWidgets","PyQt6.QtWebEngineCore"]:
    sys.modules[n] = fake(n)
sys.modules["PyQt6.QtCore"].pyqtSignal = lambda *a, **k: Dummy()
def load(path):
    src = open(path, encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
    g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g); return g
