import streamlit as st
import pandas as pd
import numpy as np
import requests
import re
from thefuzz import process 

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset: Pro Edition"
API_KEY = "31e8d45e0996d4e60b6dc48f8c656089" # <--- DIN NYCKEL HÄR
CACHE_TIME = 900 
MATCH_THRESHOLD = 85  # <--- HÅRDARE KRAV: 85% likhet

# --- PLATSHÅLLARTEXT ---
PLACEHOLDER_TEXT = """Klistra in hela sidan (Ctrl+A) från den vanliga kupongvyn."""

# --- ÖVERSÄTTNINGSLISTA ---
# Fyll på denna lista när du hittar lag som inte matchar!
TEAM_TRANSLATIONS = {
    # England
    "Sheffield U": "Sheffield United",
    "Sheffield W": "Sheffield Wednesday",
    "QPR": "Queens Park Rangers",
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
    "WBA": "West Bromwich Albion",
    "West Bromwich": "West Bromwich Albion",
    "Derby": "Derby County",
    "Portsmouth": "Portsmouth FC",
    "Millwall": "Millwall FC",
    "Luton": "Luton Town",
    "Burnley": "Burnley FC",
    "Man United": "Manchester United",
    "Man City": "Manchester City",
    "Nott. Forest": "Nottingham Forest",
    "Newcastle": "Newcastle United",
    "West Ham": "West Ham United",
    "Brighton": "Brighton and Hove Albion",
    
    # Sverige
    "IFK Gbg": "IFK Göteborg",
    "Malmö": "Malmö FF",
    "Djurgården": "Djurgårdens IF",
    "AIK": "AIK Stockholm",
    "Häcken": "BK Häcken",
    "Västerås": "Västerås SK",
    "Brommapojk": "IF Brommapojkarna",

    # Europa
    "Inter": "Internazionale",
    "Milan": "AC Milan",
    "Roma": "AS Roma",
    "Lazio": "SS Lazio",
    "Napoli": "SSC Napoli",
    "Juventus": "Juventus FC",
    "Atalanta": "Atalanta BC",
    "Barcelona": "FC Barcelona",
    "R. Madrid": "Real Madrid",
    "Atl. Madrid": "Atletico Madrid",
    "Bilbao": "Athletic Club Bilbao",
    "Real Sociedad": "Real Sociedad",
    "Betis": "Real Betis",
    "Sevilla": "Sevilla FC",
    "Bayern München": "Bayern Munich",
    "Dortmund": "Borussia Dortmund",
    "Leverkusen": "Bayer Leverkusen",
    "Leipzig": "RB Leipzig",
    "Paris SG": "Paris Saint Germain",
    "Marseille": "Olympique Marseille",
    "Lyon": "Olympique Lyonnais",
    "Ajax": "AFC Ajax",
    "PSV": "PSV Eindhoven"
}

# --- 1. HÄMTA EXTERNA ODDS (DOPAD LISTA) ---
@st.cache_data(ttl=CACHE_TIME)
def fetch_external_odds(api_key):
    if not api_key or "DIN_NYCKEL" in api_key:
        return {}

    all_odds = {}
    
    # HÄR ÄR DEN NYA SUPER-LISTAN
    leagues = [
        # --- England ---
        'soccer_epl',                   # Premier League
        'soccer_efl_championship',      # Championship
        'soccer_england_league1',       # League 1
        'soccer_england_league2',       # League 2
        'soccer_fa_cup',                # FA Cup
        'soccer_efl_cup',               # League Cup
        
        # --- Norden (Viktigt för Stryktipset) ---
        'soccer_sweden_allsvenskan',    # Allsvenskan
        'soccer_sweden_superettan',     # Superettan (Ofta med på sommaren)
        'soccer_norway_eliteserien',    # Norge
        'soccer_denmark_superliga',     # Danmark
        
        # --- Europa Stora ---
        'soccer_italy_serie_a',         # Serie A
        'soccer_spain_la_liga',         # La Liga
        'soccer_germany_bundesliga',    # Bundesliga
        'soccer_france_ligue_one',      # Ligue 1
        'soccer_netherlands_eredivisie',# Eredivisie
        'soccer_portugal_primeira_liga',# Portugal (Dyker ofta upp!)
        'soccer_turkey_super_league',   # Turkiet
        
        # --- Europa Andraligor (Europatipset gillar dessa) ---
        'soccer_italy_serie_b',         # Serie B
        'soccer_spain_segunda_division',# La Liga 2
        'soccer_germany_bundesliga2',   # 2. Bundesliga
        'soccer_france_ligue_two',      # Ligue 2
        
        # --- Skottland ---
        'soccer_spl',                   # Scottish Premiership
        
        # --- Cuper ---
        'soccer_uefa_champs_league',
        'soccer_uefa_europa_league',
        'soccer_uefa_europa_conference_league'
    ]
    
    # Förloppsindikator i appen (så man ser att den jobbar)
    prog_bar = st.progress(0, text="Hämtar odds från olika ligor...")
    total_leagues = len(leagues)
    
    for i, league in enumerate(leagues):
        # Uppdatera mätaren
        prog_bar.progress((i + 1) / total_leagues, text=f"Kollar liga: {league}...")
        
        url = f'https://api.the-odds-api.com/v4/sports/{league}/odds/?apiKey={api_key}&regions=eu&markets=h2h'
        try:
            response = requests.get(url)
            # 401 = Fel nyckel, 429 = Slut på förfrågningar (Gratis-kvot)
            if response.status_code == 429:
                st.warning("⚠️ Varning: Du har nått gränsen för din gratis API-nyckel för stunden.")
                break 
            if response.status_code != 200: continue
            
            data = response.json()
            
            for match in data:
                home_team = match['home_team']
                simple_name = home_team.replace(" FC", "").replace(" AFC", "").replace(" BC", "").replace(" SSC", "").strip()
                
                bookmakers = match.get('bookmakers', [])
                if not bookmakers: continue
                
                outcomes = bookmakers[0]['markets'][0]['outcomes']
                o1, ox, o2 = 0, 0, 0
                for outcome in outcomes:
                    if outcome['name'] == home_team: o1 = outcome['price']
                    elif outcome['name'] == match['away_team']: o2 = outcome['price']
                    else: ox = outcome['price']
                
                odds_data = {'1': o1, 'X': ox, '2': o2}
                
                # Spara både fullt namn och enkelt namn
                all_odds[home_team] = odds_data
                if simple_name != home_team:
                    all_odds[simple_name] = odds_data
                    
        except Exception:
            pass
            
    prog_bar.empty() # Ta bort mätaren när klar
    return all_odds

# --- HJÄLPFUNKTION: STÄDA NAMN ---
def clean_team_name(name):
    name = re.sub(r'^\d+[\.\s]*', '', name) 
    name = name.replace("1X2", "") 
    name = name.replace("1", "").replace("X", "").replace("2", "")
    return name.strip()

# --- 2. LÄS PASTE (Hela Sidan-logik) ---
def parse_svenskaspel_paste(text_content):
    matches = []
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    current_match = {}
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # 1. Hitta matchnummer
        if line.isdigit() and 1 <= int(line) <= 13:
            try:
                for offset in range(1, 6):
                    if i + offset < len(lines):
                        txt = lines[i+offset]
                        if '-' in txt and len(txt) > 3:
                            parts = txt.split('-')
                            hemmalag = parts[0]
                            bortalag = parts[1]
                            current_match = {'Match': int(line), 'Hemmalag': clean_team_name(hemmalag), 'Bortalag': clean_team_name(bortalag)}
                            break
                        elif txt == '-' and (i+offset+1) < len(lines):
                            hemmalag = lines[i+offset-1]
                            bortalag = lines[i+offset+1]
                            current_match = {'Match': int(line), 'Hemmalag': clean_team_name(hemmalag), 'Bortalag': clean_team_name(bortalag)}
                            break
            except Exception: pass
        
        # 2. Hitta Svenska Folket
        if current_match and ("Svenska Folket" in line or "Svenska folket" in line):
            try:
                temp_pcts = []
                for offset in range(0, 4):
                    if i + offset < len(lines):
                        check_line = lines[i+offset]
                        found = re.findall(r'(\d+)%', check_line)
                        for val in found:
                            temp_pcts.append(int(val))
                
                if len(temp_pcts) >= 3:
                    current_match.update({'Streck_1': temp_pcts[0], 'Streck_X': temp_pcts[1], 'Streck_2': temp_pcts[2]})
                    if 'Hemmalag' in current_match:
                         if not any(m['Match'] == current_match['Match'] for m in matches):
                             matches.append(current_match)
                             current_match = {}
            except ValueError: pass
        i += 1
    
    matches = sorted(matches, key=lambda x: x['Match'])
    return matches

# --- 3. BERÄKNINGAR ---
def calculate_probabilities(row):
    o1 = row.get('API_Odds_1', 0)
    ox = row.get('API_Odds_X', 0)
    o2 = row.get('API_Odds_2', 0)
    
    if o1 == 0 or ox == 0 or o2 == 0:
        return 0, 0, 0
        
    raw_1, raw_x, raw_2 = 1/o1, 1/ox, 1/o2
    total = raw_1 + raw_x + raw_2
    return round((raw_1/total)*100, 1), round((raw_x/total)*100, 1), round((raw_2/total)*100, 1)

def suggest_sign_and_status(row):
    tecken = []
    status = ""
    
    prob1 = row.get('Prob_1', 0)
    if prob1 == 0:
        return "❓", "Saknar Odds"

    val1 = row.get('Val_1', 0)
    valx = row.get('Val_X', 0)
    val2 = row.get('Val_2', 0)

    if row['Prob_1'] > 55 and val1 > -15:
        tecken.append('1')
    elif row['Prob_2'] > 55 and val2 > -15:
        tecken.append('2')
    else:
        values = [('1', val1), ('X', valx), ('2', val2)]
        values.sort(key=lambda x: x[1], reverse=True)
        tecken.append(values[0][0])
        
        if values[0][1] > 7: status = f"💎 Fynd {values[0][0]}"
        elif values[0][1] < -10: status = "⚠️ Överstreckad"
        else: status = "Neutral"
        
        if len(tecken) < 2: tecken.append(values[1][0])
        
    return "".join(sorted(tecken)), status

# --- APP LAYOUT ---
st.set_page_config(page_title="Stryktipset & Europatipset", layout="wide")
st.title(ST_PAGE_TITLE)

with st.expander("ℹ️ Instruktioner", expanded=True):
    st.write("1. Gå till Stryktipset eller Europatipset.")
    st.write("2. Se till att du är på standardvyn (kupongen).")
    st.write("3. Markera allt (Ctrl+A), kopiera (Ctrl+C) och klistra in nedan.")

# --- FORMULÄR ---
with st.form("input_form"):
    text_input = st.text_area("Klistra in här:", height=200, placeholder=PLACEHOLDER_TEXT)
    submitted = st.form_submit_button("🚀 Kör Analys", type="primary", use_container_width=True)

if submitted and text_input:
    matches_data = parse_svenskaspel_paste(text_input)
    
    if not matches_data:
        st.error("Hittade inga matcher. Kopierade du hela sidan?")
    elif len(matches_data) < 13:
        st.warning(f"Hittade bara {len(matches_data)} av 13 matcher. Resultatet kan vara ofullständigt.")
    
    if matches_data:
        with st.spinner('Hämtar odds...'):
            external_odds = fetch_external_odds(API_KEY)
        
        odds_teams = list(external_odds.keys()) if external_odds else []
        
        final_rows = []
        matches_found_in_api = 0

        for m in matches_data:
            original_name = m['Hemmalag']
            search_name = TEAM_TRANSLATIONS.get(original_name, original_name)
            
            matched = False
            m['Matchat_Lag'] = "-" 
            
            if external_odds:
                match_name, score = process.extractOne(search_name, odds_teams)
                
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
        
        # 1. Grundberäkningar
        probs = df.apply(calculate_probabilities, axis=1, result_type='expand')
        df[['Prob_1', 'Prob_X', 'Prob_2']] = probs
        
        df['Val_1'] = df['Prob_1'] - df['Streck_1']
        df['Val_X'] = df['Prob_X'] - df['Streck_X']
        df['Val_2'] = df['Prob_2'] - df['Streck_2']
        
        results = df.apply(suggest_sign_and_status, axis=1, result_type='expand')
        df['Tips'] = results[0]
        df['Analys'] = results[1]

        # 2. Räkna ut Folkets Odds (För jämförelsefliken)
        df['Folk_Odds_1'] = df['Streck_1'].apply(lambda x: round(100/x, 2) if x > 0 else 0)
        df['Folk_Odds_X'] = df['Streck_X'].apply(lambda x: round(100/x, 2) if x > 0 else 0)
        df['Folk_Odds_2'] = df['Streck_2'].apply(lambda x: round(100/x, 2) if x > 0 else 0)

        # Färgsättning
        def color_value(val):
            if pd.isna(val): return ''
            if val > 7: return 'background-color: #90ee90; color: black' 
            if val < -10: return 'background-color: #ffcccb; color: black' 
            return ''

        st.success(f"Hittade odds för {matches_found_in_api} av {len(df)} lag.")
        
        table_height = (len(df) * 35) + 38 
        tab1, tab2, tab3, tab4 = st.tabs(["💡 Kupong", "📊 Värde", "⚖️ Odds vs Folket", "🔧 Felsökning"])
        
        with tab1:
            st.dataframe(df[['Match', 'Hemmalag', 'Bortalag', 'Tips', 'Analys']], hide_index=True, use_container_width=True, height=table_height)
            
        with tab2:
            st.write("Grönt = Bra värde. Rött = Överstreckat.")
            styled_df = df[['Match', 'Hemmalag', 'Val_1', 'Val_X', 'Val_2']].style.applymap(color_value, subset=['Val_1', 'Val_X', 'Val_2'])
            st.dataframe(styled_df, hide_index=True, use_container_width=True, height=table_height)
            
        with tab3:
            st.write("**Jämför Bookmakers odds mot Folkets odds.**")
            st.write("Om 'Folkets Odds' är *lägre* än Bookmakers = Folket överskattar laget (Dåligt värde).")
            
            odds_view = df[['Match', 'Hemmalag', 'API_Odds_1', 'Folk_Odds_1', 'API_Odds_X', 'Folk_Odds_X', 'API_Odds_2', 'Folk_Odds_2']].copy()
            odds_view.columns = ['Match', 'Lag', 'Odds 1', 'Folket 1', 'Odds X', 'Folket X', 'Odds 2', 'Folket 2']
            st.dataframe(odds_view, hide_index=True, use_container_width=True, height=table_height)

        with tab4:
            st.write("**Kontrollera matchningen här.**")
            st.write("Om 'Matchat Lag' ser konstigt ut, använd Spion-verktyget nedan för att hitta rätt namn och uppdatera koden.")
            st.dataframe(df[['Match', 'Hemmalag', 'Bortalag', 'Matchat_Lag', 'Källa']], hide_index=True, use_container_width=True, height=table_height)

# --- SPION-VERKTYG (MANUELL SÖKNING) ---
st.divider()
with st.expander("🕵️ Hittar du inte laget? Klicka här för att söka i API:et"):
    st.write("Klicka på knappen nedan för att se exakt vilka namn API:et använder.")
    if st.button("Hämta alla lagnamn från API"):
        with st.spinner("Hämtar listan..."):
            all_odds = fetch_external_odds(API_KEY)
            if all_odds:
                # Sorterad lista på alla lagnamn
                team_list = sorted(list(all_odds.keys()))
                st.write(f"Hittade **{len(team_list)}** lag totalt.")
                st.text_area("Kopiera namnet härifrån och lägg in i koden (TEAM_TRANSLATIONS):", 
                             value="\n".join(team_list), 
                             height=400)
            else:
                st.error("Kunde inte hämta listan. Kolla API-nyckeln.")

