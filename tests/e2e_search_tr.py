"""1.6: search with the term translated into the website's language, another attempt in English, srcset images, recipe language."""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(__file__))
import fakeqt; fakeqt.install()
src = open(sys.argv[1], encoding="utf-8").read().split('if __name__ == "__main__":\n    _install_crash_guard')[0]
g = {"__name__": "app"}; exec(compile(src, "app", "exec"), g)
g["start_lan_http_server"] = lambda: None; g["init_db"]()

# --- language of the search term
dq = g["detect_query_lang"]
cases = {("zelňačka", "en"): "cs", ("gulas", "en"): "cs", ("shrimps", "cs"): "en", ("chocolate cake", "cs"): "en",
         ("xyzzy", "en"): "en", ("xyzzy", "cs"): "cs"}
for (q, ui), want in cases.items():
    print(f"jazyk „{q}“ (rozhraní {ui}):", dq(q, ui))
    assert dq(q, ui) == want, (q, ui)

# --- translating the term: the dictionary wins (the offline translator gives zelňačka → “Greens”)
calls = []
g["has_argos"] = lambda: True
g["load_gemini_key"] = lambda: ""
g["load_api_key"] = lambda: ""
g["argos_call"] = lambda req, t, progress=None: (calls.append(req), {"texts": [{"krevety": "Shrimps.", "kuřecí polévka": "chicken soup"}.get(x, x) for x in req["texts"]]})[1]
tq = g["translate_query"]
print("překlady:", tq("zelňačka", "cs", "en"), "|", tq("Svíčková", "cs", "en"), "|", tq("kuřecí polévka", "cs", "en"), "|", tq("sauerkraut soup", "en", "cs"))
assert tq("zelňačka", "cs", "en") == "sauerkraut soup" and tq("Svíčková", "cs", "en") == "beef sirloin in cream sauce"
assert tq("kuřecí polévka", "cs", "en") == "chicken soup" and tq("krevety", "cs", "en") in ("shrimp", "shrimps")
n = len(calls); tq("kuřecí polévka", "cs", "en")
assert len(calls) == n, "druhý stejný dotaz musí jít z mezipaměti"
assert "cs>en|kureci polevka" in json.loads(g["_QUERY_TR_FILE"].read_text(encoding="utf-8"))

# --- plan of attempts for a website
sp = g["search_plan"]
print("plány:", sp("cs", "cs"), sp("cs", "en"), sp("en", "cs"), sp("cs", "de"), sp("en", "de"), sp("cs", ""))
assert (sp("cs", "cs"), sp("cs", "en"), sp("en", "cs"), sp("cs", "de"), sp("en", "de"), sp("cs", "")) == \
       ([""], ["cs>en"], ["en>cs"], ["", "cs>en"], [""], [""])
# unclear language ("spaghetti"): as typed first, the translation only as a fallback, in both directions
sure = g["query_lang_sure"]
print("sure:", sure("zelňačka"), sure("shrimps"), sure("spaghetti"), "| plans:", sp("cs", "en", False), sp("cs", "cs", False), sp("en", "en", False))
assert sure("zelňačka") and sure("chocolate cake") and not sure("spaghetti")
assert sp("cs", "en", False) == ["", "cs>en"] and sp("cs", "cs", False) == ["", "en>cs"] and sp("en", "en", False) == ["", "cs>en"]

# --- Chefkoch is no longer a default source (it refuses embedded browsers); a user can still add a German site in
# config.json – the German-site path is tested that way
assert "chefkoch" not in [x["id"] for x in g["DEFAULT_SEARCH_SOURCES"]]
g["save_config"]({"search_sources": g["DEFAULT_SEARCH_SOURCES"] + [{"id": "chefkoch", "lang": "de", "name": "Chefkoch",
    "url": "https://www.chefkoch.de/rs/s0/{q}/Rezepte.html", "link": r"chefkoch\.de/rezepte/\d+/"}]})
# --- the whole search: Czech sites in Czech, English ones in English, the German site the typed term first
st = g["request_web_search"]("zelňačka", "title", "cs")
key = g["search_key_of"]("zelňačka", "title")
for _ in range(100):
    srcs = g["SEARCH_STATE"][key]["sources"]
    if all(s["state"] != "translating" for s in srcs.values()):
        break
    time.sleep(0.05)
srcs = g["SEARCH_STATE"][key]["sources"]
for sid, s in srcs.items():
    print(f"  {sid:12} {s['state']:8} dotaz={s['query']!r} pozn={s['note']!r} url={s['search_url']}")
assert srcs["cookidoo"]["query"] == "zelňačka" and srcs["bbcgoodfood"]["query"] == "sauerkraut soup"
assert srcs["bbcgoodfood"]["note"] == "sauerkraut soup" and "sauerkraut%20soup" in srcs["bbcgoodfood"]["search_url"]
assert srcs["chefkoch"]["query"] == "zelňačka"
queued = list(g["_SEARCH_QUEUE"])
assert (key, "bbcgoodfood") in queued and (key, "cookidoo") in queued

# browser: starts each website with its term
started = []
win = g["LocalChefStudio"]()
win._start_source_search = lambda k, cfg, q: started.append((cfg["id"], q))
win._process_search_queue()
print("spuštěno:", started)
assert ("bbcgoodfood", "sauerkraut soup") in started and ("cookidoo", "zelňačka") in started and not g["_SEARCH_QUEUE"]

# Chefkoch found nothing → another attempt in English; then nothing more
assert g["advance_search_source"](key, "chefkoch") is True
for _ in range(100):
    if srcs["chefkoch"]["state"] != "translating":
        break
    time.sleep(0.05)
print("chefkoch 2. pokus:", srcs["chefkoch"]["query"], srcs["chefkoch"]["state"])
assert srcs["chefkoch"]["query"] == "sauerkraut soup" and srcs["chefkoch"]["state"] == "pending"
assert g["advance_search_source"](key, "chefkoch") is False
assert g["advance_search_source"](key, "cookidoo") is False

# state machine per website: the page strings follow it, a finished search cannot be reopened
M = g["source_search_machine"]
print("machines:", {sid: M(key, sid).state for sid in srcs})
assert M(key, "cookidoo").state == "searching" and srcs["cookidoo"]["state"] == "pending"
assert M(key, "chefkoch").state == "queued" and M(key, "chefkoch").data["attempt"] == 1
assert M(key, "cookidoo").go("done") and srcs["cookidoo"]["state"] == "done"
assert not M(key, "cookidoo").go("searching") and srcs["cookidoo"]["state"] == "done"
assert M(key, "mcs").go("error") and srcs["mcs"]["state"] == "error"

# a website that refused the hidden page (bot protection): state "blocked", left alone for an hour
assert M(key, "iprima").go("blocked") and srcs["iprima"]["state"] == "blocked"
g["mark_site_blocked"]("allrecipes", "HTTP 403")
assert g["site_blocked"]("allrecipes") and not g["site_blocked"]("bbcgoodfood")
st2 = g["request_web_search"]("gulas s knedlikem", "title", "cs")
print("next search:", {k: v["state"] for k, v in st2["sources"].items()})
assert st2["sources"]["allrecipes"]["state"] == "blocked" and st2["sources"]["cookidoo"]["state"] != "blocked"
g["_BLOCKED_SITES"]["allrecipes"] -= g["SEARCH_BLOCK_PAUSE"] + 1
assert not g["site_blocked"]("allrecipes"), "after an hour it is asked again"
assert "blocked" in g["SEARCH_EXTRACT_JS"] and "TT.blocked" in g["SEARCH_PAGE_HTML"]
assert [h["to"] for h in M(key, "bbcgoodfood").snapshot()["history"]] == ["translating", "queued", "searching"]

# no translator and not in the dictionary: an English site gets the term as typed
g["has_argos"] = lambda: False
g["request_web_search"]("bramborová bábovka s mákem", "title", "cs")
k2 = g["search_key_of"]("bramborová bábovka s mákem", "title")
for _ in range(100):
    if g["SEARCH_STATE"][k2]["sources"]["allrecipes"]["state"] != "translating":
        break
    time.sleep(0.05)
s2 = g["SEARCH_STATE"][k2]["sources"]["allrecipes"]
print("bez překladače:", s2["state"], s2["query"], repr(s2["note"]))
assert s2["state"] == "pending" and s2["query"] == "bramborová bábovka s mákem" and s2["note"] == ""

# --- results page: sticky bar, states “translating” and “searched as”
page = g["SEARCH_PAGE_HTML"]
assert "position:sticky" in page and "translating" in page and "searched as" in page and "hledáno jako" in page

# --- srcset images with a comma in the address (BBC Good Food) – only checks that the JS has the new parser
assert "fromSrcset" in g["SEARCH_EXTRACT_JS"] and "split(',').pop()" not in g["SEARCH_EXTRACT_JS"]

# --- recipe language: the text wins over a wrong tag from the website
rl = g["recipe_source_lang"]
cz = {"title": "Zelňačka", "language": "en-US", "ingredients": ["500 g kysaného zelí", "2 lžíce sádla", "1 cibule"],
      "steps": [{"text": "Cibuli nakrájejte a osmažte na sádle, přidejte zelí a vařte asi 30 minut."}]}
en = {"title": "Shrimp scampi", "language": "", "ingredients": ["1 lb shrimp", "2 tbsp butter"],
      "steps": [{"text": "Heat the butter in a large pan and add the shrimp, then stir until pink."}]}
short = {"title": "Toast", "language": "cs-CZ", "ingredients": [], "steps": []}
print("jazyk receptu:", rl(cz), rl(en), rl(short))
assert (rl(cz), rl(en), rl(short)) == ("cs", "en", "cs")
assert g["norm_lang"]("en_GB") == "en" and g["norm_lang"](None) == ""

# a Czech recipe into Czech: no translator needed, the result is a copy with the note “already in this language”
folder = g["RECIPES_DIR"] / "web_test_cz"
folder.mkdir(parents=True)
(folder / "recipe.json").write_text(json.dumps(dict(cz, source_platform="other"), ensure_ascii=False), encoding="utf-8")
(folder / "page_snapshot.html").write_text("<html><body><h1>Zelňačka</h1></body></html>", encoding="utf-8")
g["load_gemini_key"] = lambda: ""; g["has_argos"] = lambda: False; g["HAS_DEEPL"] = False
calls.clear()
print("už česky:", g["recipe_already_in"](folder, "tm6", "cs"), g["recipe_already_in"](folder, "tm6", "en"))
assert g["recipe_already_in"](folder, "tm6", "cs") and not g["recipe_already_in"](folder, "tm6", "en")
j, h = g["generate_translated_files"](folder, "cs", target_device="tm6")
data = json.loads(j.read_text(encoding="utf-8"))
print("kopie:", j.name, h.name if h else None, data.get("translation_same_language"), data["title"])
assert data["translation_same_language"] is True and not calls and h is not None
assert g["generate_translated_files"](folder, "en", target_device="tm6") == (None, None), "do EN bez překladače nejde"
# ---- Prima FRESH video recipes: only ingredients, the method is in the video → left out of the results
import io as _io
PAGES = {
 "https://fresh.iprima.cz/videorecepty/kulajda": '<script type="application/ld+json">{"@type":"Recipe","name":"Kulajda","recipeIngredient":["houby"]}</script>',
 "https://fresh.iprima.cz/videorecepty/bramboracka": '<script type="application/ld+json">[{"@type":"VideoObject"},{"@type":"Recipe","recipeIngredient":["brambory"],"recipeInstructions":[{"text":"Uvař."}]}]</script>',
 "https://fresh.iprima.cz/videorecepty/nic": '<html>bez JSON-LD</html>',
}
class _R(_io.BytesIO):
    def __enter__(s): return s
    def __exit__(s, *a): return False
fetched = []
def _open(req, timeout=0):
    u = req.full_url; fetched.append(u)
    return _R(PAGES[u].encode())
g["urllib"].request.urlopen = _open
rh = g["recipe_has_method"]
print("method:", rh("https://fresh.iprima.cz/videorecepty/kulajda"), rh("https://fresh.iprima.cz/videorecepty/bramboracka"), rh("https://fresh.iprima.cz/videorecepty/nic"))
assert (rh("https://fresh.iprima.cz/videorecepty/kulajda"), rh("https://fresh.iprima.cz/videorecepty/bramboracka"),
        rh("https://fresh.iprima.cz/videorecepty/nic")) == (False, True, None)
fetched.clear()
res = [{"url": u, "title": u} for u in list(PAGES) + ["https://fresh.iprima.cz/recepty/ovesna-kulajda"]]
kept = [r["url"].rsplit("/", 1)[1] for r in g["drop_results_without_method"](res, r"/videorecepty/")]
print("kept:", kept, "| fetched:", len(fetched))
assert kept == ["bramboracka", "nic", "ovesna-kulajda"] and len(fetched) == 3, "ordinary recipes are not fetched"
import re as _re
prima = next(x for x in g["DEFAULT_SEARCH_SOURCES"] if x["id"] == "iprima")
assert _re.search(prima["link"], "https://fresh.iprima.cz/recepty/kulajda") and not _re.search(prima["link"], "https://fresh.iprima.cz/magazin/suroviny/svickova")
# a custom source list from an older version gets the check (and the language) from the default source
g["save_config"]({"search_sources": [{"id": "iprima", "name": "Prima", "url": prima["url"], "link": prima["link"]}]})
src = g["search_sources"]()[0]
assert src["check_method"] == "/videorecepty/" and src["lang"] == "cs" and src["name"] == "Prima"
g["save_config"]({"search_sources": None})
print("OK")
