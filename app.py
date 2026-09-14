
import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="EdgeBoard V2", page_icon="📱", layout="centered")

st.markdown("""
<style>
    .block-container {max-width: 760px; padding-top: 1rem; padding-bottom: 5rem;}
    .bet-card {
        border: 1px solid rgba(128,128,128,.28);
        border-radius: 16px;
        padding: 14px 14px 10px 14px;
        margin-bottom: 12px;
    }
    .grade {
        font-size: 0.85rem;
        font-weight: 700;
        padding: 4px 8px;
        border-radius: 999px;
        border: 1px solid rgba(128,128,128,.35);
        display: inline-block;
    }
    .small {font-size: .86rem; opacity: .78;}
    .muted {opacity: .67;}
    .metric-row {display:flex; gap:18px; flex-wrap:wrap; margin-top:8px;}
    .metric-box {min-width:95px;}
    .metric-label {font-size:.72rem; opacity:.64;}
    .metric-val {font-size:1.03rem; font-weight:650;}
    div[data-testid="stTabs"] button {font-size: 0.9rem;}
    .stButton>button {border-radius: 12px; width: 100%;}
</style>
""", unsafe_allow_html=True)

# ---------------- DEMO DATA ----------------
bets = pd.DataFrame([
    {
        "id":1,"sport":"CFB","game":"Alabama @ Tennessee","market":"Spread","selection":"Alabama -4.5",
        "model":"Alabama -7.1","prob":57.9,"edge":"2.6 pts","ev":7.2,"grade":"A","stake":"1.0u",
        "fd_line":"-4.5","fd_price":"-110","b365_line":"-5","b365_price":"-105","best_book":"FanDuel",
        "why":"Model projects a stronger Alabama efficiency edge than the market, with a favorable matchup in early-down success rate."
    },
    {
        "id":2,"sport":"NFL","game":"Bills @ Dolphins","market":"1H Spread","selection":"Bills -1.5",
        "model":"Bills -2.8","prob":55.6,"edge":"1.3 pts","ev":5.1,"grade":"A-","stake":"0.75u",
        "fd_line":"-1.5","fd_price":"-110","b365_line":"-2","b365_price":"+100","best_book":"FanDuel",
        "why":"Buffalo rates better in scripted-drive efficiency and early-down passing; Miami's edge improves later in games."
    },
    {
        "id":3,"sport":"NBA","game":"Knicks @ Celtics","market":"Player Prop","selection":"Player A O 24.5 Points",
        "model":"26.8 pts","prob":56.8,"edge":"2.3 pts","ev":5.9,"grade":"A-","stake":"0.75u",
        "fd_line":"24.5","fd_price":"-115","b365_line":"25.5","b365_price":"-105","best_book":"FanDuel",
        "why":"Projected minutes and usage create a median outcome above the market line, even after adjusting for opponent defense."
    },
    {
        "id":4,"sport":"CBB","game":"Duke @ UNC","market":"Total","selection":"Over 148.5",
        "model":"152.0","prob":55.2,"edge":"3.5 pts","ev":4.4,"grade":"B+","stake":"0.5u",
        "fd_line":"148.5","fd_price":"-110","b365_line":"149","b365_price":"-105","best_book":"FanDuel",
        "why":"Both teams project above average in transition frequency and free-throw rate; pace model lands above consensus."
    },
    {
        "id":5,"sport":"Soccer","game":"Arsenal vs Chelsea","market":"Moneyline","selection":"Arsenal ML",
        "model":"Fair +102","prob":52.8,"edge":"Price edge","ev":3.8,"grade":"B","stake":"0.5u",
        "fd_line":"+110","fd_price":"+110","b365_line":"+105","b365_price":"+105","best_book":"FanDuel",
        "why":"Expected-goals projection makes Arsenal a slightly stronger favorite than the current market price implies."
    },
    {
        "id":6,"sport":"Soccer","game":"Inter Miami vs Orlando","market":"Total","selection":"Over 2.5",
        "model":"3.05 goals","prob":55.1,"edge":"0.55 goals","ev":3.0,"grade":"B","stake":"0.5u",
        "fd_line":"2.5","fd_price":"-125","b365_line":"2.5","b365_price":"-120","best_book":"bet365",
        "why":"Both attack models project higher-quality chances than average; bet365 offers the better price at the same total."
    },
])

if "my_bets" not in st.session_state:
    st.session_state.my_bets = []

# ---------------- HEADER ----------------
top1, top2 = st.columns([3,1])
with top1:
    st.title("📱 EdgeBoard")
    st.caption("V2 mobile prototype • demo data only")
with top2:
    st.write("")
    st.write("")
    if st.button("↻ Refresh"):
        st.toast("Demo board refreshed")

sports = ["All"] + sorted(bets["sport"].unique().tolist())
sport_filter = st.segmented_control("Sport", sports, default="All")
if sport_filter != "All":
    filtered = bets[bets["sport"] == sport_filter].copy()
else:
    filtered = bets.copy()

tab_best, tab_games, tab_props, tab_track, tab_info = st.tabs(
    ["🔥 Best", "🏟 Games", "🧍 Props", "🧾 My Bets", "🧠 Info"]
)

def render_card(row):
    st.markdown(f"""
    <div class="bet-card">
        <div class="small">{row['sport']} • {row['game']} • {row['market']}</div>
        <h3 style="margin:.35rem 0 .25rem 0">{row['selection']}</h3>
        <span class="grade">{row['grade']} • {row['stake']}</span>
        <div class="metric-row">
            <div class="metric-box"><div class="metric-label">MODEL</div><div class="metric-val">{row['model']}</div></div>
            <div class="metric-box"><div class="metric-label">PROBABILITY</div><div class="metric-val">{row['prob']:.1f}%</div></div>
            <div class="metric-box"><div class="metric-label">EST. EV</div><div class="metric-val">+{row['ev']:.1f}%</div></div>
        </div>
        <div style="margin-top:8px"><b>Best book:</b> {row['best_book']}</div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("Compare books + why"):
        comp = pd.DataFrame({
            "Book":["FanDuel","bet365"],
            "Line":[row["fd_line"],row["b365_line"]],
            "Price":[row["fd_price"],row["b365_price"]]
        })
        st.dataframe(comp, use_container_width=True, hide_index=True)
        st.caption(row["why"])

    c1, c2 = st.columns(2)
    with c1:
        if st.button("＋ Track bet", key=f"track_{row['id']}"):
            if row["id"] not in [x["id"] for x in st.session_state.my_bets]:
                st.session_state.my_bets.append(row.to_dict())
                st.toast("Added to My Bets")
            else:
                st.toast("Already tracking this one")
    with c2:
        st.button(f"Open {row['best_book']} ↗", key=f"open_{row['id']}", disabled=True, help="Placeholder for future sportsbook deep link")

with tab_best:
    st.subheader("Top plays")
    min_grade = st.selectbox("Show", ["A/B plays","A plays only","Everything"], index=0)
    view = filtered.copy()
    if min_grade == "A plays only":
        view = view[view["grade"].isin(["A","A-"])]
    elif min_grade == "A/B plays":
        view = view[view["grade"] != "PASS"]
    view = view.sort_values("ev", ascending=False)

    for _, row in view.iterrows():
        render_card(row)

with tab_games:
    st.subheader("Game board")
    game_groups = filtered.groupby(["sport","game"], sort=False)
    for (sport, game), grp in game_groups:
        with st.expander(f"{sport} • {game}"):
            for _, row in grp.iterrows():
                st.markdown(f"**{row['market']} — {row['selection']}**")
                st.caption(f"Model: {row['model']} • {row['prob']:.1f}% • EV +{row['ev']:.1f}% • Best: {row['best_book']}")
                st.divider()

with tab_props:
    st.subheader("Player props")
    props = filtered[filtered["market"] == "Player Prop"]
    if props.empty:
        st.info("No demo props for this sport yet.")
    else:
        for _, row in props.iterrows():
            render_card(row)

with tab_track:
    st.subheader("My Bets")
    if not st.session_state.my_bets:
        st.info("Tap “Track bet” on any recommendation to put it here.")
    else:
        for i, item in enumerate(list(st.session_state.my_bets)):
            st.markdown(f"**{item['selection']}**  \n{item['sport']} • {item['game']} • {item['best_book']} • {item['stake']}")
            result = st.selectbox("Result", ["Pending","Win","Loss","Push"], key=f"result_{item['id']}")
            c1, c2 = st.columns(2)
            with c1:
                amount = st.number_input("Wager $", min_value=0.0, step=5.0, key=f"amt_{item['id']}")
            with c2:
                st.text_input("Odds", value=item["fd_price"] if item["best_book"]=="FanDuel" else item["b365_price"], key=f"odds_{item['id']}")
            if st.button("Remove", key=f"remove_{item['id']}"):
                st.session_state.my_bets = [x for x in st.session_state.my_bets if x["id"] != item["id"]]
                st.rerun()
            st.divider()

with tab_info:
    st.subheader("How V2 is supposed to work")
    st.markdown("""
    **You should never need Python to use the finished product.**

    1. EdgeBoard pulls current markets from **FanDuel + bet365**.
    2. Each sport-specific model estimates a fair score, margin, total, price or prop distribution.
    3. The app compares the model to each book.
    4. It ranks only the strongest differences.
    5. You choose what you actually bet and add it to **My Bets**.
    6. EdgeBoard tracks your results separately from the model's full record.
    """)
    st.markdown("#### Planned V3 plumbing")
    st.write("• Live sportsbook odds feed")
    st.write("• Real CFB model first")
    st.write("• Automatic line-movement snapshots")
    st.write("• Real results grading")
    st.write("• Mobile install/PWA behavior")
    st.write("• Sportsbook deep links where practical")
    st.warning("All V2 recommendations and prices are synthetic examples. Do not wager from them.")

st.caption("EdgeBoard V2 • Mobile-first product prototype")
