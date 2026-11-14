"""Rotazione settimanale degli articoli nei volantini: 3 fissi + 3 a rotazione per categoria.

File:
- data/catalogo.json        articoli candidati per categoria (con i dati dell'ultima verifica)
- data/storico_uscite.json  articoli usciti in ogni volantino (data -> categoria -> id)
- data/prodotti.json        volantino della settimana (scritto da "applica", letto da genera_volantini.py)

Comandi:
  python src/rotazione.py proponi  [--data AAAA-MM-GG] [--riserve 3]
      Mostra per categoria i fissi, i candidati a rotazione in ordine di scelta e scrive in
      /tmp/da_verificare.txt i link da scaricare con Firecrawl (fissi + 3 a rotazione + riserve).
  python src/rotazione.py aggiorna /tmp/pagine/*.json [--data AAAA-MM-GG]
      Aggiorna nel catalogo prezzo, promo, venditore, consegna, ecc. dalle pagine prodotto scaricate
      (stesse regole del punto 1 della procedura) e marca l'articolo "ok" o "escluso" con il motivo.
  python src/rotazione.py applica  [--data AAAA-MM-GG]
      Sceglie 3 fissi + 3 a rotazione tra gli articoli verificati oggi, "ok" e completi (punti e foto),
      scrive data/prodotti.json e registra l'uscita nello storico.
  python src/rotazione.py stato
      Riepilogo del catalogo: articoli per categoria, ok/esclusi/da completare, ultima uscita.

Criteri di scelta degli articoli a rotazione (in ordine):
  1. non usciti nelle ultime `pausa_settimane` settimane (se non bastano: quelli usciti da più tempo);
  2. esito dell'ultima verifica (gli esclusi in fondo, ma vengono ricontrollati se servono);
  3. `priorita` più alta (campo facoltativo, es. 1 per articoli adatti alla stagione);
  4. in promo sul sito, con sconto più alto;
  5. tipo di prodotto non già presente nel volantino della categoria;
  6. usciti meno volte, poi usciti da più tempo (mai usciti per primi).
I fissi (campo "fisso": true) escono tutte le settimane; se uno non è valido lo sostituisce un articolo a rotazione.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import estrai_pagina  # noqa: E402

CATALOGO = os.path.join(ROOT, "data", "catalogo.json")
STORICO = os.path.join(ROOT, "data", "storico_uscite.json")
PRODOTTI = os.path.join(ROOT, "data", "prodotti.json")
DA_VERIFICARE = "/tmp/da_verificare.txt"

SOGLIA_PREZZO = 290.0
MAX_GIORNI_CONSEGNA = 28
IMG_POLICY = "?impolicy=pdp_mobile_main_preview&imwidth=768"
# campi di servizio del catalogo che non vanno nel volantino
CAMPI_CATALOGO = ("id", "fisso", "tipo", "stato", "motivo", "verificato", "priorita", "nome_sito", "promo")
CAMPI_PROMO = ("prezzo_rif", "etichetta_rif", "sconto_sito")


def carica_json(path, vuoto=None):
    if not os.path.exists(path):
        return vuoto
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def salva_json(path, dati):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)
        f.write("\n")


def id_da_url(url):
    m = re.search(r"/product/([0-9a-f-]{36})", url or "")
    return m.group(1) if m else None


def completo(a):
    """True se l'articolo ha tutto quello che serve per il volantino."""
    return bool(a.get("nome") and a.get("immagine") and len(a.get("punti") or []) >= 3 and a.get("prezzo"))


def sconto(a):
    m = re.search(r"(\d+)", a.get("sconto_sito") or "")
    return int(m.group(1)) if m else 0


def uscite_articolo(storico, categoria, pid):
    """Date (AAAA-MM-GG) in cui l'articolo è uscito nella categoria."""
    return sorted(u["data"] for u in storico["uscite"] if pid in u["categorie"].get(categoria, []))


def ordina_rotazione(cat, articoli, storico, oggi, pausa_giorni, gia_scelti, solo_verificati=False):
    """Restituisce gli articoli non fissi (più i fissi non validi esclusi) nell'ordine di scelta."""
    candidati = []
    for a in articoli:
        if a.get("fisso") or a["id"] in gia_scelti:
            continue
        if solo_verificati and not (a.get("verificato") == oggi and a.get("stato") == "ok" and completo(a)):
            continue
        date = uscite_articolo(storico, cat, a["id"])
        ultima = dt.date.fromisoformat(date[-1]) if date else None
        giorni = (dt.date.fromisoformat(oggi) - ultima).days if ultima else 10 ** 6
        candidati.append({
            "a": a,
            "in_pausa": giorni < pausa_giorni,
            "escluso": a.get("stato") == "escluso",
            "uscite": len(date),
            "giorni": giorni,
        })
    candidati.sort(key=lambda c: (
        c["in_pausa"],                       # 1. fuori pausa prima
        c["in_pausa"] and -c["giorni"],      #    se in pausa: usciti da più tempo prima
        c["escluso"],                        # 2. ok prima degli esclusi
        -(c["a"].get("priorita") or 0),      # 3. priorità
        not c["a"].get("prezzo_rif"),        # 4. promo prima
        -sconto(c["a"]),
        c["uscite"],                         # 6. meno uscite
        -c["giorni"],                        #    uscito da più tempo
    ))
    return candidati


def scegli(cat, articoli, storico, regole, oggi, gia_scelti, solo_verificati):
    """Fissi validi + rotazione con varietà di tipo. Restituisce (fissi, rotazione, riserve)."""
    n_fissi, n_rot = regole["fissi"], regole["rotazione"]
    pausa = regole["pausa_settimane"] * 7
    fissi = [a for a in articoli if a.get("fisso")]
    if solo_verificati:
        fissi = [a for a in fissi if a.get("verificato") == oggi and a.get("stato") == "ok" and completo(a)]
    fissi = [a for a in fissi if a["id"] not in gia_scelti][:n_fissi]
    posti = n_fissi + n_rot - len(fissi)
    tipi = {a.get("tipo") for a in fissi}
    ordinati = ordina_rotazione(cat, articoli, storico, oggi, pausa, gia_scelti, solo_verificati)
    rot, resto = [], []
    for c in ordinati:  # prima passata: tipi nuovi, solo fuori pausa
        if len(rot) < posti and not c["in_pausa"] and c["a"].get("tipo") not in tipi:
            rot.append(c)
            tipi.add(c["a"].get("tipo"))
        else:
            resto.append(c)
    conta = {}
    for t in [a.get("tipo") for a in fissi] + [c["a"].get("tipo") for c in rot]:
        conta[t] = conta.get(t, 0) + 1
    while len(rot) < posti and resto:  # seconda passata: il tipo meno ripetuto, a parità l'ordine di scelta
        c = min(resto, key=lambda x: (x["in_pausa"], conta.get(x["a"].get("tipo"), 0), resto.index(x)))
        rot.append(c)
        resto.remove(c)
        conta[c["a"].get("tipo")] = conta.get(c["a"].get("tipo"), 0) + 1
    return fissi, rot, resto


def cmd_proponi(args):
    catalogo, storico = carica_json(CATALOGO), carica_json(STORICO, {"uscite": []})
    regole = catalogo["regole"]
    link, scelti = [], set()
    for cat, articoli in catalogo["categorie"].items():
        fissi_tutti = [a for a in articoli if a.get("fisso")]
        fissi, rot, resto = scegli(cat, articoli, storico, regole, args.data, scelti, False)
        riserve = resto[:args.riserve]
        print(f"\n## {cat}  ({len(articoli)} nel catalogo)")
        for a in fissi_tutti:
            print(f"  FISSO     {riga(a)}")
        for c in rot:
            print(f"  ROTAZIONE {riga(c['a'], c)}")
        for c in riserve:
            print(f"  riserva   {riga(c['a'], c)}")
        for a in fissi_tutti + [c["a"] for c in rot + riserve]:
            scelti.add(a["id"])
            link.append(a["url"])
        if len(fissi_tutti) + len(rot) < regole["fissi"] + regole["rotazione"]:
            print(f"  AVVISO: catalogo {cat} troppo piccolo, aggiungere articoli (vedi PROCEDURA_SETTIMANALE.md)")
        liberi = [c for c in rot + resto if not c["in_pausa"] and not c["escluso"]]
        if len(liberi) < regole["rotazione"] * 2:
            print(f"  AVVISO: solo {len(liberi)} articoli fuori pausa: conviene ampliare il catalogo {cat}")
    with open(DA_VERIFICARE, "w") as f:
        f.write("\n".join(link) + "\n")
    print(f"\n{len(link)} link da verificare scritti in {DA_VERIFICARE}")


def riga(a, c=None):
    extra = []
    if c:
        extra.append(f"uscito {c['uscite']}x" + (f", {c['giorni']} gg fa" if c["uscite"] else ""))
        if c["in_pausa"]:
            extra.append("IN PAUSA")
    if a.get("stato") == "escluso":
        extra.append(f"escluso il {a.get('verificato')}: {a.get('motivo')}")
    if not completo(a):
        extra.append("DA COMPLETARE (punti/foto)")
    promo = f" promo {a.get('sconto_sito')}" if a.get("prezzo_rif") else ""
    prezzo = f"{a['prezzo']:.2f} €" if a.get("prezzo") else "?"
    return f"{a['id'][:8]} {prezzo:>11}{promo:<11} {a.get('tipo', ''):<14} {a.get('nome', '')[:44]}" + \
        (f"  [{'; '.join(extra)}]" if extra else "")


def giorni_max(giorni):
    nums = [int(x) for x in re.findall(r"\d+", giorni or "")]
    return max(nums) if nums else None


def aggiorna_articolo(a, r, oggi):
    """Applica ad un articolo del catalogo i dati letti da estrai_pagina.py. Restituisce il motivo di esclusione."""
    motivi = []
    if not r.get("prezzo") or not r.get("titolo"):
        motivi.append("pagina non trovata o prodotto non acquistabile")
    if r.get("disponibilita") and r["disponibilita"] not in ("InStock", "LimitedAvailability"):
        motivi.append(f"non disponibile ({r['disponibilita']})")
    if r.get("prezzo"):
        a["prezzo"] = r["prezzo"]
        if r["prezzo"] < SOGLIA_PREZZO:
            motivi.append(f"prezzo {r['prezzo']:.2f} € sotto {SOGLIA_PREZZO:.0f} €")
    a["promo"] = bool(r.get("promo"))
    if r.get("promo") and r.get("prezzo_rif"):
        for k in CAMPI_PROMO:
            if r.get(k) is not None:
                a[k] = r[k]
    else:
        for k in CAMPI_PROMO:
            a.pop(k, None)
    a["venditore"] = r.get("venditore") or ""  # sempre dalla pagina: mai tenere il venditore della ricerca
    if (a.get("venditore") or "").strip().upper() != "METRO":
        motivi.append(f"venditore {a.get('venditore')!r} diverso da METRO")
    if r.get("spedizione") or r.get("giorni_consegna"):
        a["consegna"] = {"costo": r.get("spedizione", ""), "giorni": r.get("giorni_consegna", "")}
        gm = giorni_max(r.get("giorni_consegna"))
        if gm and gm > MAX_GIORNI_CONSEGNA:
            motivi.append(f"consegna in {r['giorni_consegna']} giorni (oltre 4 settimane)")
    sq = r.get("sconti_quantita") or []
    if sq:
        primo = sq[0]
        da = re.search(r"\d+", primo.get("quantita", ""))
        a["sconto_quantita"] = {"da": int(da.group(0)) if da else None, "prezzo": primo.get("prezzo"),
                                "risparmio": primo.get("risparmio")}
    else:
        a.pop("sconto_quantita", None)
    if r.get("valutazione") is not None:
        a["valutazione"] = {"media": r["valutazione"], "recensioni": r.get("recensioni", 0)}
    if r.get("classe_energetica"):
        a["classe_energetica"] = r["classe_energetica"]
    a["disponibilita_limitata"] = bool(r.get("disponibilita_limitata"))
    if r.get("og_image"):
        a["immagine"] = r["og_image"].split("?")[0] + IMG_POLICY
    if not a.get("marca") and r.get("marca_sito"):
        a["marca"] = r["marca_sito"]
    if r.get("titolo"):
        a["nome_sito"] = r["titolo"]
    a["verificato"] = oggi
    a["stato"] = "escluso" if motivi else "ok"
    if motivi:
        a["motivo"] = "; ".join(motivi)
    else:
        a.pop("motivo", None)
    return a["motivo"] if motivi else None


def cmd_aggiorna(args):
    catalogo = carica_json(CATALOGO)
    per_id = {a["id"]: (cat, a) for cat, arts in catalogo["categorie"].items() for a in arts}
    risultati = {}
    for p in args.pagine:
        h, meta = estrai_pagina.carica(p)
        risultati[p] = estrai_pagina.estrai(h, meta)
    if estrai_pagina.diagnostica(risultati):
        raise SystemExit("Interrotto: l'HTML del sito sembra cambiato, controllare estrai_pagina.py")
    for p, r in risultati.items():
        pid = r.get("id") or id_da_url(os.path.basename(p)) or os.path.basename(p).split(".")[0]
        if pid not in per_id:
            print(f"AVVISO: {p}: prodotto {pid} non presente nel catalogo (aggiungerlo prima con il suo url)")
            continue
        cat, a = per_id[pid]
        motivo = aggiorna_articolo(a, r, args.data)
        esito = f"ESCLUSO: {motivo}" if motivo else "ok"
        if not motivo and not completo(a):
            esito += " ma DA COMPLETARE (scrivere 3 punti e controllare nome e foto)"
        print(f"{cat:<18} {a.get('nome', '')[:44]:<44} {a.get('prezzo') or 0:>9.2f} {esito}")
    salva_json(CATALOGO, catalogo)


def cmd_applica(args):
    catalogo, storico = carica_json(CATALOGO), carica_json(STORICO, {"uscite": []})
    prodotti = carica_json(PRODOTTI)
    regole, oggi = catalogo["regole"], args.data
    meta_cat = {c["titolo"]: c for c in prodotti["categorie"]}
    nuove_cat, uscita, scelti, problemi = [], {}, set(), []
    for cat, articoli in catalogo["categorie"].items():
        fissi, rot, _ = scegli(cat, articoli, storico, regole, oggi, scelti, True)
        sel = fissi + [c["a"] for c in rot]
        n = regole["fissi"] + regole["rotazione"]
        if len(sel) < n:
            problemi.append(f"{cat}: solo {len(sel)} articoli verificati oggi, ok e completi su {n}: "
                            f"verificare/completare le riserve e rilanciare")
        scelti.update(a["id"] for a in sel)
        uscita[cat] = [a["id"] for a in sel]
        base = dict(meta_cat.get(cat, {"titolo": cat}))
        base["prodotti"] = [{k: v for k, v in a.items() if k not in CAMPI_CATALOGO} for a in sel]
        nuove_cat.append(base)
        prec = {i for u in storico["uscite"] if u["data"] < oggi for i in u["categorie"].get(cat, [])}
        print(f"\n## {cat}")
        for a in sel:
            tag = "FISSO   " if a.get("fisso") else ("NUOVO   " if a["id"] not in prec else "RITORNA ")
            promo = f" (promo {a.get('sconto_sito')})" if a.get("prezzo_rif") else ""
            print(f"  {tag} {a.get('tipo', ''):<14} {a['nome'][:50]} {a['prezzo']:.2f} €{promo}")
    if problemi:
        for p in problemi:
            print("ERRORE:", p)
        raise SystemExit("data/prodotti.json NON aggiornato")
    prodotti["categorie"] = nuove_cat
    d = dt.date.fromisoformat(oggi)
    prodotti["data_verifica"] = d.strftime("%d/%m/%Y")
    salva_json(PRODOTTI, prodotti)
    storico["uscite"] = [u for u in storico["uscite"] if u["data"] != oggi]
    storico["uscite"].append({"data": oggi, "categorie": uscita})
    storico["uscite"].sort(key=lambda u: u["data"])
    salva_json(STORICO, storico)
    print("\ndata/prodotti.json e data/storico_uscite.json aggiornati. "
          "Controllare i sottotitoli delle categorie (devono descrivere solo i tipi presenti).")


def cmd_stato(args):
    catalogo, storico = carica_json(CATALOGO), carica_json(STORICO, {"uscite": []})
    for cat, articoli in catalogo["categorie"].items():
        ok = sum(a.get("stato") == "ok" for a in articoli)
        esc = sum(a.get("stato") == "escluso" for a in articoli)
        dc = sum(not completo(a) for a in articoli)
        print(f"\n## {cat}: {len(articoli)} articoli, {sum(bool(a.get('fisso')) for a in articoli)} fissi, "
              f"{ok} ok, {esc} esclusi, {dc} da completare")
        for a in articoli:
            date = uscite_articolo(storico, cat, a["id"])
            print(f"  {'F' if a.get('fisso') else ' '} {riga(a)}  ultima uscita: {date[-1] if date else '-'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    oggi = dt.date.today().isoformat()
    p = sub.add_parser("proponi")
    p.add_argument("--data", default=oggi)
    p.add_argument("--riserve", type=int, default=3)
    p = sub.add_parser("aggiorna")
    p.add_argument("pagine", nargs="+")
    p.add_argument("--data", default=oggi)
    p = sub.add_parser("applica")
    p.add_argument("--data", default=oggi)
    sub.add_parser("stato")
    args = ap.parse_args()
    {"proponi": cmd_proponi, "aggiorna": cmd_aggiorna, "applica": cmd_applica, "stato": cmd_stato}[args.cmd](args)


if __name__ == "__main__":
    main()
