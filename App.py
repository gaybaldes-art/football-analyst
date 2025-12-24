import streamlit as st
import pandas as pd
import requests
import math
from datetime import datetime, timedelta

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Pro Football Analyst V3", layout="wide", page_icon="📈")

# --- FUNZIONI MATEMATICHE (POISSON) ---

def poisson_probability(k, lamb):
    """Calcola la probabilità che accadano k eventi dato un valore atteso lamb."""
    return (lamb**k * math.exp(-lamb)) / math.factorial(k)

def calcola_probabilita_esatte(xg_home, xg_away):
    """
    Simula tutti i possibili risultati (fino a 6-6) usando Poisson
    per derivare le percentuali reali di 1X2, Over, Goal.
    """
    prob_home_win = 0
    prob_draw = 0
    prob_away_win = 0
    prob_over_2_5 = 0
    prob_btts = 0 # Both Teams To Score
    
    # Simuliamo punteggi da 0-0 a 6-6
    for h in range(7):
        for a in range(7):
            p = poisson_probability(h, xg_home) * poisson_probability(a, xg_away)
            
            # Accumula probabilità 1X2
            if h > a: prob_home_win += p
            elif h == a: prob_draw += p
            else: prob_away_win += p
            
            # Accumula probabilità Over 2.5
            if (h + a) > 2.5: prob_over_2_5 += p
            
            # Accumula BTTS (Goal)
            if h > 0 and a > 0: prob_btts += p

    return {
        "1": prob_home_win * 100,
        "X": prob_draw * 100,
        "2": prob_away_win * 100,
        "Over2.5": prob_over_2_5 * 100,
        "Under2.5": (1 - prob_over_2_5) * 100,
        "Goal": prob_btts * 100,
        "NoGoal": (1 - prob_btts) * 100
    }

# --- GESTIONE API E DATI ---

@st.cache_data(ttl=3600)
def get_standings(api_key, competition_id):
    url = f"https://api.football-data.org/v4/competitions/{competition_id}/standings"
    headers = {'X-Auth-Token': api_key}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        teams_stats = {}
        if 'standings' in data and len(data['standings']) > 0:
            table = data['standings'][0]['table']
            for row in table:
                team_id = row['team']['id']
                teams_stats[team_id] = {
                    'played': row['playedGames'],
                    'gf': row['goalsFor'],
                    'ga': row['goalsAgainst'],
                    'form_str': row.get('form', '')
                }
        return teams_stats
    except:
        return {}

def get_matches_by_date(api_key, date_obj):
    """Scarica le partite per una data specifica."""
    date_str = date_obj.strftime("%Y-%m-%d")
    date_to = (date_obj + timedelta(days=1)).strftime("%Y-%m-%d") # Prende una finestra di 1 giorno extra per sicurezza
    
    url = f"https://api.football-data.org/v4/matches?dateFrom={date_str}&dateTo={date_to}"
    headers = {'X-Auth-Token': api_key}
    
    try:
        response = requests.get(url, headers=headers)
        return response.json().get('matches', [])
    except:
        return []

def calculate_form_modifier(form_str):
    """Calcola un moltiplicatore basato sulla forma recente (W=Win, L=Loss)."""
    if not form_str: return 1.0
    
    score = 1.0
    # Analizza le ultime 5 partite (l'API le dà come stringa "W,L,D...")
    recent = form_str.split(',')[-5:] 
    for result in recent:
        if result == 'W': score += 0.05  # +5% forza per vittoria
        elif result == 'L': score -= 0.05 # -5% forza per sconfitta
    return score

def analyze_match_advanced(home_id, away_id, standings):
    """Analisi accurata basata su dati storici e Poisson."""
    
    # Recupera stats o usa valori medi di default
    h_stats = standings.get(home_id, {'played': 1, 'gf': 1.2, 'ga': 1.2, 'form_str': ''})
    a_stats = standings.get(away_id, {'played': 1, 'gf': 1.0, 'ga': 1.0, 'form_str': ''})
    
    h_played = max(h_stats['played'], 1)
    a_played = max(a_stats['played'], 1)

    # Forza Offensiva e Difensiva
    h_attack = (h_stats['gf'] / h_played)
    h_defense = (h_stats['ga'] / h_played)
    a_attack = (a_stats['gf'] / a_played)
    a_defense = (a_stats['ga'] / a_played)
    
    # Modificatori Forma
    h_form_mod = calculate_form_modifier(h_stats['form_str'])
    a_form_mod = calculate_form_modifier(a_stats['form_str'])

    # Calcolo Expected Goals (xG) per questo match
    # xG Casa = Attacco Casa * Difesa Ospite * Fattore Campo (1.15) * Forma
    xg_home = h_attack * a_defense * 1.15 * h_form_mod
    # xG Ospite = Attacco Ospite * Difesa Casa * Forma
    xg_away = a_attack * h_defense * a_form_mod
    
    # Calcolo Probabilità Percentuali
    probs = calcola_probabilita_esatte(xg_home, xg_away)
    
    # Determinazione BEST BET (La scommessa con % più alta sopra una soglia sicura)
    best_bet = "No Bet (Troppo Incerto)"
    best_prob = 0
    
    candidates = {
        "1 Fisso": probs['1'],
        "2 Fisso": probs['2'],
        "1X Doppia": probs['1'] + probs['X'],
        "X2 Doppia": probs['2'] + probs['X'],
        "Over 2.5": probs['Over2.5'],
        "Under 2.5": probs['Under2.5'],
        "Gol (GG)": probs['Goal']
    }
    
    # Filtro: cerchiamo la probabilità più alta > 55%
    sorted_bets = sorted(candidates.items(), key=lambda item: item[1], reverse=True)
    if sorted_bets[0][1] > 55:
        best_bet = sorted_bets[0][0]
        best_prob = sorted_bets[0][1]
    
    return {
        'xg_home': xg_home,
        'xg_away': xg_away,
        'probs': probs,
        'best_bet': best_bet,
        'best_prob': best_prob
    }

# --- INTERFACCIA ---

def main():
    st.sidebar.header("🔍 Filtri Analisi")
    
    # 1. INPUT API KEY
    api_key = st.sidebar.text_input("API Key football-data.org", type="password")
    
    # 2. SELEZIONE DATA
    selected_date = st.sidebar.date_input("Seleziona Data Partite", datetime.now())
    
    st.title("📈 AI Football Probability V3")
    st.markdown(f"Analisi probabilistica per le partite del: **{selected_date.strftime('%d/%m/%Y')}**")

    if not api_key:
        st.warning("Inserisci l'API Key nella barra laterale.")
        return

    # CARICAMENTO DATI
    with st.spinner("Scarico calendario e classifiche..."):
        all_matches = get_matches_by_date(api_key, selected_date)
        
        if not all_matches:
            st.error("Nessuna partita trovata in questa data o errore API.")
            return

        # 3. FILTRO CAMPIONATO (Dinamico)
        competitions = list(set([m['competition']['name'] for m in all_matches]))
        selected_comp = st.sidebar.multiselect("Filtra Campionato", competitions, default=competitions)
        
        # Filtra match
        matches = [m for m in all_matches if m['competition']['name'] in selected_comp]
        
        # Scarica classifiche necessarie
        comp_ids = set([m['competition']['id'] for m in matches])
        standings_db = {}
        for cid in comp_ids:
            standings_db[cid] = get_standings(api_key, cid)

    st.write(f"Analisi di **{len(matches)}** partite.")
    st.divider()

    # VISUALIZZAZIONE PARTITE
    for m in matches:
        h_name = m['homeTeam']['name']
        a_name = m['awayTeam']['name']
        comp_name = m['competition']['name']
        
        # Analisi
        data = analyze_match_advanced(
            m['homeTeam']['id'], 
            m['awayTeam']['id'], 
            standings_db.get(m['competition']['id'], {})
        )
        probs = data['probs']
        
        # LAYOUT CARD
        with st.container():
            # Intestazione Match
            st.markdown(f"#### 🏆 {comp_name} | {h_name} vs {a_name}")
            
            c1, c2, c3 = st.columns([1.5, 2, 1.5])
            
            # Colonna Sinistra: Statistiche Squadre
            with c1:
                st.caption("xG (Gol Attesi)")
                st.info(f"{h_name}: **{data['xg_home']:.2f}**")
                st.warning(f"{a_name}: **{data['xg_away']:.2f}**")
            
            # Colonna Centrale: Percentuali
            with c2:
                st.caption("Probabilità Esito Finale (Poisson)")
                
                # Barre Percentuali
                col_1, col_x, col_2 = st.columns(3)
                col_1.metric("1", f"{probs['1']:.1f}%")
                col_x.metric("X", f"{probs['X']:.1f}%")
                col_2.metric("2", f"{probs['2']:.1f}%")
                
                st.progress(int(probs['1']))
                
                st.caption("Probabilità Gol")
                col_o, col_u, col_gg = st.columns(3)
                col_o.metric("Over 2.5", f"{probs['Over2.5']:.1f}%")
                col_u.metric("Under 2.5", f"{probs['Under2.5']:.1f}%")
                col_gg.metric("Goal", f"{probs['Goal']:.1f}%")
                
            
            # Colonna Destra: BEST BET
            with c3:
                st.markdown("### ⭐ CONSIGLIO")
                if data['best_prob'] > 60:
                    color = "green"
                    risk = "ALTA PROBABILITÀ"
                elif data['best_prob'] > 50:
                    color = "orange"
                    risk = "MEDIA PROBABILITÀ"
                else:
                    color = "red"
                    risk = "RISCHIOSO"
                    
                st.markdown(f":{color}[**{data['best_bet']}**]")
                st.markdown(f"Affidabilità: **{data['best_prob']:.1f}%**")
                st.caption(f"Risk: {risk}")

            st.divider()

if __name__ == "__main__":
    main()