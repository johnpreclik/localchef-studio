import sys, os; sys.path.insert(0, os.path.dirname(__file__)); from stub import load
g = load(sys.argv[1])
S, M, T, ST = g["scale_ingredient_line"], g["convert_text_to_metric"], g["normalize_dial_time"], g["scale_step_text"]
for l in ["500 gramů brambor", "2-3 lžíce oleje", "1 1/2 hrnku mouky", "½ čajové lžičky soli", "100 g hořká čokoláda (70 % kakaa)",
          "2 vejce (vel. M)", "Mehl 200 g", "1 balíček (250 g) tvarohu", "sůl dle chuti", "1⁄2 cup sugar", "1 špetka sůl", "0,5 l mléka"]:
    print(f"{l!r:42} x2 → {S(l, 2)!r}")
for t in ["2 cups flour", "1 1/2 tbsp butter", "8 fl oz milk", "1 lb beef", "Bake at 350°F for 20 min", "350 degrees F", "2-3 tsp salt",
          "1 stick butter", "9 inch pan", "2 sticks cinnamon", "120 °C rychlost 1", "1⁄2 cup sugar", "16 oz pasta"]:
    print(f"{t!r:32} → {M(t, html_highlight=False)}")
for t in ["10 minut", "2 hodiny", "30 Sek.", "1 h 30 min", "5 Min.", "—", "", "90 s", "3 minuty"]:
    print(repr(t), "→", T(t))
print(ST("Přidejte <b>200 g</b> mouky a 0,5 l mléka, vařte 10 min/120 °C/rychlost 2.", 2))
