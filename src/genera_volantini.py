"""Generatore volantini Horeca METRO Mercato Online.

Legge config.json + un file prodotti (JSON) e produce un PDF per categoria
(max 6 referenze), ottimizzato per l'invio via WhatsApp:
foto statiche incorporate, prezzo rosso (promo) / blu (prezzo pieno),
pulsante cliccabile e QR code verso la pagina prodotto.

Uso:
    python src/genera_volantini.py --prodotti data/prodotti.json
    python src/genera_volantini.py --prodotti data/prodotti.esempio.json --bozza
"""

import argparse
import io
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date

import qrcode
from PIL import Image, ImageOps
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Palette: blu e giallo METRO, rosso promo, blu prezzo pieno
BLU = HexColor("#002D72")
BLU_PREZZO = HexColor("#0050C8")
GIALLO = HexColor("#FFE500")
ROSSO = HexColor("#E30613")
GRIGIO = HexColor("#6B7280")
GRIGIO_CHIARO = HexColor("#F3F4F6")
BORDO = HexColor("#E5E7EB")
TESTO = HexColor("#111827")

MAX_REFERENZE = 6
PAGE_W, PAGE_H = A4


def registra_font():
    candidati = {
        "Reg": ["/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
        "Bold": ["/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    }
    nomi = {}
    for peso, percorsi in candidati.items():
        for p in percorsi:
            if os.path.exists(p):
                pdfmetrics.registerFont(TTFont("F" + peso, p))
                nomi[peso] = "F" + peso
                break
        else:
            nomi[peso] = "Helvetica-Bold" if peso == "Bold" else "Helvetica"
    return nomi["Reg"], nomi["Bold"]


FONT, FONT_B = registra_font()


def euro(valore):
    s = f"{valore:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"€ {s}"


def con_utm(url, cfg, categoria):
    utm = cfg.get("utm")
    if not utm or not url:
        return url
    parti = urllib.parse.urlsplit(url)
    q = dict(urllib.parse.parse_qsl(parti.query))
    q.update({
        "utm_source": utm.get("source", "whatsapp"),
        "utm_medium": utm.get("medium", "volantino"),
        "utm_campaign": utm.get("campaign", "horeca"),
        "utm_content": re.sub(r"[^a-z0-9]+", "-", categoria.lower()).strip("-"),
    })
    return urllib.parse.urlunsplit(parti._replace(query=urllib.parse.urlencode(q)))


def wrap(testo, font, size, larghezza, max_righe):
    parole, righe, riga = testo.split(), [], ""
    for p in parole:
        prova = (riga + " " + p).strip()
        if pdfmetrics.stringWidth(prova, font, size) <= larghezza:
            riga = prova
        else:
            if riga:
                righe.append(riga)
            riga = p
    if riga:
        righe.append(riga)
    if len(righe) > max_righe:
        righe = righe[:max_righe]
        ultima = righe[-1]
        while pdfmetrics.stringWidth(ultima + "…", font, size) > larghezza and ultima:
            ultima = ultima[:-1]
        righe[-1] = ultima.rstrip() + "…"
    return righe


def carica_immagine(src):
    """Restituisce un ImageReader JPEG statico (sfondo bianco) o None."""
    if not src:
        return None
    try:
        if re.match(r"https?://", src):
            m = re.search(r"item_image/([0-9a-f-]{36})", src)
            cache = os.path.join(ROOT, "assets", "img", f"{m.group(1)}.jpg") if m else None
            if cache and os.path.exists(cache):
                img = Image.open(cache)
            else:
                req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
                dati = urllib.request.urlopen(req, timeout=20).read()
                if cache:
                    os.makedirs(os.path.dirname(cache), exist_ok=True)
                    with open(cache, "wb") as f:
                        f.write(dati)
                img = Image.open(io.BytesIO(dati))
        else:
            img = Image.open(os.path.join(ROOT, src))
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            sfondo = Image.new("RGB", img.size, "white")
            sfondo.paste(img, mask=img.split()[-1])
            img = sfondo
        img = img.convert("RGB")
        img.thumbnail((600, 600))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85, optimize=True)
        buf.seek(0)
        return ImageReader(buf)
    except Exception as e:  # immagine mancante: segnaposto, non blocca il volantino
        print(f"  ! immagine non caricata ({src}): {e}")
        return None


def qr_image(url):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#002D72", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return ImageReader(buf)


def disegna_header(c, cat, cfg):
    h = 168
    c.setFillColor(BLU)
    c.rect(0, PAGE_H - h, PAGE_W, h, stroke=0, fill=1)
    # fascia diagonale gialla (accento stagionale)
    p = c.beginPath()
    p.moveTo(PAGE_W - 190, PAGE_H)
    p.lineTo(PAGE_W, PAGE_H)
    p.lineTo(PAGE_W, PAGE_H - h)
    p.lineTo(PAGE_W - 110, PAGE_H - h)
    p.close()
    c.setFillColor(GIALLO)
    c.drawPath(p, stroke=0, fill=1)

    # wordmark
    c.setFillColor(GIALLO)
    c.roundRect(24, PAGE_H - 46, 78, 24, 3, stroke=0, fill=1)
    c.setFillColor(BLU)
    c.setFont(FONT_B, 16)
    c.drawCentredString(63, PAGE_H - 40, "METRO")
    c.setFillColor(white)
    c.setFont(FONT, 9.5)
    c.drawString(110, PAGE_H - 38, "Mercato Online  ·  metro.it/marketplace")

    c.setFont(FONT_B, 10)
    c.setFillColor(GIALLO)
    c.drawString(24, PAGE_H - 74, cfg["etichetta"].upper())
    c.setFillColor(white)
    c.setFont(FONT_B, 30)
    c.drawString(24, PAGE_H - 106, cat["titolo"])
    c.setFont(FONT, 12)
    for i, riga in enumerate(wrap(cat.get("sottotitolo", ""), FONT, 12, PAGE_W - 250, 2)):
        c.drawString(24, PAGE_H - 126 - i * 15, riga)

    # bollino a destra
    cx, cy = PAGE_W - 78, PAGE_H - 92
    c.setFillColor(BLU)
    c.circle(cx, cy, 48, stroke=0, fill=1)
    c.setFillColor(white)
    c.circle(cx, cy, 45, stroke=0, fill=1)
    c.setFillColor(BLU)
    righe = cfg["bollino"]
    for i, r in enumerate(righe):
        size = 15 if i == 1 else (9 if i == 0 else 7.5)
        c.setFont(FONT_B, size)
        c.drawCentredString(cx, cy + 14 - i * 15 - (2 if i == 1 else 0), r)


def disegna_card(c, x, y, w, h, prod, cfg, cat_titolo):
    url = con_utm(prod["url"], cfg, cat_titolo)
    rif = prod.get("prezzo_rif")
    promo = rif is not None and rif > prod["prezzo"]

    c.setFillColor(white)
    c.setStrokeColor(BORDO)
    c.setLineWidth(0.8)
    c.roundRect(x, y, w, h, 8, stroke=1, fill=1)
    # accento laterale
    c.setFillColor(ROSSO if promo else BLU_PREZZO)
    c.rect(x, y + 14, 3, h - 28, stroke=0, fill=1)

    pad = 10
    img_s = 104
    ix, iy = x + pad, y + h - pad - img_s
    c.setFillColor(GRIGIO_CHIARO)
    c.roundRect(ix, iy, img_s, img_s, 6, stroke=0, fill=1)
    img = prod.get("_img")
    if img:
        iw, ih = img.getSize()
        k = min((img_s - 8) / iw, (img_s - 8) / ih)
        dw, dh = iw * k, ih * k
        c.setFillColor(white)
        c.roundRect(ix, iy, img_s, img_s, 6, stroke=0, fill=1)
        c.drawImage(img, ix + (img_s - dw) / 2, iy + (img_s - dh) / 2, dw, dh)
    else:
        c.setFillColor(GRIGIO)
        c.setFont(FONT, 8)
        c.drawCentredString(ix + img_s / 2, iy + img_s / 2, "FOTO PRODOTTO")
    c.linkURL(url, (ix, iy, ix + img_s, iy + img_s), relative=0)

    # badge
    badges = []
    if promo:
        badges.append((f"-{int((1 - prod['prezzo'] / rif) * 100)}%", ROSSO, white))
    if prod.get("badge"):
        badges.append((prod["badge"], GIALLO, BLU))
    for k, (testo, fondo, colore) in enumerate(badges):
        c.setFont(FONT_B, 8.5)
        bw = pdfmetrics.stringWidth(testo, FONT_B, 8.5) + 12
        by_ = iy + img_s - 15 if k == 0 else iy + 2
        c.setFillColor(fondo)
        c.roundRect(ix - 3, by_, bw, 17, 4, stroke=0, fill=1)
        c.setFillColor(colore)
        c.drawString(ix + 3, by_ + 5, testo)

    # testo a destra della foto
    tx = ix + img_s + 10
    tw = x + w - pad - tx
    ty = y + h - pad - 8
    c.setFillColor(GRIGIO)
    c.setFont(FONT_B, 7.5)
    c.drawString(tx, ty, prod.get("marca", "").upper())
    ty -= 12
    c.setFillColor(TESTO)
    for riga in wrap(prod["nome"], FONT_B, 10, tw, 3):
        c.setFont(FONT_B, 10)
        c.drawString(tx, ty, riga)
        ty -= 12
    ty -= 2
    c.setFont(FONT, 8)
    c.setFillColor(HexColor("#374151"))
    for punto in prod.get("punti", [])[:3]:
        righe = wrap(punto, FONT, 8, tw - 8, 2)
        if ty - 10 * (len(righe) - 1) < iy:
            break
        c.setFillColor(BLU_PREZZO)
        c.circle(tx + 2, ty + 2.6, 1.6, stroke=0, fill=1)
        c.setFillColor(HexColor("#374151"))
        for r in righe:
            c.drawString(tx + 8, ty, r)
            ty -= 10

    # fascia prezzo / CTA / QR
    qr_s = 62
    qx, qy = x + w - pad - qr_s, y + pad + 6
    c.drawImage(qr_image(url), qx, qy, qr_s, qr_s)
    c.linkURL(url, (qx, qy, qx + qr_s, qy + qr_s), relative=0)
    c.setFillColor(GRIGIO)
    c.setFont(FONT, 6.5)
    c.drawCentredString(qx + qr_s / 2, y + pad - 1, "Inquadra e acquista")

    px = x + pad + 2
    prezzo_y = y + pad + 40
    prezzo = prod["prezzo"]
    nota_iva = cfg.get("nota_iva", "IVA escl.")
    if promo:
        vecchio = euro(rif)
        etichetta = prod.get("etichetta_rif", "")
        extra = max(pdfmetrics.stringWidth(vecchio, FONT, 8.5), pdfmetrics.stringWidth(etichetta, FONT, 5.8)) + 5
    else:
        extra = pdfmetrics.stringWidth(nota_iva, FONT, 7) + 5
    size = 21
    while size > 13 and px + pdfmetrics.stringWidth(euro(prezzo), FONT_B, size) + extra > qx - 4:
        size -= 1
    c.setFillColor(ROSSO if promo else BLU_PREZZO)
    c.setFont(FONT_B, size)
    c.drawString(px, prezzo_y, euro(prezzo))
    nx = px + pdfmetrics.stringWidth(euro(prezzo), FONT_B, size) + 5
    c.setFillColor(GRIGIO)
    if promo:
        c.setFont(FONT, 8.5)
        c.drawString(nx, prezzo_y + 11, vecchio)
        if etichetta.startswith("Prezzo più basso"):  # come sul sito: barrato solo il prezzo più basso 30 gg
            c.setStrokeColor(ROSSO)
            c.setLineWidth(0.9)
            c.line(nx - 1, prezzo_y + 14, nx + pdfmetrics.stringWidth(vecchio, FONT, 8.5) + 1, prezzo_y + 14)
        c.setFont(FONT, 5.8)
        c.drawString(nx, prezzo_y + 3.5, etichetta)
        c.setFont(FONT, 6.5)
        c.drawString(nx, prezzo_y - 4, nota_iva)
    else:
        c.setFont(FONT, 7)
        c.drawString(nx, prezzo_y - 1, nota_iva)

    bx, by, bw, bh = px, y + pad + 6, qx - px - 10, 24
    c.setFillColor(GIALLO)
    c.roundRect(bx, by, bw, bh, 12, stroke=0, fill=1)
    c.setFillColor(BLU)
    c.setFont(FONT_B, 10)
    c.drawCentredString(bx + bw / 2, by + 8, "ACQUISTA ONLINE  ›")
    c.linkURL(url, (bx, by, bx + bw, by + bh), relative=0)


def disegna_footer(c, cat, cfg):
    h = 92
    c.setFillColor(BLU)
    c.rect(0, 0, PAGE_W, h, stroke=0, fill=1)
    c.setFillColor(GIALLO)
    c.setFont(FONT_B, 9)
    c.drawString(24, h - 24, cfg["footer_titolo"])
    c.setFillColor(white)
    c.setFont(FONT_B, 13)
    c.drawString(24, h - 43, cfg["footer_testo"])

    url_cat = cat.get("url_categoria")
    if url_cat:
        bx, by, bw, bh = PAGE_W - 24 - 170, h - 54, 170, 30
        c.setFillColor(GIALLO)
        c.roundRect(bx, by, bw, bh, 15, stroke=0, fill=1)
        c.setFillColor(BLU)
        c.setFont(FONT_B, 10)
        c.drawCentredString(bx + bw / 2, by + 11, "Vedi tutta la categoria  ›")
        c.linkURL(con_utm(url_cat, cfg, cat["titolo"]), (bx, by, bx + bw, by + bh), relative=0)

    c.setFillColor(HexColor("#C7D2FE"))
    c.setFont(FONT, 6.8)
    nota = cfg["note_legali"].format(data=cfg["data_verifica"])
    for i, r in enumerate(wrap(nota, FONT, 6.8, PAGE_W - 48, 2)):
        c.drawString(24, 20 - i * 9, r)


def genera_categoria(cat, cfg, out_dir, bozza):
    prodotti = cat["prodotti"][:MAX_REFERENZE]
    for p in prodotti:
        p["_img"] = carica_immagine(p.get("immagine"))
    nome = f"Volantino_METRO_{re.sub(r'[^A-Za-z0-9]+', '_', cat['titolo']).strip('_')}.pdf"
    path = os.path.join(out_dir, nome)
    c = canvas.Canvas(path, pagesize=A4)
    c.setTitle(f"METRO Mercato Online – {cat['titolo']}")
    c.setAuthor("METRO Italia")
    c.setSubject(cfg["etichetta"])

    disegna_header(c, cat, cfg)
    disegna_footer(c, cat, cfg)

    top, bottom, margin, gap = PAGE_H - 168 - 12, 92 + 12, 18, 9
    cols, rows = 2, 3
    cw = (PAGE_W - 2 * margin - gap) / cols
    ch = (top - bottom - gap * (rows - 1)) / rows
    for i, prod in enumerate(prodotti):
        col, row = i % cols, i // cols
        disegna_card(c, margin + col * (cw + gap), top - (row + 1) * ch - row * gap, cw, ch, prod, cfg, cat["titolo"])

    if bozza:
        c.saveState()
        c.setFillColor(ROSSO, alpha=0.12)
        c.setFont(FONT_B, 54)
        c.translate(PAGE_W / 2, PAGE_H / 2)
        c.rotate(35)
        c.drawCentredString(0, 10, "BOZZA LAYOUT")
        c.setFont(FONT_B, 22)
        c.drawCentredString(0, -22, "prodotti e prezzi di esempio")
        c.restoreState()

    c.showPage()
    c.save()
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    ap.add_argument("--prodotti", default=os.path.join(ROOT, "data", "prodotti.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "output"))
    ap.add_argument("--bozza", action="store_true", help="filigrana 'bozza layout'")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    with open(args.prodotti, encoding="utf-8") as f:
        dati = json.load(f)
    cfg.setdefault("data_verifica", dati.get("data_verifica", date.today().strftime("%d/%m/%Y")))
    os.makedirs(args.out, exist_ok=True)

    for cat in dati["categorie"]:
        if len(cat["prodotti"]) > MAX_REFERENZE:
            print(f"  ! {cat['titolo']}: {len(cat['prodotti'])} referenze, uso le prime {MAX_REFERENZE}")
        print("Creato", genera_categoria(cat, cfg, args.out, args.bozza or dati.get("esempio", False)))


if __name__ == "__main__":
    main()
