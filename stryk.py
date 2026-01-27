import streamlit as st
import pandas as pd
import numpy as np
import requests
from thefuzz import process 

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset: Hej Då PM Edition"
API_KEY = "31e8d45e0996d4e60b6dc48f8c656089" # <--- DIN NYCKEL HÄR
CACHE_TIME = 900 

# --- PLATSHÅLLARTEXT (FÖRHANDSVISNING) ---
PLACEHOLDER_TEXT = """(Exempel på hur texten ska se ut:)
1
Liverpool
-
Newcastle
1
X
2
Tipsinformation för match nummer 1
Tipsinfo
1
X
2
Svenska folket"""

# --- ÖVERSÄTTNINGSLISTA (FIXAR NAMNPROBLEM) ---
TEAM_TRANSLATIONS = {
    # Engelska lag
    "Sheffield U": "Sheffield United",
    "Sheffield W": "Sheffield Wednesday",
    "Queens Park Rangers": "QPR",
    "QPR": "Queens Park Rangers",
    "Wolverhampton": "Wolverhampton Wanderers",
    "Wolves": "Wolverhampton Wanderers",
    "Blackburn": "Blackburn Rovers",
    "Preston": "Preston North End",
    "Plymouth": "Plymouth Argyle",
    "Oxford": "Oxford United",
    "Coventry": "Coventry City",
    "Norwich": "Norwich City",
    "Middlesbrough": "Middlesbrough FC",
    "Leeds": "Leeds United",
    "Leicester": "Leicester City",
    "Ipswich": "Ipswich Town",
    "Hull": "Hull City",
    "Cardiff": "Cardiff City",
    "Bristol C": "Bristol City",
    "Swansea": "Swansea City",
    "Stoke": "Stoke City",
    "West Bromwich": "West Bromwich Albion",
    "WBA": "West Bromwich Albion",
    "Derby": "Derby County",
    "Portsmouth": "Portsmouth FC",
    "Millwall": "Millwall FC",
    "Luton": "Luton Town",
    "Burnley": "Burnley FC",
    
    # Svenska lag
    "IFK Gbg": "IFK Göteborg",
    "Malmö": "Malmö FF",
    "Djurgården": "Djurgårdens IF",
    "AIK": "AIK Stockholn"
}

# --- 1. HÄMTA EXTERNA ODDS ---
@st.cache_data(ttl=CACHE_TIME)
def fetch_external_odds(api_key):
    if not api_key or "DIN_NYCKEL" in api_key:
        return {}

    all_odds = {}
    
    leagues = [
        'soccer_epl',                  
        'soccer_efl_championship',     
        'soccer_england_league1',      
        'soccer_england_league2',      
        'soccer_fa_cup',               
        'soccer_efl_cup',              
        'soccer_sweden_allsvenskan'    
    ]
    
    for league in leagues:
        url = f'https://api.the-odds-api.com/v4/sports/{league}/odds/?apiKey={api_key}&regions=eu&markets=h2h'
        try:
            response = requests.get(url)
            if response.status_code != 200: continue
            data = response.json()
            
            for match in data:
                home_team = match['home_team']
                simple_name = home_team.replace(" FC", "").replace(" AFC", "").strip()
                
                bookmakers = match.get('bookmakers', [])
                if not bookmakers: continue
                
                outcomes = bookmakers[0]['markets'][0]['outcomes']
                o1, ox, o2 = 0, 0, 0
                for outcome in outcomes:
                    if outcome['name'] == home_team: o1 = outcome['price']
                    elif outcome['name'] == match['away_team']: o2 = outcome['price']
                    else: ox = outcome['price']
                
                all_odds[home_team] = {'1': o1, 'X': ox, '2': o2}
                if simple_name != home_team:
                    all_odds[simple_name] = {'1': o1, 'X': ox, '2': o2}
                    
        except Exception:
            pass
            
    return all_odds

# --- 2. LÄS PASTE ---
def parse_svenskaspel_paste(text_content):
    matches = []
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    current_match = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.isdigit() and 1 <= int(line) <= 13:
            try:
                for offset in range(1, 5):
                    if i + offset < len(lines):
                        txt = lines[i+offset]
                        if '-' in txt:
                            if txt == '-': 
                                hemmalag = lines[i+offset-1]
                                bortalag = lines[i+offset+1]
                            else:
                                parts = txt.split('-')
                                hemmalag = parts[0].strip()
                                bortalag = parts[1].strip()
                            current_match = {'Match': int(line), 'Hemmalag': hemmalag, 'Bortalag': bortalag}
                            break
            except IndexError: pass
        
        if "Svenska folket" in line and current_match:
            try:
                temp_pcts = []
                for offset in range(1, 6):
                    if i + offset < len(lines) and '%' in lines[i+offset]:
                        temp_pcts.append(int(lines[i+offset].replace('%', '')))
                if len(temp_pcts) >= 3:
                    current_match.update({'Streck_1': temp_pcts[0], 'Streck_X': temp_pcts[1], 'Streck_2': temp_pcts[2]})
            except ValueError: pass

        if "Odds" in line and current_match:
            try:
                temp_odds = []
                for offset in range(1, 6):
                    if i + offset < len(lines) and ',' in lines[i+offset]:
                            temp_odds.append(float(lines[i+offset].replace(',', '.')))
                if len(temp_odds) >= 3:
                    current_match.update({'SvS_Odds_1': temp_odds[0], 'SvS_Odds_X': temp_odds[1], 'SvS_Odds_2': temp_odds[2]})
                    matches.append(current_match)
                    current_match = {} 
            except ValueError: pass
        i += 1
    return matches

# --- 3. BERÄKNINGAR ---
def calculate_probabilities(row):
    o1 = row.get('API_Odds_1', row.get('SvS_Odds_1', 0))
    ox = row.get('API_Odds_X', row.get('SvS_Odds_X', 0))
    o2 = row.get('API_Odds_2', row.get('SvS_Odds_2', 0))
    if o1 == 0: return 0, 0, 0
    raw_1, raw_x, raw_2 = 1/o1, 1/ox, 1/o2
    total = raw_1 + raw_x + raw_2
    return round((raw_1/total)*100, 1), round((raw_x/total)*100, 1), round((raw_2/total)*100, 1)

def suggest_sign_and_status(row):
    tecken = []
    status = ""
    if row['Prob_1'] > 55 and row['Val_1'] > -15:
        tecken.append('1')
    elif row['Prob_2'] > 55 and row['Val_2'] > -15:
        tecken.append('2')
    else:
        values = [('1', row['Val_1']), ('X', row['Val_X']), ('2', row['Val_2'])]
        values.sort(key=lambda x: x[1], reverse=True)
        tecken.append(values[0][0])
        if values[0][1] > 7: status = f"💎 Fynd {values[0][0]}"
        elif values[0][1] < -10: status = "⚠️ Överstreckad"
        else: status = "Neutral"
        if len(tecken) < 2: tecken.append(values[1][0])
    return "".join(sorted(tecken)), status

# --- APP LAYOUT ---
st.set_page_config(page_title="Stryktipset Master", layout="wide")
st.title(ST_PAGE_TITLE)

# --- INSTRUKTIONER ---
with st.expander("ℹ️ Instruktioner", expanded=True):
    col1, col2 = st.columns([1, 3])
    with col1:
        st.link_button("Gå till Stryktipset ↗️", "https://spela.svenskaspel.se/stryktipset")
    with col2:
        st.write("1. Klicka på knappen för att öppna Svenska Spel.")
        st.write("2. Markera **ALL** text på sidan (Ctrl+A), kopiera (Ctrl+C).")
        st.write("3. Klistra in texten i rutan nedanför.")

# --- FORMULÄR ---
with st.form("input_form"):
    text_input = st.text_area(
        "Klistra in här:", 
        height=250, 
        help="Klistra in hela sidan från Svenska Spel",
        placeholder=PLACEHOLDER_TEXT 
    )
    
    submitted = st.form_submit_button("🚀 Kör Analys", type="primary", use_container_width=True)

if submitted and text_input:
    matches_data = parse_svenskaspel_paste(text_input)
    
    if not matches_data:
        st.error("Kunde inte läsa några matcher. Kontrollera att du kopierat ALLT, inklusive 'Svenska folket'.")
    else:
        external_odds = fetch_external_odds(API_KEY)
        odds_teams = list(external_odds.keys()) if external_odds else []
        
        final_rows = []
        matches_found_in_api = 0

        for m in matches_data:
            original_name = m['Hemmalag']
            search_name = TEAM_TRANSLATIONS.get(original_name, original_name)
            
            matched = False
            if external_odds:
                match_name, score = process.extractOne(search_name, odds_teams)
                
                if score > 55: 
                    odds = external_odds[match_name]
                    m['API_Odds_1'] = odds['1']
                    m['API_Odds_X'] = odds['X']
                    m['API_Odds_2'] = odds['2']
                    m['Källa'] = "The Odds API"
                    matches_found_in_api += 1
                    matched = True
            
            if not matched:
                m['Källa'] = "SvS (Eget Odds)"
            
            final_rows.append(m)

        df = pd.DataFrame(final_rows)
        probs = df.apply(calculate_probabilities, axis=1, result_type='expand')
        df[['Prob_1', 'Prob_X', 'Prob_2']] = probs
        df['Val_1'] = df['Prob_1'] - df['Streck_1']
        df['Val_X'] = df['Prob_X'] - df['Streck_X']
        df['Val_2'] = df['Prob_2'] - df['Streck_2']
        results = df.apply(suggest_sign_and_status, axis=1, result_type='expand')
        df['Tips'] = results[0]
        df['Analys'] = results[1]

        # --- RESULTAT ---
        st.success(f"Träffade {matches_found_in_api} av 13 lag i API:et.")
        
        table_height = (len(df) * 35) + 38 
        
        # TRE FLIKAR NU
        tab1, tab2, tab3 = st.tabs(["💡 Kupong", "📊 Värde", "🎲 Odds"])
        
        with tab1:
            st.dataframe(df[['Match', 'Hemmalag', 'Bortalag', 'Tips', 'Analys', 'Källa']], hide_index=True, use_container_width=True, height=table_height)
            txt_rad = "\n".join([f"M{r['Match']}: {r['Tips']}" for _, r in df.iterrows()])
            st.download_button("Ladda ner rad", txt_rad, "rad.txt")

        with tab2:
            st.dataframe(df[['Match', 'Hemmalag', 'Val_1', 'Val_X', 'Val_2']], hide_index=True, use_container_width=True, height=table_height)
            
        with tab3:
            st.write("Här jämförs oddsen (från spelbolag) med hur folket har streckat (%)")
            # Skapar en snyggare vy för odds-tabellen och byter namn på kolumnerna
            odds_view = df[['Match', 'Hemmalag', 'API_Odds_1', 'API_Odds_X', 'API_Odds_2', 'Streck_1', 'Streck_X', 'Streck_2']].copy()
            odds_view.columns = ['Match', 'Hemmalag', 'Odds 1', 'Odds X', 'Odds 2', 'Folk 1 (%)', 'Folk X (%)', 'Folk 2 (%)']
            st.dataframe(odds_view, hide_index=True, use_container_width=True, height=table_height)
