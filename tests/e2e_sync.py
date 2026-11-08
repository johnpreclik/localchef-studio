import sys, types, json, sqlite3
class Dummy:
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return Dummy()
    def __getattr__(self, n): return Dummy()
def fake(name):
    m = types.ModuleType(name); m.__getattr__ = lambda n: Dummy; return m
for n in ["PyQt6","PyQt6.QtCore","PyQt6.QtGui","PyQt6.QtWidgets","PyQt6.QtWebEngineWidgets","PyQt6.QtWebEngineCore"]:
    sys.modules[n] = fake(n)
sys.modules["PyQt6.QtCore"].pyqtSignal = lambda *a, **k: Dummy()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["init_db"]()
R = g["RECIPES_DIR"]
def mk(name, data, deleted=False):
    f = R / name; f.mkdir(parents=True)
    if data is not None: (f/"recipe.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if deleted: (f/g["DELETED_MARK"]).write_text("x", encoding="utf-8")
    return f
mk("r1_gulas", {"recipe_id": "r1", "title": "Guláš", "url": "https://cookidoo.cz/r1", "category": "Hlavní jídla", "is_favorite": True, "source_platform": "tm6"})
mk("mcs_x_polevka", {"recipe_id": "mcs_x", "title": "Polévka", "device": "mcs"})
mk("r2_smazany", {"recipe_id": "r2", "title": "Smazaný"}, deleted=True)
mk("r3_known", {"recipe_id": "r3", "title": "Nový název"})
mk("prazdna", None)
mk("rozbity", None); (R/"rozbity"/"recipe.json").write_text("{nejson", encoding="utf-8")
con = sqlite3.connect(g["DB_PATH"]); con.execute("INSERT INTO recipes (recipe_id,title,folder_path,category) VALUES ('r3','Můj název','x','Dezerty')"); con.commit(); con.close()
print("přidáno:", g["sync_catalog_from_folders"]())
print("podruhé:", g["sync_catalog_from_folders"]())
con = sqlite3.connect(g["DB_PATH"])
for row in con.execute("SELECT recipe_id,title,category,is_favorite,source_platform FROM recipes ORDER BY recipe_id"): print(row)
g["set_recipe_json_field"](R/"mcs_x_polevka", "is_favorite", True)
print("json fav:", json.loads((R/"mcs_x_polevka"/"recipe.json").read_text(encoding="utf-8"))["is_favorite"])
