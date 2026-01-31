import streamlit as st
import pandas as pd
import re

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset: Robust Edition v2"
SVENSKA_SPEL_URL = "https://www.svenskaspel.se/stryktipset"

# --- PLATSHÅLLARTEXT ---
PLACEHOLDER_TEXT = """Klistra in hela sidan (Ctrl+A) från den vanliga kupongvyn.
Se till att både streckprocent och odds kommer med."""

# --- 1. HJÄLPFUNKTIONER ---
def clean_team_name(name):
    if not isinstance(name, str): return "-"
    # Tar bort siffror i början, punkt, och 1X2-tecken
    name = re.sub(r'^\d+[\.\s]*', '', name) 
    name = name.replace("1X2", "").replace("1", "").replace("X", "").replace("2", "")
    return name.strip()

def find_three_values(lines, start_index, search_type="percent"):
    """Letar efter 3 värden (procent eller odds) i de kommande raderna."""
    found_values = []
    # Sök i upp till 8 rader framåt
    for offset in range(1, 9):
        if start_index + offset >= len(lines):
            break
        
        txt = lines[start_index + offset].strip()
        if not txt: continue 

        if search_type == "percent":
            matches = re.findall(r'(\d+)%', txt)
            if not matches and txt.isdigit() and int(txt) < 100:
                matches = [txt]
            for m in matches: found_values.append(int(m))

        elif search_type == "odds":
            clean_txt = txt.replace(',', '.')
            matches = re.findall(r'(\d+\.\d{2})', clean_txt)
            for m in matches: found_values.append(float(m))
        
        if len(found_values) >= 3:
            return found_values[:3]
            
    return None

# --- 2. PARSER ---
def parse_svenskaspel_paste(text_content):
    matches = []
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    current_match = {}
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # --- HITTA MATCHNUMMER ---
        if line.isdigit() and 1 <= int(line) <= 13:
            if current_match and 'Hemmalag' in current_match:
                matches.append(current_match)
            current_match = {'Match': int(line)}
            
            # --- HITTA LAGNAMN ---
            try:
                # Sök i buffer
                buffer = lines[i+1:i+6]
                if '-' in buffer:
                    idx = buffer.index('-')
                    current_match['Hemmalag'] = clean_team_name(buffer[idx-1])
                    current_match['Bortalag'] = clean_team_name(buffer[idx+1])
                else:
                    for txt in buffer:
                        if ' - ' in txt:
                            parts = txt.split(' - ')
                            current_match['Hemmalag'] = clean_team_name(parts[0])
                            current_match['Bortalag'] = clean_team_name(parts[1])
                            break
            except Exception: pass
            
        # --- HITTA STRECK ---
        if "Svenska folket" in line or "Svenska Folket" in line:
            pcts = find_three_values(lines, i, "percent")
            if pcts:
                current_match['Streck_1'] = pcts[0]
                current_match['Streck_X'] = pcts[1]
                current_match['Streck_2'] = pcts[2]

        # --- HITTA ODDS ---
        if "Odds" in line and len(line) < 20:
            odds = find_three_values(lines, i, "odds")
            if odds:
                current_match['Odds_1'] = odds[0]
                current_match['Odds_X'] = odds[1]
                current_match['Odds_2'] = odds[2]

        i += 1
    
    if current_match and 'Match' in current_match:
        matches.append(current_match)

    unique = {m['Match']: m for m in matches}.values()
    return sorted(list(unique), key=lambda x: x['Match'])

# --- 3. BERÄKNINGAR ---
def calculate_probabilities(row):
    o1, ox, o2 = row.get('Odds_1', 0), row.get('Odds_X', 0), row.get('Odds_2', 0)
    if o1 == 0 or ox == 0 or o2 == 0: return 0, 0, 0
    raw = [1/o1, 1/ox, 1/o2]
    total = sum(raw)
    return tuple(round((r/total)*100, 1) for r in raw)

def suggest_sign_and_status(row):
    if row['Prob_1'] == 0: return "❓", "Saknar Odds"

    val1, valx, val2 = row['Val_1'], row['Val_X'], row['Val_2']
    options = [('1', val1, row['Prob_1']), ('X', valx, row['Prob_X']), ('2', val2, row['Prob_2'])]
    options.sort(key=lambda x: x[1], reverse=True) # Sortera på värde
    
    best_sign = options[0]
    tecken = [best_sign[0]]
    status = "Neutral"

    if best_sign[1] > 10: status = f"💎 Fynd {best_sign[0]}"
    elif best_sign[1] < -10: status = "⚠️ Dåligt värde"

    # Gardering
    probs_sorted = sorted(options, key=lambda x: x[2], reverse=True)
    favorite = probs_sorted[0][0]

    if best_sign[0] != favorite:
        tecken.append(favorite)
    elif best_sign[1] < 5: 
        tecken.append(options[1][0])

    return "".join(sorted(tecken)), status

# --- APP START ---
st.set_page_config(page_title="Stryktipset Robust", layout="wide")
st.title(ST_PAGE_TITLE)

with st.expander("ℹ️ Instruktioner", expanded=True):
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info("Klistra in hela sidan (Ctrl+A -> Ctrl+C).")
    with col2:
        st.link_button("Öppna Svenska Spel ↗️", SVENSKA_SPEL_URL, use_container_width=True)

with st.form("input_form"):
    text_input = st.text_area("Klistra in här:", height=300, placeholder=PLACEHOLDER_TEXT)
    submitted = st.form_submit_button("🚀 Kör Analys", type="primary", use_container_width=True)

if submitted and text_input:
    raw_data = parse_svenskaspel_paste(text_input)
    
    if not raw_data:
        st.error("Hittade inga matcher.")
    else:
        df = pd.DataFrame(raw_data)
        
        # --- FIX: SÄKERSTÄLL ATT TEXT ÄR TEXT OCH SIFFROR ÄR SIFFROR ---
        
        # 1. Se till att textkolumner finns och fyll tomma med "-"
        if 'Hemmalag' not in df.columns: df['Hemmalag'] = "-"
        if 'Bortalag' not in df.columns: df['Bortalag'] = "-"
        
        # Fyll textkolumnerna med strängar innan vi fyller resten med 0
        df['Hemmalag'] = df['Hemmalag'].fillna("-").astype(str)
        df['Bortalag'] = df['Bortalag'].fillna("-").astype(str)

        # 2. Se till att sifferkolumner finns
        required_cols = ['Streck_1', 'Streck_X', 'Streck_2', 'Odds_1', 'Odds_X', 'Odds_2']
        for col in required_cols:
            if col not in df.columns: df[col] = 0

        # 3. Nu kan vi fylla resten (siffror) med 0 säkert
        df = df.fillna(0)
        
        # --- BERÄKNINGAR ---
        probs = df.apply(calculate_probabilities, axis=1, result_type='expand')
        df[['Prob_1', 'Prob_X', 'Prob_2']] = probs
        
        df['Val_1'] = df['Prob_1'] - df['Streck_1']
        df['Val_X'] = df['Prob_X'] - df['Streck_X']
        df['Val_2'] = df['Prob_2'] - df['Streck_2']
        
        results = df.apply(suggest_sign_and_status, axis=1, result_type='expand')
        df['Tips'] = results[0]
        df['Analys'] = results[1]
        
        # Nu är det säkert att slå ihop strängarna
        df['Match_Rubrik'] = df['Hemmalag'] + " - " + df['Bortalag']

        # --- VISNING ---
        st.success(f"Lyckades läsa in {len(df)} matcher!")
        
        h = (len(df) * 35) + 38
        tab1, tab2, tab3 = st.tabs(["💡 Kupong", "📊 Värdetabell", "🔍 Rådata"])
        
        with tab1:
            st.dataframe(
                df[['Match', 'Match_Rubrik', 'Tips', 'Analys', 'Streck_1', 'Streck_X', 'Streck_2']], 
                hide_index=True, use_container_width=True, height=h
            )

        with tab2:
            st.write("Positivt = Bra värde. Negativt = Dåligt värde.")
            display_cols = ['Match', 'Match_Rubrik', 'Val_1', 'Val_X', 'Val_2', 'Odds_1', 'Odds_X', 'Odds_2']
            st.dataframe(
                df[display_cols].style.map(
                    lambda x: 'background-color: #d4edda' if x > 7 else ('background-color: #f8d7da' if x < -10 else ''), 
                    subset=['Val_1', 'Val_X', 'Val_2']
                ).format("{:.1f}", subset=['Val_1', 'Val_X', 'Val_2']),
                hide_index=True, use_container_width=True, height=h
            )
            
        with tab3:
            st.dataframe(df, use_container_width=True)
