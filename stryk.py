import streamlit as st
import pandas as pd
import re

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset: Svenska Spel Edition"
SVENSKA_SPEL_URL = "https://www.svenskaspel.se/stryktipset"
PLACEHOLDER_TEXT = """Klistra in hela sidan (Ctrl+A) från Stryktipset här..."""

# --- HJÄLPFUNKTIONER ---
def clean_team_name(name):
    name = re.sub(r'^\d+[\.\s]*', '', name) 
    name = name.replace("1X2", "").replace("1", "").replace("X", "").replace("2", "")
    return name.strip()

# --- 1. PARSA PASTE (FÖRBÄTTRAD FÖR ATT HITTA ODDS) ---
def parse_svenskaspel_paste(text_content):
    matches = []
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    
    current_match = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 1. Hitta Matchnummer (1-13)
        if line.isdigit() and 1 <= int(line) <= 13:
            match_num = int(line)
            # Sök efter lag
            for offset in range(1, 4):
                if i + offset < len(lines):
                    txt = lines[i+offset]
                    if '-' in txt and len(txt) > 3:
                        parts = txt.split('-')
                        current_match = {
                            'Match': match_num,
                            'Hemmalag': clean_team_name(parts[0]),
                            'Bortalag': clean_team_name(parts[1]),
                            'SS_Odds_1': 0, 'SS_Odds_X': 0, 'SS_Odds_2': 0,
                            'Streck_1': 0, 'Streck_X': 0, 'Streck_2': 0
                        }
                        break

        # 2. Hitta Svenska Spels Odds (t.ex. "2,45  3,20  3,10")
        # Letar efter mönster med decimaltal (komma eller punkt)
        odds_found = re.findall(r'(\d+[\.,]\d+)', line)
        if current_match and len(odds_found) >= 3:
            # Vi tar de tre första talen vi hittar efter lagnamnet som odds
            if current_match['SS_Odds_1'] == 0:
                current_match['SS_Odds_1'] = float(odds_found[0].replace(',', '.'))
                current_match['SS_Odds_X'] = float(odds_found[1].replace(',', '.'))
                current_match['SS_Odds_2'] = float(odds_found[2].replace(',', '.'))

        # 3. Hitta Streckfördelning (Svenska folket)
        if current_match and ("Svenska folket" in line.lower()):
            try:
                temp_pcts = []
                for offset in range(0, 4):
                    if i + offset < len(lines):
                        found = re.findall(r'(\d+)%', lines[i+offset])
                        for val in found: temp_pcts.append(int(val))
                if len(temp_pcts) >= 3:
                    current_match.update({
                        'Streck_1': temp_pcts[0], 
                        'Streck_X': temp_pcts[1], 
                        'Streck_2': temp_pcts[2]
                    })
                    # Spara matchen när vi har både lag och streck
                    if not any(m['Match'] == current_match['Match'] for m in matches):
                        matches.append(current_match)
                        current_match = {}
            except Exception: pass
        i += 1
    return sorted(matches, key=lambda x: x['Match'])

# --- 2. BERÄKNINGAR BASERAT PÅ ODDS ---
def calculate_probabilities(row):
    o1, ox, o2 = row['SS_Odds_1'], row['SS_Odds_X'], row['SS_Odds_2']
    if o1 == 0: return 0, 0, 0
    # Beräkna sannolikhet baserat på oddset (inkl. marginal)
    raw_1, raw_x, raw_2 = 1/o1, 1/ox, 1/o2
    total = raw_1 + raw_x + raw_2
    return round((raw_1/total)*100, 1), round((raw_x/total)*100, 1), round((raw_2/total)*100, 1)

def suggest_sign(row):
    if row['Prob_1'] == 0: return "❓", "Inga odds hittades"
    
    val1 = row['Prob_1'] - row['Streck_1']
    valx = row['Prob_X'] - row['Streck_X']
    val2 = row['Prob_2'] - row['Streck_2']
    
    vals = [('1', val1), ('X', valx), ('2', val2)]
    vals.sort(key=lambda x: x[1], reverse=True)
    
    best_sign = vals[0][0]
    if vals[0][1] > 5: status = f"💎 Värdespik {best_sign}"
    elif vals[0][1] < -5: status = "⚠️ Överstreckad"
    else: status = "Neutral"
    
    # Garderingstips om det är jämnt värde
    tips = best_sign
    if vals[1][1] > -2: # Om näst bästa tecken också har hyfsat värde
        tips = "".join(sorted([best_sign, vals[1][0]]))
        
    return tips, status

# --- APP LAYOUT ---
st.set_page_config(page_title="Stryktipset Offline", layout="wide")
st.title(ST_PAGE_TITLE)

st.info("Klistra in datan från Svenska Spel. Scriptet läser nu av både **Svenska folkets streck** och **Svenska Spels egna odds** för att hitta värde.")

text_input = st.text_area("Klistra in (Ctrl+A -> Ctrl+C) från kupongen:", height=200, placeholder=PLACEHOLDER_TEXT)
submitted = st.button("🚀 Analysera Värde", type="primary", use_container_width=True)

if submitted and text_input:
    data = parse_svenskaspel_paste(text_input)
    
    if not data:
        st.error("Kunde inte läsa datan. Se till att du kopierar hela sidan inkl. odds och procent.")
    else:
        df = pd.DataFrame(data)
        
        # Beräkna sannolikhet från odds
        df[['Prob_1', 'Prob_X', 'Prob_2']] = df.apply(calculate_probabilities, axis=1, result_type='expand')
        
        # Beräkna över/undervärde
        df['Val_1'] = df['Prob_1'] - df['Streck_1']
        df['Val_X'] = df['Prob_X'] - df['Streck_X']
        df['Val_2'] = df['Prob_2'] - df['Streck_2']
        
        # Tips och Status
        tips_res = df.apply(suggest_sign, axis=1, result_type='expand')
        df['Tips'] = tips_res[0]
        df['Status'] = tips_res[1]
        
        # Visa resultat
        tab1, tab2 = st.tabs(["📋 Spelförslag", "📊 Detaljerad Analys"])
        
        with tab1:
            st.dataframe(df[['Match', 'Hemmalag', 'Bortalag', 'Tips', 'Status']], hide_index=True, use_container_width=True)
            
        with tab2:
            st.write("Skillnad mellan Odds-sannolikhet och Svenska folkets streckning:")
            def color_val(v):
                if v > 5: return 'background-color: #90ee90'
                if v < -8: return 'background-color: #ffcccb'
                return ''
            
            styled_df = df[['Match', 'Hemmalag', 'Streck_1', 'Val_1', 'Streck_X', 'Val_X', 'Streck_2', 'Val_2']].style.applymap(color_val, subset=['Val_1', 'Val_X', 'Val_2'])
            st.dataframe(styled_df, hide_index=True, use_container_width=True)

st.divider()
st.caption("Notera: Detta verktyg använder nu de fasta oddsen från Svenska Spel för att beräkna sannolikhet istället för externa API:er.")
