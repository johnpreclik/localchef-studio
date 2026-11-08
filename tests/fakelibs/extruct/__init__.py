# zjednodušený extruct jen pro testy (čte JSON-LD)
import json, re
def extract(html, base_url=None, syntaxes=None, errors="ignore", uniform=False, **kw):
    out = {"json-ld": [], "microdata": [], "opengraph": [], "rdfa": []}
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        out["json-ld"].extend(d if isinstance(d, list) else [d])
    return out
