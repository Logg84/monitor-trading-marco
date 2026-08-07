import streamlit as st

def render_metric_guide():
    """
    Guida rapida alle metriche della tabella screening.
    Richiamata in coda al pannello automazione, prima delle tabelle.
    """
    with st.expander("📘 Guida alle metriche — Health · Bottom · Size (apri per spiegare una colonna)", expanded=False):
        st.markdown("""
        ### 🩺 Health Check (0‑4) – Salute finanziaria assoluta
        Valuta la solidità dell’azienda **in sé**, senza confronti con altre.
        - **FCF > 0** → genera cassa operativa
        - **Crescita Ricavi YoY > 0** → fatturato in espansione (ultimo trimestre vs stesso trimestre anno prima)
        - **Utile Netto > 0** → redditività positiva
        - **D/E < 1.5** → indebitamento contenuto

        | Punteggio | Simbolo | Significato |
        |-----------|---------|-------------|
        | 4/4 | ✅ | Tutti i criteri superati – azienda solida |
        | 2‑3/4 | ⚠️ | Qualche debolezza – attenzione |
        | 0‑1/4 | ❌ | Criteri largamente non soddisfatti – fragile |

        **Nota per i mercati europei**  
        Le small cap europee possono mostrare fisiologicamente D/E più elevati o FCF negativo per investimenti. Un punteggio di 2‑3/4 ⚠️ in questi casi non è di per sé un segnale di debolezza: va letto nel contesto della capitalizzazione e del settore.

        *N.B. I dati provengono da Yahoo Finance e vengono aggiornati ogni 14 giorni.*

        ---

        ### 📉 Bottom Score (0‑4) – Segnali di inversione tecnica
        Indica se il titolo sta mostrando **segnali di esaurimento della discesa**:
        - Decelerazione del Rate of Change (ROC)
        - MACD Histogram in risalita
        - Vicinanza a un POC strutturale con momentum rialzista
        - Convergenza di più VWAP
        - Aumento di volume e forza (Force Index)

        | Punteggio | Semaforo | Significato |
        |-----------|----------|-------------|
        | 4 | 🟢 | Forte inversione – pronto per l’ingresso |
        | 3 | 🟡 | Segnali iniziali – monitorare |
        | 2 | 🟡 | Esaurimento vendita – pazienza |
        | 0‑1 | 🔴 | Nessuna inversione – non entrare |

        ---

        ### 💰 Size Suggerita (%) – Dimensione operativa consigliata
        È un **riferimento di posizionamento**, non un ordine. Combina:
        - Capitalizzazione di mercato (base)
        - **Health Check** (moltiplicatore: ×1.2 se ≥3, ×0.6 se ≤1)
        - **Bias della Bussola ARGO** (×0.3 in SHORT, ×0.6 in NEUTRO, ×1 in LONG)
        - Valori inferiori a 1% vengono azzerati (size 0)

        *La size è puramente indicativa e va adattata al tuo money management.*

        ---

        ### 📊 Altre colonne
        - **Drawdown %**: distanza dal massimo storico (ATH). Più è negativo, più il titolo è “in sconto”.
        - **POC più vicino / dPOC%**: POC operativo con la distanza percentuale attuale.
        - **VWAP vicino / dVWAP%**: il VWAP (3M/1Y/4Y) più prossimo al prezzo e la relativa distanza.
        - **🎯 Alert**: compare solo se il prezzo tocca un POC o un VWAP entro la soglia configurata in sidebar.
        - **Entry Mode**: indicazione di massima su come approcciare il titolo (Market, Limite, Verifica manuale) in base alla distanza dal POC e al regime ARGO.
        - **Stato**: Active (in forte sconto), Ripartito (uscito dallo sconto), Nuovo (prima apparizione).
        """)
