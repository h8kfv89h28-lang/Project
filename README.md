# Volantini Horeca – METRO Mercato Online (Trento)

Volantini delle attrezzature professionali più scelte sul Mercato Online METRO, 5 categorie × 6 prodotti,
da inviare ai clienti dal team commerciale.

## Cosa viene generato (`output/`)
- `PDF_A4/Volantino_METRO_<Categoria>_A4.pdf` – A4 in stile metro.it (logo ufficiale, font Lato, colori del sito),
  pulsante "Acquista online" cliccabile e QR code per ogni prodotto. Per e-mail, stampa o computer.
- `PDF_WhatsApp/Volantino_METRO_<Categoria>_WhatsApp.pdf` – formato smartphone verticale (9:16), da inviare come
  documento su WhatsApp: pagina 1 con i 6 prodotti (pulsanti "Dettagli" e "Acquista"), poi una pagina per prodotto
  con il pulsante "Acquista online su metro.it" e la navigazione tra le pagine.
- `Testi_WhatsApp/Messaggio_<Categoria>.txt` – testo facoltativo da incollare insieme al PDF, con i link.
- `Volantini_METRO_Horeca.zip` – pacchetto unico con tutto quanto sopra e il file LEGGIMI.

## Contenuto delle schede prodotto
Foto ufficiale, marca, nome, valutazione (solo se ≥ 4 su almeno 3 recensioni), 3 punti chiave,
prezzo IVA esclusa **rosso se in promozione sul sito / blu se prezzo pieno** (classe CSS del sito),
prezzo di riferimento con l'etichetta del sito, sconto quantità, **venditore**, tempi e costi di consegna,
classe energetica, "Disponibilità limitata". Nessun contatto personale: il footer invita a fare riferimento
al proprio referente commerciale METRO.

## Uso
```bash
pip install -r requirements.txt
python src/genera_volantini.py            # PDF A4 + PDF WhatsApp + testi + zip
python src/estrai_pagina.py pagina.html   # dati di una pagina prodotto (vedi PROCEDURA_SETTIMANALE.md)
```
Chromium: `/opt/pw-browsers/chromium-1194/chrome-linux/chrome` (modificabile con `CHROMIUM_PATH`).

- `data/prodotti.json`: categorie e prodotti verificati sul sito.
- `config.json`: testi del footer, note legali, parametri UTM per misurare i clic per canale.
- `assets/`: logo ufficiale METRO (SVG dal sito), font Lato del sito, cache foto prodotti.
- `PROCEDURA_SETTIMANALE.md`: aggiornamento automatico del lunedì (prezzi, promo, venditori, sostituzioni).
