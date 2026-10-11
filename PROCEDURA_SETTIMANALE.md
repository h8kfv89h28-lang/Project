# Aggiornamento settimanale volantini (lunedì 08:00)

Procedura eseguita dall'attività programmata. Strumenti: connettore **Firecrawl** (pagine categoria e foto),
**Parallel Search** web_fetch come alternativa gratuita per le pagine prodotto, script `src/genera_volantini.py`.

## 1. Verifica referenze attuali
Per ogni prodotto in `data/prodotti.json` leggere la pagina prodotto (Firecrawl `formats: ["json"]`,
`maxAge: 0`, una richiesta alla volta per il limite di concorrenza) ed estrarre:
- prezzo attuale IVA esclusa;
- prezzo di riferimento barrato e la sua etichetta (`Prezzo più basso` → "Prezzo più basso 30 gg",
  `Consigl.` → "Prezzo consigliato", `Prezzo abituale` → "Prezzo abituale");
- disponibilità/consegna; foto principale = `metadata.og:image`.

Aggiornare `prezzo`, `prezzo_rif`, `etichetta_rif` (rimuoverli se lo sconto non c'è più), `immagine`
(`<og:image>?impolicy=pdp_mobile_main_preview&imwidth=768`), badge "Pezzi limitati" se il sito
indica disponibilità limitata.

## 2. Sostituzione referenze non più valide
Un prodotto va sostituito se: pagina non trovata/non acquistabile, consegna oltre 4 settimane,
prezzo sceso sotto 290 € IVA esclusa.
Sostituto: dalla sezione **"I preferiti dai nostri clienti"** dell'`url_categoria` (Firecrawl JSON),
scegliendo attrezzature professionali ≥ 290 € non già presenti, privilegiando promo e stagionalità.
Verificare il sostituto come al punto 1. Max 6 referenze per categoria.
Non usare mai dati non verificati sulla pagina prodotto; controllare visivamente che la foto
corrisponda al prodotto.

## 3. Generazione e consegna
```bash
python src/genera_volantini.py --prodotti data/prodotti.json --out output
```
Aggiornare `data_verifica` alla data odierna, controllare l'anteprima dei PDF, fare commit e push sul
branch, inviare i 5 PDF con un riepilogo delle modifiche (prezzi cambiati, promo nuove/terminate,
referenze sostituite e motivo).
