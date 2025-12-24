import streamlit as st
import pandas as pd
import requests
import math
from datetime import datetime, timedelta

# --- CONFIGURAZIONE STILE ---
st.set_page_config(page_title="AI Bet Master V4", layout="wide", page_icon="⚽")

# CSS Personalizzato per rendere l'interfaccia "Carina"
st.markdown("""
<style>
    .big-font { font-size:20px !important; font-weight: bold; }
    .metric-card { background-color: #f0f2f6; padding: 15px; border-radius: 10px; text-align: center; }
    .best-bet { background-color: #d4edda; color: #155724; padding: 10px; border-radius: 5px; border: 1px solid #c3e6cb; text-align: center; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# --- MOTORE MATEMATICO (POISSON MATRIX) ---

def poisson(k, lamb):
    return (lamb**k * math.exp(-lamb)) / math.factorial(k)

def genera_matrice_probabilita(xg_home, xg_away):
    """
    Crea un dizionario con TUTTE le scommesse possibili e le loro probabilità reali
    basate sulla somma dei risultati esatti.
    """
    markets = {
        "1": 0, "X": 0, "2": 0,
        "Over 1.5": 0, "Under 1.5": 0,
        "Over 2.5": 0, "Under 2.5": 0,
        "Goal (GG)": 0, "NoGoal (NG)": 0,
        "1 + Over 1.5": 0, "1 + Under 3.5": 0, "1X + Over 1.5": 0,
        "2 + Over 1.5": 0, "X2 + Under 3.5": 0,
        "MG 1-3": 0, "MG 2-4": 0, "MG 2-5": 0,
        "Casa MG 1-2": 0, "Casa MG 1-3": 0,
        "Ospite MG 1-2": 0, "Ospite MG 1-3": 0
    }

    # Analizziamo risultati fino a 9-9 per massima precisione
    for h in range(10):
        for a in range(10):
            prob = poisson(h, xg_home) * poisson(a, xg_away)
            total_goals = h + a
            
            # 1X2
            if h > a: markets["1"] += prob
            elif h == a: markets["X"] += prob
            else: markets["2"] += prob
            
            # Under/Over
            if total_goals > 1.5: markets["Over 1.5"] += prob
            else: markets["Under 1.5"] += prob
            
            if total_goals > 2.5: markets["Over 2.5"] += prob
            else: markets["Under 2.5"] += prob
            
            # Goal/NoGoal
            if h > 0 and a > 0: markets["Goal (GG)"] += prob
            else: markets["NoGoal (NG)"] += prob
            
            # MULTIGOAL
            if 1 <= total_goals <= 3: markets["MG 1-3"] += prob
            if 2 <= total_goals <= 4: markets["MG 2-4"] += prob
            if 2 <= total_goals <= 5: markets["MG 2-5"] += prob
            
            # MULTIGOAL SQUADRE
            if 1 <= h <= 2: markets["Casa MG 1-2"] += prob
            if 1 <= h <= 3: markets["Casa MG 1-3"] += prob
            if 1 <= a <= 2: markets["Ospite MG 1-2"] += prob
            if 1 <= a <= 3: markets["Ospite MG 1-3"] += prob
            
            # COMBO (La parte difficile!)
            # 1 + Over 1.5
            if h > a and total_goals > 1.5: markets["1 + Over 1.5"] += prob
            # 1 + Under 3.5
            if h > a and total_goals < 3.5: markets["1 + Under 3.5"] += prob
            # 1X + Over 1.5
            if h >= a and total_goals > 1.5: markets["1X + Over 1.5"] += prob
            # 2 + Over 1.5
            if a > h and total_goals > 1.5: markets["2 + Over 1.5"] += prob
            # X2 + Under 3.5
            if a >= h and total_goals < 3.5: markets["X2 + Under 3.5"] += prob

    # Converti in percentuali
    return {k: v * 100 for k, v in markets.items()}

# --- API E DATI ---

@st.cache_data(ttl=3600)
def get_data(api_key, date_obj):
    headers = {'X-Auth-Token': api_key}
    
    # 1. Scarica Partite
    date_str = date_obj.strftime("%Y-%m-%d")
    d_to = (date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
    url_m = f"https://api.football-data.org/v4/matches?dateFrom={date_str}&dateTo={d_to}"
    
    matches = []
    try:
        resp = requests.get(url_m, headers=headers)
        matches = resp.json().get('matches', [])
    except: return [], {}

    if not matches: return [], {}

    # 2. Scarica Classifiche (Solo quelle necessarie)
    comp_ids = set([m['competition']['id'] for m in matches])
    standings = {}
    
    for cid in comp_ids:
        try:
            url_s = f"https://api.football-data.org/v4/competitions/{cid}/standings"
            resp_s = requests.get(url_s, headers=headers).json()
            if 'standings' in resp_s:
                table = resp_s['standings'][0]['table']
                for row in table:
                    standings[row['team']['id']] = {
                        'gf': row['goalsFor'] / row['playedGames'],
                        'ga': row['goalsAgainst'] / row['playedGames'],
                        'form': row.get('form', '')
                    }
        except: continue
        
    return matches, standings

def get_xg(h_id, a_id, db):
    # Recupera dati o usa default
    h = db.get(h_id, {'gf': 1.2, 'ga': 1.2, 'form': ''})
    a = db.get(a_id, {'gf': 1.0, 'ga': 1.0, 'form': ''})
    
    # Calcolo Forma (Semplificato)
    h_f = 1 + (h['form'].count('W') * 0.05) - (h['form'].count('L') * 0.05)
    a_f = 1 + (a['form'].count('W') * 0.05) - (a['form'].count('L') * 0.05)
    
    # Calcolo xG
    xg_h = h['gf'] * a['ga'] * 1.15 * h_f # 1.15 fattore campo
    xg_a = a['gf'] * h['ga'] * a_f
    
    return xg_h, xg_a

# --- INTERFACCIA ---

def main():
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/53/53283.png", width=100)
    st.sidebar.title("Impostazioni")
    api_key = st.sidebar.text_input("🔑 API Key", type="password")
    day = st.sidebar.date_input("📅 Data", datetime.now())
    
    st.title("⚽ AI Betting Suite V4")
    st.markdown("Analisi **Multigoal**, **Combo** e **Ranking Probabilità**.")

    if not api_key:
        st.info("Inserisci la chiave API per iniziare.")
        return

    with st.spinner("Analisi in corso..."):
        matches, db = get_data(api_key, day)
    
    if not matches:
        st.error("Nessuna partita trovata.")
        return

    # Filtro Competizione
    comps = list(set([m['competition']['name'] for m in matches]))
    sel_comp = st.sidebar.multiselect("Filtra Campionato", comps, default=comps)
    clean_matches = [m for m in matches if m['competition']['name'] in sel_comp]
    
    st.write(f"Trovate **{len(clean_matches)}** partite.")
    st.markdown("---")

    for m in clean_matches:
        h_name = m['homeTeam']['name']
        a_name = m['awayTeam']['name']
        
        # Analisi
        xg_h, xg_a = get_xg(m['homeTeam']['id'], m['awayTeam']['id'], db)
        probs = genera_matrice_probabilita(xg_h, xg_a)
        
        # Identifica la BEST BET (Top Prob > 55%)
        sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)
        best_bet = sorted_probs[0]
        
        # --- UI CARD ---
        with st.container():
            col_head_1, col_head_2 = st.columns([3, 1])
            with col_head_1:
                st.subheader(f"{h_name} 🆚 {a_name}")
                st.caption(f"{m['competition']['name']} | xG: {xg_h:.2f} - {xg_a:.2f}")
            with col_head_2:
                # Box Best Bet
                st.markdown(f"""
                <div class="best-bet">
                    🔥 TOP PICK<br>
                    {best_bet[0]}<br>
                    {best_bet[1]:.1f}%
                </div>
                """, unsafe_allow_html=True)
            
            # TABS PER CATEGORIE
            tab1, tab2, tab3, tab4 = st.tabs(["📊 Classifica Quote", "🏠 Principali", "🔢 Multigoal", "⚡ Combo"])
            
            with tab1:
                st.write("Le scommesse più probabili per questo evento:")
                # Creiamo un DataFrame per la classifica
                df_probs = pd.DataFrame(sorted_probs, columns=["Esito", "Probabilità %"])
                df_probs['Probabilità %'] = df_probs['Probabilità %'].round(1)
                
                # Visualizza come tabella con barre
                st.dataframe(
                    df_probs.head(10), # Mostra le top 10
                    column_config={
                        "Probabilità %": st.column_config.ProgressColumn(
                            "Affidabilità",
                            format="%.1f%%",
                            min_value=0,
                            max_value=100,
                        ),
                    },
                    hide_index=True,
                    use_container_width=True
                )

            with tab2:
                c1, c2, c3 = st.columns(3)
                c1.metric("1 (Casa)", f"{probs['1']:.1f}%")
                c2.metric("X (Pareggio)", f"{probs['X']:.1f}%")
                c3.metric("2 (Ospite)", f"{probs['2']:.1f}%")
                st.divider()
                c4, c5 = st.columns(2)
                c4.metric("Goal (Entrambe)", f"{probs['Goal (GG)']:.1f}%")
                c5.metric("Over 2.5", f"{probs['Over 2.5']:.1f}%")

            with tab3:
                st.markdown("**Totale Partita**")
                cm1, cm2, cm3 = st.columns(3)
                cm1.metric("1-3 Gol", f"{probs['MG 1-3']:.1f}%")
                cm2.metric("2-4 Gol", f"{probs['MG 2-4']:.1f}%")
                cm3.metric("2-5 Gol", f"{probs['MG 2-5']:.1f}%")
                
                st.markdown("**Squadre**")
                cs1, cs2 = st.columns(2)
                cs1.info(f"Casa 1-2 Gol: **{probs['Casa MG 1-2']:.1f}%**")
                cs2.info(f"Ospite 1-2 Gol: **{probs['Ospite MG 1-2']:.1f}%**")

            with tab4:
                st.warning("⚠️ Le Combo richiedono alta precisione")
                cc1, cc2 = st.columns(2)
                with cc1:
                    st.write(f"1 + Over 1.5: **{probs['1 + Over 1.5']:.1f}%**")
                    st.write(f"1X + Over 1.5: **{probs['1X + Over 1.5']:.1f}%**")
                    st.write(f"1 + Under 3.5: **{probs['1 + Under 3.5']:.1f}%**")
                with cc2:
                    st.write(f"2 + Over 1.5: **{probs['2 + Over 1.5']:.1f}%**")
                    st.write(f"X2 + Under 3.5: **{probs['X2 + Under 3.5']:.1f}%**")
            
            st.divider()

if __name__ == "__main__":
    main()