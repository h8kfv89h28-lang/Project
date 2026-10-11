"""Elenca i prodotti di una pagina categoria/ricerca metro.it/marketplace (griglia e caroselli).

Input: JSON di Firecrawl con chiave "rawHtml" (pagina /c/<categoria> o /search?q=...).
Output: id prodotto, prezzo IVA esclusa, R = prezzo rosso (promo), nome. Solo prezzi >= soglia.
Il venditore non compare nelle schede: va verificato sulla pagina prodotto con estrai_pagina.py.

Uso: python src/griglia_categoria.py pagina.json [pagina2.json ...] [--soglia 290]
"""

import html as htmlmod
import json
import re
import sys


def num(testo):
    t = re.sub(r"[^\d,]", "", htmlmod.unescape(testo))
    return float(t.replace(",", ".")) if t else None


def prodotti(h):
    visti = set()
    for m in re.finditer(r'<article id="([0-9a-f-]{36})-\d+"(.*?)</article>', h, re.S):
        pid, blocco = m.group(1), m.group(2)
        if pid in visti:
            continue
        visti.add(pid)
        nome = re.search(r'data-testid="product-name"[^>]*>(.*?)</p>', blocco, re.S)
        prezzo = re.search(r'multi-unit-main-price.*?<span[^>]*>(.*?)</span>', blocco, re.S)
        yield {
            "id": pid,
            "prezzo": num(prezzo.group(1)) if prezzo else None,
            "promo": "text-metro-red" in blocco,
            "nome": htmlmod.unescape(nome.group(1)).strip() if nome else "",
        }


if __name__ == "__main__":
    args = sys.argv[1:]
    soglia = 290.0
    if "--soglia" in args:
        i = args.index("--soglia")
        soglia = float(args[i + 1])
        del args[i:i + 2]
    for p in args:
        h = json.load(open(p, encoding="utf-8"))["rawHtml"]
        url = re.search(r'"og:url" content="([^"]+)"', h)
        tot = re.search(r"<span>(\d+) risultati</span>", h)
        print("##", url.group(1) if url else p, f"({tot.group(1)} risultati)" if tot else "")
        for r in prodotti(h):
            if r["prezzo"] and r["prezzo"] >= soglia:
                print(f"{r['id']} {r['prezzo']:>9.2f} {'R' if r['promo'] else ' '} {r['nome'][:90]}")
