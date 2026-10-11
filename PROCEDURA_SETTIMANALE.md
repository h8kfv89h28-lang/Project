# Aggiornamento settimanale volantini (lunedì 08:00)

Procedura eseguita dall'attività programmata. Strumenti: connettore **Firecrawl** (pagine categoria e foto),
**Parallel Search** web_fetch come alternativa gratuita per le pagine prodotto, script `src/genera_volantini.py`.

## 1. Verifica referenze attuali
Per ogni prodotto in `data/prodotti.json` leggere la pagina prodotto con Firecrawl
(`formats: ["html"]`, `maxAge: 0`, `onlyMainContent: false`, una richiesta alla volta) estraendo solo:
`includeTags: ["[test-target=\"price-box__total\"]", "[data-testid^=\"reference-price-row\"]"]`.

**Regola promo (colore come sul sito):**
- bottone `price-box__total` con classe `text-metro-red` → prezzo in **promozione** (rosso sul volantino);
- classe `text-metro-blue-main` → prezzo **pieno** (blu), senza prezzo di riferimento;
- se in promo, `prezzo_rif` ed `etichetta_rif` vanno presi dalla **prima** riga `reference-price-row-*`:
  `-reference` → "Prezzo più basso 30 gg" (barrato), `-msrp` → "Prezzo consigliato",
  `-usual` → "Prezzo abituale".
Non dedurre mai la promo dal testo della pagina: le promo cambiano spesso e vanno rilette ogni volta.

Aggiornare `prezzo`, `prezzo_rif`, `etichetta_rif` (rimuoverli se il prezzo è blu), foto da
`metadata.og:image` (`<og:image>?impolicy=pdp_mobile_main_preview&imwidth=768`), badge "Pezzi limitati"
solo se la pagina indica "Disponibilità limitata".

## 2. Sostituzione referenze non più valide
Un prodotto va sostituito se: pagina non trovata/non acquistabile, consegna oltre 4 settimane,
prezzo sceso sotto 290 € IVA esclusa.
Sostituto: dalla sezione **"I preferiti dai nostri clienti"** dell'`url_categoria` (Firecrawl JSON),
scegliendo attrezzature professionali ≥ 290 € non già presenti, privilegiando promo e prodotti adatti al
periodo stagionale. La stagionalità serve **solo per scegliere** i prodotti: nei volantini non vanno
inseriti riferimenti stagionali né contatti di referenti specifici.
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
