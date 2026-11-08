import sys, os, json, sqlite3
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None
R = g["RECIPES_DIR"]
def mk(rid, title, cat, plat="tm6"):
    f = R / f"{rid}_{title}"; f.mkdir(parents=True, exist_ok=True)
    (f/"recipe.json").write_text(json.dumps({"recipe_id": rid, "title": title, "category": cat, "source_platform": plat,
        "ingredients": ["500 g brambor"], "steps": [{"text": "Vařte 10 minut.", "dials": {"time": "10 minut"}}]}, ensure_ascii=False), encoding="utf-8")
    (f/"page_snapshot.html").write_text("<html><body>x</body></html>", encoding="utf-8")
    return f
mk("r1", "Kulajda", "Polévky"); mk("r2", "Svíčková na smetaně", "Hlavní jídla"); mk("r3", "Guláš", "Hlavní jídla"); mk("mcs_x", "Pancakes", "Pečení & Dezerty", "mcs")
g["init_db"]()
win = g["LocalChefStudio"]()
win._run_bg = lambda label, fn, done: done({"result": fn()})
def visible():
    out = []
    root = win.recipe_tree.invisibleRootItem()
    for i in range(root.childCount()):
        c = root.child(i)
        if c.isHidden(): continue
        kids = [c.child(j).text(0) for j in range(c.childCount()) if not c.child(j).isHidden()]
        out.append((c.text(0), kids, c.isExpanded()))
    return out
print("start:", visible())
for q in ["kulajda", "KULAJ", "svickova", "smetan svíč", "hlavni", "xyz"]:
    win.search_input.setText(q); win._filter_catalog(q)
    print(f"hledat {q!r}:", [(c, k) for c, k, e in visible()], "| info:", win.lbl_search_info.text(), win.lbl_search_info.isVisible())
win._filter_catalog("")
# přeložené názvy
con = sqlite3.connect(g["DB_PATH"]); con.execute("UPDATE recipes SET title_en='Bohemian mushroom soup' WHERE recipe_id='r1'"); con.commit(); con.close()
win.combo_title_lang.setCurrentIndex(1)
print("názvy EN:", visible())
win.search_input.setText("mushroom"); win._filter_catalog("mushroom"); print("hledat 'mushroom':", [(c, k) for c, k, e in visible()])
win._filter_catalog(""); win.search_input.setText("")
print("config title_lang:", g["load_config"]().get("title_lang"))
# nová kategorie bez vybraného receptu
fakeqt.Inp.text_answer = ("Saláty", True)
win._new_category()
print("kategorie v comboboxu:", [i[0] for i in win.combo_category_filter._items])
print("strom:", [c for c, k, e in visible()])
# nová kategorie s vybraným receptem → přesun
root = win.recipe_tree.invisibleRootItem()
item = [root.child(i).child(j) for i in range(root.childCount()) for j in range(root.child(i).childCount()) if root.child(i).child(j).data(0, 257) == "r3"][0]
win.recipe_tree.setCurrentItem(item)
fakeqt.Inp.text_answer = ("Rychlovky", True); fakeqt.MB.answer = "yes"
win._new_category()
print("po přesunu:", [(c, k) for c, k, e in visible()])
print("recipe.json category:", json.loads((R/"r3_Guláš"/"recipe.json").read_text(encoding="utf-8"))["category"])
# filtr kategorie
idx = win.combo_category_filter.findData("Saláty"); win.combo_category_filter.setCurrentIndex(idx)
print("jen Saláty:", visible())
win.combo_category_filter.setCurrentIndex(0)
# jazyk UI
win._change_ui_language(1)
print("EN UI:", win.btn_settings.text(), "|", win.btn_translate_all.text(), "|", win.btn_new_cat.text(), "|", win.lbl_view.text(), "|", [i[0] for i in win.combo_title_lang._items], "|", [c for c, k, e in visible()])
# PDF
win.current_recipe_folder = R/"r1_Kulajda"; win.current_recipe_id = "r1"
fakeqt.FD.path = str(g["PDF_DIR"] / "kulajda")
fakeqt.msgs.clear()
win._export_current_to_pdf()
print("PDF:", fakeqt.msgs, os.path.exists(fakeqt.FD.path + ".pdf"), "Ingredients" in fakeqt.printed.get("html", ""))
# hromadný překlad
g["translation_available"] = lambda: True
win._ensure_translator = lambda: True
g["translate_strings"] = lambda s, t, src: ([f"[{t}] {x}" for x in s], "gemini")
g["load_gemini_key"] = lambda: "x"
fakeqt.msgs.clear(); fakeqt.MB.answer = "yes"
import threading
win._bulk_translate()
for th in threading.enumerate():
    if th is not threading.current_thread() and th.daemon: th.join(timeout=10)
win._poll_bulk_translation()
print("bulk:", fakeqt.msgs[-1], g["BULK_TR"]["done"], g["BULK_TR"]["failed"])
print("názvy EN po překladu:", visible())
win._bulk_translate(); print("bulk again:", fakeqt.msgs[-1])
# zastavení
print("TM render s dávkou 2:")
win.current_offline_data = json.loads((R/"r1_Kulajda"/"recipe.json").read_text(encoding="utf-8")); win.portion_scale = 2.0
win._render_tm_step(); print("  čas:", win.lbl_dial_time.text().replace("\n", " "))
