"""Verze 1.3: záloha receptů do .7z (označené recepty / kategorie → export) a import jednoho či více .7z,
i se styly a obrázky karet; přepsání → koš; podezřelý archiv se odmítne; přejmenování cookidoo_data → localchef_data."""
import sys, os, json, sqlite3, shutil, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None
assert g["has_py7zr"](), "chybí py7zr"
import py7zr

R, WA = g["RECIPES_DIR"], g["WEB_ASSETS_DIR"]
CSS_URL, FONT_URL, IMG_URL = "https://site.example/s.css", "https://site.example/font.woff2", "https://site.example/i.jpg"
css_rel, font_rel, img_rel = "other/css/" + "a" * 24 + ".css", "other/fonts/" + "b" * 24 + ".woff2", "other/images/" + "c" * 24 + ".jpg"
for rel, data in ((css_rel, f"body{{font-family:x}} @font-face{{src:url({FONT_URL})}}".encode()), (font_rel, b"FONT"), (img_rel, b"JPEG")):
    (WA / rel).parent.mkdir(parents=True, exist_ok=True)
    (WA / rel).write_bytes(data)
(WA / "index.json").write_text(json.dumps({CSS_URL: {"file": css_rel, "kind": "css"}, FONT_URL: {"file": font_rel, "kind": "fonts"},
                                           IMG_URL: {"file": img_rel, "kind": "images"}}), encoding="utf-8")


def mk(rid, title, cat, fav=False):
    f = R / f"{rid}_{title}"
    f.mkdir(parents=True, exist_ok=True)
    (f / "recipe.json").write_text(json.dumps({"recipe_id": rid, "title": title, "category": cat, "source_platform": "other",
                                               "url": f"https://site.example/{rid}", "is_favorite": fav, "ingredients": ["1 kg brambor"],
                                               "steps": [{"text": "Vař 10 minut.", "dials": {}}]}, ensure_ascii=False), encoding="utf-8")
    (f / "page_snapshot.html").write_text(f'<html><head><link rel="stylesheet" href="{CSS_URL}"></head>'
                                          f'<body><h1>{title}</h1><img src="{IMG_URL}"></body></html>', encoding="utf-8")
    (f / "recipe_en.json").write_text('{"title": "EN"}', encoding="utf-8")
    return f


mk("web_a", "Kulajda", "Polévky"); mk("web_b", "Guláš", "Hlavní jídla", fav=True); mk("web_c", "Svíčková", "Hlavní jídla")
g["init_db"]()
win = g["LocalChefStudio"]()
win._run_bg = lambda label, fn, done: done({"result": fn()})


def items():
    out, root = {}, win.recipe_tree.invisibleRootItem()
    for i in range(root.childCount()):
        cat = root.child(i)
        out[cat.data(0, 256 + 3)] = cat
        for j in range(cat.childCount()):
            out[cat.child(j).data(0, 256 + 1)] = cat.child(j)
    return out


it = items()
# výběr: dva recepty (Ctrl + klik)
win.recipe_tree.setCurrentItem(it["web_a"]); it["web_b"].setSelected(True)
print("označené:", [x.data(0, 257) for x in win._selected_recipe_items()])
assert {x.data(0, 257) for x in win._selected_recipe_items()} == {"web_a", "web_b"}
# výběr celé kategorie
win.recipe_tree.setCurrentItem(it["Hlavní jídla"])
print("kategorie:", sorted(x.data(0, 257) for x in win._selected_recipe_items()))
assert sorted(x.data(0, 257) for x in win._selected_recipe_items()) == ["web_b", "web_c"]

# ---- export
win.recipe_tree.setCurrentItem(it["web_a"]); it["web_b"].setSelected(True)
arch = g["EXPORT_DIR"] / "zaloha.7z"
fakeqt.FD.path = str(arch.with_suffix(""))           # bez přípony – aplikace ji doplní
win._export_backup()
print("export:", fakeqt.msgs[-1])
assert arch.exists() and fakeqt.msgs[-1][0] == "info"
with py7zr.SevenZipFile(arch, "r") as z:
    names = z.getnames()
print("v archivu:", sorted(names))
assert "manifest.json" in names and f"web_assets/{font_rel}" in names and f"web_assets/{img_rel}" in names
assert any(n.startswith("recipes/web_a_Kulajda/") for n in names) and not any("web_c" in n for n in names)
assert g["backup_file_name"](["Guláš"]) == "Guláš.7z" and g["backup_file_name"](["a", "b"]).startswith("recepty_2_")

# ---- „jiný počítač“: recepty, databáze a soubory karet pryč
for f in R.iterdir():
    if f.name.startswith(("web_a", "web_b")):
        shutil.rmtree(f)
conn = sqlite3.connect(g["DB_PATH"]); conn.execute("DELETE FROM recipes WHERE recipe_id IN ('web_a','web_b')"); conn.commit(); conn.close()
shutil.rmtree(WA); g["_ASSET_INDEX"].update({"loaded": False, "map": {}})
fakeqt.FD.paths = [str(arch)]
win._import_backup()
print("import:", fakeqt.msgs[-1])
assert "Nové recepty: 2" in fakeqt.msgs[-1][1], fakeqt.msgs[-1]
rows = dict((r[0], r[1:]) for r in sqlite3.connect(g["DB_PATH"]).execute("SELECT recipe_id, category, is_favorite FROM recipes"))
print("v kuchařce:", rows)
assert rows["web_a"] == ("Polévky", 0) and rows["web_b"] == ("Hlavní jídla", 1)
assert (R / "web_a_Kulajda" / "recipe_en.json").exists(), "překlady musí přijít se zálohou"
assert g["asset_lookup"](CSS_URL) == css_rel and g["asset_lookup"](FONT_URL) == font_rel and (WA / img_rel).read_bytes() == b"JPEG"
assert json.loads((WA / "index.json").read_text(encoding="utf-8"))[FONT_URL]["file"] == font_rel

# ---- znovu: Ne = ponechat současné, Ano = přepsat (stará verze do koše)
rj = R / "web_a_Kulajda" / "recipe.json"
d = json.loads(rj.read_text(encoding="utf-8")); d["title"] = "Kulajda ZMĚNĚNÁ"; rj.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
fakeqt.MB.answer = "no"; win._import_backup()
print("import Ne:", fakeqt.msgs[-1][1].replace("\n", " | "))
assert "Přeskočené (už v kuchařce): 2" in fakeqt.msgs[-1][1] and "ZMĚNĚNÁ" in rj.read_text(encoding="utf-8")
assert any(m[0] == "question" for m in fakeqt.msgs[-3:])
fakeqt.MB.answer = "yes"; win._import_backup()
print("import Ano:", fakeqt.msgs[-1][1].replace("\n", " | "))
assert "Nahrazené: 2" in fakeqt.msgs[-1][1] and "ZMĚNĚNÁ" not in rj.read_text(encoding="utf-8")
trash = [p.name for p in g["DELETED_DIR"].iterdir()]
print("koš:", trash)
assert any(n.startswith("web_a_Kulajda") for n in trash)
assert sqlite3.connect(g["DB_PATH"]).execute("SELECT COUNT(*) FROM recipes WHERE recipe_id='web_a'").fetchone()[0] == 1

# ---- podezřelý archiv (cesta mimo složku) se odmítne a nic se nerozbalí
bad = Path(tempfile.mkdtemp()) / "zly.7z"
with py7zr.SevenZipFile(bad, "w") as z:
    z.writestr(b'{"format": "localchef-recipes"}', "manifest.json")
    z.writestr(b"x", "skripty/zlo.bat")           # mimo manifest/recipes/web_assets (cesty s ../ py7zr ani nezapíše)
st = g["stage_recipe_backups"]([str(bad)])
print("podezřelý archiv:", st["errors"])
assert st["errors"] and not st["items"]
shutil.rmtree(st["tmp"], ignore_errors=True)
assert not (Path.cwd() / "zlo.txt").exists() and not (R.parent / "zlo.txt").exists()
assert not g["_backup_name_ok"]("C:/x") and not g["_backup_name_ok"]("recipes/../x") and g["_backup_name_ok"]("recipes/r1/a.json")

# ---- přejmenování datové složky (do 1.2 cookidoo_data)
old_cwd = os.getcwd()
t = Path(tempfile.mkdtemp()); os.chdir(t)
(t / "cookidoo_data" / "recipes" / "r9_x").mkdir(parents=True)
c = sqlite3.connect(t / "cookidoo_data" / "catalog.db")
c.execute("CREATE TABLE recipes (recipe_id TEXT, folder_path TEXT)")
c.execute("INSERT INTO recipes VALUES ('r9', ?)", (str((t / "cookidoo_data" / "recipes" / "r9_x").resolve()),)); c.commit(); c.close()
new = g["_data_dir"]()
fp = sqlite3.connect(new / "catalog.db").execute("SELECT folder_path FROM recipes").fetchone()[0]
print("migrace:", new.name, "| stará zůstala:", (t / "cookidoo_data").exists(), "| cesta v DB:", fp)
assert new.name == "localchef_data" and not (t / "cookidoo_data").exists() and Path(fp).exists() and "localchef_data" in fp
assert g["_data_dir"]() == new                      # podruhé už nic nedělá
os.chdir(old_cwd)

# ---- nainstalováno tam, kam nejde zapisovat (Program Files) → data do %LOCALAPPDATA%\LocalChef Studio
la = Path(tempfile.mkdtemp())
os.environ["LOCALAPPDATA"] = str(la)
orig_w = g["_dir_writable"]
g["_dir_writable"] = lambda d: False
alt = g["_data_dir"]()
print("bez práva zápisu:", alt, "|", g["_DATA_NOTES"][-1])
assert alt == la / "LocalChef Studio" / "localchef_data"
g["_dir_writable"] = orig_w
assert g["_dir_writable"](la / "x") and (la / "x").is_dir()
