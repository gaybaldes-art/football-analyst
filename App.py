import streamlit as st
import pandas as pd
import requests
import math
from datetime import datetime, timedelta

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Value Bet Finder V7", layout="wide", page_icon="💎")

st.markdown("""
<style>
    .value-box-green { background-color: #d4edda; color: #155724; padding: 15px; border-radius: 8px; border: 1px solid #c3e6cb; text-align: center; font-weight: bold; }
    .value-box-red { background-color: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; border: 1px solid #f5c6cb; text-align: center; font-weight: bold; }
    .quiz-container { background-color: #f8f9fa; padding: 10px; border-radius: 5px; margin-bottom: 5px; border-left: 4px solid #6c757d; }
    .stRadio > label { font-weight: bold; font-size: 16px; }
</style>
""", unsafe_allow_html=True)

# --- MOTORE MATEMATICO ---
def poisson(k, lamb):
    return (lamb**k * math.exp(-lamb)) / math.factorial(k)

def calcola_probabilita_v7(xg_home, xg_away):
    markets = {"1":0, "X":0, "2":0, "Over 2.5":0, "Goal":0}
    for h in range(10):
        for a in range(10):
            p = poisson(h, xg_home) * poisson(a, xg_away)
            if h > a: markets["1"] += p
            elif h == a: markets["X"] += p
            else: markets["2"] += p
            if (h+a) > 2.5: markets["Over 2.5"] += p
            if h > 0 and a > 0: markets["Goal"] += p
    return {k: v for k,v in markets.items()} # Restituisce probabilità pure (0.0 - 1.0)

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

# --- QUIZ ORIZZONTALE ---
def quiz_rapido(team_name, key_id):
    moltiplicatore = 1.0
    st.markdown(f"**🕵️ Analisi {team_name}**")
    
    # Domanda 1
    col1, col2 = st.columns([1, 2])
    with col1: st.write("🎯 Motivazione?")
    with col2: 
        mot = st.radio("mot", ["Normale", "🔥 Alta (Salvezza/Titolo)", "😴 Bassa (Fine Stagione)"], 
                       key=f"m_{key_id}", horizontal=True, label_visibility="collapsed")
        if "Alta" in mot: moltiplicatore *= 1.15
        elif "Bassa" in mot: moltiplicatore *= 0.85

    # Domanda 2
    col3, col4 = st.columns([1, 2])
    with col3: st.write("🚑 Rosa/Assenti?")
    with col4:
        ros = st.radio("ros", ["✅ Completa", "⚠️ Manca Top Player", "🚑 Emergenza Totale"], 
                       key=f"r_{key_id}", horizontal=True, label_visibility="collapsed")
        if "Manca" in ros: moltiplicatore *= 0.85
        elif "Emergenza" in ros: moltiplicatore *= 0.70

    # Domanda 3
    col5, col6 = st.columns([1, 2])
    with col5: st.write("🔋 Stanchezza?")
    with col6:
        stanc = st.checkbox("Hanno giocato le Coppe < 3gg fa?", key=f"s_{key_id}")
        if stanc: moltiplicatore *= 0.90
        
    st.divider()
    return moltiplicatore

# --- MAIN ---
def main():
    st.sidebar.title("💎 Value Bet Hunter")
    api_key = st.sidebar.text_input("🔑 API Key", type="password")
    day = st.sidebar.date_input("📅 Data", datetime.now())

    if not api_key: return

    matches, db = get_data(api_key, day)
    if not matches: st.error("Nessuna partita."); return

    comps = list(set([m['competition']['name'] for m in matches]))
    sel_comp = st.sidebar.multiselect("Campionati", comps, default=comps)
    clean = [m for m in matches if m['competition']['name'] in sel_comp]

    st.info("💡 CONSIGLIO: Compila il Quiz per raffinare le percentuali, POI inserisci la quota del Bookmaker per scoprire se è una Value Bet.")

    for m in clean:
        h, a = m['homeTeam'], m['awayTeam']
        hid, aid = h['id'], a['id']
        
        # Stats Base
        hs = db.get(hid, {'gf':1.2, 'ga':1.2})
        as_ = db.get(aid, {'gf':1.0, 'ga':1.0})
        
        xg_h_base = hs['gf'] * as_['ga'] * 1.15
        xg_a_base = as_['gf'] * hs['ga']

        # --- BOX PARTITA ---
        with st.expander(f"⚽ {h['name']} vs {a['name']}", expanded=False):
            
            # 1. IL QUIZ
            c_quiz1, c_quiz2 = st.columns(2)
            with c_quiz1: mh = quiz_rapido(h['name'], hid)
            with c_quiz2: ma = quiz_rapido(a['name'], aid)
            
            # Calcolo Live
            xg_h = xg_h_base * mh
            xg_a = xg_a_base * ma
            probs = calcola_probabilita_v7(xg_h, xg_a)
            
            # Visualizza Percentuali AI
            st.write("📊 **Probabilità Calcolate dal Modello (AI):**")
            c_p1, c_p2, c_p3, c_p4 = st.columns(4)
            c_p1.metric("1 (Casa)", f"{probs['1']*100:.1f}%")
            c_p2.metric("X (Pari)", f"{probs['X']*100:.1f}%")
            c_p3.metric("2 (Ospite)", f"{probs['2']*100:.1f}%")
            c_p4.metric("Over 2.5", f"{probs['Over 2.5']*100:.1f}%")

            st.markdown("---")
            
            # 2. IL CALCOLATORE VALUE BET
            st.subheader("💰 Caccia al Valore (Value Bet Detector)")
            
            col_v1, col_v2, col_v3 = st.columns([1, 1, 2])
            
            with col_v1:
                scelta = st.selectbox("Su cosa vuoi scommettere?", ["1", "X", "2", "Over 2.5", "Goal"], key=f"sel_{hid}")
            
            with col_v2:
                quota_book = st.number_input("Inserisci Quota Bookmaker", min_value=1.01, value=1.50, step=0.01, key=f"q_{hid}")
            
            with col_v3:
                # LOGICA VALUE BET
                prob_ai = probs[scelta] # Es. 0.60
                quota_reale_ai = 1 / prob_ai if prob_ai > 0 else 99 # Es. 1 / 0.60 = 1.66
                
                # EV (Expected Value)
                ev = (prob_ai * quota_book) - 1
                ev_perc = ev * 100
                
                st.write("") # Spazio vuoto per allineamento
                if ev > 0.05: # Soglia del 5% di vantaggio
                    st.markdown(f"""
                    <div class="value-box-green">
                        ✅ VALUE BET TROVATA!<br>
                        Vantaggio: +{ev_perc:.1f}%<br>
                        <small>La quota giusta sarebbe {quota_reale_ai:.2f}, ma ti pagano {quota_book}!</small>
                    </div>
                    """, unsafe_allow_html=True)
                elif ev >= 0:
                    st.warning(f"⚖️ Quota Giusta (Nessun vantaggio reale). Edge: {ev_perc:.1f}%")
                else:
                    st.markdown(f"""
                    <div class="value-box-red">
                        ⛔ TRAPPOLA (No Bet)<br>
                        Svantaggio: {ev_perc:.1f}%<br>
                        <small>Non scommettere sotto quota {quota_reale_ai:.2f}</small>
                    </div>
                    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()