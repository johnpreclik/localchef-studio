"""MCS community recipes: steps as cards (number, title, text / settings), the list twice on the page; temperature “℃”."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import stub
g = stub.load(sys.argv[1])
from bs4 import BeautifulSoup


def card(n, name, body):
    return (f'<div class="create-recipe-step-list-item"><div class="step-list-item"><div class="step-title">'
            f'<div class="v-avatar">{n}</div><div class="step-name">{name}</div><button>poznámka</button></div>'
            f'<div class="step-drag-details"><span class="mode-name">{body}</span></div></div></div>')


cards = (card(1, "Příprava zeleniny", "Mrkev oškrábej a nakrájej na kostičky.")
         + card(2, "Opékání masa", "Opékání 125℃ 6min.")
         + card(3, "Rozpuštění másla", "Manuální vaření 120℃ 35sek. 1 Vlevo")
         + card(4, "Mixování", "Manuální vaření 0℃ 30sek. 8 Vpravo"))
html = (f'<html><body><h1>Svíčková</h1><div class="create-recipe-step-list">{cards}</div>'
        f'<div class="print"><div class="create-recipe-step-list">{cards}</div></div></body></html>')
ex = g["extract_recipe_content"](BeautifulSoup(html, "html.parser"), "", "x")
print("zdroj:", ex["steps_source"])
for s in ex["steps"]:
    print(" ", s["text"], s["dials"])
assert ex["steps_source"] == "mcs-dom" and len(ex["steps"]) == 4, (ex["steps_source"], len(ex["steps"]))
assert ex["steps"][0]["text"] == "Příprava zeleniny: Mrkev oškrábej a nakrájej na kostičky."
assert ex["steps"][1]["dials"] == {"time": "6min", "temp": "125 °C", "speed": "—"}, ex["steps"][1]["dials"]
assert ex["steps"][2]["dials"]["speed"] == "Speed 1 (↺ Reverse)", ex["steps"][2]["dials"]
assert ex["steps"][3]["dials"]["speed"] == "Speed 8", ex["steps"][3]["dials"]
print("℃ v textu:", g["extract_tm_dials"]("Vař 10 min při 98℃")["temp"])
assert g["extract_tm_dials"]("Vař 10 min při 98℃")["temp"] == "98 °C"

# ordering of web search results: results with the query word first (stem without accents)
res = [{"title": "Frappé ledová káva", "url": "https://x/recipe/frappe"}, {"title": "Rajská polévka", "url": "https://x/recipe/rajska"},
       {"title": "Zelná polévka s klobásou", "url": "https://x/recipe/zelna"}, {"title": "Poctivá zelňačka", "url": "https://x/recipe/zelnacka"}]
ranked = [r["title"] for r in g["rank_search_results"](res, "zelňačka", "title")]
print("řazení:", ranked)
assert ranked[:2] == ["Zelná polévka s klobásou", "Poctivá zelňačka"], ranked
assert g["rank_search_results"](res, "zelí", "ingredient") == res
