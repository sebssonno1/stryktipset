import streamlit as st
import pandas as pd
import numpy as np
import requests
from thefuzz import process 

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset & Europatipset: Hej Då PM Edition"
API_KEY = "31e8d45e0996d4e60b6dc48f8c656089" 
CACHE_TIME = 900 

# --- ÖVERSÄTTNINGSLISTA (FIXAR NAMNPROBLEM FÖR BÅDA KUPONGERNA) ---
TEAM_TRANSLATIONS = {
    # Engelska lag
    "Sheffield U": "Sheffield United",
    "Sheffield W": "Sheffield Wednesday",
    "Queens Park Rangers": "QPR",
    "Wolverhampton": "Wolverhampton Wanderers",
    "Wolves": "Wolverhampton Wanderers",
    "Blackburn": "Blackburn Rovers",
    "West Bromwich": "West Bromwich Albion",
    "WBA": "West Bromwich Albion",
    
    # Svenska lag
    "IFK Gbg": "IFK Göteborg",
    "Malmö": "Malmö FF",
    "Djurgården": "Djurgårdens IF",
    "AIK": "AIK Stockholm",

    # Europatipset / Internationella (Exempel på vanliga förkortningar)
    "Paris Saint-Germain": "Paris Saint Germain",
    "PSG": "Paris Saint Germain",
    "Inter": "Inter Milan",
    "AC Milan": "Milan",
    "Bayern München": "Bayern Munich",
    "Athletic Bilbao": "Athletic Club",
    "Sporting Lissabon": "Sporting CP",
    "Royale Union SG": "Union St. Gilloise",
    "Marseille": "Olympique de Marseille",
    "Ajax": "Ajax Amsterdam",
    "Bodö/Glimt": "Bodo/Glimt"
}

# --- 1. HÄMTA EXTERNA ODDS ---
@st.cache_data(ttl=CACHE_TIME)
def fetch_external_odds(api_key):
    if not api_key or "DIN_NYCKEL" in api_key:
        return {}

    all_odds = {}
    
    # Utökad lista för att täcka Europatipset
    leagues = [
        'soccer_epl',                   # Premier League
        'soccer_efl_championship',      # Championship
        'soccer_uefa_champs_league',    # Champions League (VIKTIGT)
        'soccer_uefa_europa_league',    # Europa League
        'soccer_spain_la_liga',         # La Liga
        'soccer_italy_serie_a',         # Serie A
        'soccer_germany_bundesliga',    # Bundesliga
        'soccer_france_ligue_one',      # Ligue 1
        'soccer_sweden_allsvenskan',
        'soccer_portugal_primeira_liga', # Portugal
        'soccer_netherlands_eredivisie'  # Holland
    ]
    
    for league in leagues:
        url = f'https://api.the-odds-api.com/v4/sports/{league}/odds/?apiKey={api_key}&regions=eu&markets=h2h'
        try:
            response = requests.get(url)
            if response.status_code != 200: continue
            data = response.json()
            
            for match in data:
                home_team = match['home_team']
                away_team = match['away_team']
                
                bookmakers = match.get('bookmakers', [])
                if not bookmakers: continue
                
                # Vi letar efter bästa odds bland tillgängliga bookmakers
                outcomes = bookmakers[0]['markets'][0]['outcomes']
                o1, ox, o2 = 0, 0, 0
                for outcome in outcomes:
                    if outcome['name'] == home_team: o1 = outcome['price']
                    elif outcome['name'] == away_team: o2 = outcome['price']
                    else: ox = outcome['price']
                
                # Spara under hemmalagets namn
                all_odds[home_team] = {'1': o1, 'X': ox, '2': o2}
                # Skapa en förenklad version av namnet för lättare matchning
                simple_name = home_team.replace(" FC", "").replace(" AFC", "").replace(" AS", "").strip()
                if simple_name != home_team:
                    all_odds[simple_name] = {'1': o1, 'X': ox, '2': o2}
                    
        except Exception:
            pass
            
    return all_odds

# --- (Resten av koden bibehålls men med små justeringar för logik) ---

def parse_svenskaspel_paste(text_content):
    matches = []
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    current_match = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        # Matchar siffer-rader 1-13
        if line.isdigit() and 1 <= int(line) <= 13:
            try:
                for offset in range(1, 5):
                    if i + offset < len(lines):
                        txt = lines[i+offset]
                        if '-' in txt and len(txt) > 3: # Undvik lösa bindestreck
                            parts = txt.split('-')
                            current_match = {
                                'Match': int(line), 
                                'Hemmalag': parts[0].strip(), 
                                'Bortalag': parts[1].strip()
                            }
                            break
                        elif txt == '-': # Om bindestrecket står ensamt på en rad
                            current_match = {
                                'Match': int(line),
                                'Hemmalag': lines[i+offset-1],
                                'Bortalag': lines[i+offset+1]
                            }
                            break
            except: pass
        
        if "Svenska folket" in line and current_match:
            try:
                temp_pcts = []
                for offset in range(1, 6):
                    if i + offset < len(lines) and '%' in lines[i+offset]:
                        temp_pcts.append(int(lines[i+offset].replace('%', '')))
                if len(temp_pcts) >= 3:
                    current_match.update({'Streck_1': temp_pcts[0], 'Streck_X': temp_pcts[1], 'Streck_2': temp_pcts[2]})
            except: pass

        if "Odds" in line and current_match and 'Streck_1' in current_match:
            try:
                temp_odds = []
                for offset in range(1, 6):
                    if i + offset < len(lines) and ',' in lines[i+offset]:
                            temp_odds.append(float(lines[i+offset].replace(',', '.')))
                if len(temp_odds) >= 3:
                    current_match.update({'SvS_Odds_1': temp_odds[0], 'SvS_Odds_X': temp_odds[1], 'SvS_Odds_2': temp_odds[2]})
                    matches.append(current_match)
                    current_match = {} 
            except: pass
        i += 1
    return matches

def calculate_probabilities(row):
    # Prioritera API-odds, använd annars Svenska Spels egna odds för beräkning
    o1 = row.get('API_Odds_1') if pd.notnull(row.get('API_Odds_1')) else row.get('SvS_Odds_1', 0)
    ox = row.get('API_Odds_X') if pd.notnull(row.get('API_Odds_X')) else row.get('SvS_Odds_X', 0)
    o2 = row.get('API_Odds_2') if pd.notnull(row.get('API_Odds_2')) else row.get('SvS_Odds_2', 0)
    
    if not o1 or o1 == 0: return 0, 0, 0
    raw_1, raw_x, raw_2 = 1/o1, 1/ox, 1/o2
    total = raw_1 + raw_x + raw_2
    return round((raw_1/total)*100, 1), round((raw_x/total)*100, 1), round((raw_2/total)*100, 1)

def suggest_sign_and_status(row):
    tecken = []
    # Strategi: Om sannolikheten är hög (>55%) och värdet inte är katastrofalt, spika.
    if row['Prob_1'] > 55 and row['Val_1'] > -15: tecken.append('1')
    elif row['Prob_2'] > 55 and row['Val_2'] > -15: tecken.append('2')
    else:
        values = [('1', row['Val_1']), ('X', row['Val_X']), ('2', row['Val_2'])]
        values.sort(key=lambda x: x[1], reverse=True)
        tecken.append(values[0][0])
        if len(tecken) < 2: tecken.append(values[1][0])
    
    # Statusmeddelande
    max_val = max(row['Val_1'], row['Val_X'], row['Val_2'])
    if max_val > 8: status = "💎 Bra värde"
    elif max_val < -10: status = "⚠️ Överstreckad"
    else: status = "Neutral"
    
    return "".join(sorted(tecken)), status

# --- UI ---
st.set_page_config(page_title="Stryktipset & Europatipset", layout="wide")
st.title(ST_PAGE_TITLE)

with st.form("input_form"):
    text_input = st.text_area("Klistra in från Svenska Spel (Stryktipset eller Europatipset):", height=200)
    submitted = st.form_submit_button("🚀 Analysera Kupong", type="primary")

if submitted and text_input:
    matches_data = parse_svenskaspel_paste(text_input)
    
    if not matches_data:
        st.error("Kunde inte tolka datan. Se till att kopiera hela sidan.")
    else:
        with st.spinner('Hämtar odds från API...'):
            external_odds = fetch_external_odds(API_KEY)
            odds_teams = list(external_odds.keys())
        
        for m in matches_data:
            search_name = TEAM_TRANSLATIONS.get(m['Hemmalag'], m['Hemmalag'])
            match_name, score = process.extractOne(search_name, odds_teams) if odds_teams else (None, 0)
            
            if score > 75: # Högre tröskel för säkerhet
                odds = external_odds[match_name]
                m.update({'API_Odds_1': odds['1'], 'API_Odds_X': odds['X'], 'API_Odds_2': odds['2'], 'Källa': "API"})
            else:
                m.update({'API_Odds_1': None, 'API_Odds_X': None, 'API_Odds_2': None, 'Källa': "SvS Odds"})

        df = pd.DataFrame(matches_data)
        df[['Prob_1', 'Prob_X', 'Prob_2']] = df.apply(calculate_probabilities, axis=1, result_type='expand')
        df['Val_1'] = df['Prob_1'] - df['Streck_1']
        df['Val_X'] = df['Prob_X'] - df['Streck_X']
        df['Val_2'] = df['Prob_2'] - df['Streck_2']
        df[['Tips', 'Analys']] = df.apply(suggest_sign_and_status, axis=1, result_type='expand')

        # Visa tabeller
        st.subheader("Analysresultat")
        st.dataframe(df[['Match', 'Hemmalag', 'Bortalag', 'Tips', 'Analys', 'Källa']], use_container_width=True, hide_index=True)
        
        with st.expander("Se detaljerat värde (Procentenheter)"):
            st.dataframe(df[['Match', 'Hemmalag', 'Val_1', 'Val_X', 'Val_2']].style.background_gradient(cmap='RdYlGn', axis=None), use_container_width=True)
