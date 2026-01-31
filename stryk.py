import streamlit as st
import pandas as pd
import re

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset: Strict Sequence Edition"
SVENSKA_SPEL_URL = "https://www.svenskaspel.se/stryktipset"

# --- HJÄLPFUNKTIONER ---
def to_float(val_str):
    try:
        clean = val_str.replace(',', '.').replace('%', '').strip()
        return float(clean)
    except ValueError: return None

def clean_team_name(name):
    if not isinstance(name, str): return "-"
    # Ta bort inledande siffror, punkt och 1X2-tecken
    name = re.sub(r'^\d+[\.\s]*', '', name) 
    name = name.replace("1X2", "").replace("1", "").replace("X", "").replace("2", "")
    return name.strip()

# --- DEN NYA PARSERN (STRIKT SEKVENS) ---
def parse_svenskaspel_paste(text_content):
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    
    # 1. Hitta Start-index för match 1, 2, 3... 13
    # Vi tvingar ordningen: Vi letar inte efter 2 förrän vi hittat 1.
    match_indices = {}
    current_target = 1
    
    for idx, line in enumerate(lines):
        # Om raden är EXAKT siffran vi letar efter
        if line == str(current_target):
            match_indices[current_target] = idx
            current_target += 1
            if current_target > 13: break # Vi behöver bara 13 matcher
            
    if len(match_indices) < 13:
        # Om vi inte hittade alla 13, försök en mjukare sökning (t.ex. "1." istället för "1")
        return []

    matches = []
    
    # 2. Bearbeta varje match-block
    for m_num in range(1, 14):
        start_idx = match_indices[m_num]
        
        # Slutet på detta block är starten på nästa, eller slutet på filen
        if m_num < 13 and (m_num + 1) in match_indices:
            end_idx = match_indices[m_num + 1]
        else:
            end_idx = len(lines)
            
        block = lines[start_idx:end_idx]
        current_match = {'Match': m_num}
        
        # --- A. LAGNAMN ---
        # Leta i de första 6 raderna efter lagnamn
        # Strategi: Leta efter bindestreck. Hittas inget, ta rad 1 och 3 (rad 0 är siffran).
        found_teams = False
        
        # Sök efter "Lag - Lag" på en rad
        for i in range(min(len(block), 6)):
            if '-' in block[i] and len(block[i]) > 3:
                parts = block[i].split('-')
                current_match['Hemmalag'] = clean_team_name(parts[0])
                current_match['Bortalag'] = clean_team_name(parts[1])
                found_teams = True
                break
        
        # Sök efter "Lag" [ny rad] "-" [ny rad] "Lag"
        if not found_teams:
            for i in range(min(len(block), 6)):
                if block[i] in ['-', '–', 'vs'] and i > 0:
                    current_match['Hemmalag'] = clean_team_name(block[i-1])
                    current_match['Bortalag'] = clean_team_name(block[i+1])
                    found_teams = True
                    break
        
        # Fallback: Ta bara textraderna direkt efter siffran
        if not found_teams and len(block) > 3:
            current_match['Hemmalag'] = clean_team_name(block[1])
            current_match['Bortalag'] = clean_team_name(block[3])

        # --- B. ODDS & STRECK ---
        # Vi samlar ALLA decimaltal och ALLA procenttal i blocket
        decimals = []
        percents = []
        
        for line in block:
            # Hitta odds (t.ex 1,78)
            found_floats = re.findall(r'(\d+[.,]\d{2})', line)
            for f in found_floats: decimals.append(to_float(f))
            
            # Hitta procent (t.ex 58%)
            found_pcts = re.findall(r'(\d+)%', line)
            for p in found_pcts: percents.append(int(p))
            
        # Logik för Odds: Ta de 3 första decimaltalen vi hittade
        if len(decimals) >= 3:
            current_match['Odds_1'] = decimals[0]
            current_match['Odds_X'] = decimals[1]
            current_match['Odds_2'] = decimals[2]
        else:
            current_match['Odds_1'] = 0; current_match['Odds_X'] = 0; current_match['Odds_2'] = 0
            
        # Logik för Streck: Ta de 3 första procenttalen
        if len(percents) >= 3:
            current_match['Streck_1'] = percents[0]
            current_match['Streck_X'] = percents[1]
            current_match['Streck_2'] = percents[2]
        else:
            # Om % saknas, leta efter heltal (Svenska folket-raden utan %)
            ints = []
            capture = False
            for line in block:
                if "Svenska folket" in line: capture = True
                if capture:
                    # Hitta heltal mindre än 100
                    nums = re.findall(r'\b(\d{1,2})\b', line)
                    for n in nums: ints.append(int(n))
            
            if len(ints) >= 3:
                current_match['Streck_1'] = ints[0]
                current_match['Streck_X'] = ints[1]
                current_match['Streck_2'] = ints[2]
            else:
                current_match['Streck_1'] = 0; current_match['Streck_X'] = 0; current_match['Streck_2'] = 0

        matches.append(current_match)

    return matches

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

    if best_sign[1] > 7: status = f"💎 Fynd {best_sign[0]}"
    elif best_sign[1] < -10: status = "⚠️ Dåligt värde"

    # Gardering
    probs_sorted = sorted(options, key=lambda x: x[2], reverse=True)
    favorite = probs_sorted[0][0]

    if best_sign[0] != favorite:
        tecken.append(favorite)
    elif best_sign[1] < 5: 
        tecken.append(options[1][0])

    return "".join(sorted(tecken)), status

# --- APP LAYOUT ---
st.set_page_config(page_title="Stryktipset Strict", layout="wide")
st.title(ST_PAGE_TITLE)

with st.expander("ℹ️ Instruktioner", expanded=True):
    st.info("Klistra in hela sidan (Ctrl+A -> Ctrl+C). Denna version tvingar fram exakt 13 matcher.")

with st.form("input_form"):
    text_input = st.text_area("Klistra in här:", height=300)
    submitted = st.form_submit_button("🚀 Kör Analys", type="primary", use_container_width=True)

if submitted and text_input:
    raw_data = parse_svenskaspel_paste(text_input)
    
    if not raw_data:
        st.error("Kunde inte hitta sekvensen 1 till 13. Kontrollera att du kopierat hela kupongen.")
    else:
        df = pd.DataFrame(raw_data)
        
        # Safety checks
        if 'Hemmalag' not in df.columns: df['Hemmalag'] = "-"
        if 'Bortalag' not in df.columns: df['Bortalag'] = "-"
        df['Hemmalag'] = df['Hemmalag'].fillna("-").astype(str)
        df['Bortalag'] = df['Bortalag'].fillna("-").astype(str)
        
        for col in ['Streck_1', 'Streck_X', 'Streck_2', 'Odds_1', 'Odds_X', 'Odds_2']:
            if col not in df.columns: df[col] = 0.0
            df[col] = df[col].fillna(0.0)

        # Calculations
        probs = df.apply(calculate_probabilities, axis=1, result_type='expand')
        df[['Prob_1', 'Prob_X', 'Prob_2']] = probs
        
        df['Val_1'] = df['Prob_1'] - df['Streck_1']
        df['Val_X'] = df['Prob_X'] - df['Streck_X']
        df['Val_2'] = df['Prob_2'] - df['Streck_2']
        
        results = df.apply(suggest_sign_and_status, axis=1, result_type='expand')
        df['Tips'] = results[0]
        df['Analys'] = results[1]
        
        df['Match_Rubrik'] = df['Hemmalag'] + " - " + df['Bortalag']

        st.success(f"Hittade {len(df)} matcher.")

        h = (len(df) * 35) + 38
        
        tab1, tab2, tab3 = st.tabs(["💡 Kupong", "📊 Värdetabell", "🔍 Rådata"])
        
        with tab1:
            st.dataframe(
                df[['Match', 'Match_Rubrik', 'Tips', 'Analys', 'Streck_1', 'Streck_X', 'Streck_2']], 
                hide_index=True, use_container_width=True, height=h
            )

        with tab2:
            st.write("Positivt värde (Grönt) = Spelvärt.")
            display_cols = ['Match', 'Match_Rubrik', 'Val_1', 'Val_X', 'Val_2', 'Odds_1', 'Odds_X', 'Odds_2']
            st.dataframe(
                df[display_cols].style.map(
                    lambda x: 'background-color: #d4edda' if x > 7 else ('background-color: #f8d7da' if x < -10 else ''), 
                    subset=['Val_1', 'Val_X', 'Val_2']
                ).format("{:.2f}", subset=['Odds_1', 'Odds_X', 'Odds_2'])
                 .format("{:.1f}", subset=['Val_1', 'Val_X', 'Val_2']),
                hide_index=True, use_container_width=True, height=h
            )
            
        with tab3:
            st.dataframe(df, use_container_width=True)
