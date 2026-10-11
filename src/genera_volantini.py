"""Generatore volantini Horeca METRO Mercato Online.

Da data/prodotti.json + config.json produce, per ogni categoria (max 6 referenze):
  - output/pdf/Volantino_METRO_<Categoria>.pdf          A4, link cliccabili e QR code
  - output/whatsapp/<Categoria>/00_copertina.jpg        1080x1920 (9:16, anche per lo Stato)
  - output/whatsapp/<Categoria>/01..06_<prodotto>.jpg   1080x1350 (4:5), una scheda per prodotto
  - output/whatsapp/<Categoria>/messaggio.txt           testo da incollare, con i link
  - output/whatsapp/WhatsApp_<Categoria>.zip            tutto il kit WhatsApp della categoria

Grafica in HTML/CSS (font Lato e colori del sito metro.it) convertita con Chromium (Playwright).

Uso:
    python src/genera_volantini.py [--prodotti data/prodotti.json] [--out output] [--solo-pdf]
"""

import argparse
import base64
import html
import io
import json
import os
import re
import shutil
import urllib.parse
import urllib.request
import zipfile

import qrcode
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMIUM = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
MAX_REFERENZE = 6

# Colori rilevati sul sito metro.it/marketplace
NAVY = "#002D72"      # blu primario (testi, header, prezzo pieno)
BLUE = "#0064FE"      # pulsanti ("Aggiungi al carrello")
RED = "#ED003B"       # prezzo in promozione (classe text-metro-red)
YELLOW = "#FFE500"    # logo
BG = "#F2F5F8"
GREY = "#5A6F94"
EEC_COLORI = {"A": "#00A651", "B": "#50B848", "C": "#BFD730", "D": "#FFF200",
              "E": "#FDB913", "F": "#F37021", "G": "#ED1C24"}


# ---------------------------------------------------------------- utilità
def euro(v):
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def esc(t):
    return html.escape(str(t), quote=True)


def slug(t):
    return re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")


def con_utm(url, cfg, categoria, medium):
    utm = cfg.get("utm") or {}
    if not utm:
        return url
    parti = urllib.parse.urlsplit(url)
    q = dict(urllib.parse.parse_qsl(parti.query))
    q.update({"utm_source": utm.get("source", "whatsapp"), "utm_medium": medium,
              "utm_campaign": utm.get("campaign", "horeca"),
              "utm_content": re.sub(r"[^a-z0-9]+", "-", categoria.lower()).strip("-")})
    return urllib.parse.urlunsplit(parti._replace(query=urllib.parse.urlencode(q)))


def qr_uri(url):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color=NAVY, back_color="white").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def foto(prod):
    """Scarica (una volta) la foto ufficiale e restituisce l'URI file:// del JPEG locale."""
    src = prod.get("immagine")
    m = re.search(r"item_image/([0-9a-f-]{36})", src or "")
    if not m:
        return ""
    path = os.path.join(ROOT, "assets", "img", f"{m.group(1)}.jpg")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        img = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=30).read()))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            sfondo = Image.new("RGB", img.size, "white")
            sfondo.paste(img, mask=img.split()[-1])
            img = sfondo
        img.convert("RGB").save(path, "JPEG", quality=90)
    return "file://" + path


def logo_svg(altezza):
    svg = open(os.path.join(ROOT, "assets", "brand", "metro_logo.svg"), encoding="utf-8").read()
    return svg.replace('width="152" height="28"', f'height="{altezza}" style="display:block"')


def css_base():
    f = os.path.join(ROOT, "assets", "fonts")
    return f"""
@font-face {{ font-family: Lato; font-weight: 400; src: url('file://{f}/Lato-Regular.ttf'); }}
@font-face {{ font-family: Lato; font-weight: 700; src: url('file://{f}/Lato-Bold.ttf'); }}
@font-face {{ font-family: Lato; font-weight: 900; src: url('file://{f}/Lato-Black.ttf'); }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ font-family: Lato, sans-serif; color: {NAVY}; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
a {{ color: inherit; text-decoration: none; }}
.promo {{ color: {RED}; }} .pieno {{ color: {NAVY}; }} .grey {{ color: {GREY}; }}
.disc {{ background: {RED}; color: #fff; font-weight: 900; border-radius: 4px; }}
.lim {{ background: #FFF0E0; color: #B04A00; font-weight: 700; border-radius: 4px; }}
.eec {{ font-weight: 900; display: inline-flex; align-items: center;
        clip-path: polygon(0 0, 76% 0, 100% 50%, 76% 100%, 0 100%); }}
.stars {{ color: #FFB400; letter-spacing: .06em; }}
.btn {{ background: {BLUE}; color: #fff; font-weight: 700; border-radius: 6px; text-align: center; }}
ul.punti {{ list-style: none; color: #1F3B6B; line-height: 1.3; }}
ul.punti li {{ position: relative; padding-left: 1.35em; margin-bottom: .2em; }}
ul.punti li::before {{ content: ""; position: absolute; left: .25em; top: .12em; width: .32em; height: .65em;
                      border: solid {BLUE}; border-width: 0 .14em .14em 0; transform: rotate(45deg); }}
"""


ICONA_CAMION = ('<svg viewBox="0 0 24 24" width="1.15em" height="1.15em" fill="none" stroke="#002D72" stroke-width="1.8" '
                'stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-0.22em">'
                '<path d="M3 6h11v9H3z"/><path d="M14 9h4l3 3v3h-7z"/><circle cx="7" cy="17" r="1.8"/>'
                '<circle cx="17" cy="17" r="1.8"/></svg>')
ICONA_NEGOZIO = ('<svg viewBox="0 0 24 24" width="1.15em" height="1.15em" fill="none" stroke="#002D72" stroke-width="1.8" '
                 'stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-0.22em">'
                 '<path d="M4 9l1.5-5h13L20 9"/><path d="M4 9h16v2a2.5 2.5 0 0 1-5 0 2.5 2.5 0 0 1-5 0 2.5 2.5 0 0 1-5 0z"/>'
                 '<path d="M5 13v7h14v-7"/></svg>')
ICONA_QTA = ('<svg viewBox="0 0 24 24" width="1.15em" height="1.15em" fill="none" stroke="#002D72" stroke-width="1.8" '
             'stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-0.22em">'
             '<path d="M3 8l9-5 9 5-9 5z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/></svg>')


def stelle(media):
    piene = int(round(media))
    return "★" * piene + '<span style="color:#D5DCE6">' + "★" * (5 - piene) + "</span>"


def mostra_valutazione(p):
    """Recensioni mostrate solo se positive e su un campione minimo (media >= 4 e almeno 3 recensioni)."""
    v = p.get("valutazione")
    return bool(v) and v["media"] >= 4.0 and v["recensioni"] >= 3


# ---------------------------------------------------------------- blocchi comuni (dimensioni in px)
def blocco_valutazione(p, fs):
    if not mostra_valutazione(p):
        return ""
    v = p["valutazione"]
    return (f'<div style="font-size:{fs}px;margin-top:.3em"><span class="stars">{stelle(v["media"])}</span> '
            f'<span class="grey">{str(v["media"]).replace(".", ",")} ({v["recensioni"]} recensioni)</span></div>')


def blocco_prezzo(p, fs):
    """Prezzo come sul sito: rosso se in promo, blu se prezzo pieno. fs = corpo del prezzo in px."""
    promo = p.get("prezzo_rif") is not None
    out = (f'<div style="display:flex;align-items:baseline;gap:{0.15*fs}px;white-space:nowrap">'
           f'<span class="{"promo" if promo else "pieno"}" style="font-size:{fs}px;font-weight:900;line-height:1">'
           f'{euro(p["prezzo"])}</span><span class="grey" style="font-size:{0.4*fs}px">+ IVA</span></div>')
    if promo:
        barrato = p["etichetta_rif"].startswith("Prezzo più basso")
        rif = f'<s>{euro(p["prezzo_rif"])}</s>' if barrato else euro(p["prezzo_rif"])
        out += (f'<div class="grey" style="font-size:{0.38*fs}px;margin-top:{0.12*fs}px">{esc(p["etichetta_rif"])}: '
                f'{rif} <b class="promo">{esc(p["sconto_sito"])}</b></div>')
    return out


def righe_info(p, fs, quantita=True):
    righe = []
    v = p.get("sconto_quantita")
    if quantita and v:
        righe.append(f'{ICONA_QTA} Da {v["da"]} pz: <b>{euro(v["prezzo"])}</b> cad. <b class="promo">({esc(v["risparmio"])})</b>')
    righe.append(f'{ICONA_NEGOZIO} Venduto da: <b>{esc(p.get("venditore") or "—")}</b>')
    c = p.get("consegna") or {}
    costo = "spedizione gratuita" if c.get("costo") == "gratuita" else (f'spedizione {c["costo"]}' if c.get("costo") else "")
    gg = f'consegna in {c["giorni"]} gg lav.' if c.get("giorni") else ""
    testo = " · ".join(x for x in (gg, costo) if x)
    if testo:
        righe.append(f'{ICONA_CAMION} {testo[0].upper() + testo[1:]}')
    return "".join(f'<div style="font-size:{fs}px;line-height:1.5;white-space:nowrap">{r}</div>' for r in righe)


def badge_foto(p, fs):
    out = ""
    if p.get("prezzo_rif") is not None:
        out += (f'<div class="disc" style="position:absolute;top:0;left:0;font-size:{fs}px;'
                f'padding:.15em .45em">{esc(p["sconto_sito"])}</div>')
    if p.get("classe_energetica"):
        k = p["classe_energetica"]
        col = EEC_COLORI.get(k[0], "#999")
        fg = NAVY if k[0] in "CD" else "#fff"
        out += (f'<div class="eec" style="position:absolute;top:0;right:0;background:{col};color:{fg};'
                f'font-size:{0.85*fs}px;padding:.12em .9em .12em .45em">{esc(k)}</div>')
    if p.get("disponibilita_limitata"):
        out += (f'<div class="lim" style="position:absolute;bottom:0;left:0;font-size:{0.72*fs}px;'
                f'padding:.15em .45em">Disponibilità limitata</div>')
    return out


def lista_punti(p, fs, n=3):
    li = "".join(f"<li>{esc(x)}</li>" for x in p.get("punti", [])[:n])
    return f'<ul class="punti" style="font-size:{fs}px">{li}</ul>'


# ---------------------------------------------------------------- A4 (794 x 1123 px)
def html_a4(cat, cfg, data):
    cards = ""
    for p in cat["prodotti"][:MAX_REFERENZE]:
        url = con_utm(p["url"], cfg, cat["titolo"], "volantino-pdf")
        cards += f"""
<div class="card">
  <a href="{esc(url)}" class="foto"><img src="{foto(p)}">{badge_foto(p, 12)}</a>
  <div class="brand">{esc(p.get("marca", ""))}</div>
  <a href="{esc(url)}" class="nome">{esc(p["nome"])}</a>
  {blocco_valutazione(p, 10.5)}
  <div style="margin-top:7px">{lista_punti(p, 10.8)}</div>
  <div style="flex:1"></div>
  <div class="sep"></div>
  {blocco_prezzo(p, 25)}
  <div style="margin-top:5px">{righe_info(p, 10.2)}</div>
  <div class="cta">
    <a class="btn" href="{esc(url)}">Acquista online ›</a>
    <a href="{esc(url)}" class="qr"><img src="{qr_uri(url)}"><span>Inquadra</span></a>
  </div>
</div>"""
    url_cat = con_utm(cat.get("url_categoria", "https://www.metro.it/marketplace"), cfg, cat["titolo"], "volantino-pdf")
    nota = esc(cfg["note_legali"].format(data=data))
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{css_base()}
@page {{ size: A4; margin: 0; }}
body {{ width: 794px; height: 1123px; overflow: hidden; background: {BG}; display: flex; flex-direction: column; }}
.top {{ background: {NAVY}; height: 50px; padding: 0 26px; display: flex; align-items: center; justify-content: space-between; flex: none; }}
.top .mo {{ color: #fff; font-weight: 700; font-size: 14px; border-left: 1px solid rgba(255,255,255,.35); padding-left: 12px; margin-left: 12px; }}
.top .url {{ color: #fff; opacity: .85; font-size: 12px; }}
.hero {{ background: #fff; padding: 12px 26px; border-bottom: 1px solid #DCE3EC; display: flex; justify-content: space-between; align-items: flex-end; flex: none; }}
.bc {{ color: {BLUE}; font-size: 11px; }}
h1 {{ font-size: 34px; font-weight: 900; line-height: 1.1; margin-top: 2px; }}
.sub {{ font-size: 13px; color: #33578E; margin-top: 2px; max-width: 470px; }}
.chip {{ background: #E6F0FF; border-radius: 20px; padding: 6px 13px; font-size: 12px; font-weight: 700; white-space: nowrap; text-align: center; }}
.agg {{ font-size: 10.5px; color: {GREY}; margin-top: 6px; text-align: right; }}
.grid {{ flex: 1; display: grid; grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(2, 1fr);
         gap: 11px; padding: 12px 18px 6px; min-height: 0; }}
.card {{ background: #fff; border: 1px solid #DCE3EC; border-radius: 10px; padding: 10px 12px;
         display: flex; flex-direction: column; min-height: 0; overflow: hidden; }}
.foto {{ position: relative; height: 116px; flex: none; display: flex; align-items: center; justify-content: center; }}
.foto img {{ max-height: 112px; max-width: 100%; object-fit: contain; }}
.brand {{ font-size: 9.5px; letter-spacing: .5px; color: {GREY}; margin-top: 8px; text-transform: uppercase; }}
.nome {{ font-size: 13px; font-weight: 700; line-height: 1.25; margin-top: 2px; display: -webkit-box;
         -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 32px; }}
.sep {{ border-top: 1px solid #E8EDF3; margin: 6px 0 7px; }}
.cta {{ display: flex; align-items: center; gap: 8px; margin-top: 7px; }}
.cta .btn {{ flex: 1; font-size: 13px; padding: 9px 4px; }}
.qr {{ display: flex; flex-direction: column; align-items: center; }}
.qr img {{ width: 52px; height: 52px; }}
.qr span {{ font-size: 8px; color: {GREY}; }}
.legal {{ font-size: 8.6px; color: {GREY}; padding: 0 20px 6px; line-height: 1.35; flex: none; }}
.bottom {{ background: {NAVY}; color: #fff; padding: 12px 26px; display: flex; align-items: center; justify-content: space-between; flex: none; }}
.bottom .t1 {{ font-size: 12px; font-weight: 700; color: {YELLOW}; }}
.bottom .t2 {{ font-size: 14px; font-weight: 700; margin-top: 1px; }}
.bottom .out {{ border: 1.5px solid #fff; border-radius: 6px; padding: 8px 14px; font-size: 12.5px; font-weight: 700; }}
</style></head><body>
<div class="top"><div style="display:flex;align-items:center">{logo_svg(22)}<span class="mo">Mercato Online</span></div>
  <span class="url">metro.it/marketplace</span></div>
<div class="hero">
  <div><div class="bc">Mercato Online › {esc(cat["titolo"])}</div><h1>{esc(cat["titolo"])}</h1>
       <div class="sub">{esc(cat.get("sottotitolo", ""))}</div></div>
  <div><div class="chip">★ I preferiti dai nostri clienti</div><div class="agg">Prezzi IVA esclusa · verificati il {esc(data)}</div></div>
</div>
<div class="grid">{cards}</div>
<div class="legal">{nota}</div>
<div class="bottom"><div><div class="t1">{esc(cfg["footer_titolo"])}</div><div class="t2">{esc(cfg["footer_testo"])}</div></div>
  <a class="out" href="{esc(url_cat)}">Vedi tutta la categoria ›</a></div>
</body></html>"""


# ---------------------------------------------------------------- WhatsApp
def html_wa_scheda(cat, cfg, p, n, tot):
    """Scheda prodotto 1080 x 1350 (4:5)."""
    url = con_utm(p["url"], cfg, cat["titolo"], "whatsapp-immagine")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{css_base()}
body {{ width: 1080px; height: 1350px; overflow: hidden; background: #fff; display: flex; flex-direction: column; }}
.top {{ background: {NAVY}; height: 108px; padding: 0 50px; display: flex; align-items: center; justify-content: space-between; flex: none; }}
.top .mo {{ color: #fff; font-weight: 700; font-size: 30px; border-left: 2px solid rgba(255,255,255,.35); padding-left: 22px; margin-left: 22px; }}
.top .cat {{ color: {NAVY}; background: #fff; border-radius: 40px; padding: 10px 26px; font-size: 26px; font-weight: 700; }}
.foto {{ position: relative; height: 470px; margin: 26px 50px 0; flex: none; display: flex; align-items: center; justify-content: center; }}
.foto img {{ max-height: 460px; max-width: 100%; object-fit: contain; }}
.corpo {{ flex: 1; padding: 16px 60px 0; display: flex; flex-direction: column; min-height: 0; }}
.brand {{ font-size: 24px; letter-spacing: 1px; color: {GREY}; text-transform: uppercase; }}
.nome {{ font-size: 44px; font-weight: 900; line-height: 1.15; margin-top: 4px; display: -webkit-box; -webkit-line-clamp: 2;
         -webkit-box-orient: vertical; overflow: hidden; }}
.info {{ background: {BG}; border-radius: 14px; padding: 14px 22px; margin: 16px 0 24px; }}
.bar {{ background: {BLUE}; color: #fff; height: 128px; padding: 0 50px; display: flex; align-items: center; justify-content: space-between; flex: none; }}
.bar .t1 {{ font-size: 40px; font-weight: 900; }} .bar .t2 {{ font-size: 25px; opacity: .95; margin-top: 2px; }}
.bar img {{ width: 104px; height: 104px; background: #fff; padding: 6px; border-radius: 10px; }}
</style></head><body>
<div class="top"><div style="display:flex;align-items:center">{logo_svg(42)}<span class="mo">Mercato Online</span></div>
  <span class="cat">{esc(cat["titolo"])} · {n}/{tot}</span></div>
<div class="foto"><img src="{foto(p)}">{badge_foto(p, 34)}</div>
<div class="corpo">
  <div class="brand">{esc(p.get("marca", ""))}</div>
  <div class="nome">{esc(p["nome"])}</div>
  {blocco_valutazione(p, 28)}
  <div style="margin-top:16px">{lista_punti(p, 31)}</div>
  <div style="flex:1"></div>
  <div>{blocco_prezzo(p, 84)}</div>
  <div class="info">{righe_info(p, 27)}</div>
</div>
<div class="bar"><div><div class="t1">Acquista online su metro.it</div>
  <div class="t2">Il link diretto è nel messaggio · oppure inquadra il QR</div></div>
  <img src="{qr_uri(url)}"></div>
</body></html>"""


def html_wa_copertina(cat, cfg, data):
    """Copertina 1080 x 1920 (9:16): panoramica dei 6 prodotti, adatta anche allo Stato WhatsApp."""
    tiles = ""
    for p in cat["prodotti"][:MAX_REFERENZE]:
        promo = p.get("prezzo_rif") is not None
        disc = (f'<div class="disc" style="position:absolute;top:0;left:0;font-size:30px;padding:4px 14px">'
                f'{esc(p["sconto_sito"])}</div>') if promo else ""
        tiles += f"""<div class="t"><div class="f"><img src="{foto(p)}">{disc}</div>
  <div class="n">{esc(p["nome"])}</div>
  <div class="p {'promo' if promo else 'pieno'}">{euro(p["prezzo"])}<span class="grey"> + IVA</span></div></div>"""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{css_base()}
body {{ width: 1080px; height: 1920px; overflow: hidden; background: {BG}; display: flex; flex-direction: column; }}
.head {{ background: {NAVY}; color: #fff; padding: 120px 60px 40px; flex: none; }}
.head .mo {{ font-weight: 700; font-size: 34px; border-left: 2px solid rgba(255,255,255,.35); padding-left: 24px; margin-left: 24px; }}
h1 {{ font-size: 108px; font-weight: 900; line-height: 1; margin-top: 36px; }}
.chip {{ display: inline-block; margin-top: 24px; background: {YELLOW}; color: {NAVY}; border-radius: 50px; padding: 12px 30px;
         font-size: 32px; font-weight: 900; }}
.grid {{ flex: 1; display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: repeat(3, 1fr); gap: 24px; padding: 30px 40px; min-height: 0; }}
.t {{ background: #fff; border-radius: 24px; padding: 18px 22px 20px; display: flex; flex-direction: column; min-height: 0; border: 2px solid #DCE3EC; }}
.f {{ position: relative; flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; }}
.f img {{ max-height: 100%; max-width: 100%; object-fit: contain; }}
.n {{ font-size: 28px; font-weight: 700; line-height: 1.2; margin-top: 10px; display: -webkit-box; -webkit-line-clamp: 2;
      -webkit-box-orient: vertical; overflow: hidden; min-height: 67px; }}
.p {{ font-size: 50px; font-weight: 900; margin-top: 6px; }} .p span {{ font-size: 24px; font-weight: 400; }}
.foot {{ background: {NAVY}; color: #fff; padding: 32px 60px 140px; flex: none; }}
.foot .t1 {{ font-size: 36px; font-weight: 900; color: {YELLOW}; }}
.foot .t2 {{ font-size: 27px; margin-top: 10px; line-height: 1.35; }}
</style></head><body>
<div class="head"><div style="display:flex;align-items:center">{logo_svg(56)}<span class="mo">Mercato Online</span></div>
  <h1>{esc(cat["titolo"])}</h1><div class="chip">★ I preferiti dai nostri clienti</div></div>
<div class="grid">{tiles}</div>
<div class="foot"><div class="t1">Dettagli e link per acquistare nei messaggi seguenti</div>
  <div class="t2">Prezzi IVA esclusa verificati su metro.it il {esc(data)}.<br>{esc(cfg["footer_testo"])}</div></div>
</body></html>"""


def messaggio(cat, cfg, data):
    """Testo WhatsApp (formattazione *grassetto* e ~barrato~) con i link cliccabili."""
    num = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    righe = [f"*METRO Mercato Online · {cat['titolo']}*",
             f"I preferiti dai nostri clienti, prezzi IVA esclusa verificati su metro.it il {data}.", ""]
    for i, p in enumerate(cat["prodotti"][:MAX_REFERENZE]):
        prezzo = f"*{euro(p['prezzo'])}* + IVA"
        if p.get("prezzo_rif") is not None:
            rif = euro(p["prezzo_rif"])
            if p["etichetta_rif"].startswith("Prezzo più basso"):
                rif = f"~{rif}~"
            prezzo += f" ({p['etichetta_rif'].lower()}: {rif} {p['sconto_sito']})"
        righe += [f"{num[i]} *{p['nome']}*", f"{prezzo} · venduto da {p.get('venditore') or '—'}",
                  f"👉 {con_utm(p['url'], cfg, cat['titolo'], 'whatsapp-messaggio')}", ""]
    righe.append(f"Per informazioni o un preventivo {cfg['footer_testo'][0].lower() + cfg['footer_testo'][1:]}")
    return "\n".join(righe) + "\n"


ISTRUZIONI = """COME INVIARE IL VOLANTINO SU WHATSAPP

1. Apri la chat del cliente, tocca + (o la graffetta) > Foto e video.
2. Seleziona nell'ordine 00_copertina e le 6 schede prodotto: WhatsApp le invia come un unico album.
3. Prima di inviare tocca "HD" in alto: WhatsApp comprime meno le immagini e i prezzi restano nitidi.
4. Subito dopo incolla il testo di messaggio.txt: contiene i link diretti a ogni prodotto
   (nelle immagini i link non sono cliccabili, nel testo sì).
5. Facoltativo: pubblica 00_copertina come Stato (formato 9:16).
6. Il PDF A4 resta disponibile per chi preferisce stamparlo o riceverlo via e-mail
   (su WhatsApp il PDF va aperto e scaricato prima di essere visto).
"""


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    ap.add_argument("--prodotti", default=os.path.join(ROOT, "data", "prodotti.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "output"))
    ap.add_argument("--solo-pdf", action="store_true")
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    dati = json.load(open(args.prodotti, encoding="utf-8"))
    data = dati.get("data_verifica", "")
    out_pdf = os.path.join(args.out, "pdf")
    out_wa = os.path.join(args.out, "whatsapp")
    tmp = os.path.join(args.out, ".html")
    for d in (out_pdf, out_wa, tmp):
        os.makedirs(d, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page()

        def carica(nome, contenuto, w, h):
            f = os.path.join(tmp, nome)
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(contenuto)
            page.set_viewport_size({"width": w, "height": h})
            page.goto("file://" + f, wait_until="load")
            page.evaluate("document.fonts.ready")

        for cat in dati["categorie"]:
            nome = slug(cat["titolo"])
            carica(f"{nome}_a4.html", html_a4(cat, cfg, data), 794, 1123)
            pdf = os.path.join(out_pdf, f"Volantino_METRO_{nome}.pdf")
            page.pdf(path=pdf, width="210mm", height="297mm", print_background=True, page_ranges="1")
            print("Creato", os.path.relpath(pdf, ROOT))
            if args.solo_pdf:
                continue

            cartella = os.path.join(out_wa, nome)
            shutil.rmtree(cartella, ignore_errors=True)
            os.makedirs(cartella)
            carica(f"{nome}_cop.html", html_wa_copertina(cat, cfg, data), 1080, 1920)
            page.screenshot(path=os.path.join(cartella, "00_copertina.jpg"), type="jpeg", quality=90)
            prodotti = cat["prodotti"][:MAX_REFERENZE]
            for i, p in enumerate(prodotti, 1):
                carica(f"{nome}_{i}.html", html_wa_scheda(cat, cfg, p, i, len(prodotti)), 1080, 1350)
                page.screenshot(path=os.path.join(cartella, f"{i:02d}_{slug(p['nome'])[:40].rstrip('_')}.jpg"),
                                type="jpeg", quality=90)
            with open(os.path.join(cartella, "messaggio.txt"), "w", encoding="utf-8") as fh:
                fh.write(messaggio(cat, cfg, data))
            with open(os.path.join(cartella, "COME_INVIARE.txt"), "w", encoding="utf-8") as fh:
                fh.write(ISTRUZIONI)
            z = os.path.join(out_wa, f"WhatsApp_{nome}.zip")
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(os.listdir(cartella)):
                    zf.write(os.path.join(cartella, f), os.path.join(nome, f))
            print("Creato", os.path.relpath(z, ROOT))
        browser.close()
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
