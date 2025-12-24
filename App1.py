import streamlit as st
import pandas as pd
import requests
import math
from scipy.stats import norm
from datetime import datetime

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="NBA Pro Analyst Real", layout="wide", page_icon="🏀")

st.markdown("""
<style>
    .value-box-green { background-color: #d4edda; color: #155724; padding: 15px; border-radius: 8px; border: 1px solid #c3e6cb; text-align: center; font-weight: bold; }
    .value-box-red { background-color: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; border: 1px solid #f5c6cb; text-align: center; font-weight: bold; }
    .quiz-container { background-color: #fff3e0; padding: 10px; border-radius: 5px; border-left: 4px solid #ff9800; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# --- DATABASE STATISTICHE NBA 2024-25 (Aggiornato Stima Media) ---
# Questo dizionario mappa il nome della squadra (come scritto nelle API) alle sue stats.
# Puoi aggiornarlo mensilmente da siti come Basketball Reference.
NBA_STATS = {
    "Boston Celtics": {"off": 122.5, "def": 110.8, "pace": 98.5},
    "Denver Nuggets": {"off": 118.2, "def": 114.5, "pace": 97.2},
    "Milwaukee Bucks": {"off": 120.5, "def": 116.8, "pace": 101.5},
    "Philadelphia 76ers": {"off": 115.5, "def": 113.5, "pace": 98.0},
    "Minnesota Timberwolves": {"off": 114.8, "def": 108.5, "pace": 98.5},
    "Oklahoma City Thunder": {"off": 119.5, "def": 111.0, "pace": 100.5},
    "L.A. Clippers": {"off": 118.8, "def": 115.2, "pace": 97.8},
    "Phoenix Suns": {"off": 117.5, "def": 115.0, "pace": 99.0},
    "New York Knicks": {"off": 116.5, "def": 114.2, "pace": 96.5},
    "Cleveland Cavaliers": {"off": 115.0, "def": 112.5, "pace": 97.5},
    "Dallas Mavericks": {"off": 118.5, "def": 116.0, "pace": 101.0},
    "New Orleans Pelicans": {"off": 116.8, "def": 113.5, "pace": 99.5},
    "Indiana Pacers": {"off": 121.5, "def": 119.5, "pace": 103.0},
    "Sacramento Kings": {"off": 117.0, "def": 116.5, "pace": 100.5},
    "Orlando Magic": {"off": 113.5, "def": 111.5, "pace": 97.5},
    "Miami Heat": {"off": 113.0, "def": 111.8, "pace": 96.8},
    "Los Angeles Lakers": {"off": 115.8, "def": 116.2, "pace": 102.5},
    "Golden State Warriors": {"off": 118.0, "def": 115.5, "pace": 99.8},
    "Houston Rockets": {"off": 114.5, "def": 113.8, "pace": 99.5},
    "Atlanta Hawks": {"off": 119.0, "def": 120.5, "pace": 101.5},
    "Brooklyn Nets": {"off": 114.0, "def": 116.5, "pace": 98.0},
    "Utah Jazz": {"off": 115.5, "def": 119.5, "pace": 99.5},
    "Memphis Grizzlies": {"off": 108.5, "def": 113.0, "pace": 98.5},
    "Toronto Raptors": {"off": 114.0, "def": 118.5, "pace": 100.5},
    "Chicago Bulls": {"off": 113.5, "def": 116.0, "pace": 97.5},
    "Charlotte Hornets": {"off": 109.5, "def": 119.8, "pace": 98.5},
    "Portland Trail Blazers": {"off": 108.5, "def": 117.5, "pace": 98.0},
    "San Antonio Spurs": {"off": 111.5, "def": 116.5, "pace": 102.0},
    "Washington Wizards": {"off": 111.8, "def": 120.5, "pace": 103.5},
    "Detroit Pistons": {"off": 110.5, "def": 119.0, "pace": 100.0}
}

# Funzione per trovare la squadra nel DB gestendo nomi diversi
def get_team_stats(name):
    # Mapping manuale per nomi API vs nomi Database
    mapping = {
        "Los Angeles Clippers": "L.A. Clippers",
        # Aggiungi qui altri se l'API usa nomi diversi
    }
    name = mapping.get(name, name)
    return NBA_STATS.get(name, {"off": 114.0, "def": 114.0, "pace": 99.0}) # Default medio

# --- API REAL ---
@st.cache_data(ttl=3600)
def get_nba_games_real(api_key):
    # SPORT KEY per NBA: 'basketball_nba'
    url = f"https://api.the-odds-api.com/v4/sports/basketball_nba/odds"
    params = {
        'apiKey': api_key,
        'regions': 'eu', # Bookmaker europei
        'markets': 'h2h', # Solo vincente per ora, spread li calcoliamo noi
        'oddsFormat': 'decimal'
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        # Filtra eventuali messaggi di errore
        if 'message' in data:
            st.error(f"Errore API: {data['message']}")
            return []
            
        return data
    except Exception as e:
        st.error(f"Errore connessione: {e}")
        return []

# --- MOTORE GAUSSIANO ---
def calcola_prob_nba(proj_h, proj_a, std_dev=12.5):
    diff = proj_h - proj_a
    total = proj_h + proj_a
    
    # Moneyline
    prob_h = norm.cdf(diff, loc=0, scale=std_dev)
    
    # Spreads dinamici
    spreads = {}
    for line in [-9.5, -6.5, -3.5, 3.5, 6.5, 9.5]:
        p = 1 - norm.cdf(line, loc=diff, scale=std_dev)
        key = f"Casa {line}" if line < 0 else f"Casa +{line}"
        spreads[key] = p
        
    # Totals dinamici
    totals = {}
    base_line = round(total / 5) * 5 # Arrotonda ai 5 più vicini
    lines = [base_line - 10, base_line, base_line + 10]
    for line in lines:
        p_over = 1 - norm.cdf(line, loc=total, scale=18.0)
        totals[f"Over {line}"] = p_over
        totals[f"Under {line}"] = 1 - p_over

    return {"ML_Home": prob_h, "Spreads": spreads, "Totals": totals, "Score": (proj_h, proj_a)}

# --- QUIZ ---
def quiz_nba(name, k):
    m = 1.0
    st.markdown(f"**{name}**")
    c1, c2 = st.columns(2)
    with c1:
        if st.checkbox("Back-to-Back (Ieri)", key=f"b2b_{k}"): m -= 0.06
    with c2:
        if st.checkbox("Assenza Star", key=f"star_{k}"): m -= 0.12
    return m

# --- MAIN ---
def main():
    st.sidebar.title("🏀 NBA Real Time")
    api_key = st.sidebar.text_input("Inserisci API Key (The-Odds-API)", type="password")
    
    st.title("🏀 NBA Value Bet - Dati Reali")
    st.info("Utilizza calendario e quote reali di The-Odds-API + Database Stats 2025.")

    if not api_key:
        st.warning("Prendi una chiave gratis su the-odds-api.com per iniziare.")
        return

    matches = get_nba_games_real(api_key)
    
    if not matches:
        st.write("Nessuna partita trovata al momento o chiave errata.")
        return

    st.write(f"Trovate **{len(matches)}** partite in programma.")
    st.divider()

    for i, m in enumerate(matches):
        h_name = m['home_team']
        a_name = m['away_team']
        start_time = datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ").strftime("%H:%M")

        # Recupera Stats dal DB interno
        s_h = get_team_stats(h_name)
        s_a = get_team_stats(a_name)
        
        # Recupera quota reale (se disponibile)
        try:
            # Prende la prima quota disponibile dal primo bookmaker
            odds_h = m['bookmakers'][0]['markets'][0]['outcomes'][0]['price']
            odds_a = m['bookmakers'][0]['markets'][0]['outcomes'][1]['price']
            # Verifica che outcomes[0] sia davvero la casa (a volte l'ordine cambia)
            if m['bookmakers'][0]['markets'][0]['outcomes'][0]['name'] != h_name:
                odds_h, odds_a = odds_a, odds_h
        except:
            odds_h, odds_a = 1.90, 1.90 # Default se non trova quote

        with st.expander(f"⏰ {start_time} | {h_name} vs {a_name}"):
            # 1. QUIZ
            colQ1, colQ2 = st.columns(2)
            with colQ1: 
                st.markdown('<div class="quiz-container">', unsafe_allow_html=True)
                mod_h = quiz_nba(h_name, f"h_{i}")
                st.markdown('</div>', unsafe_allow_html=True)
            with colQ2: 
                st.markdown('<div class="quiz-container">', unsafe_allow_html=True)
                mod_a = quiz_nba(a_name, f"a_{i}")
                st.markdown('</div>', unsafe_allow_html=True)
            
            # 2. CALCOLO
            avg_pace = (s_h['pace'] + s_a['pace']) / 2
            score_h = ((s_h['off'] + s_a['def'])/2) * (avg_pace/100) * mod_h + 3.0 # +3 Casa
            score_a = ((s_a['off'] + s_h['def'])/2) * (avg_pace/100) * mod_a
            
            data = calcola_prob_nba(score_h, score_a)
            
            # 3. RISULTATI
            c1, c2, c3 = st.columns([1,2,1])
            with c1:
                st.metric("Previsto", f"{int(score_h)} - {int(score_a)}")
                st.caption(f"Totale: {int(score_h+score_a)}")
            with c2:
                prob_h = data['ML_Home']
                st.progress(prob_h, text=f"Vittoria Casa: {prob_h*100:.1f}%")
            with c3:
                # Value Check Automatico sulla Vittoria
                fair_h = 1/prob_h if prob_h > 0 else 99
                ev = (prob_h * odds_h) - 1
                color = "green" if ev > 0 else "red"
                st.markdown(f"<div style='color:{color}; font-weight:bold'>Quota Casa: {odds_h}</div>", unsafe_allow_html=True)
                st.caption(f"Fair Value: {fair_h:.2f}")

            # 4. TABELLA DETTAGLIATA
            st.write("---")
            st.write("**Analisi Spread & Totali**")
            cols = st.columns(4)
            # Mostra alcuni spread interessanti
            keys = list(data['Spreads'].keys())[:4]
            for idx, k in enumerate(keys):
                cols[idx].metric(k, f"{data['Spreads'][k]*100:.0f}%")

if __name__ == "__main__":
    main()