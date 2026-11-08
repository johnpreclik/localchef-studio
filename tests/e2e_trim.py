"""Ostatní weby (vzor Prima FRESH): postup bez balastu stránky, tipy zvlášť, karta 1:1 oříznutá na recept."""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None; g["init_db"]()
g["schedule_page_assets"] = lambda f: None
g["scrape_other_recipe"] = lambda html, url: None        # test čtení ze stránky, ne recipe-scrapers
win = g["LocalChefStudio"]()

ld = {"@context": "https://schema.org", "@type": "Recipe", "name": "Česneková polévka s krutony",
      "description": "Poctivá česnečka se smaženými krutony, která postaví na nohy každého.",
      "author": {"@type": "Person", "name": "Jana Nováková"},
      "image": {"@type": "ImageObject", "url": "https://cdn.example.cz/2026/abc123def456.jpg"},
      "recipeIngredient": ["1 litr vývar zeleninový", "6 stroužků česnek", "4 ks brambory", "2 plátky chléb", "1 lžíce sádlo"],
      "recipeYield": "4 porce", "totalTime": "PT30M"}
html = f"""<html><head><title>Česnečka</title><link rel="stylesheet" href="/css/site.css">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script></head><body>
<header><nav><a href="/">Recepty</a> <a href="/tv">TV program</a> <a href="/houby">HOUBY</a></nav></header>
<div class="trends"><p>Trendy:</p><ul><li><a href="/x">Jednoduchá dýňová polévka s česnekem a bramborami</a></li></ul></div>
<div class="wrapper">
 <div class="byline"><span>Jana Nováková</span> <a href="/pin">Pin it</a></div>
 <aside class="hits"><h3>Hit týdne</h3><ul><li>Banana bread</li><li>Kynuté lívance</li></ul></aside>
 <div class="hero"><figure><img src="https://cdn.example.cz/2026/medium/abc123def456.jpg"><figcaption>Zdroj: Web</figcaption></figure></div>
 <main>
  <h1>Česneková polévka s krutony</h1>
  <p>Poctivá česnečka se smaženými krutony, která postaví na nohy každého.</p>
  <div class="ingredients-box"><h3>Suroviny</h3><ul><li>vývar (zeleninový) 1 litr</li><li>česnek 6 stroužků</li>
   <li>brambory 4 ks</li></ul></div>
  <div class="ingredients-box"><h4>Krutony</h4><ul><li>chléb 2 plátky</li><li>sádlo 1 lžíce</li></ul></div>
  <div class="video"><p>Připravte česnečku podle videoreceptu</p><div>Subtitles Font family Default Opacity 50%</div></div>
  <p>Na TOMTO ODKAZU můžete vyhrát zásobu polévek.</p>
  <h2><b>Postup přípravy</b></h2>
  <ol><li><p>Brambory oloupejte, nakrájejte na kostičky a vařte ve vývaru 15 minut doměkka.</p></li>
   <li><p>Česnek prolisujte a vmíchejte do polévky, už ji jen krátce prohřejte.</p></li>
   <li><p>Chléb nakrájejte na kostky a osmažte na sádle dozlatova.</p></li>
   <li><p>Polévku podávejte s krutony a posypte petrželkou.</p></li></ol>
  <div class="ad">REKLAMA</div>
  <blockquote><b>PRIMA TIP:</b> Česnek nevařte, jinak zhořkne a ztratí vůni.</blockquote>
  <h3><b>Tipy na obměny receptu</b></h3>
  <ul><li><p><b>Se sýrem:</b> Do misky přidejte nastrouhaný eidam.</p></li>
   <li><p><b>S vejcem:</b> Na závěr vmíchejte rozšlehané vejce.</p></li></ul>
  <h2><b>Všechny recepty z pořadu najdete v tomto odkazu</b></h2>
  <p><a href="/porad">Bistro s Janou Novákovou a dalšími kuchaři z pořadu</a></p>
  <h2>Přečtěte si také</h2>
  <ul><li>Menopauza by v práci neměla být tabu</li><li>10 mýtů o houbách a houbaření</li></ul>
 </main>
 <div class="recipe-source"><h4>Jana Nováková</h4><a href="/diskuze">Vstoupit do diskuze</a></div>
</div>
<div class="newsletter"><h3>Nejlepší recepty e-mailem</h3><form><input name="e"></form></div>
<footer><a href="/podminky">Podmínky užívání</a> Vlastník FTV spol. s r.o.</footer>
</body></html>"""
visible = "\n".join(["Recepty", "Česneková polévka s krutony", "Postup přípravy",
                     "Brambory oloupejte, nakrájejte na kostičky a vařte ve vývaru 15 minut doměkka.",
                     "Česnek prolisujte a vmíchejte do polévky, už ji jen krátce prohřejte.",
                     "Tipy na obměny receptu", "Se sýrem: Do misky přidejte nastrouhaný eidam.",
                     "Přečtěte si také", "Menopauza by v práci neměla být tabu", "Podmínky užívání"])

# záchranná cesta z viditelného textu se zastaví na tipech
vt_steps = g["steps_from_visible_text"](visible)
print("kroky z textu:", vt_steps)
assert len(vt_steps) == 2, vt_steps

url = "https://www.example.cz/cesnekova-polevka-s-krutony-123"
rid = g["other_recipe_id"](url)
win.is_batch_running = False
win._process_and_store_recipe(rid, url, html, True, "other", visible, "")
folder = next(g["RECIPES_DIR"].iterdir())
d = json.loads((folder / "recipe.json").read_text(encoding="utf-8"))
print("zdroj kroků:", d["extraction"]["steps"])
for i, s in enumerate(d["steps"], 1):
    print(f"  {i}. {s['text']}")
print("tipy:", d.get("tips"))
assert d["extraction"]["steps"] == "dom", d["extraction"]
assert len(d["steps"]) == 4, len(d["steps"])
assert d["steps"][0]["text"].startswith("Brambory oloupejte")
assert len(d.get("tips", [])) == 3 and d["tips"][0].startswith("PRIMA TIP:"), d.get("tips")
print("tipy v doplňcích:", g["recipe_extras"](folder)["tips"] == d["tips"])
assert g["recipe_extras"](folder)["tips"] == d["tips"]

from bs4 import BeautifulSoup
card = BeautifulSoup((folder / "page_snapshot.html").read_text(encoding="utf-8"), "html.parser")
text = card.body.get_text(" ", strip=True)
print("karta:", text)
for must in ("Česneková polévka s krutony", "Jana Nováková", "Poctivá česnečka", "Suroviny", "vývar (zeleninový)",
             "Krutony", "sádlo 1 lžíce", "Postup přípravy", "Polévku podávejte", "PRIMA TIP", "Tipy na obměny", "S vejcem"):
    assert must in text, f"na kartě chybí: {must}"
for junk in ("TV program", "Trendy", "Hit týdne", "videoreceptu", "Subtitles", "TOMTO ODKAZU", "REKLAMA",
             "Všechny recepty z pořadu", "Přečtěte si také", "Menopauza", "Vstoupit do diskuze", "e-mailem",
             "Podmínky užívání", "Pin it"):
    assert junk not in text, f"na kartě zůstalo: {junk}"
assert card.find("img") is not None and "abc123def456" in card.find("img")["src"]
assert card.head.find("link", rel="stylesheet") is not None, "styly webu musí zůstat"
assert g["find_recipe_ld"](card).get("name") == ld["name"], "JSON-LD musí zůstat"
print("karta oříznutá: OK")

# stránka, kde recept nejde najít, zůstane celá
plain = "<html><body><h1>Článek</h1><p>Nic o vaření.</p><footer>Patička</footer></body></html>"
s2 = BeautifulSoup(plain, "html.parser")
print("bez receptu ořezáno:", g["trim_recipe_page"](s2, {}, [], []), "| patička zůstala:", "Patička" in s2.get_text())
assert "Patička" in s2.get_text()
