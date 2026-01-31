import streamlit as st
import pandas as pd
import requests
import re
from thefuzz import process 

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset: Precision Edition (UK Auto)"
API_KEY = "a2d13d188dd18fd41218508d2dd0408f" # <--- DIN NYCKEL
CACHE_TIME = 900 
MATCH_THRESHOLD = 85  # Lite lägre tröskel kan behövas för vissa lagnamn
SVENSKA_SPEL_URL = "https://www.svenskaspel.se/stryktipset"

# --- PLATSHÅLLARTEXT ---
PLACEHOLDER_TEXT = """Klistra in hela sidan (Ctrl+A) från den vanliga kupongvyn."""

# --- 1. HÄMTA EXTERNA ODDS (UPPDATERAD) ---
@st.cache_data(ttl=CACHE_TIME)
def fetch_external_odds(api_key):
    if not api_key or "DIN_NYCKEL" in api_key:
        return {}

    all_odds = {}
    
    # 1. Prioriterad ordning! (Engelska ligor först för att säkra Stryktipset)
    # Vi lägger till FA Cup högst upp eftersom det är cup-tider.
    leagues = [
        'soccer_fa_cup',            # FA-cupen (Viktig nu!)
        'soccer_efl_championship',  # The Championship
        'soccer_england_league1',   # League 1
        'soccer_england_league2',   # League 2
        'soccer_epl',               # Premier League
        'soccer_sweden_allsvenskan',
        'soccer_italy_serie_a', 
        'soccer_spain_la_liga', 
        'soccer_germany_bundesliga', 
        'soccer_france_ligue_one'
    ]
    
    prog_bar = st.progress(0, text="Hämtar odds...")
    total_leagues = len(leagues)
    
    for i, league in enumerate(leagues):
        prog_bar.progress((i + 1) / total_leagues, text=f"Kollar liga: {league}...")
        
        # ÄNDRING HÄR: Vi lägger till "uk" i regions för att hitta fler engelska odds!
        url = f'https://api.the-odds-api.com/v4/sports/{league}/odds/?apiKey={api_key}&regions=eu,uk&markets=h2h'
        
        try:
            response = requests.get(url)
            
            if response.status_code == 429:
                st.warning(f"⚠️ API-kvoten tog slut vid {league}. Vissa matcher kan saknas.")
                break 
            
            if response.status_code != 200: 
                continue
            
            data = response.json()
            for match in data:
                home_team = match['home_team']
                # Enkla städningar av lagnamn
                simple_name = home_team.replace(" FC", "").replace(" AFC", "").strip()
                
                bookmakers = match.get('bookmakers', [])
                if not bookmakers: continue
                
                # Vi tar första bästa odds vi hittar
                market = bookmakers[0]['markets'][0]
                outcomes = market['outcomes']
                
                o1, ox, o2 = 0, 0, 0
                for outcome in outcomes:
                    if outcome['name'] == home_team: o1 = outcome['price']
                    elif outcome['name'] == match['away_team']: o2 = outcome['price']
                    else: ox = outcome['price']
                
                # Spara odds om vi hittade dem
                if o1 > 0:
                    odds_data = {'1': o1, 'X': ox, '2': o2}
                    all_odds[home_team] = odds_data
                    if simple_name != home_team:
                        all_odds[simple_name] = odds_data
                        
        except Exception as e:
            print(f"Fel vid hämtning av {league}: {e}")
            pass
            
    prog_bar.empty()
    return all_odds

# --- HJÄLPFUNKTION: STÄDA NAMN ---
def clean_team_name(name):
    name = re.sub(r'^\d+[\.\s]*', '', name) 
    name = name.replace("1X2", "").replace("1", "").replace("X", "").replace("2", "")
    return name.strip()

# --- 2. LÄS PASTE ---
def parse_svenskaspel_paste(text_content):
    matches = []
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    current_match = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        # Letar efter matchnummer (1-13)
        if line.isdigit() and 1 <= int(line) <= 13:
            try:
                # Sök framåt efter lagnamn
                for offset in range(1, 6):
                    if i + offset < len(lines):
                        txt = lines[i+offset]
                        # Fall 1: "Lag A - Lag B" på samma rad
                        if '-' in txt and len(txt) > 3:
                            parts = txt.split('-')
                            current_match = {
                                'Match': int(line), 
                                'Hemmalag': clean_team_name(parts[0]), 
                                'Bortalag': clean_team_name(parts[1])
                            }
                            break
                        # Fall 2: Lag A på en rad, bindestreck, Lag B på nästa
                        elif txt == '-' and (i+offset+1) < len(lines):
                            hemmalag = lines[i+offset-1]
                            bortalag = lines[i+offset+1]
                            current_match = {
                                'Match': int(line), 
                                'Hemmalag': clean_team_name(hemmalag), 
                                'Bortalag': clean_team_name(bortalag)
                            }
                            break
            except Exception: pass
        
        # Letar efter streckfördelning
        if current_match and ("Svenska Folket" in line or "Svenska folket" in line):
            try:
                temp_pcts = []
                for offset in range(0, 4):
                    if i + offset < len(lines):
                        found = re.findall(r'(\d+)%', lines[i+offset])
                        for val in found: temp_pcts.append(int(val))
                if len(temp_pcts) >= 3:
                    current_match.update({'Streck_1': temp_pcts[0], 'Streck_X': temp_pcts[1], 'Streck_2': temp_pcts[2]})
                    if 'Hemmalag' in current_match:
                         if not any(m['Match'] == current_match['Match'] for m in matches):
                             matches.append(current_match)
                             current_match = {}
            except ValueError: pass
        i += 1
    return sorted(matches, key=lambda x: x['Match'])

# --- 3. BERÄKNINGAR ---
def calculate_probabilities(row):
    o1 = row.get('API_Odds_1', 0)
    ox = row.get('API_Odds_X', 0)
    o2 = row.get('API_Odds_2', 0)
    if o1 == 0 or ox == 0 or o2 == 0: return 0, 0, 0
    raw_1, raw_x, raw_2 = 1/o1, 1/ox, 1/o2
    total = raw_1 + raw_x + raw_2
    return round((raw_1/total)*100, 1), round((raw_x/total)*100, 1), round((raw_2/total)*100, 1)

def suggest_sign_and_status(row):
    tecken = []
    status = ""
    prob1 = row.get('Prob_1', 0)
    
    if prob1 == 0: return "❓", "Saknar Odds"

    val1, valx, val2 = row.get('Val_1', 0), row.get('Val_X', 0), row.get('Val_2', 0)

    # Enkel algoritm för tecken
    if row['Prob_1'] > 55 and val1 > -15: tecken.append('1')
    elif row['Prob_2'] > 55 and val2 > -15: tecken.append('2')
    else:
        # Gå på värde
        values = [('1', val1), ('X', valx), ('2', val2)]
        values.sort(key=lambda x: x[1], reverse=True) # Sortera efter högst värde
        
        tecken.append(values[0][0]) # Ta det med bäst värde
        
        if values[0][1] > 10: status = f"💎 Fynd {values[0][0]}"
        elif values[0][1] < -10: status = "⚠️ Varning"
        else: status = "Neutral"
        
        # Gardera om favoriten är svag
        if len(tecken) < 2: 
            tecken.append(values[1][0])
        
    return "".join(sorted(tecken)), status

# --- APP LAYOUT ---
st.set_page_config(page_title="Stryktipset UK Edition", layout="wide")
st.title(ST_PAGE_TITLE)

with st.expander("ℹ️ Instruktioner", expanded=True):
    col1, col2 = st.columns([2, 1])
    with col1:
        st.write("1. Markera allt (Ctrl+A) på Svenska Spel, kopiera (Ctrl+C).")
        st.write("2. Klistra in nedan och kör.")
        st.write("3. **Nyhet:** Skriptet söker nu automatiskt efter alla ligor i England & Skottland.")
    with col2:
        st.link_button("Öppna Stryktipset ↗️", SVENSKA_SPEL_URL, use_container_width=True)

# --- FORMULÄR ---
with st.form("input_form"):
    text_input = st.text_area("Klistra in här:", height=200, placeholder=PLACEHOLDER_TEXT)
    submitted = st.form_submit_button("🚀 Kör Analys", type="primary", use_container_width=True)

if submitted and text_input:
    matches_data = parse_svenskaspel_paste(text_input)
    
    if not matches_data: st.error("Hittade inga matcher. Kontrollera att du kopierat hela sidan.")
    
    if matches_data:
        with st.spinner('Scannar av England & Skottland efter matcher...'):
            external_odds = fetch_external_odds(API_KEY)
        
        odds_teams = list(external_odds.keys()) if external_odds else []
        final_rows = []
        matches_found_in_api = 0

        for m in matches_data:
            original_name = m['Hemmalag']
            matched = False
            m['Matchat_Lag'] = "-" 
            
            if external_odds:
                # Fuzzy matchning (Fixat variabel-felet här!)
                result = process.extractOne(original_name, odds_teams)
                
                if result:
                    match_name, score = result[0], result[1]
                    
                    if score >= MATCH_THRESHOLD: 
                        odds = external_odds[match_name]
                        m['API_Odds_1'] = odds['1']
                        m['API_Odds_X'] = odds['X']
                        m['API_Odds_2'] = odds['2']
                        m['Källa'] = "Odds API"
                        m['Matchat_Lag'] = match_name 
                        matches_found_in_api += 1
                        matched = True
            
            if not matched:
                m['Källa'] = "Saknas"
                m['API_Odds_1'] = 0
                m['API_Odds_X'] = 0
                m['API_Odds_2'] = 0
            
            final_rows.append(m)

        df = pd.DataFrame(final_rows)
        
        # Beräkningar
        probs = df.apply(calculate_probabilities, axis=1, result_type='expand')
        df[['Prob_1', 'Prob_X', 'Prob_2']] = probs
        
        df['Val_1'] = df['Prob_1'] - df['Streck_1']
        df['Val_X'] = df['Prob_X'] - df['Streck_X']
        df['Val_2'] = df['Prob_2'] - df['Streck_2']
        
        results = df.apply(suggest_sign_and_status, axis=1, result_type='expand')
        df['Tips'] = results[0]
        df['Analys'] = results[1]
        
        df['Folk_Odds_1'] = df['Streck_1'].apply(lambda x: round(100/x, 2) if x > 0 else 0)
        df['Folk_Odds_X'] = df['Streck_X'].apply(lambda x: round(100/x, 2) if x > 0 else 0)
        df['Folk_Odds_2'] = df['Streck_2'].apply(lambda x: round(100/x, 2) if x > 0 else 0)

        df['Match_Rubrik'] = df['Hemmalag'] + " - " + df['Bortalag']

        def color_value(val):
            if pd.isna(val): return ''
            if val > 7: return 'background-color: #90ee90; color: black' 
            if val < -10: return 'background-color: #ffcccb; color: black' 
            return ''

        st.success(f"Hittade odds för {matches_found_in_api} av {len(df)} lag via UK-sökning.")
        if matches_found_in_api < 8:
            st.warning("Hittade få odds. Kontrollera att matcherna faktiskt spelas i England/Skottland denna omgång.")

        table_height = (len(df) * 35) + 38 
        
        tab1, tab2, tab3, tab4 = st.tabs(["💡 Kupong", "📊 Värde", "⚖️ Jämförelse", "🔧 Info"])
        
        with tab1:
            kupong_view = df[['Match', 'Match_Rubrik', 'Tips', 'Analys']].copy()
            st.dataframe(kupong_view, hide_index=True, use_container_width=True, height=table_height)
            
        with tab2:
            st.write("Grönt = Bra värde (Folket underskattar). Rött = Överstreckat (Folket överskattar).")
            val_view = df[['Match', 'Match_Rubrik', 'Val_1', 'Val_X', 'Val_2']].copy()
            styled_df = val_view.style.map(color_value, subset=['Val_1', 'Val_X', 'Val_2'])
            st.dataframe(styled_df, hide_index=True, use_container_width=True, height=table_height)
            
        with tab3:
            odds_view = df[['Match', 'Match_Rubrik', 'API_Odds_1', 'Folk_Odds_1', 'API_Odds_X', 'Folk_Odds_X', 'API_Odds_2', 'Folk_Odds_2']].copy()
            st.dataframe(odds_view, hide_index=True, use_container_width=True, height=table_height)

        with tab4:
            st.write("Visar vilket lag API:et matchade med:")
            st.dataframe(df[['Match', 'Hemmalag', 'Matchat_Lag', 'Källa']], hide_index=True, use_container_width=True, height=table_height)

