"""Generatore volantini Horeca METRO Mercato Online.

Da data/prodotti.json + config.json produce, per ogni categoria (max 6 referenze):
  - output/PDF_A4/Volantino_METRO_<Categoria>_A4.pdf              A4, pulsanti cliccabili e QR code
  - output/PDF_WhatsApp/Volantino_METRO_<Categoria>_WhatsApp.pdf  smartphone 9:16: 1 pagina per
                                                                   prodotto con pulsante "Acquista online"
  - output/Testi_WhatsApp/Messaggio_<Categoria>.txt               testo facoltativo con i link
e il pacchetto unico output/Volantini_METRO_Horeca.zip.

Grafica in HTML/CSS (font Lato e colori del sito metro.it) convertita con Chromium (Playwright).

Uso:
    python src/genera_volantini.py [--prodotti data/prodotti.json] [--out output]
"""

import argparse
import base64
import glob
import html
import io
import json
import os
import re
import shutil
import tempfile
import unicodedata
import urllib.parse
import urllib.request
import zipfile

import qrcode
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def trova_chromium():
    """Percorso di Chromium: CHROMIUM_PATH, altrimenti la versione più recente in /opt/pw-browsers,
    altrimenti None (Chromium gestito da Playwright)."""
    env = os.environ.get("CHROMIUM_PATH")
    if env and os.path.exists(env):
        return env
    candidati = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"),
                       key=lambda x: int(re.search(r"chromium-(\d+)", x).group(1)), reverse=True)
    return candidati[0] if candidati else None
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


UNITA = r"(?:L|l|cm|mm|m|W|kW|V|bar|kg|g|pz|gg|°C|°|%|x|lame|camer[ae]|port[ae]|vasc(?:a|he)|cest[oi]|pizze|zone)"


def nbsp(t):
    """Evita gli a capo tra numero e unità ("130 L", "50 x 50 cm", "2 camere"): spazi non separabili."""
    t = str(t)
    t = re.sub(r"(\d) (?=" + UNITA + r"\b)", "\\1\u00a0", t)
    t = re.sub(r"(\d)\u00a0x (?=\d)", "\\1\u00a0x\u00a0", t)
    return t


def esc_nb(t):
    return esc(nbsp(t))


def slug(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()  # caffè -> caffe
    return re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")


def con_utm(url, cfg, categoria, medium, contenuto=True):
    utm = cfg.get("utm") or {}
    if not utm:
        return url
    parti = urllib.parse.urlsplit(url)
    q = dict(urllib.parse.parse_qsl(parti.query))
    q.update({"utm_source": utm.get("source", "whatsapp"), "utm_medium": medium,
              "utm_campaign": utm.get("campaign", "horeca")})
    if contenuto:
        q["utm_content"] = re.sub(r"[^a-z0-9]+", "-", categoria.lower()).strip("-")
    return urllib.parse.urlunsplit(parti._replace(query=urllib.parse.urlencode(q)))


def qr_uri(url):
    """QR del link (versione bassa = moduli più grandi e lettura più facile da stampa e da schermo)."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=1)
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
    return "file://" + foto_ottimizzata(path)


def foto_ottimizzata(path, lato_max=900, qualita=82):
    """Copia più leggera della foto per l'inserimento nel PDF (stessa resa a schermo e in stampa)."""
    dest_dir = os.path.join(tempfile.gettempdir(), "volantini_foto")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"{os.path.splitext(os.path.basename(path))[0]}_{lato_max}_{qualita}.jpg")
    if not os.path.exists(dest):
        img = Image.open(path).convert("RGB")
        img.thumbnail((lato_max, lato_max))
        img.save(dest, "JPEG", quality=qualita, optimize=True, progressive=True)
    return dest


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
    return "".join(f'<div style="font-size:{fs}px;line-height:1.45;white-space:nowrap">{r}</div>' for r in righe)


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
    li = "".join(f"<li>{esc_nb(x)}</li>" for x in p.get("punti", [])[:n])
    return f'<ul class="punti" style="font-size:{fs}px">{li}</ul>'


# ---------------------------------------------------------------- A4 (794 x 1123 px)
def html_a4(cat, cfg, data):
    cards = ""
    prodotti = cat["prodotti"][:MAX_REFERENZE]
    righe_con_stelle = {i // 3 for i, p in enumerate(prodotti) if mostra_valutazione(p)}
    for i, p in enumerate(prodotti):
        stelle_a4 = blocco_valutazione(p, 10.5) or (
            '<div style="font-size:10.5px;margin-top:.3em">&nbsp;</div>' if i // 3 in righe_con_stelle else "")
        url = con_utm(p["url"], cfg, cat["titolo"], "volantino-pdf")
        url_qr = con_utm(p["url"], cfg, cat["titolo"], "a4-qr", contenuto=False)
        cards += f"""
<div class="card">
  <div class="foto"><img src="{foto(p)}" alt="{esc(p["nome"])}">{badge_foto(p, 12)}</div>
  <div class="brand">{esc(p.get("marca", ""))}</div>
  <div class="nome">{esc_nb(p["nome"])}</div>
  {stelle_a4}
  <div style="margin-top:7px" class="punti-a4">{lista_punti(p, 10.8)}</div>
  <div class="sep"></div>
  {blocco_prezzo(p, 25)}
  <div style="margin-top:5px">{righe_info(p, 10.2)}</div>
  <div style="flex:1"></div>
  <div class="cta">
    <a class="btn" href="{esc(url)}">Acquista online ›</a>
    <a href="{esc(url)}" class="qr"><img src="{qr_uri(url_qr)}" alt="QR code"><span>Inquadra</span></a>
  </div>
</div>"""
    nota = esc(cfg["note_legali"].format(data=data))
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>Volantino METRO {esc(cat["titolo"])} – Mercato Online</title><style>{css_base()}
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
         gap: 9px; padding: 8px 18px 4px; min-height: 0; }}
.card {{ background: #fff; border: 1px solid #DCE3EC; border-radius: 10px; padding: 9px 12px 6px;
         display: flex; flex-direction: column; min-height: 0; overflow: hidden; }}
.foto {{ position: relative; height: 92px; flex: none; display: flex; align-items: center; justify-content: center; }}
.foto img {{ max-height: 90px; max-width: 100%; object-fit: contain; }}
.brand {{ font-size: 9.5px; letter-spacing: .5px; color: {GREY}; margin-top: 6px; text-transform: uppercase; }}
.nome {{ font-size: 13px; font-weight: 700; line-height: 1.25; margin-top: 2px; display: -webkit-box;
         -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 32px; }}
.sep {{ border-top: 1px solid #E8EDF3; margin: 6px 0 7px; }}
.punti-a4 {{ min-height: 52px; }}
.cta {{ display: flex; align-items: center; gap: 10px; margin-top: 4px; }}
.cta .btn {{ flex: 1; font-size: 13px; padding: 11px 4px; }}
.qr {{ display: flex; flex-direction: column; align-items: center; }}
.qr img {{ width: 76px; height: 76px; }}
.qr span {{ font-size: 8px; line-height: 1; margin-top: 1px; color: {GREY}; }}
.legal {{ font-size: 8.6px; color: {GREY}; padding: 0 20px 6px; line-height: 1.35; flex: none; }}
.bottom {{ background: {NAVY}; color: #fff; padding: 12px 26px; display: flex; align-items: center; justify-content: space-between; flex: none; }}
.bottom .t1 {{ font-size: 12px; font-weight: 700; color: {YELLOW}; }}
.bottom .t2 {{ font-size: 14px; font-weight: 700; margin-top: 1px; }}
.bottom .out {{ font-size: 12.5px; font-weight: 700; }}
</style></head><body>
<div class="top"><div style="display:flex;align-items:center">{logo_svg(22)}<span class="mo">Mercato Online</span></div>
  <span class="url">metro.it/marketplace</span></div>
<div class="hero">
  <div><div class="bc">Mercato Online › {esc(cat["titolo"])}</div><h1>{esc(cat["titolo"])}</h1>
       <div class="sub">{esc(cat.get("sottotitolo", ""))}</div></div>
  <div><div class="chip">★ Venduti direttamente da METRO</div><div class="agg">Prezzi IVA esclusa · verificati il {esc(data)}</div></div>
</div>
<div class="grid">{cards}</div>
<div class="legal">{nota}</div>
<div class="bottom"><div><div class="t1">{esc(cfg["footer_titolo"])}</div><div class="t2">{esc(cfg["footer_testo"])}</div></div>
  <div class="out">Vedi tutta la categoria su metro.it</div></div>
</body></html>"""


# ---------------------------------------------------------------- WhatsApp (PDF verticale 9:16, 1080 x 1920 px per pagina)
def html_wa_pdf(cat, cfg, data):
    """PDF da smartphone: una pagina per prodotto; gli unici link sono il pulsante "Acquista online"
    e il QR code."""
    prodotti = cat["prodotti"][:MAX_REFERENZE]
    tot = len(prodotti)
    nota = esc(cfg["note_legali"].format(data=data))

    schede = ""
    for i, p in enumerate(prodotti, 1):
        url = con_utm(p["url"], cfg, cat["titolo"], "whatsapp-pdf")
        url_qr = con_utm(p["url"], cfg, cat["titolo"], "wa-qr", contenuto=False)
        schede += f"""<section class="pag" id="p{i}">
<div class="top"><div class="riga">{logo_svg(42)}<span class="mo">Mercato Online</span></div>
  <span class="cat">{esc(cat["titolo"])} · {i}/{tot}</span></div>
<div class="foto"><img src="{foto(p)}" alt="{esc(p["nome"])}">{badge_foto(p, 36)}</div>
<div class="corpo">
  <div class="brand">{esc(p.get("marca", ""))}</div>
  <div class="nome">{esc_nb(p["nome"])}</div>
  {blocco_valutazione(p, 32)}
  <div style="margin-top:22px">{lista_punti(p, 36)}</div>
  <div style="flex:1"></div>
  <div style="margin-top:18px">{blocco_prezzo(p, 104)}</div>
  <div class="info">{righe_info(p, 31)}</div>
  <div class="cta"><a class="btn big" href="{esc(url)}">Acquista Online</a>
    <a class="qrw" href="{esc(url)}"><img src="{qr_uri(url_qr)}" alt="QR code"><span>Inquadra il QR</span></a></div>
</div>
<div class="fondo"><div class="t1">{esc(cfg["footer_titolo"])}</div><div class="t2">{esc(cfg["footer_testo"])}</div>
  <div class="legal">{nota}</div></div>
</section>"""

    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>Volantino METRO {esc(cat["titolo"])} – Mercato Online (smartphone)</title><style>{css_base()}
@page {{ size: 1080px 1920px; margin: 0; }}
body {{ width: 1080px; }}
.pag {{ width: 1080px; height: 1920px; overflow: hidden; display: flex; flex-direction: column; break-after: page; background: {BG}; }}
.pag:last-child {{ break-after: auto; }}
.riga {{ display: flex; align-items: center; }}
.mo {{ color: #fff; font-weight: 700; font-size: 32px; border-left: 2px solid rgba(255,255,255,.35); padding-left: 22px; margin-left: 22px; }}
.head {{ background: {NAVY}; color: #fff; padding: 60px 56px 36px; flex: none; }}
h1 {{ font-size: 100px; font-weight: 900; line-height: 1; margin-top: 34px; }}
.chip {{ display: inline-block; margin-top: 22px; background: {YELLOW}; color: {NAVY}; border-radius: 50px; padding: 10px 28px; font-size: 30px; font-weight: 900; }}
.sub {{ font-size: 28px; margin-top: 18px; opacity: .92; line-height: 1.3; }}
.grid {{ flex: 1; display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: repeat(3, 1fr); gap: 22px; padding: 26px 36px; min-height: 0; }}
.t {{ background: #fff; border-radius: 22px; padding: 16px 20px 18px; display: flex; flex-direction: column; min-height: 0; border: 2px solid #DCE3EC; }}
.f {{ position: relative; flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; }}
.f img {{ max-height: 100%; max-width: 100%; object-fit: contain; }}
.n {{ font-size: 26px; font-weight: 700; line-height: 1.2; margin-top: 8px; display: -webkit-box; -webkit-line-clamp: 2;
      -webkit-box-orient: vertical; overflow: hidden; min-height: 62px; }}
.pr {{ font-size: 46px; font-weight: 900; margin-top: 4px; }} .pr span {{ font-size: 22px; font-weight: 400; }}
.tb {{ display: flex; gap: 12px; margin-top: 10px; }}
.tb a {{ flex: 1; font-size: 26px; padding: 12px 0; border-radius: 10px; text-align: center; font-weight: 700; }}
.sec {{ border: 2px solid {BLUE}; color: {BLUE}; }}
.foot {{ background: {NAVY}; color: #fff; padding: 30px 56px 40px; flex: none; }}
.foot .t1 {{ font-size: 30px; font-weight: 900; color: {YELLOW}; }}
.foot .t2 {{ font-size: 24px; margin-top: 8px; opacity: .9; }}
.out {{ display: block; margin-top: 22px; border: 2px solid #fff; border-radius: 12px; padding: 18px; text-align: center; font-size: 30px; font-weight: 700; }}
/* scheda prodotto */
.top {{ background: {NAVY}; height: 120px; padding: 0 50px; display: flex; align-items: center; justify-content: space-between; flex: none; }}
.top .cat {{ color: {NAVY}; background: #fff; border-radius: 40px; padding: 10px 26px; font-size: 27px; font-weight: 700; }}
.foto {{ position: relative; height: 580px; min-height: 440px; margin: 28px 50px 0; flex: 0 1 auto; display: flex; align-items: center; justify-content: center;
         background: #fff; border-radius: 22px; padding: 24px; }}
.foto img {{ max-height: 100%; max-width: 100%; object-fit: contain; }}
.corpo {{ flex: 1 0 auto; padding: 24px 56px 0; display: flex; flex-direction: column; }}
.brand {{ font-size: 26px; letter-spacing: 1px; color: {GREY}; text-transform: uppercase; }}
.nome {{ font-size: 50px; font-weight: 900; line-height: 1.15; margin-top: 4px; display: -webkit-box; -webkit-line-clamp: 2;
         -webkit-box-orient: vertical; overflow: hidden; flex-shrink: 0; }}
.info {{ background: #fff; border-radius: 16px; padding: 16px 24px; margin: 18px 0 22px; border: 2px solid #DCE3EC; }}
.cta {{ display: flex; align-items: stretch; gap: 26px; margin-bottom: 30px; }}
.big {{ flex: 1; display: flex; flex-direction: column; justify-content: center; font-size: 66px; line-height: 1.1; border-radius: 16px; }}
.qrw {{ display: flex; flex-direction: column; align-items: center; background: #fff; border: 2px solid #DCE3EC; border-radius: 16px; padding: 12px 14px 8px; }}
.qrw img {{ width: 170px; height: 170px; }}
.qrw span {{ font-size: 20px; color: {GREY}; margin-top: 4px; }}
.fondo {{ background: {NAVY}; color: #fff; padding: 24px 56px 26px; flex: none; }}
.fondo .t1 {{ font-size: 24px; font-weight: 700; color: {YELLOW}; }}
.fondo .t2 {{ font-size: 30px; font-weight: 700; margin-top: 4px; }}
.fondo .legal {{ font-size: 19px; color: #D5DEEC; margin-top: 12px; line-height: 1.35; }}
</style></head><body>{schede}</body></html>"""


def messaggio(cat, cfg, data):
    """Testo d'accompagnamento facoltativo (formattazione WhatsApp), con i link cliccabili."""
    num = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    righe = [f"*METRO Mercato Online · {cat['titolo']}*",
             f"Ti invio una selezione di attrezzature professionali vendute direttamente da METRO (prezzi IVA esclusa verificati su metro.it il {data}).",
             "Nel PDF tocca *Acquista Online* per andare direttamente al prodotto.", ""]
    for i, p in enumerate(cat["prodotti"][:MAX_REFERENZE]):
        prezzo = f"*{euro(p['prezzo'])}* + IVA"
        if p.get("prezzo_rif") is not None:
            prezzo += f" ({p['sconto_sito']})"
        righe += [f"{num[i]} {p['nome']} · {prezzo}",
                  f"👉 {con_utm(p['url'], cfg, cat['titolo'], 'whatsapp-messaggio', contenuto=False)}", ""]
    righe.append(f"Per informazioni o un preventivo {cfg['footer_testo'][0].lower() + cfg['footer_testo'][1:]}")
    return "\n".join(righe) + "\n"


LEGGIMI = """VOLANTINI METRO MERCATO ONLINE - HORECA (prezzi verificati il {data})

PDF_A4/        5 volantini A4 (uno per categoria): pulsanti cliccabili e QR code.
               Per e-mail, stampa o per chi legge da computer.
PDF_WhatsApp/  5 volantini in formato smartphone (verticale 9:16), uno per categoria:
               una pagina per prodotto con il pulsante "Acquista online" e il QR code
Testi_WhatsApp/ testo facoltativo da incollare insieme al PDF (con i link diretti ai prodotti).

COME INVIARE SU WHATSAPP
1. Apri la chat del cliente, tocca + (o la graffetta) > Documento e scegli il PDF della categoria.
2. Aggiungi una riga di presentazione (o incolla il testo della cartella Testi_WhatsApp).
3. Il cliente apre il PDF sul telefono e tocca i pulsanti per acquistare online.
"""


# ---------------------------------------------------------------- controlli sui dati
SOGLIA_PREZZO = 290.0
MAX_PUNTO = 42


def controlla_dati(dati):
    """Controlli prima della generazione: errori bloccanti e avvisi (stampati a video)."""
    errori, avvisi, visti = [], [], {}
    for cat in dati["categorie"]:
        prodotti = cat["prodotti"]
        if len(prodotti) > MAX_REFERENZE:
            avvisi.append(f"{cat['titolo']}: {len(prodotti)} referenze, nel volantino ne entrano {MAX_REFERENZE}")
        for p in prodotti[:MAX_REFERENZE]:
            nome = f"{cat['titolo']} / {p.get('nome', '?')}"
            for campo in ("nome", "url", "prezzo", "immagine"):
                if not p.get(campo):
                    errori.append(f"{nome}: manca '{campo}'")
            if p.get("url") in visti:
                errori.append(f"{nome}: stesso link di {visti[p['url']]}")
            visti[p.get("url")] = nome
            if (p.get("venditore") or "").strip().upper() != "METRO":
                errori.append(f"{nome}: venditore '{p.get('venditore')}' (ammessi solo prodotti venduti da METRO)")
            if isinstance(p.get("prezzo"), (int, float)) and p["prezzo"] < SOGLIA_PREZZO:
                avvisi.append(f"{nome}: prezzo {euro(p['prezzo'])} sotto la soglia di {euro(SOGLIA_PREZZO)}")
            if p.get("prezzo_rif") is not None and not (p.get("etichetta_rif") and p.get("sconto_sito")):
                errori.append(f"{nome}: promo senza etichetta_rif/sconto_sito")
            punti = p.get("punti") or []
            if len(punti) < 3:
                avvisi.append(f"{nome}: {len(punti)} punti chiave (attesi 3)")
            for x in punti[:3]:
                if len(x) > MAX_PUNTO:
                    avvisi.append(f"{nome}: punto lungo {len(x)} caratteri (max {MAX_PUNTO}): {x}")
    return errori, avvisi


def unisci_pdf(files, dest):
    """PDF unico (es. MarketPlace_A4.pdf) con un segnalibro per categoria."""
    from pypdf import PdfWriter
    w = PdfWriter()
    for titolo, f in files:
        pagina = len(w.pages)
        w.append(f)
        w.add_outline_item(titolo, pagina)
    w.add_metadata({"/Title": os.path.splitext(os.path.basename(dest))[0].replace("_", " "),
                    "/Author": "METRO Mercato Online"})
    with open(dest, "wb") as fh:
        w.write(fh)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    ap.add_argument("--prodotti", default=os.path.join(ROOT, "data", "prodotti.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "output"))
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    dati = json.load(open(args.prodotti, encoding="utf-8"))
    data = dati.get("data_verifica", "")

    errori, avvisi = controlla_dati(dati)
    for a in avvisi:
        print("AVVISO:", a)
    if errori:
        for e in errori:
            print("ERRORE:", e)
        raise SystemExit("Generazione interrotta: correggere data/prodotti.json")

    # si genera in una cartella temporanea: i volantini esistenti vengono sostituiti solo a fine lavoro riuscito
    tmp_out = args.out.rstrip("/") + ".tmp"
    shutil.rmtree(tmp_out, ignore_errors=True)
    cartelle = {k: os.path.join(tmp_out, v) for k, v in
                (("a4", "PDF_A4"), ("wa", "PDF_WhatsApp"), ("txt", "Testi_WhatsApp"), ("tmp", ".html"))}
    for d in cartelle.values():
        os.makedirs(d)

    generati = []  # (titolo, pdf A4, pdf WhatsApp)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=trova_chromium())
        page = browser.new_page()

        def carica(nome, contenuto, w, h):
            f = os.path.join(cartelle["tmp"], nome)
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(contenuto)
            page.set_viewport_size({"width": w, "height": h})
            page.goto("file://" + f, wait_until="load")
            page.evaluate("document.fonts.ready")

        def tagliati(selettore):
            """Elementi il cui contenuto non entra nello spazio disponibile (testo o pulsanti tagliati)."""
            return page.evaluate("""s => [...document.querySelectorAll(s)]
                .filter(e => e.scrollHeight > e.clientHeight + 1)
                .map(e => (e.querySelector(".nome") || e).textContent.trim().slice(0, 50) + " (+" + (e.scrollHeight - e.clientHeight) + " px)")""", selettore)

        for cat in dati["categorie"]:
            nome = slug(cat["titolo"])
            carica(f"{nome}_a4.html", html_a4(cat, cfg, data), 794, 1123)
            for t in tagliati(".card"):
                print(f"AVVISO: {cat['titolo']} A4, scheda con contenuto tagliato: {t}")
            pdf_a4 = os.path.join(cartelle["a4"], f"Volantino_METRO_{nome}_A4.pdf")
            page.pdf(path=pdf_a4, width="210mm", height="297mm", print_background=True, page_ranges="1")

            carica(f"{nome}_wa.html", html_wa_pdf(cat, cfg, data), 1080, 1920)
            for t in tagliati(".pag"):
                print(f"AVVISO: {cat['titolo']} WhatsApp, pagina con contenuto tagliato: {t}")
            pdf_wa = os.path.join(cartelle["wa"], f"Volantino_METRO_{nome}_WhatsApp.pdf")
            page.pdf(path=pdf_wa, width="1080px", height="1920px", print_background=True)

            with open(os.path.join(cartelle["txt"], f"Messaggio_{nome}.txt"), "w", encoding="utf-8") as fh:
                fh.write(messaggio(cat, cfg, data))
            generati.append((cat["titolo"], pdf_a4, pdf_wa))
            print("Creati i volantini", cat["titolo"])
        browser.close()
    shutil.rmtree(cartelle["tmp"], ignore_errors=True)

    # PDF unici con tutte le categorie (in ordine alfabetico, con segnalibri)
    generati.sort(key=lambda g: g[0].lower())
    unisci_pdf([(t, a) for t, a, _ in generati], os.path.join(tmp_out, "MarketPlace_A4.pdf"))
    unisci_pdf([(t, w) for t, _, w in generati], os.path.join(tmp_out, "MarketPlace_WA.pdf"))

    # pacchetto unico da scaricare
    z = os.path.join(tmp_out, "Volantini_METRO_Horeca.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("LEGGIMI.txt", LEGGIMI.format(data=data))
        for k in ("a4", "wa", "txt"):
            for f in sorted(os.listdir(cartelle[k])):
                zf.write(os.path.join(cartelle[k], f), os.path.join(os.path.basename(cartelle[k]), f))

    shutil.rmtree(args.out, ignore_errors=True)
    os.replace(tmp_out, args.out)
    for f in ("PDF_A4", "PDF_WhatsApp", "MarketPlace_A4.pdf", "MarketPlace_WA.pdf", "Volantini_METRO_Horeca.zip"):
        print("Creato", os.path.relpath(os.path.join(args.out, f), ROOT))


if __name__ == "__main__":
    main()
