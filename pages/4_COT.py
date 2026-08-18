"""
COT — CFTC positioning.
Workflow: annual Excel zip (historical) + weekly comma-delimited txt (update).
"""
import re
from datetime import datetime

import streamlit as st
import pandas as pd

st.set_page_config(page_title="COT", page_icon="🛢️", layout="wide")

from ui.theme import inject_css, COLORS
from ui.nav import render_navbar, sidebar_nav
from core.cot import get_cot_scores, list_files, COT_DIR

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

inject_css(dark=st.session_state.dark_mode)
render_navbar(title="COT")
sidebar_nav()

st.markdown("## COT — CFTC Positioning")
st.caption("Legacy Futures Only = single file containing all markets (commodities, FX, indices).")

# ── Verified download links ────────────────────────────────
st.markdown("### Report Download")
year = datetime.now().year

st.markdown("**Legacy (all-in-one, required)**")
cols = st.columns(4)
for c, y in zip(cols[:3], [year - 2, year - 1, year]):
    c.markdown(f"[📥 Annual {y}]({f'https://cftc.gov/files/dea/history/dea_fut_xls_{y}.zip'})")
cols[3].markdown("[📥 Weekly current](https://cftc.gov/dea/newcot/deafut.txt)")

with st.expander("Optional: Disaggregated (commodities) and TFF (indices/FX)"):
    st.markdown(f"[📥 Disaggregated annual {year}](https://cftc.gov/files/dea/history/fut_disagg_xls_{year}.zip) · "
                f"[📥 Disaggregated weekly](https://cftc.gov/dea/newcot/f_disagg.txt)")
    st.markdown(f"[📥 TFF annual {year}](https://cftc.gov/files/dea/history/fut_fin_xls_{year}.zip) · "
                f"[📥 TFF weekly](https://cftc.gov/dea/newcot/FinFutWk.txt)")

# ── Multi-format upload ────────────────────────────────────
COT_DIR.mkdir(parents=True, exist_ok=True)
uploaded = st.file_uploader("Upload reports (.zip, .txt, .csv, .xls, .xlsx)",
                            type=["zip", "txt", "csv", "xls", "xlsx"],
                            accept_multiple_files=True)
if uploaded:
    saved = []
    today = datetime.now().strftime("%Y%m%d")
    for up in uploaded:
        name = up.name
        if not re.search(r"(19|20)\d{2}", name):
            name = f"weekly_{today}_{name}"
        with open(COT_DIR / name, "wb") as f:
            f.write(up.getbuffer())
        saved.append(name)
    st.success(f"Saved: {', '.join(saved)}")
    st.cache_data.clear()
    st.rerun()

# ── Computed scores ────────────────────────────────────────
scores = get_cot_scores()
if scores is None:
    st.warning("No COT reports loaded, or format not recognized. "
               "Download the annual Legacy (Excel zip) and weekly (txt).")
else:
    st.markdown("### COT Scores")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Money Manager", f"{scores['managed_money']:+.0f}")
        st.caption(scores["managed_money_detail"])
    with c2:
        st.metric("Producers", f"{scores['producers']:+.0f}")
        st.caption(scores["producers_detail"])

    if scores.get("extreme_producer"):
        st.error("⚠️ **Producer extreme rule**: producer positioning at extreme percentile — potentially strong reversal signal.")

    st.markdown("### Interpretation")
    st.markdown(f"""
- Markets analyzed: **{scores['market']}** · historical observations: **{scores['n_obs']}**
- **Money Manager**: positive score = extreme fear (opportunity); negative = euphoria (risk).
- **Producers**: positive score = producers cutting shorts (seeing low prices); negative = adding shorts (seeing high prices).
""")

# ── Loaded files ───────────────────────────────────────────
st.markdown("### Loaded Files")
files = list_files()
if files:
    rows = [{"File": p.name,
             "Modified": pd.to_datetime(p.stat().st_mtime, unit="s").strftime("%Y-%m-%d %H:%M")}
            for p in files]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No reports loaded.")