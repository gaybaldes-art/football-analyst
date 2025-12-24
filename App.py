import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Football Data Pro Analyst", layout="wide", page_icon="⚽")

# --- GESTIONE API E DATI ---

@st.cache_data(ttl=3600)  # Cache di 1 ora per non consumare tutte le chiamate API
def get_standings(api_key, competition_id):
    """Scarica la classifica per avere dati su gol e forma."""
    url = f"https://api.football-data.org/v4/competitions/{competition_id}/standings"
    headers = {'X-Auth-Token': api_key}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        
        # Creiamo un dizionario {team_id: stats} per accesso rapido
        teams_stats = {}
        if 'standings' in data and len(data['standings']) > 0:
            table = data['standings'][0]['table'] # Classifica "Total"
            for row in table:
                team_id = row['team']['id']
                teams_stats[team_id] = {
                    'position': row['position'],
                    'played': row['playedGames'],
                    'won': row['won'],
                    'draw': row['draw'],
                    'lost': row['lost'],
                    'gf': row['goalsFor'],
                    'ga': row['goalsAgainst'],
                    'gd': row['goalDifference'],
                    'form': row.get('form', None) # Es. "W,D,L,W,W"
                }
        return teams_stats
    except:
        return {}

@st.cache_data(ttl=3600)
def get_upcoming_matches(api_key, days=5):
    """Scarica le partite dei prossimi giorni."""
    today = datetime.now()
    date_from = today.strftime("%Y-%m-%d")
    date_to = (today + timedelta(days=days)).strftime("%Y-%m-%d")
    
    url = f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}"
    headers = {'X-Auth-Token': api_key}
    
    try:
        response = requests.get(url, headers=headers)
        return response.json().get('matches', [])
    except:
        return []

# --- CALCOLO METRICHE E PRONOSTICI ---

def calculate_form_score(form_string):
    """Converte stringa forma (es. 'W,D,L') in un numero 0-100."""
    if not form_string:
        return 50 # Neutro se dati mancanti
    
    score = 0
    games = form_string.split(',')
    # Pesi: le partite più recenti (alla fine della stringa nell'API) contano di più? 
    # Solitamente l'API dà la più recente a destra.
    # W=3, D=1, L=0
    points = 0
    max_points = len(games) * 3
    
    for match in games:
        if match == 'W': points += 3
        elif match == 'D': points += 1
    
    if max_points == 0: return 50
    return (points / max_points) * 100

def analyze_match_real_data(home_id, away_id, home_name, away_name, standings):
    """Analizza il match usando i dati reali della classifica."""
    
    # Recupera stats, se non esistono (es. coppe o inizio stagione) usa default
    h_stats = standings.get(home_id, {'played': 1, 'gf': 1, 'ga': 1, 'form': None})
    a_stats = standings.get(away_id, {'played': 1, 'gf': 1, 'ga': 1, 'form': None})
    
    # Evita divisione per zero
    h_played = max(h_stats['played'], 1)
    a_played = max(a_stats['played'], 1)

    # 1. Metriche Attacco/Difesa Medie
    h_attack = h_stats['gf'] / h_played  # Gol fatti a partita
    h_defense = h_stats['ga'] / h_played # Gol subiti a partita
    a_attack = a_stats['gf'] / a_played
    a_defense = a_stats['ga'] / a_played
    
    # 2. Forma (0-100)
    h_form = calculate_form_score(h_stats['form'])
    a_form = calculate_form_score(a_stats['form'])
    
    # 3. Calcolo Gol Attesi (Algoritmo di Poisson semplificato)
    # Gol Casa = (Attacco Casa * Difesa Ospite) * Fattore Campo
    xg_home = (h_attack * a_defense) * 1.15 # 1.15 è il vantaggio casa medio
    # Gol Ospite = (Attacco Ospite * Difesa Casa)
    xg_away = (a_attack * h_defense)
    
    # Aggiusta con la forma
    xg_home *= (1 + (h_form - 50)/200) # +/- 10% in base alla forma
    xg_away *= (1 + (a_form - 50)/200)

    # 4. Generazione Scommesse
    tips = []
    
    # 1X2
    diff = xg_home - xg_away
    if diff > 0.5:
        tips.append("1 Fisso")
        if h_form > 70: tips.append("1 + Over 1.5")
    elif diff < -0.5:
        tips.append("2 Fisso")
    else:
        tips.append("X o Goal")
        tips.append("Doppia Chance 1X")

    # Gol
    total_xg = xg_home + xg_away
    if total_xg > 2.6:
        tips.append("Over 2.5")
        tips.append("Multigoal 3-5")
    elif total_xg < 1.9:
        tips.append("Under 2.5")
    else:
        tips.append("Multigoal 2-4")
        
    if h_attack > 1.2 and a_attack > 1.2:
        tips.append("Goal (Entrambe segnano)")

    return {
        'xg_home': round(xg_home, 2),
        'xg_away': round(xg_away, 2),
        'tips': tips,
        'h_form': int(h_form),
        'a_form': int(a_form),
        'stats_raw': (h_attack, h_defense, a_attack, a_defense)
    }

# --- INTERFACCIA ---

def main():
    st.sidebar.header("Impostazioni")
    api_key = st.sidebar.text_input("Inserisci API Key football-data.org", type="password")
    
    st.title("⚽ Scommesse AI - Analisi Dati Reali")
    st.markdown("Algoritmo basato su **Classifiche Reali**, **Gol Fatti/Subiti** e **Forma**.")

    if not api_key:
        st.warning("Inserisci la chiave API a sinistra per iniziare.")
        return

    # 1. Scarica Partite
    with st.spinner("Scarico il calendario..."):
        matches = get_upcoming_matches(api_key)
    
    if not matches:
        st.error("Nessuna partita trovata o API Key errata.")
        return

    # 2. Trova le competizioni uniche per scaricare le classifiche necessarie
    comp_ids = set([m['competition']['id'] for m in matches])
    standings_cache = {}
    
    progress_bar = st.progress(0)
    st.write(f"Analisi di {len(matches)} partite da {len(comp_ids)} campionati...")
    
    # Scarica classifiche (una volta per campionato)
    for idx, cid in enumerate(comp_ids):
        standings_cache[cid] = get_standings(api_key, cid)
        progress_bar.progress((idx + 1) / len(comp_ids))
    
    st.divider()

    # 3. Mostra Partite e Analisi
    for m in matches:
        comp_name = m['competition']['name']
        comp_id = m['competition']['id']
        
        h_team = m['homeTeam']
        a_team = m['awayTeam']
        match_date = datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ").strftime("%d/%m %H:%M")
        
        # Analisi
        data = analyze_match_real_data(
            h_team['id'], a_team['id'], 
            h_team['name'], a_team['name'], 
            standings_cache.get(comp_id, {})
        )
        
        # CARD PARTITA
        with st.container():
            st.subheader(f"{comp_name} | {match_date}")
            col1, col2, col3 = st.columns([4, 3, 4])
            
            with col1:
                st.markdown(f"### {h_team['name']}")
                st.write(f"📊 Forma: **{data['h_form']}%**")
                st.write(f"⚔️ Segna: {data['stats_raw'][0]:.1f} gol/p")
                st.write(f"🛡️ Subisce: {data['stats_raw'][1]:.1f} gol/p")
            
            with col2:
                st.markdown("<div style='text-align: center; background-color: #f0f2f6; padding: 10px; border-radius: 10px;'>", unsafe_allow_html=True)
                st.markdown("**xG PREVISTI**")
                st.markdown(f"## {data['xg_home']} - {data['xg_away']}")
                st.markdown("</div>", unsafe_allow_html=True)
                
                st.write("")
                st.markdown("**💡 CONSIGLI:**")
                for tip in data['tips']:
                    st.success(f"Build: {tip}")

            with col3:
                st.markdown(f"### {a_team['name']}")
                st.write(f"📊 Forma: **{data['a_form']}%**")
                st.write(f"⚔️ Segna: {data['stats_raw'][2]:.1f} gol/p")
                st.write(f"🛡️ Subisce: {data['stats_raw'][3]:.1f} gol/p")
            
            st.divider()

if __name__ == "__main__":
    main()