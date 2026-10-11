# Aggiornamento settimanale volantini (lunedì 08:00)

Procedura eseguita dall'attività programmata. Strumenti: connettore **Firecrawl** (pagine prodotto e
categoria), `src/estrai_pagina.py` (lettura dati dalla pagina), `src/genera_volantini.py` (PDF + kit WhatsApp).

## 1. Verifica referenze attuali
Per ogni prodotto in `data/prodotti.json` scaricare la pagina prodotto con Firecrawl
(`formats: ["rawHtml"]`, `maxAge: 0`, `waitFor: 3000`, al massimo 2 richieste in parallelo e 10 al minuto).
Il risultato viene salvato su file: copiarlo in `/tmp/pagine/<id>.json` ed eseguire
`python src/estrai_pagina.py /tmp/pagine/*.json`, che restituisce per ogni pagina:

- **prezzo** e **promo** (colore come sul sito: classe `text-metro-red` = rosso/promo,
  `text-metro-blue-main` = blu/prezzo pieno);
- se in promo: `prezzo_rif`, `etichetta_rif` (prima riga `reference-price-row-*`:
  `-reference` → "Prezzo più basso 30 gg" barrato, `-msrp` → "Prezzo consigliato",
  `-usual` → "Prezzo abituale") e `sconto_sito` (percentuale mostrata dal sito);
- **venditore** ("Venduto da"), **spedizione** e **giorni di consegna**, **sconti quantità**,
  **valutazione** e numero di recensioni, **classe energetica**, **disponibilità limitata**;
- foto principale (`og_image`), punti chiave e caratteristiche tecniche.

Aggiornare in `data/prodotti.json`: `prezzo`, `prezzo_rif`/`etichetta_rif`/`sconto_sito` (da rimuovere se il
prezzo è blu), `venditore`, `consegna`, `sconto_quantita` (fascia minima), `valutazione`,
`classe_energetica`, `disponibilita_limitata`, `immagine` (`<og_image>?impolicy=pdp_mobile_main_preview&imwidth=768`).
Non dedurre mai la promo dal testo: le promo cambiano spesso e vanno rilette ogni volta.

## 2. Sostituzione referenze non più valide
Un prodotto va sostituito se: pagina non trovata o non acquistabile, consegna oltre 4 settimane,
prezzo sceso sotto 290 € IVA esclusa.
Sostituto: dalla sezione **"I preferiti dai nostri clienti"** dell'`url_categoria`
(Firecrawl `formats: ["json"]`), scegliendo attrezzature professionali ≥ 290 € non già presenti,
privilegiando promo e prodotti adatti al periodo stagionale. La stagionalità serve **solo per scegliere**
i prodotti: nei volantini non vanno inseriti riferimenti stagionali né contatti di referenti specifici.
Verificare il sostituto come al punto 1. Max 6 referenze per categoria.

Per il sostituto scrivere 3 `punti` brevi (max ~42 caratteri) usando solo dati presenti sulla pagina
(punti chiave, caratteristiche, descrizione); `marca` = marchio indicato dal sito (vuota se assente).
Controllare visivamente che la foto corrisponda al prodotto.

## 3. Generazione e consegna
```bash
python src/genera_volantini.py
```
Aggiornare `data_verifica` alla data odierna, controllare l'anteprima di PDF e immagini, fare commit e push
sul branch, inviare i 5 PDF e i 5 zip WhatsApp con un riepilogo delle modifiche (prezzi cambiati,
promo nuove/terminate, venditori cambiati, referenze sostituite e motivo).
