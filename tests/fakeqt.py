import sys, types
class Sig:
    def __init__(self): self.f = []
    def connect(self, f): self.f.append(f)
    def emit(self, *a):
        for f in self.f: f(*a)
class Enumish:
    def __getattr__(self, n): return Enumish()
    def __call__(self, *a, **k): return Enumish()
    def __or__(self, o): return self
    value = 0
class Meta(type):
    def __getattr__(cls, n):
        if n.startswith("__"): raise AttributeError(n)
        return Enumish()
class W(metaclass=Meta):
    """Universal widget: remembers text, data, state and offers signals."""
    def __init__(self, *a, **k):
        self._text = a[0] if a and isinstance(a[0], str) else ""
        self._items = []; self._idx = -1; self._checked = bool(k.get("checkable") and False); self._visible = True
        self._sigs = {}; self._tooltip = ""
    def __getattr__(self, n):
        if n.startswith("_"): raise AttributeError(n)
        if n in ("clicked", "toggled", "triggered", "textChanged", "currentIndexChanged", "currentTextChanged", "itemClicked", "timeout",
                 "urlChanged", "loadFinished", "recipe_moved", "finished_ok", "failed_err", "customContextMenuRequested", "returnPressed"):
            return self._sigs.setdefault(n, Sig())
        return lambda *a, **k: W()
    def setText(self, t): self._text = t
    def text(self): return self._text
    def setTitle(self, t): self._text = t
    def setToolTip(self, t): self._tooltip = t
    def setPlaceholderText(self, t): self._ph = t
    def isChecked(self): return self._checked
    def setChecked(self, v): self._checked = v
    def setVisible(self, v): self._visible = v
    def isVisible(self): return self._visible
    # combo
    def addItem(self, text, userData=None):
        self._items.append([text, userData])
        if self._idx < 0: self._idx = 0
    def clear(self): self._items = []; self._idx = -1
    def count(self): return len(self._items)
    def currentData(self): return self._items[self._idx][1] if 0 <= self._idx < len(self._items) else None
    def currentIndex(self): return self._idx
    def setCurrentIndex(self, i):
        old = self._idx; self._idx = i
        if old != i and not getattr(self, "_blocked", False): self._sigs.setdefault("currentIndexChanged", Sig()).emit(i)
    def findData(self, d):
        for i, it in enumerate(self._items):
            if it[1] == d: return i
        return -1
    def setItemText(self, i, t): self._items[i][0] = t
    def itemText(self, i): return self._items[i][0]
    def blockSignals(self, b): self._blocked = b
    def addAction(self, a):
        w = W(a) if isinstance(a, str) else a
        self.__dict__.setdefault('_acts', []).append(w); return w
    def addMenu(self, t):
        w = W(t); self.__dict__.setdefault('_acts', []).append(w); return w
    def setEnabled(self, v): self._enabled = v
    def isEnabled(self): return getattr(self, '_enabled', True)
    def addSection(self, t): return W(t)
    def currentIndexOf(self): return self._idx
class Item:
    def __init__(self, parent=None):
        self._kids = []; self._data = {}; self._text = ""; self._hidden = False; self._exp = False; self._tt = ""
        if parent is not None: parent._root()._kids.append(self) if isinstance(parent, Tree) else parent._kids.append(self)
    def setText(self, c, t): self._text = t
    def text(self, c): return self._text
    def setData(self, c, r, v): self._data[int(r)] = v
    def data(self, c, r): return self._data.get(int(r))
    def setHidden(self, h): self._hidden = h
    def isHidden(self): return self._hidden
    def setExpanded(self, e): self._exp = e
    def isExpanded(self): return self._exp
    def childCount(self): return len(self._kids)
    def child(self, i): return self._kids[i]
    def setFont(self, *a): pass
    def setToolTip(self, c, t): self._tt = t
    def isSelected(self): return getattr(self, '_sel', False)
    def setSelected(self, v): self._sel = v
class Tree(W):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self.__dict__["_r"] = Item(); self.__dict__["_cur"] = None
    def _root(self): return self._r
    def clear(self): self._r._kids = []
    def invisibleRootItem(self): return self._r
    def setCurrentItem(self, it):
        for x in self._all(): x._sel = False
        self._cur = it
        if it is not None: it._sel = True
    def _all(self):
        out, todo = [], list(self._r._kids)
        while todo:
            x = todo.pop(0); out.append(x); todo[:0] = x._kids
        return out
    def selectedItems(self): return [x for x in self._all() if x.isSelected()]
    def currentItem(self): return self._cur
    def itemAt(self, pos): return pos
class Role:
    UserRole = 256
class QtNS:
    ItemDataRole = Role
    def __getattr__(self, n): return Enumish()
Qt = QtNS()
msgs = []
class MB:
    class StandardButton: Yes = "yes"; No = "no"
    answer = "yes"
    @staticmethod
    def warning(*a): msgs.append(("warning", a[2]))
    @staticmethod
    def information(*a): msgs.append(("info", a[2]))
    @staticmethod
    def critical(*a): msgs.append(("critical", a[2]))
    @classmethod
    def question(cls, *a): msgs.append(("question", a[2])); return cls.answer
class Inp:
    text_answer = ("", False)
    @classmethod
    def getText(cls, *a, **k): return cls.text_answer
    @classmethod
    def getItem(cls, *a, **k): return ("", False)
class FD:
    path = ""
    @classmethod
    def getSaveFileName(cls, *a, **k): return (cls.path, "PDF")
    paths = []
    @classmethod
    def getOpenFileNames(cls, *a, **k): return (list(cls.paths), "7z")
printed = {}
class Doc:
    class ResourceType:
        class ImageResource: value = 2
    def __init__(self): self.res = {}
    def setDefaultFont(self, f): pass
    def setDocumentMargin(self, m): pass
    def setPageSize(self, size): self.page_size = size
    def addResource(self, t, u, r): self.res[str(u)] = r
    def setHtml(self, h): self.html = h
    def print(self, w): printed["html"] = self.html; open(w.path, "wb").write(b"%PDF-1.4 " + b"x" * 2000)
class Writer:
    def __init__(self, path): self.path = path
    def __getattr__(self, n): return lambda *a, **k: None
class Img:
    def __init__(self, p=""): self.p = p
    def isNull(self): return False
    def width(self): return 800
class Url:
    def __init__(self, s=""): self.s = s
    def __str__(self): return self.s
    def toString(self): return self.s
    @staticmethod
    def fromLocalFile(p): return Url("file://" + p)
def install():
    names = dict(Qt=Qt, QMessageBox=MB, QInputDialog=Inp, QFileDialog=FD, QTextDocument=Doc, QPdfWriter=Writer, QImage=Img, QUrl=Url,
                 QTreeWidgetItem=Item, QTreeWidget=Tree, pyqtSignal=lambda *a, **k: Sig())
    for modname in ["PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineCore"]:
        m = types.ModuleType(modname)
        m.__getattr__ = (lambda nm: names.get(nm, W))
        sys.modules[modname] = m
