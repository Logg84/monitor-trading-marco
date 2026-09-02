# ADDENDO SETTORI — studio di settore via ETF (cap-weighted + equal-weighted)

Integrazione al report di passaggio. Fonte di verità delle regole: questo file
per la parte settori; per tutto il resto vale il report originale.

## A. Principio non negoziabile

Il settore è **CONTESTO, mai segnale**. `core/sectors.py` non è importato da
`reversal_state`, né da `_check_exit_conditions`, né da `prune_watchlist`, né da
`auto_populate` (che lo usa solo come campo informativo da salvare). Quindi:

- i punti 0-6 e il cancello A restano identici;
- 🟡 = A + punti ≥2, 🟢 = A + punti ≥5 e D (invariati);
- le uscite watchlist restano **solo** in `core/reversal.py`;
- `reconcile` continua a non rimuovere mai;
- il circuito anti-svuotamento non è stato toccato;
- chiavi di dedup alert (`ticker:kind`), cooldown 5 giorni, day_lock: invariati
  (il settore aggiunge **testo** al messaggio, non un tipo di alert).

## B. Tassonomia: cosa esiste già di standard (e perché l'ho usata)

Niente famiglie inventate: una classificazione fatta in casa rende il Δ una media
di perimetri non confrontabili (agricoltura + oro nella stessa "famiglia", chip e
media in "tecnologia"). Il portale usa quindi classificazioni pubblicate:

**Livello 1 · GICS** (S&P Dow Jones Indices / MSCI): 4 livelli, 11 settori →
25 industry group → 74 industrie → 163 sub-industries. È la spina del portale
perché è l'unica tassonomia con **coppie ETF sullo stesso identico indice**:
`Select Sector SPDR` (capitalizzazione) ↔ `Invesco S&P 500 Equal Weight
<settore>` (pesi uguali) = stessi titoli, pesi diversi.

| settore GICS | cw | ew |
|---|---|---|
| Information Technology | XLK | RSPT |
| Financials | XLF | RSPF |
| Health Care | XLV | RSPH |
| Industrials | XLI | RSPN |
| Consumer Discretionary | XLY | RSPD |
| Consumer Staples | XLP | RSPS |
| Materials | XLB | RSPM |
| Energy | XLE | RSPG |
| Utilities | XLU | RSPU |
| Real Estate | XLRE | RSPR |
| Communication Services | XLC | RSPC |
| (mercato) | SPY | RSP |

**Livello 2 · S&P Select Industry** (i «SPDR S&P <Industria>», indice
modified equal-weight by design):semiconduttori XSD, software XSW,
farmaci XPH, biotech XBI, dispositivi medici XHE, servizi sanitari XHS, banche
KBE, banche regionali KRE, assicurazioni KIE, mercati capitali KCE, oil&gas E&P
XOP, metalli&miniere XME, costruttori casa XHB, retail XRT, aerospazio&difesa
XAR. Il gemello a capitalizzazione esiste solo per alcuni (SOXX, IGV, PPH, IBB,
IEO, ITB, ITA, RTH): **dove non esiste, il Δ è n/d e il termine di breadth nel
punteggio vale neutro**, non zero — è la differenza tra un numero e una
convenzione.

**Livello 3 · temi che GICS non contiene** (minatori d'oro, uranio, solare,
energia pulita, robotica/IA, agribusiness, rame): tabella separata, perché non
sono categorie di classificazione e non hanno equal-weighted dedicato.

Alternative scartate con motivo: **ICB** (FTSE Russell, 11/20/45/173) è la
spina dei prodotti UK/EU ma i fondi EW americani non la seguono; **TRBC**
(LSEG) e **Morningstar** (11 settori, 3 super-settori ciclico/difensivo/sensibile)
non hanno famiglie ETF: utili come crosswalk, non per misurare un Δ.

## C. Punteggio, Δ e metriche di "durata"

Punteggio 0-100: 25% trend (SMA50 e SMA200 della gamba cw) + 25% momentum 3m +
15% momentum 6m + 15% forza relativa 3m vs `SPY` + 10% posizione sul range 52
settimane + 10% breadth (Δ EW−CW a 3 mesi).
Stato: 🚀 FORTE (≥65 con mom3m>0) · 📈 IN MIGLIORAMENTO (≥50) · ↔️ NEUTRO (≥35)
· ⚠️ DEBOLE (≥20) · 🔻 IN CALO (<20) · ⚪ n/d (nessun dato ≠ neutro).
Direzione separata (mom3m + SMA50) e `vento()` = `favore|contro|misto|nd`: è
l'unica funzione che le UI leggono, non confrontare `dir` a mano altrove.

Del Δ esistono tre letture, tutte numeriche: **Δ 1m / Δ 3m / Δ 6m** (punti),
**consistenza** (% delle ultime 63 sedute in cui il rapporto EW/CW stava sopra
la propria SMA20 — continuità, non intensità) e **streak** (sedute consecutive di
vantaggio, col segno). Per il rapporto EW/CW anche la **posizione nel proprio
range annuo** (100 = le seconde linee non avevano mai guidato così tanto).

## D. Titolo → tassonomia (`inquadra`)

`inquadra(ticker)` ritorna una terna `(settore GICS, sotto-settore, tema)` e
legge, nell'ordine: campi `sector`/`industry` live (cache info 24h, negli
screening sono già scaricati) → `data/sector_map.json` del repo → `None`.

- Il **settore** viene dal campo `sector` di Yahoo, che *è* il settore GICS
  ("Technology", "Financial Services", "Healthcare", ...): nessuna classificazione
  casalinga. Mappa `GICS_BY_YAHOO`; se il campo manca, `GICS_PAROLE`.
- Il **sotto-settore** viene da `industry` con `SUB_RULES` (prima corrispondenza,
  dal più specifico al generico) e porta con sé il `gics` di appartenenza: è la
  mappa della classificazione, non una famiglia inventata.
- Il **tema** (`TEMA_REGOLE`: oro, uranio, solare, IA, agribusiness, rame) è un
  tag separato, perché quei panieri non esistono in GICS.

`sector_of`/`sub_of` sono i comodi accessori (cache 24h). Copertura dichiarata
nella diagnostica dello screening: `sector_classified`, `sub_classified`. Se un
titolo non ha dati (tipico di alcune mid cap europee e ADR), resta "—/n/d" e il
settore si riempe rigenerando la mappa: `python scripts/download_sectors_map.py
--refresh`. Una chiave salvata in watchlist che non esiste più nel registro viene
ignorata e riclassificata (`valid_key`), mai mostrata come settore fantasma.

## E. Colonne nello screening (`data_engine.screening`)

Livello 1 (GICS): `Settore` (etichetta; `⚠️` solo se c'è un segnale 🟡/🟢 su
settore in calo) · `SettoreKey` · `Sector` (`emoji + freccia + punteggio + Δ`) ·
`SectorETF` (`XLE · RSPG`) · `SectorScore` · `Δ EW−CW` (punti, 3 mesi) ·
`Vento` (`favore|contro|misto|nd`) · `Priorità` = `Bottom + bonus_sector`,
`bonus_sector = clip((stato−50)/5, −10, +10)`.
Livello 2: `Sotto-settore`, `SottoKey`, `SottoScore`, `SottoΔ`.
`Priorità` ordina e non decide; i campi di settore non entrano in nessuna regola.

Diagnostica: `sector_classified`, `sub_classified` (quanti titoli hanno settore /
sotto-settore) e `sector_source`, `sub_source` (`live`|`cache CI`|`n/d`).
`build_universe()` include anche i ~40 ETF dei registri: si possono quindi
aprire XSD, KBE, XME in analisi singola e vedere le zone volumetriche del
settore con lo stesso motore usato sui titoli.

## F. Frontend

- **🏭 Settori** (`pages/5_Settori.py`) — è la pagina dedicata al trend, con
  doppia rappresentazione come richiesto:
  * *Tabella numerica*: gambe CW/EW, stato, momentum CW ed EW su 1/3/6 mesi,
    Δ sulle tre finestre, RS, consistenza, streak, posizione del rapporto nel
    range annuo, chi tira, completezza delle gambe; ordinabile per Δ, filtro per
    settori, slider della finestra del Δ; sotto, expander "gamba per gamba" con i
    singoli ETF (momentum/RS/posizione di ciascuno).
  * *Heatmap*: Δ (settori × 1/3/6 mesi) e le due gambe + RS, con i numeri dentro
    le celle; barre Δ 3m ordinate con etichette; linee del rapporto EW/CW a più
    settori (sopra 100 = guidano le seconde linee).
  * *Dettaglio settore*: indici 100 CW vs EW (+ mercato), il loro rapporto con la
    linea di parità, e i numeri chiave in metriche.
  * *Candidati per settore*: unione con la cache screening + conteggio segnali
    con vento a favore/contro.
- **Watchlist** (`app.py`): colonne `Settore`/`Sector`/`Priorità`, ordinamenti,
  riga di contesto sotto il grafico ed expander "🏭 Contesto di settore" con le
  due gambe e i Δ.
- **Screening** (`pages/2_Screening.py`): BIOS dei segnali per vento di settore,
  chip di rotazione (stato + Δ), colonne nuove ordinabili, contesto nel pannello
  di decelerazione. Cache vecchia senza colonne → "—" e avviso, mai valori inventati.
- **Alert Telegram**: riga `✅ settore X in crescita…` / `⚠️ settore X in calo…`
  solo sui tipi CANDIDATO/INVERSIONE, letta da `data/sectors_latest.json`
  (il checker non scarica nulla: gira ogni 2 ore su Actions).

## G. Persistenza, CI e chiavi della cache

`sector_snapshot()` produce un solo blob `rows` con tutte le chiavi dei tre registri
(11 + sotto-settori + temi) più le liste `settori/sotto/temi`, e scrive
`data/sectors_latest.json`; `screening.yml` la committa con screening e watchlist.
`load_sector_cache()` **rifiuta** una cache il cui formato non coincide
(`_REQ_ROW_KEYS`, ora incluso `lettura`): una cache vecchia è peggiore di nessuna
cache, perché i Δ mancanti verrebbero letti come 0 = "breadth neutra".
Letture disponibili: `sector_rows()`, `sub_rows()`, `theme_rows()`, `all_rows()`,
con `snapshot_and_source()` che dichiara `live` / `cache CI` / `n/d` (live se
rinfrescata da <6 ore). I tre consumatori principali (screening, pagine, alert)
passano sempre da qui: nessuno si calcola un punteggio suo.

## H. Trappole (non reintrodurre)

1. **`_close_column`**: `yf.download` dà MultiIndex `(Field,Ticker)` o
   `(Ticker,Field)`, e con un solo ticker le colonne sono i campi. Una richiesta
   multi-ticker non-MultiIndex viene **scartata**, non attribuita a caso.
2. **Niente medie di prezzi**: se tornano gambe multiple, il composito va fatto
   sui **rendimenti** (base 100), mai facendo la media di prezzi di ETF diversi.
   Oggi con GICS ogni gamba è un ETF: il problema non esiste, non reimportarlo.
3. **"n/d" ≠ "neutro" ≠ 0**: `None` resta `None` in punteggio, celle, tooltip e
   heatmap. Un `or 0` su `Δ` o un `n/d` reso come "DEBOLE" sono bug di lettura.
4. **Sotto-settore senza paniere**: Nove chiavi di `SUBSECTORS` non hanno alcun ETF
   dedicato (es. chimica, media, auto): `score=None`, `Lettura` lo dice. Non è un
   errore di download.
5. **`sector`/`sub` in watchlist sono informativi**: se qualcuno li lega a una
   regola di uscita viola la regola d'oro (uscite solo in `prune_watchlist`).
   `reconcile` li riempie una volta sola e non li cancella: per riallineare una
   mappatura cambiata, ricreare l'entry (Yahoo può riassegnare un titolo).
6. **Blocco settore difensivo nello screening** con `try` proprio: altrimenti
   l'`except Exception: continue` del ciclo scarta titoli in silenzio.
7. **Checker leggero**: `alerts.py` legge solo la cache, mai live — il job gira
   ogni 2 ore su Actions.
8. **plotly**: heatmap con `%{z:+.1f}` inaffidabile tra versioni → `text`
   pre-formattato + `texttemplate="%{text}"`; `add_hline(...,
   annotation_position=)` con underscore (`annotationposition` esplode a runtime
   solo in quella tab).
9. **`st.column_config.NumberColumn(label, …)`**: label è il *primo* argomento
   posizionale, non il secondo.
10. **`ui/nav.py`**: colonne navbar = `len(PAGES)+1`, toggle tema su
    `cols[len(PAGES)]`.
11. **`sector_cell`** oggi appende `Δ`: le colonne `Sector` delle tabelle sono
    cambiate di formato, non di semantica — aggiornare i tooltip insieme.

## I. Come verificare il lavoro

    python scripts/verifica_settori.py     # 55 controlli, exit 0 = tutto ok

Copre: integrità del registro (11 GICS con coppie cw/ew simmetriche e codici
officiali, chiavi di_rules esistenti, universo ETF coerente, nessun residuo di
'famiglia'), invarianti contrattuali (reversal_state senza argomenti di settore,
essun settore in _check_exit_conditions/prune_watchlist, dedup alert invariato,
reconcile che non rimuove entry), sanità del dato (stati presenti, Δ solo dove
esistono entrambe le gambe, cache di formato precedente rifiutata, classificazione
di un campione misto USA/EU). Sola lettura: non scrive e non pusha nulla.

## J. Cosa osservare dopo il deploy

1. Copertura: `diagnostics["sector_classified"] / valid` (se i mercati UE sono
   molti e cala, rigenerare `data/sector_map.json`).
2. I settori "n/d" devono essere zero in condizioni normali: se crescono, è il
   download ETF (yfinance transitorio), non il mercato.
3. Verificare sui 🟡 che la riga di contesto appaia nel messaggio Telegram e che
   non siano cambiati day_lock/cooldown (stesse chiavi di `data/alerts.json`).
4. Taratura: le soglie (65/50/35/20) e i pesi sono una scelta dichiarata, non una verità statistica: serve
   osservazione prima di considerarli un edge.

## L. Frequenza di aggiornamento (chiara perché il dato sia interpretabile)

| cosa | quando | dove |
|---|---|---|
| snapshot settori (≈60 ETF, una batch) | **21:35 UTC** nei giorni di borsa aperta, cioè dopo la chiusura di Wall Street | `.github/workflows/settori.yml` → `scripts/update_sectors.py` → committa `data/sectors_latest.json` |
| screening completo (che a sua volta rigenera lo snapshot) | 06:30 e 14:30 UTC | `screening.yml` (invariato) |
| stato di settore visto dagli alert | ogni 2 ore 06-22 UTC, **senza scaricare nulla**: legge la cache commitata | `alerts.yml` |
| apertura pagina sul portale | download live se la cache di processo è vecchia >1h, altrimenti cache; fallback = cache del repo | `sector_snapshot()`/`snapshot_and_source()` |

Conseguenze da conoscere, e infatti il portale le dichiara in faccia:

1. **Sono chiusure, non intraday.** Alle 15:00 italiane il numero di stasera è
   ancora quello di ieri; durante la seduta USA la barra del giorno è parziale e
   lo snapshot porta `market_open_bar=true` (la riga di stato della pagina lo
   scrive: "barra di oggi ancora parziale"). Il job serale serve proprio a
   fissare la chiusura prima che qualcuno la interpreti come intraday.
2. **La cache del repo è un fallback, non la verità in tempo reale**: le pagine
   dicono `live` o `cache del repo (job CI)` con l'età in ore/giorni
   (`freschezza()`), e una cache di formato precedente viene rifiutata invece di
   essere letta a metà.
3. **Un solo job in più, non due**: lo snapshot sta anche dentro
   `run_screening.py`, quindi anche i due run di screening aggiornano la cache.
   Il job serale è l'unico che garantisce una fotografia *post-chiusura*.
4. **Il digest Telegram serale è opt-in**: `SETTORI_NOTIFICA=1` (nel workflow
   manuale con spunta `notifica`, o a mano
   `SETTORI_NOTIFICA=1 python scripts/update_sectors.py`). Il cron non lo
   imposta: un messaggio al giorno va deciso, non ereditato. Il testo è
   `rotation_digest()` (forti/deboli/Δ EW−CW/mercato).

Se vuoi spostare l'orario: il fuso del cron GitHub è **UTC** — 21:35 UTC =
23:35 con l'ora legale italiana (chiusura NASDAQ alle 22:00 italiane) e 22:35
con l'ora solare. Per una fotografia *dopo la chiusura europea* ma *prima* di
quella USA si salirebbe a ~22:30 UTC, sacrificando la chiusura di Wall Street
che è quella che muove questi ETF.
