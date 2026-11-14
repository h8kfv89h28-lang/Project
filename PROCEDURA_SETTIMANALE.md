# Aggiornamento settimanale volantini (lunedì 08:00)

Procedura eseguita dall'attività programmata. Strumenti: connettore **Firecrawl** (pagine prodotto e
ricerca), `src/rotazione.py` (scelta degli articoli della settimana), `src/estrai_pagina.py` (lettura dati dalla
pagina), `src/genera_volantini.py` (PDF + kit WhatsApp).

**Rotazione (dal 16/11/2026, scelta di Michael):** ogni categoria ha **3 articoli fissi + 3 a rotazione** che
cambiano ogni settimana. Gli articoli vengono da `data/catalogo.json` (15-20 per categoria, con i dati
dell'ultima verifica) e lo storico delle uscite è in `data/storico_uscite.json`: un articolo a rotazione non
torna prima di 4 settimane (`regole.pausa_settimane`). `data/prodotti.json` non si modifica più a mano: lo scrive
`rotazione.py applica`. Fissi: campo `"fisso": true` nel catalogo (3 per categoria, si cambiano lì).
Priorità stagionale facoltativa: campo `"priorita": 1` su un articolo del catalogo (scelto prima degli altri).

## 1. Proposta della settimana
```bash
python src/rotazione.py proponi
```
Per ogni categoria mostra i 3 fissi, i 3 a rotazione e 3 riserve, nell'ordine dei criteri: fuori pausa, ultima
verifica ok, `priorita`, promo con sconto più alto, tipo di prodotto non già presente, uscito meno volte / da
più tempo. Scrive i 45 link in `/tmp/da_verificare.txt`. Se segnala `AVVISO: catalogo ... troppo piccolo` o
pochi articoli fuori pausa, ampliare il catalogo (punto 4) dopo la consegna.

## 2. Verifica degli articoli proposti
Scaricare ogni link di `/tmp/da_verificare.txt` con Firecrawl
(`formats: ["rawHtml"]`, `maxAge: 0`, `waitFor: 3000`, al massimo 2 richieste in parallelo e 10 al minuto).
Il risultato viene salvato su file: copiarlo in `/tmp/pagine/<id>.json` ed eseguire
```bash
python src/rotazione.py aggiorna /tmp/pagine/*.json
```
che legge ogni pagina con `estrai_pagina.py` e aggiorna l'articolo nel catalogo (`prezzo`,
`prezzo_rif`/`etichetta_rif`/`sconto_sito` solo se il prezzo è rosso, `venditore`, `consegna`,
`sconto_quantita` (fascia minima), `valutazione`, `classe_energetica`, `disponibilita_limitata`, `immagine`)
e lo marca `ok` oppure `escluso` con il motivo: pagina non trovata o non acquistabile, consegna oltre 4 settimane,
prezzo sotto 290 € IVA esclusa, **venditore diverso da METRO** ("Venduto da" ≠ METRO, sempre letto dalla
pagina prodotto, mai dalla ricerca). Un articolo escluso resta nel catalogo e viene ricontrollato più avanti.
Se un dato essenziale (prezzo, venditore, titolo, foto) manca su **tutte** le pagine lo script si ferma: è
cambiato l'HTML del sito, aggiornare le espressioni regolari di `estrai_pagina.py` prima di proseguire
(un `AVVISO` su una sola pagina indica invece una pagina non disponibile da controllare).

Dati letti da `estrai_pagina.py`:
- **prezzo** e **promo** (colore come sul sito: classe `text-metro-red` = rosso/promo,
  `text-metro-blue-main` = blu/prezzo pieno);
- se in promo: `prezzo_rif`, `etichetta_rif` (prima riga `reference-price-row-*`:
  `-reference` → "Prezzo più basso 30 gg" barrato, `-msrp` → "Prezzo consigliato",
  `-usual` → "Prezzo abituale") e `sconto_sito` (percentuale mostrata dal sito);
- **venditore** ("Venduto da"), **spedizione** e **giorni di consegna**, **sconti quantità**,
  **valutazione** e numero di recensioni, **classe energetica**, **disponibilità limitata**;
- foto principale (`og_image`), punti chiave e caratteristiche tecniche.


Non dedurre mai la promo dal testo: le promo cambiano spesso e vanno rilette ogni volta.

Gli articoli segnalati `DA COMPLETARE` (nuovi nel catalogo) vanno completati nel catalogo prima del punto 3:
3 `punti` brevi (max 42 caratteri) usando solo dati presenti sulla pagina (punti chiave, caratteristiche,
descrizione), `nome` breve come gli altri (tipo + modello + dato principale), `marca` = marchio indicato dal sito
(vuota se assente). Controllare visivamente che la foto corrisponda al prodotto.

## 3. Volantino della settimana
```bash
python src/rotazione.py applica
```
Sceglie tra gli articoli **verificati oggi**, `ok` e completi: i 3 fissi (se un fisso è escluso lo sostituisce un
articolo a rotazione) e 3 a rotazione con gli stessi criteri del punto 1, senza ripetere un articolo in due
categorie. Scrive `data/prodotti.json` (con `data_verifica` di oggi) e aggiunge l'uscita a `data/storico_uscite.json`.
Se in una categoria mancano articoli validi si ferma con `ERRORE`: verificare altre riserve (gli articoli
successivi in `proponi`, o `python src/rotazione.py stato`) e rilanciare `aggiorna` e `applica`.
Il riepilogo segna ogni articolo come FISSO, NUOVO o RITORNA.

## 4. Ampliare il catalogo (quando serve)
Candidati: attrezzature professionali ≥ 290 € **vendute da METRO**. La pagina di ricerca
`https://www.metro.it/marketplace/search?q=metro%20professional%20<tipo>` (es. forno, abbattitore, affettatrice,
ghiaccio, banco refrigerato) con Firecrawl `formats: ["rawHtml"]` e **`waitFor: 8000`** mostra la griglia con il
venditore: `python src/griglia_categoria.py <file>` elenca id, prezzo, promo, venditore e nome. Anche i caroselli
delle pagine prodotto già scaricate funzionano (senza venditore). Aggiungere al catalogo un oggetto con almeno
`id`, `url`, `nome`, `marca`, `tipo` (es. "forno pizza", "affettatrice": serve a variare i tipi) e
`"stato": "da verificare"`; verrà verificato e completato quando `proponi` lo sceglie. Il venditore va **sempre
confermato sulla pagina prodotto**. La stagionalità serve **solo per scegliere** (campo `priorita`): nei volantini
non vanno inseriti riferimenti stagionali né contatti di referenti specifici.

## 5. Generazione e consegna
Prima di generare: con la rotazione i tipi di prodotto cambiano ogni settimana, quindi aggiornare il
`sottotitolo` di ogni categoria in `data/prodotti.json` perché descriva solo ciò che c'è nel volantino.
```bash
python src/genera_volantini.py
```
Lo script si ferma con `ERRORE:` se un dato obbligatorio manca o il venditore non è METRO (correggere e rilanciare)
e stampa `AVVISO:` per prezzi sotto 290 €, punti oltre 42 caratteri o schede con contenuto tagliato
(da correggere accorciando nome o punti). Crea anche `output/MarketPlace_A4.pdf` e
`output/MarketPlace_WA.pdf`. Controllare l'anteprima dei PDF, fare commit e push
sul branch, inviare il pacchetto `output/Volantini_METRO_Horeca.zip` (5 PDF A4 + 5 PDF WhatsApp + testi) con un riepilogo delle modifiche (prezzi cambiati,
promo nuove/terminate, venditori cambiati, articoli nuovi e ritornati per categoria, articoli esclusi e motivo).
