# Volantini Horeca – METRO Mercato Online (Trento)

Generatore di volantini PDF (1 per categoria, max 6 referenze) da inviare ai clienti via WhatsApp.

- Foto prodotto incorporate come JPEG statici (nessun contenuto dinamico).
- Prezzo promozionale in **rosso** (con prezzo pieno barrato e % sconto), prezzo pieno in **blu**.
- Pulsante "ACQUISTA ONLINE" cliccabile e QR code verso la pagina prodotto (con UTM per misurare i clic per campagna).
- Footer con referente commerciale e pulsante "Chiedi un preventivo su WhatsApp" (link wa.me).

## Uso

```bash
pip install reportlab qrcode pillow
python src/genera_volantini.py --prodotti data/prodotti.json          # volantini definitivi in output/
python src/genera_volantini.py --prodotti data/prodotti.esempio.json --out output/bozza   # bozza layout
```

- `config.json`: referente, testi stagionali, note legali, parametri UTM.
- `data/prodotti.json`: categorie e referenze (`marca`, `nome`, `punti`, `prezzo` attuale, `prezzo_rif` +
  `etichetta_rif` se il sito mostra un prezzo barrato, `badge` opzionale, `url`, `immagine`) + `data_verifica`.
  Le referenze provengono dalle sezioni "I preferiti dai nostri clienti" delle categorie del Mercato Online.
- `PROCEDURA_SETTIMANALE.md`: aggiornamento automatico del lunedì (prezzi, disponibilità, sostituzioni).

`data/prodotti.esempio.json` contiene **solo dati fittizi** per validare il layout.
