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

**Ampliamento continuo (dal 23/11/2026, richiesta di Michael):** a **ogni** aggiornamento del lunedì, prima della
proposta, si aggiungono al catalogo nuovi articoli venduti da METRO (punto 1), così la selezione si basa su una
scelta sempre più ampia. Gli articoli già presenti non si tolgono: quelli non più validi restano `escluso` e
vengono ricontrollati più avanti.

## 1. Ampliare il catalogo (ogni lunedì, prima della proposta)
Obiettivo: **almeno 5 articoli nuovi a settimana**, almeno 1 per categoria, con priorità alle categorie che
`python src/rotazione.py proponi` (o `stato`) segnala con `AVVISO` o con meno articoli fuori pausa.
Candidati: attrezzature professionali ≥ 290 € IVA esclusa **vendute da METRO**, di tipi o modelli non ancora nel catalogo.

1. Scaricare con Firecrawl (`formats: ["rawHtml"]`, **`waitFor: 8000`**, `maxAge: 0`) 4-6 pagine di ricerca
   `https://www.metro.it/marketplace/search?q=<termine>` e copiarle in `/tmp/ricerche/<termine>.json`.
   I filtri del sito (venditore, marca) non funzionano via link: servono termini che restituiscono prodotti
   venduti da METRO. Termini che funzionano (ruotarli di settimana in settimana):
   - `metro professional <tipo>` (forno, friggitrice, piastra, lavastoviglie, lavabicchieri, frigorifero,
     cantinetta vino, sottovuoto, tritacarne, frullatore, spremiagrumi...);
   - `metro professional <prefisso modello>`: GCS, GDW, GGW, GEG, GSC, GCC, GCV, GWC, GVS, GMG, GPO, GIM...;
   - marchi venduti da METRO: `atosa`, `cookrite`, `casselin lavastoviglie`, `casselin cantina`.
2. `python src/griglia_categoria.py /tmp/ricerche/*.json --nuovi` elenca solo i candidati con venditore METRO
   nella scheda e non ancora nel catalogo (id, prezzo, promo, nome).
3. Scegliere i candidati privilegiando tipi nuovi per la categoria, promo e stagionalità; scaricare la loro pagina
   prodotto come al punto 3 (`/tmp/pagine/<id>.json`) e scartare quelli con venditore ≠ METRO, non disponibili
   ("Non disponibile"/esaurito), consegna oltre 4 settimane o **foto mancante/segnaposto** (logo METRO.IT al posto
   del prodotto).
4. Aggiungere ognuno in fondo alla sua categoria di `data/catalogo.json` con `id`, `url`, `nome` breve (tipo +
   modello + dato principale, max ~44 caratteri), `marca` (maiuscolo come gli altri, es. "METRO PROFESSIONAL",
   "ATOSA", "CASSELIN"), `tipo` (es. "forno pizza", "cantinetta vino": serve a variare i tipi), 3 `punti` brevi
   (max 42 caratteri, solo dati della pagina), `"stato": "da verificare"` e `"aggiunto": "<data di oggi>"`.
5. `python src/rotazione.py aggiorna /tmp/pagine/<id nuovi>.json` completa prezzo, promo, venditore, consegna e
   foto e li marca `ok`. Controllare visivamente le foto dei nuovi articoli.

Nel riepilogo della consegna indicare gli articoli aggiunti al catalogo per categoria.

## 2. Proposta della settimana
```bash
python src/rotazione.py proponi
```
Per ogni categoria mostra i 3 fissi, i 3 a rotazione e 3 riserve, nell'ordine dei criteri: fuori pausa, ultima
verifica ok, `priorita`, promo con sconto più alto, tipo di prodotto non già presente, uscito meno volte / da
più tempo. Scrive i 45 link in `/tmp/da_verificare.txt`. Se segnala `AVVISO: catalogo ... troppo piccolo` o
pochi articoli fuori pausa, aggiungere altri articoli a quella categoria (punto 1) e rilanciare `proponi`.

## 3. Verifica degli articoli proposti
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

Gli articoli segnalati `DA COMPLETARE` vanno completati nel catalogo prima del punto 4:
3 `punti` brevi (max 42 caratteri) usando solo dati presenti sulla pagina (punti chiave, caratteristiche,
descrizione), `nome` breve come gli altri (tipo + modello + dato principale), `marca` = marchio indicato dal sito
(vuota se assente). Controllare visivamente che la foto corrisponda al prodotto.

## 4. Volantino della settimana
```bash
python src/rotazione.py applica
```
Sceglie tra gli articoli **verificati oggi**, `ok` e completi: i 3 fissi (se un fisso è escluso lo sostituisce un
articolo a rotazione) e 3 a rotazione con gli stessi criteri del punto 2, senza ripetere un articolo in due
categorie. Scrive `data/prodotti.json` (con `data_verifica` di oggi) e aggiunge l'uscita a `data/storico_uscite.json`.
Se in una categoria mancano articoli validi si ferma con `ERRORE`: verificare altre riserve (gli articoli
successivi in `proponi`, o `python src/rotazione.py stato`) e rilanciare `aggiorna` e `applica`.
Il riepilogo segna ogni articolo come FISSO, NUOVO o RITORNA.

Nota: la stagionalità serve **solo per scegliere** (campo `priorita`): nei volantini non vanno inseriti
riferimenti stagionali né contatti di referenti specifici.

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
promo nuove/terminate, venditori cambiati, articoli nuovi e ritornati per categoria, articoli esclusi e motivo,
articoli aggiunti al catalogo).
