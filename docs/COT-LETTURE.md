# COT materie prime — cosa significano davvero le tre linee

Fonti: **CFTC, “Disaggregated Commitments of Traders — Explanatory Notes”**
(definizioni ufficiali delle 4 categorie + la sezione “Potential Limitations of
the Data”), **CFTC, “Staff Report on Commodity Swap Dealers & Index Traders”
(settembre 2008)”** da cui nasce la disaggregazione, e — per la parte applicata
— letture di mercato moderne (COTInsight, *“Are Commercials Really the Smart
Money?”*, 2026). Link in fondo.

## 1. Producer/Merchant/Processor/User — non è “il parere dei produttori”

Definizione CFTC: *«entity that predominantly engages in the production,
processing, packing or handling of a physical commodity and uses the futures
markets to manage or hedge risks associated with those activities»*.

Il campo è la **somma di due incentivi opposti**, ed è qui che la lettura va
corretta:

| chi è | rischio che teme | copertura naturale |
|---|---|---|
| **produttore / merchant** che detiene o sta per immettere fisico | che il prezzo **scenda** | **SHORT** (vende futures) |
| **processor / user** che deve comprare fisico (refiner, mulino, food company, utility) | che il prezzo **salga** | **LONG** (compra futures) |

Quindi: *producer short = “si copre da un aumento”* **no** — è il contrario: lo
short fissa il prezzo di una **vendita**, cioè protegge da un ribasso. E un netto
**long** anormale non è “previsione di discesa”: di solito è chi deve comprare
che blocca i costi, o un produttore che **ricopre** (short covering) la copertura
fatta in precedenza.

La linea resta utile, ma si legge **così**: il numero informativo non è il segno
grezzo (quasi tutti i mercati fisici sono strutturalmente short) ma il
**percentile rispetto alla storia di quel mercato** e il **verso del cambiamento**.

* netto che **scende da livelli già bassi** → stanno *vendendo copertura sui
  forti*: il lato reale non crede alla forza che vede (contesto di prudenza);
* netto che **sale da_levels alti** → bloccano costi o ricoprono: il rischio
  fisico sta passando da “devo vendere” a “devo comprare”;
* **estremo basso (pP<10)**: gran parte del fisico è già coperto → poca vendita
  di copertura in arrivo, ed è la condizione dello *squeeze* se il Managed Money
  è long;
* **estremo alto (pP>90)**: accumulo/assorbimento dal lato reale.

Avverte sempre la CFTC: la classificazione è per *prevalent activity*, e
*«staff will generally know… that a trader is a “producer/merchant/processor/user”
but we cannot know with certainty that all of that trader's activity is
hedging»*.

## 2. Swap Dealer — flusso, non opinione

Definizione CFTC: *«entity that deals primarily in swaps for a commodity and
uses the futures markets to manage or hedge the risk associated with those swaps
transactions […]; the swap dealer's counterparties may be speculative traders,
like hedge funds, or traditional commercial clients»*.

Il suo netto è la **conseguenza meccanica del libro swap dei clienti**: compra
esposizione via swap → il dealer compra futures; il cliente riscatta → il dealer
vende. Non c'è una view. Quindi:

* il **livello dice poco** (nel report Legacy questa categoria stava dentro i
  “commercial”: è da lì che nasce il mito “commerciali = smart money”, e la
  disaggregazione del 2009 serve proprio a separare le due cose);
* **informativo è il cambiamento, letto contro il prezzo** — ed è il motivo per
  cui la vecchia nota “rumoroso; utile solo se cambia segno” era insufficiente.
  Il portale ora lo formula da sé (`swap_lettura`):
  * **afflusso** (netto che sale da livello alto): dall'OTC arriva domanda di
    esposizione — il compratore passivo/index c'è;
  * **deflusso** (netto che scende da livello basso): i clienti OTC stanno
    uscendo (riscatti di indici, coperture che si alleggeriscono). Se il prezzo
    intanto sale, sale **senza** il suo fluxo strutturale: è il “carburante in
    calo” vero;
  * **neutro**: book in posizione, la linea non aggiunge nulla — dilo, non
    camuffarlo da segnale;
  * **confronto col Managed Money** (`conferma`): stessa direzione = OTC e
    speculazione nella stessa mano (se gira, gira doppia); direzione opposta =
    **passaggio di mano** del rischio (cambia proprietario, non dimensione
    totale dell'esposizione).

## 3. Zone di divergenza sul grafico (`divergenze`)

Divergenza = **variazione del prezzo contro variazione del posizionamento** su 8
settimane, con due soglie (prezzo ≥ 2,5%; posizionamento ≥ 0,5 dev-std dei suoi
delta settimanali) e durata minima di 3 settimane. Quattro tipi:

| tipo | condizione | lettura |
|---|---|---|
| `COP-` | prezzo su, netto producer giù | il fisico vende copertura sui forti: non difende i massimi |
| `COP+` | prezzo giù, netto producer su | blocco costi / short covering: il lato reale assorbe |
| `CARB-` | prezzo su, Managed **o** Swap giù | salita senza denaro dietro |
| `CARB+` | prezzo giù, Managed **o** Swap su | qualcuno entra mentre scende |

Ogni zona è una banda sul grafico (verde = lettura rialzista, rossa = ribassista)
etichettata `tipo / settimane / esito`, ed è elencata nella tabella **“⚡
Divergenze”** con l'**esito a 13 settimane** e il tasso di risoluzione del
campione (`Zones_summary`). Sono storia locale con il suo punteggio, non una
legge: su ~86 settimane il campione è piccolo, e la pagina lo scrive. Se il
prezzo non è disponibile (niente mapping yfinance o download fallito) **non viene
disegnata alcuna zona**: è “non calcolabile”, non “nessuna divergenza”.

Soglie in `core/cot.py`: `W_DIV = 8`, `MIN_ZONE = 3`, `TH_PX = 0.025`,
soglia posizionamento `0,5·σ`. Si possono tarare: se lo si fa, va registrato qui.

## Fonti

* CFTC — Disaggregated Explanatory Notes:
  <https://www.cftc.gov/MarketReports/CommitmentsofTraders/DisaggregatedExplanatoryNotes/index.htm>
* CFTC — Explanatory Notes (Legacy) e *Staff Report on Commodity Swap Dealers &
  Index Traders* (2008):
  <https://www.cftc.gov/MarketReports/CommitmentsofTraders/ExplanatoryNotes/index.htm>
* CFTC — comunicato di avvio della disaggregazione:
  <https://www.cftc.gov/PressRoom/PressReleases/5760-09>
* COTInsight — *Are Commercials Really the Smart Money?*:
  <https://cotinsight.com/blog/are-commercials-really-the-smart-money>
