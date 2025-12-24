import streamlit as st
import pandas as pd
import requests
import math
from datetime import datetime, timedelta

# --- CONFIGURAZIONE E STILE ---
st.set_page_config(page_title="Ultimate Value Bet V8", layout="wide", page_icon="💰")

st.markdown("""
<style>
    .value-box-green { background-color: #d4edda; color: #155724; padding: 15px; border-radius: 8px; border: 1px solid #c3e6cb; text-align: center; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .value-box-red { background-color: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; border: 1px solid #f5c6cb; text-align: center; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .value-box-neutral { background-color: #fff3cd; color: #856404; padding: 15px; border-radius: 8px; border: 1px solid #ffeeba; text-align: center; font-weight: bold; }
    .quiz-container { background-color: #f8f9fa; padding: 10px; border-radius: 5px; border-left: 4px solid #007bff; margin-bottom: 10px; }
    div[data-testid="stExpander"] div[role="button"] p { font-size: 1.1rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# --- MOTORE MATEMATICO AVANZATO (MATRIX) ---
def poisson(k, lamb):
    return (lamb**k * math.exp(-lamb)) / math.factorial(k)

def calcola_tutte_probabilita(xg_home, xg_away):
    """
    Genera la matrice 10x10 e calcola le probabilità per TUTTI i mercati richiesti.
    """
    markets = {
        # Principali
        "1": 0, "X": 0, "2": 0,
        "1X": 0, "X2": 0, "12": 0,
        "Goal": 0, "NoGoal": 0,
        # Under / Over
        "Over 1.5": 0, "Under 1.5": 0,
        "Over 2.5": 0, "Under 2.5": 0,
        "Over 3.5": 0, "Under 3.5": 0,
        # Multigoal Match
        "MG 1-3": 0, "MG 2-4": 0, "MG 2-5": 0,
        # Multigoal Casa
        "Casa MG 1-2": 0, "Casa MG 1-3": 0, "Casa MG 2+": 0,
        # Multigoal Ospite
        "Ospite MG 1-2": 0, "Ospite MG 1-3": 0, "Ospite MG 2+": 0,
        # Combo
        "1 + Over 1.5": 0, "1 + Under 3.5": 0, "1 + Goal": 0,
        "X + Goal": 0, "X + Under 2.5": 0,
        "2 + Over 1.5": 0, "2 + Under 3.5": 0, "2 + Goal": 0,
        "1X + Over 1.5": 0, "X2 + Over 1.5": 0, "12 + Over 1.5": 0,
        "Goal + Over 2.5": 0
    }

    # Ciclo su risultati esatti da 0-0 a 9-9
    for h in range(10):
        for a in range(10):
            prob = poisson(h, xg_home) * poisson(a, xg_away)
            tot = h + a
            
            # --- 1X2 & DC ---
            if h > a: 
                markets["1"] += prob
                markets["1X"] += prob
                markets["12"] += prob
            elif h == a: 
                markets["X"] += prob
                markets["1X"] += prob
                markets["X2"] += prob
            else: 
                markets["2"] += prob
                markets["X2"] += prob
                markets["12"] += prob
            
            # --- GOAL / NOGOAL ---
            if h > 0 and a > 0: markets["Goal"] += prob
            else: markets["NoGoal"] += prob

            # --- U/O ---
            if tot > 1.5: markets["Over 1.5"] += prob
            else: markets["Under 1.5"] += prob
            
            if tot > 2.5: markets["Over 2.5"] += prob
            else: markets["Under 2.5"] += prob
            
            if tot > 3.5: markets["Over 3.5"] += prob
            else: markets["Under 3.5"] += prob

            # --- MULTIGOAL ---
            if 1 <= tot <= 3: markets["MG 1-3"] += prob
            if 2 <= tot <= 4: markets["MG 2-4"] += prob
            if 2 <= tot <= 5: markets["MG 2-5"] += prob

            # --- SQUADRE ---
            if 1 <= h <= 2: markets["Casa MG 1-2"] += prob
            if 1 <= h <= 3: markets["Casa MG 1-3"] += prob
            if h >= 2: markets["Casa MG 2+"] += prob

            if 1 <= a <= 2: markets["Ospite MG 1-2"] += prob
            if 1 <= a <= 3: markets["Ospite MG 1-3"] += prob
            if a >= 2: markets["Ospite MG 2+"] += prob

            # --- COMBO ---
            # 1 + ...
            if h > a and tot > 1.5: markets["1 + Over 1.5"] += prob
            if h > a and tot < 3.5: markets["1 + Under 3.5"] += prob
            if h > a and h > 0 and a > 0: markets["1 + Goal"] += prob
            
            # 2 + ...
            if a > h and tot > 1.5: markets["2 + Over 1.5"] += prob
            if a > h and tot < 3.5: markets["2 + Under 3.5"] += prob
            if a > h and h > 0 and a > 0: markets["2 + Goal"] += prob
            
            # X + ...
            if h == a and h > 0 and a > 0: markets["X + Goal"] += prob
            if h == a and tot < 2.5: markets["X + Under 2.5"] += prob
            
            # DC + Over
            if h >= a and tot > 1.5: markets["1X + Over 1.5"] += prob
            if a >= h and tot > 1.5: markets["X2 + Over 1.5"] += prob
            if h != a and tot > 1.5: markets["12 + Over 1.5"] += prob
            
            # Goal + Over
            if h > 0 and a > 0 and tot > 2.5: markets["Goal + Over 2.5"] += prob

    return markets # Restituisce probabilità pure (0.0 - 1.0)

# --- API ---
@st.cache_data(ttl=3600)
def get_data(api_key, date_obj):
    headers = {'X-Auth-Token': api_key}
    d_str = date_obj.strftime("%Y-%m-%d")
    d_to = (date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        url = f"https://api.football-data.org/v4/matches?dateFrom={d_str}&dateTo={d_to}"
        matches = requests.get(url, headers=headers).json().get('matches', [])
        cids = set([m['competition']['id'] for m in matches])
        db = {}
        for cid in cids:
            res = requests.get(f"https://api.football-data.org/v4/competitions/{cid}/standings", headers=headers).json()
            if 'standings' in res:
                for row in res['standings'][0]['table']:
                    db[row['team']['id']] = {
                        'gf': row['goalsFor']/row['playedGames'],
                        'ga': row['goalsAgainst']/row['playedGames']
                    }
        return matches, db
    except: return [], {}

# --- UI COMPONENTI ---
def quiz_rapido_orizzontale(team_name, key_id):
    molt = 1.0
    st.markdown(f"**🕵️ {team_name}**")
    
    # Riga unica per compattezza
    c1, c2, c3 = st.columns(3)
    
    with c1:
        mot = st.radio("Motivazione", ["Media", "🔥 Alta", "😴 Bassa"], 
                       key=f"m_{key_id}", label_visibility="collapsed", horizontal=False)
        if "Alta" in mot: molt *= 1.15
        elif "Bassa" in mot: molt *= 0.85
        st.caption("Motivazione")

    with c2:
        ros = st.radio("Rosa", ["✅ Ok", "⚠️ No Big", "🚑 Emergenza"], 
                       key=f"r_{key_id}", label_visibility="collapsed", horizontal=False)
        if "No Big" in ros: molt *= 0.85
        elif "Emergenza" in ros: molt *= 0.70
        st.caption("Rosa")

    with c3:
        fat = st.checkbox("Stanchi?", key=f"f_{key_id}")
        if fat: molt *= 0.90
        st.caption("Coppe/Turnover")
        
    return molt

# --- MAIN ---
def main():
    st.sidebar.title("💰 Ultimate Value V8")
    st.sidebar.markdown("Combos, Multigoal e Value Detector")
    api_key = st.sidebar.text_input("🔑 API Key", type="password")
    day = st.sidebar.date_input("📅 Data Partite", datetime.now())

    if not api_key: return

    with st.spinner("Analisi mercati in corso..."):
        matches, db = get_data(api_key, day)
    
    if not matches: st.error("Nessuna partita."); return

    comps = list(set([m['competition']['name'] for m in matches]))
    sel_comp = st.sidebar.multiselect("Campionati", comps, default=comps)
    clean = [m for m in matches if m['competition']['name'] in sel_comp]

    st.markdown("---")

    for m in clean:
        h, a = m['homeTeam'], m['awayTeam']
        hid, aid = h['id'], a['id']
        
        hs = db.get(hid, {'gf':1.2, 'ga':1.2})
        as_ = db.get(aid, {'gf':1.0, 'ga':1.0})
        
        xg_h_base = hs['gf'] * as_['ga'] * 1.15
        xg_a_base = as_['gf'] * hs['ga']

        # --- CARD PARTITA ---
        with st.expander(f"⚽ {h['name']} vs {a['name']}", expanded=False):
            
            # 1. QUIZ
            col_q1, col_q2 = st.columns(2)
            with col_q1: 
                st.markdown('<div class="quiz-container">', unsafe_allow_html=True)
                mh = quiz_rapido_orizzontale(h['name'], hid)
                st.markdown('</div>', unsafe_allow_html=True)
            with col_q2: 
                st.markdown('<div class="quiz-container">', unsafe_allow_html=True)
                ma = quiz_rapido_orizzontale(a['name'], aid)
                st.markdown('</div>', unsafe_allow_html=True)

            # 2. CALCOLO MATRICE
            xg_h = xg_h_base * mh
            xg_a = xg_a_base * ma
            
            # Calcoliamo TUTTE le probabilità
            probs = calcola_tutte_probabilita(xg_h, xg_a)

            st.divider()

            # 3. VALUE BET DETECTOR (Il cuore della richiesta)
            st.markdown("### 💎 Value Bet Detector (Tutti i mercati)")
            st.caption("Scegli un mercato (anche Combo o Multigoal), inserisci la quota e scopri se conviene.")

            # Layout: Selezione | Input Quota | Risultato
            c_sel, c_quo, c_res = st.columns([2, 1, 2])
            
            with c_sel:
                # Ordiniamo le chiavi per trovarle meglio
                options = sorted(list(probs.keys()))
                # Mettiamo i più comuni in cima per comodità
                priority = ["1", "X", "2", "Over 2.5", "Goal", "1X", "X2"]
                sorted_options = priority + [k for k in options if k not in priority]
                
                market_choice = st.selectbox("Mercato", sorted_options, key=f"s_{hid}")
            
            with c_quo:
                quota_input = st.number_input("Quota Bookmaker", min_value=1.01, value=1.80, step=0.05, key=f"q_{hid}")

            with c_res:
                real_prob = probs[market_choice]
                fair_odd = 1 / real_prob if real_prob > 0 else 99.0
                
                # Calcolo EV
                ev = (real_prob * quota_input) - 1
                ev_perc = ev * 100
                
                # Visualizzazione Risultato
                if ev > 0.02: # Margine 2%
                    st.markdown(f"""
                    <div class="value-box-green">
                        ✅ VALUE BET!<br>
                        Vantaggio: +{ev_perc:.1f}%<br>
                        <small>Quota Reale AI: {fair_odd:.2f}</small>
                    </div>
                    """, unsafe_allow_html=True)
                elif ev > -0.05:
                    st.markdown(f"""
                    <div class="value-box-neutral">
                        ⚖️ QUOTA GIUSTA<br>
                        Nessun vantaggio<br>
                        <small>Quota Reale AI: {fair_odd:.2f}</small>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="value-box-red">
                        ⛔ TRAPPOLA<br>
                        Svantaggio: {ev_perc:.1f}%<br>
                        <small>Dovrebbe pagare almeno {fair_odd:.2f}</small>
                    </div>
                    """, unsafe_allow_html=True)

            # 4. TABELLA RIEPILOGO RAPIDO
            st.markdown("---")
            st.caption("🔍 Panoramica Probabilità AI (Top Selections)")
            
            # Mostriamo solo le probabilità > 40% per non intasare
            top_picks = {k:v for k,v in probs.items() if v > 0.40}
            # Ordiniamo per probabilità decrescente
            top_sorted = sorted(top_picks.items(), key=lambda x: x[1], reverse=True)[:6]
            
            cols = st.columns(len(top_sorted))
            for idx, (mkt, p) in enumerate(top_sorted):
                with cols[idx]:
                    st.metric(mkt, f"{p*100:.0f}%")

if __name__ == "__main__":
    main()