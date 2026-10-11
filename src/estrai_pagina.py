"""Estrae i dati di un prodotto dal codice HTML di una pagina metro.it/marketplace/product/<id>.

Input: file HTML grezzo (o JSON di Firecrawl con chiave "rawHtml").
Output (stdout): JSON con prezzo, promo (colore come sul sito), prezzo di riferimento, venditore,
valutazioni, consegna, sconti quantità, disponibilità, foto principale e punti chiave.

Uso: python src/estrai_pagina.py pagina.html [pagina2.html ...]
"""

import html as htmlmod
import json
import re
import sys

ETICHETTE_RIF = {
    "reference": "Prezzo più basso 30 gg",
    "msrp": "Prezzo consigliato",
    "usual": "Prezzo abituale",
}


def num(testo):
    """'1.290,00 €' -> 1290.0"""
    t = re.sub(r"[^\d,.]", "", htmlmod.unescape(testo))
    return float(t.replace(".", "").replace(",", ".")) if t else None


def testo(frammento):
    t = re.sub(r"<!--.*?-->", "", frammento, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", htmlmod.unescape(t)).strip()


def carica(path):
    raw = open(path, encoding="utf-8").read()
    if raw.lstrip().startswith("{"):
        d = json.loads(raw)
        return d.get("rawHtml") or d.get("html") or "", d.get("metadata", {})
    return raw, {}


def json_ld(h):
    out = []
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', h, re.S):
        try:
            out.append(json.loads(m.group(1)))
        except ValueError:
            pass
    return out


def estrai(h, meta=None):
    meta = meta or {}
    r = {}
    m = re.search(r'<button class="([^"]*)" test-target="price-box__total">(.*?)</button>', h, re.S)
    if m:
        r["prezzo"] = num(testo(m.group(2)))
        r["promo"] = "text-metro-red" in m.group(1)
        r["colore_sito"] = "rosso" if r["promo"] else "blu"
    m = re.search(r'data-testid="reference-price-row-(\w+)".*?test-target="price-box__reference__price"[^>]*>(.*?)</div>'
                  r'.*?product-promotion__percentage">(.*?)</span>', h, re.S)
    if m and r.get("promo"):
        r["prezzo_rif"] = num(testo(m.group(2)))
        r["etichetta_rif"] = ETICHETTE_RIF.get(m.group(1), m.group(1))
        r["sconto_sito"] = testo(m.group(3)).replace(" ", "")
    m = re.search(r'test-target="seller-name-desktop"[^>]*>(.*?)</a>', h, re.S)
    if m:
        r["venditore"] = testo(m.group(1))
    m = re.search(r'test-target="dynamic-shipping-price".*?<span>(.*?)</span>', h, re.S)
    if m:
        r["spedizione"] = testo(m.group(1))
    m = re.search(r'data-testid="shipping-info".*?<b>(.*?)</b>', h, re.S)
    if m:
        r["consegna_date"] = testo(m.group(1))
    m = re.search(r'data-testid="dynamic-shipping-label"[^>]*>(.*?)<', h, re.S)
    if m:
        r["tipo_consegna"] = testo(m.group(1))
    # parte alta della scheda (titolo + riquadro d'acquisto), esclusi i caroselli di altri prodotti
    i0 = h.find("<h1")
    i1 = h.find('data-testid="product-description"', i0)
    top = h[i0:i1] if i0 > 0 and i1 > i0 else h
    if re.search(r">\s*Disponibilità limitata\s*<", top):  # solo testo visibile, non le traduzioni JSON
        r["disponibilita_limitata"] = True
    m = re.search(r'alt="Classe efficienza energetica ([A-G+]+)"', top)
    if m:
        r["classe_energetica"] = m.group(1)
    vol = []
    for m in re.finditer(r'data-testid="VOLUME_PRICE_TABLE_ITEM".*?<span class="w-\[40%\][^"]*">(.*?)</span>'
                         r'<span class="w-1/4[^"]*">(.*?)</span><span[^>]*>(.*?)</span>', h, re.S):
        q, p, s = testo(m.group(1)), testo(m.group(2)), testo(m.group(3)).replace(" ", "")
        if "+" in q:
            vol.append({"quantita": q.replace("Acquistando", "").strip(), "prezzo": num(p), "risparmio": s})
    vol = [v for i, v in enumerate(vol) if v not in vol[:i]]
    if vol:
        r["sconti_quantita"] = vol
    for d in json_ld(h):
        if d.get("@type") != "Product":
            continue
        ar = d.get("aggregateRating")
        if ar and "valutazione" not in r:
            r["valutazione"] = round(float(ar["ratingValue"]), 1)
            r["recensioni"] = int(ar["reviewCount"])
        off = d.get("offers") or {}
        tt = (((off.get("shippingDetails") or {}).get("deliveryTime") or {}).get("transitTime") or {})
        if tt.get("minValue") is not None:
            r["giorni_consegna"] = f"{tt['minValue']}-{tt['maxValue']}"
        if off.get("availability"):
            r["disponibilita"] = off["availability"].rsplit("/", 1)[-1]
        if d.get("gtin"):
            r["gtin"] = d["gtin"]
        if d.get("brand", {}).get("name"):
            r["marca_sito"] = d["brand"]["name"]
    # punti chiave: elenco puntato della descrizione
    m = re.search(r'<ul[^>]*test-target="[^"]*highlights[^"]*"[^>]*>(.*?)</ul>', h, re.S)
    if m:
        r["punti_sito"] = [testo(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.S) if testo(x)][:6]
    # caratteristiche del prodotto (etichetta -> valore)
    car = {}
    for m in re.finditer(r'<span class="text-\[14px\] leading-\[20px\] text-grey-tint-40[^"]*">(.*?)</span>'
                         r'<span class="mx-2[^"]*"></span><span class="[^"]*font-bold[^"]*">(.*?)</span>', h, re.S):
        k, v = testo(m.group(1)), testo(m.group(2))
        if k and v:
            car.setdefault(k, v)
    if car:
        r["caratteristiche"] = car
    img = meta.get("og:image") or meta.get("ogImage")
    if not img:
        m = re.search(r'<meta property="og:image" content="([^"]+)"', h)
        img = m.group(1) if m else None
    if img:
        r["og_image"] = img
    url = meta.get("og:url") or meta.get("ogUrl") or meta.get("sourceURL") or ""
    if not url:
        m = re.search(r'<meta property="og:url" content="([^"]+)"', h)
        url = m.group(1) if m else ""
    m = re.search(r"/product/([0-9a-f-]{36})", url)
    if m:
        r["id"] = m.group(1)
    m = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
    if m:
        r["titolo"] = testo(m.group(1))
    return r


if __name__ == "__main__":
    out = {}
    for p in sys.argv[1:]:
        h, meta = carica(p)
        out[p] = estrai(h, meta)
    print(json.dumps(out, ensure_ascii=False, indent=1))
