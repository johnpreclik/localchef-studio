import sys, os, json, sqlite3
exec(open(os.path.join(os.path.dirname(__file__), "e2e_sync.py"), encoding="utf-8").read().split('print("přidáno:"')[0])
T = g["DELETED_DIR"]
ls = lambda d: sorted(x.name for x in d.iterdir()) if d.exists() else []
print("1. první start (kuchařka má recepty):", g["sync_catalog_from_folders"]())
print("   recipes:", ls(R)); print("   koš:", ls(T))
mk("r9_novy", {"recipe_id": "r9", "title": "Zkopírovaný"})
print("2. zkopírovaný recept:", g["sync_catalog_from_folders"]())
# deleting in the app
print("3. smazání r9 →", g["move_recipe_to_trash"](R/"r9_novy").name, "| recipes:", ls(R))
mk("r9_novy", {"recipe_id": "r9", "title": "Znovu stažený"})
print("4. stejný recept znovu, pak smazat →", g["move_recipe_to_trash"](R/"r9_novy").name)
print("   koš:", ls(T), "| mimo recipes:", g["move_recipe_to_trash"](T/"r9_novy"))
