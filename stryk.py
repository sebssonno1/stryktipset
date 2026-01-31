import streamlit as st
import pandas as pd
import re

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset"
SVENSKA_SPEL_URL = "https://www.svenskaspel.se/stryktipset"

# --- HJÄLPFUNKTIONER ---
def to_float(val_str):
    """Gör om '1,78' till 1.78. Returnerar None om det inte är ett decimaltal."""
    try:
        clean = val_str.replace(',', '.').replace('%', '').strip()
        # Vi kräver att det finns en punkt/komma för att det ska räknas som odds
        if '.' in clean:
            return float(clean)
        return float(clean)
    except ValueError:
        return None

def clean_team_name(name):
    if not isinstance(name, str): return "-"
    name = re.sub(r'^\d+[\.\s]*', '', name) 
    name = name.replace("1X2", "").replace("1", "").replace("X", "").replace("2", "")
    return name.strip()

# --- PARSER (DEN ROBUSTA VERSIONEN) ---
def parse_svenskaspel_paste(text_content):
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    
    match_indices = {}
    current_target = 1
    
    # 1. Hitta matchstarter (1-13)
    for i, line in enumerate(lines):
        if line == str(current_target):
            is_real_match = True
            
            # Titta på nästa rad för att undvika rubriker
            if i + 1 < len(lines):
                next_line = lines[i+1]
                if next_line in ['X', '-', '–', '1X2'] or "Tipsinfo" in next_line:
                    is_real_match = False
            
            # Titta på föregående rad
            if i > 0:
                prev_line = lines[i-1]
                if prev_line in ['X'] or "Tipsinfo" in prev_line:
                    is_real_match = False

            if is_real_match:
                match_indices[current_target] = i
                current_target += 1
                if current_target > 13: break 

    if len(match_indices) < 13:
        st.error(f"Hittade bara {len(match_indices)} av 13 matcher. Kopierade du hela listan?")
        return []

    matches = []
    
    # 2. Loopa igenom match 1 till 13
    for m_num in range(1, 14):
        start_idx = match_indices[m_num]
        if m_num < 13:
            end_idx = match_indices[m_num + 1]
        else:
            end_idx = min(len(lines), start_idx + 60)
            
        block = lines[start_idx:end_idx]
        current_match = {'Match': m_num}
        
        # A. Hitta Lagnamn
        found_names = False
        if len(block) > 3:
            for offset in [1, 2, 3]:
                if offset < len(block) and block[offset] in ['-', '–', '—', 'vs']:
                    current_match['Hemmalag'] = clean_team_name(block[offset-1])
                    current_match['Bortalag'] = clean_team_name(block[offset+1])
                    found_names = True
                    break
        if not found_names:
             current_match['Hemmalag'] = "-"; current_match['Bortalag'] = "-"

        # B. Hitta Streck (Svenska folket)
        streck_values = []
        capture_streck = False
        for line in block:
            if '%' in line:
                try:
                    val = int(line.replace('%', '').strip())
                    streck_values.append(val)
                except: pass
            
            if "Svenska folket" in line: capture_streck = True
            if "Odds" in line: capture_streck = False
            
            if capture_streck and '%' not in line and line.isdigit():
                val = int(line)
                if val <= 100: streck_values.append(val)

        if len(streck_values) >= 3:
            current_match['Streck_1'] = streck_values[0]
            current_match['Streck_X'] = streck_values[1]
            current_match['Streck_2'] = streck_values[2]
        else:
            current_match['Streck_1'] = 0; current_match['Streck_X'] = 0; current_match['Streck_2'] = 0

        # C. Hitta Odds
        odds_values = []
        capture_odds = False
        for line in block:
            if "Odds" in line:
                capture_odds = True
                continue
            
            if capture_odds:
                if re.match(r'^\d+[.,]\d{2}$', line):
                    val = to_float(line)
                    if val: odds_values.append(val)
                if len(odds_values) >= 3: break
        
        if len(odds_values) >= 3:
            current_match['Odds_1'] = odds_values[0]
            current_match['Odds_X'] = odds_values[1]
            current_match['Odds_2'] = odds_values[2]
        else:
            current_match['Odds_1'] = 0; current_match['Odds_X'] = 0; current_match['Odds_2'] = 0

        matches.append(current_match)

    return matches

# --- BERÄKNINGAR ---
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
    
    options.sort(key=lambda x: x[1], reverse=True) 
    
    best_sign = options[0]
    tecken = [best_sign[0]]
    status = "Neutral"

    if best_sign[1] > 7: status = f"💎 Fynd {best_sign[0]}"
    elif best_sign[1] < -10: status = "⚠️ Dåligt värde"

    probs_sorted = sorted(options, key=lambda x: x[2], reverse=True)
    favorite = probs_sorted[0][0]

    if best_sign[0] != favorite:
        tecken.append(favorite)
    elif best_sign[1] < 5: 
        tecken.append(options[1][0])

    return "".join(sorted(tecken)), status

# --- APP LAYOUT ---
st.set_page_config(page_title="Stryktipset", layout="wide")
st.title(ST_PAGE_TITLE)

# --- HÄR ÄR LÄNKEN TILLBAKA ---
with st.expander("ℹ️ Instruktioner", expanded=True):
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info("1. Markera allt (Ctrl+A) på Svenska Spel.\n2. Kopiera (Ctrl+C).\n3. Klistra in nedan.")
    with col2:
        st.link_button("Öppna Stryktipset ↗️", SVENSKA_SPEL_URL, use_container_width=True)

with st.form("input_form"):
    text_input = st.text_area("Klistra in här:", height=300)
    submitted = st.form_submit_button("🚀 Kör Analys", type="primary", use_container_width=True)

if submitted and text_input:
    raw_data = parse_svenskaspel_paste(text_input)
    
    if raw_data:
        df = pd.DataFrame(raw_data)
        
        for col in ['Streck_1', 'Streck_X', 'Streck_2', 'Odds_1', 'Odds_X', 'Odds_2']:
            if col not in df.columns: df[col] = 0.0
        
        # Beräkna
        probs = df.apply(calculate_probabilities, axis=1, result_type='expand')
        df[['Prob_1', 'Prob_X', 'Prob_2']] = probs
        
        df['Val_1'] = df['Prob_1'] - df['Streck_1']
        df['Val_X'] = df['Prob_X'] - df['Streck_X']
        df['Val_2'] = df['Prob_2'] - df['Streck_2']
        
        results = df.apply(suggest_sign_and_status, axis=1, result_type='expand')
        df['Tips'] = results[0]
        df['Analys'] = results[1]
        
        df['Match_Rubrik'] = df['Hemmalag'] + " - " + df['Bortalag']
        
        st.success(f"Analyserade {len(df)} matcher.")
        h = (len(df) * 35) + 38
        
        # --- FLIKAR ---
        tab1, tab2, tab3, tab4 = st.tabs(["💡 Match & Tips", "📊 Värdetabell", "⚖️ Odds vs Folket", "🔍 Rådata"])
        
        # FLIK 1: Match, Tips, Analys
        with tab1:
            st.dataframe(
                df[['Match', 'Match_Rubrik', 'Tips', 'Analys']], 
                hide_index=True, use_container_width=True, height=h
            )

        # FLIK 2: Värdetabell (TYDLIGA FÄRGER)
        with tab2:
            st.write("Visar **Värde** (Sannolikhet minus Streckprocent).")
            st.write("🟢 **Stark Grön** (> 7) = Understreckad (Bra spelvärde).")
            st.write("🔴 **Stark Röd** (< -10) = Överstreckad (Dåligt spelvärde).")
            
            val_cols = ['Match', 'Match_Rubrik', 'Val_1', 'Val_X', 'Val_2']
            st.dataframe(
                df[val_cols].style.map(
                    lambda x: 'background-color: #85e085' if x > 7 else ('background-color: #ff9999' if x < -10 else ''), 
                    subset=['Val_1', 'Val_X', 'Val_2']
                ).format("{:.1f}", subset=['Val_1', 'Val_X', 'Val_2']),
                hide_index=True, use_container_width=True, height=h
            )
            
        # FLIK 3: Odds vs Folket (Jämförelse)
        with tab3:
            st.write("Jämför vad **Oddsen** säger (sannolikhet %) mot vad **Folket** streckat (%).")
            
            comp_df = df[['Match', 'Hemmalag', 'Prob_1', 'Streck_1', 'Prob_X', 'Streck_X', 'Prob_2', 'Streck_2']].copy()
            comp_df.columns = ['Match', 'Lag', 'Odds 1 (%)', 'Folk 1 (%)', 'Odds X (%)', 'Folk X (%)', 'Odds 2 (%)', 'Folk 2 (%)']
            
            st.dataframe(
                comp_df.style.format("{:.1f}", subset=['Odds 1 (%)', 'Odds X (%)', 'Odds 2 (%)']), 
                hide_index=True, use_container_width=True, height=h
            )

        # FLIK 4: Rådata
        with tab4:
            st.dataframe(df, use_container_width=True)

