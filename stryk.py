import streamlit as st
import pandas as pd
import re

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset: Strict Sequence Edition"
SVENSKA_SPEL_URL = "https://www.svenskaspel.se/stryktipset"

# --- HJÄLPFUNKTIONER ---
def to_float(val_str):
    """Gör om '1,78' eller '1.78' till float 1.78."""
    try:
        # Ta bort % och ersätt komma med punkt
        clean = val_str.replace(',', '.').replace('%', '').strip()
        return float(clean)
    except ValueError:
        return 0.0

def clean_team_name(name):
    """Städar bort skräptecken från lagnamn."""
    if not isinstance(name, str): return "-"
    # Ta bort inledande siffror och 1X2
    name = re.sub(r'^\d+[\.\s]*', '', name) 
    name = name.replace("1X2", "").replace("1", "").replace("X", "").replace("2", "")
    return name.strip()

# --- DEN NYA PARSERN (Strikt Sekvens 1-13) ---
def parse_svenskaspel_paste(text_content):
    # Rensa tomma rader
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    
    # 1. Hitta VAR varje matchnummer (1-13) finns i texten
    # Vi tvingar ordningen: Vi letar efter 2 först efter att vi hittat 1.
    match_indices = {}
    current_target = 1
    
    for idx, line in enumerate(lines):
        # Om raden är EXAKT siffran vi letar efter (t.ex. "1")
        if line == str(current_target):
            match_indices[current_target] = idx
            current_target += 1
            if current_target > 13: break # Vi är klara efter 13
            
    if len(match_indices) < 13:
        st.error(f"Hittade bara {len(match_indices)} av 13 matcher. Kontrollera att du kopierat hela listan.")
        return []

    matches = []
    
    # 2. Loopa igenom match 1 till 13
    for m_num in range(1, 14):
        start_idx = match_indices[m_num]
        
        # Bestäm var detta block slutar (vid nästa match, eller slutet av texten)
        if m_num < 13:
            end_idx = match_indices[m_num + 1]
        else:
            # För sista matchen, läs ca 30 rader till (så vi slipper skräpet på slutet)
            end_idx = min(len(lines), start_idx + 40)
            
        block = lines[start_idx:end_idx]
        current_match = {'Match': m_num}
        
        # --- A. LAGNAMN (Struktur: Siffra -> Lag -> Streck -> Lag) ---
        # I din text ligger lagen oftast på rad 1 och 3 i blocket (rad 0 är siffran)
        if len(block) > 3:
            # Kontrollera att rad 2 är ett bindestreck "-"
            if block[2] in ['-', '–', '—', 'vs']:
                current_match['Hemmalag'] = clean_team_name(block[1])
                current_match['Bortalag'] = clean_team_name(block[3])
            else:
                # Fallback: Ta rad 1 och 2 om strecket saknas
                current_match['Hemmalag'] = clean_team_name(block[1])
                current_match['Bortalag'] = clean_team_name(block[2])
        else:
            current_match['Hemmalag'] = "-"; current_match['Bortalag'] = "-"

        # --- B. STRECK (Svenska folket) ---
        streck_values = []
        # Leta efter rader med "%"
        for line in block:
            if '%' in line:
                val = to_float(line)
                if val > 0: streck_values.append(int(val))
        
        if len(streck_values) >= 3:
            current_match['Streck_1'] = streck_values[0]
            current_match['Streck_X'] = streck_values[1]
            current_match['Streck_2'] = streck_values[2]
        else:
            current_match['Streck_1'] = 0; current_match['Streck_X'] = 0; current_match['Streck_2'] = 0

        # --- C. ODDS (Efter ordet "Odds") ---
        odds_values = []
        found_odds_keyword = False
        
        for line in block:
            if "Odds" in line:
                found_odds_keyword = True
                continue # Hoppa till nästa rad där siffrorna börjar
            
            if found_odds_keyword:
                # Din text har formatet "1,78". Vi kollar om raden ser ut som ett tal.
                # Regex som hittar "siffra,siffra" eller "siffra.siffra"
                if re.match(r'^\d+[.,]\d+$', line):
                    val = to_float(line)
                    odds_values.append(val)
                
                # Vi behöver bara 3 odds per match
                if len(odds_values) >= 3:
                    break
        
        if len(odds_values) >= 3:
            current_match['Odds_1'] = odds_values[0]
            current_match['Odds_X'] = odds_values[1]
            current_match['Odds_2'] = odds_values[2]
        else:
            current_match['Odds_1'] = 0; current_match['Odds_X'] = 0; current_match['Odds_2'] = 0

        matches.append(current_match)

    return matches

# --- 3. BERÄKNINGAR ---
def calculate_probabilities(row):
    o1, ox, o2 = row.get('Odds_1', 0), row.get('Odds_X', 0), row.get('Odds_2', 0)
    if o1 == 0 or ox == 0 or o2 == 0: return 0, 0, 0
    # Omvandla odds till sannolikhet (1/odds)
    raw = [1/o1, 1/ox, 1/o2]
    total = sum(raw)
    # Normalisera till 100%
    return tuple(round((r/total)*100, 1) for r in raw)

def suggest_sign_and_status(row):
    if row['Prob_1'] == 0: return "❓", "Saknar Odds"

    val1, valx, val2 = row['Val_1'], row['Val_X'], row['Val_2']
    options = [('1', val1, row['Prob_1']), ('X', valx, row['Prob_X']), ('2', val2, row['Prob_2'])]
    
    # Sortera på VÄRDE (högst först)
    options.sort(key=lambda x: x[1], reverse=True) 
    
    best_sign = options[0]
    tecken = [best_sign[0]]
    status = "Neutral"

    # Status-gränser
    if best_sign[1] > 7: status = f"💎 Fynd {best_sign[0]}"
    elif best_sign[1] < -10: status = "⚠️ Dåligt värde"

    # Gardering: Ta alltid med favoriten (högst sannolikhet) om den inte är vald
    probs_sorted = sorted(options, key=lambda x: x[2], reverse=True)
    favorite = probs_sorted[0][0]

    if best_sign[0] != favorite:
        tecken.append(favorite)
    elif best_sign[1] < 5: # Om värdet är marginellt, gardera med näst bästa
        tecken.append(options[1][0])

    return "".join(sorted(tecken)), status

# --- APP LAYOUT ---
st.set_page_config(page_title="Stryktipset Fix", layout="wide")
st.title(ST_PAGE_TITLE)

with st.expander("ℹ️ Instruktioner", expanded=True):
    st.info("Klistra in hela sidan (Ctrl+A -> Ctrl+C). Denna version hanterar din vertikala text och ignorerar skräp på slutet.")

with st.form("input_form"):
    text_input = st.text_area("Klistra in här:", height=300)
    submitted = st.form_submit_button("🚀 Kör Analys", type="primary", use_container_width=True)

if submitted and text_input:
    raw_data = parse_svenskaspel_paste(text_input)
    
    if raw_data:
        df = pd.DataFrame(raw_data)
        
        # Säkerställ att vi inte kraschar på saknad data
        for col in ['Streck_1', 'Streck_X', 'Streck_2', 'Odds_1', 'Odds_X', 'Odds_2']:
            if col not in df.columns: df[col] = 0.0
        
        # Beräkna
        probs = df.apply(calculate_probabilities, axis=1, result_type='expand')
        df[['Prob_1', 'Prob_X', 'Prob_2']] = probs
        
        # Värde = Sannolikhet - Streck
        df['Val_1'] = df['Prob_1'] - df['Streck_1']
        df['Val_X'] = df['Prob_X'] - df['Streck_X']
        df['Val_2'] = df['Prob_2'] - df['Streck_2']
        
        results = df.apply(suggest_sign_and_status, axis=1, result_type='expand')
        df['Tips'] = results[0]
        df['Analys'] = results[1]
        
        df['Match_Rubrik'] = df['Hemmalag'] + " - " + df['Bortalag']
        
        odds_count = df[df['Odds_1'] > 0].shape[0]
        st.success(f"Lyckades! Analyserade {len(df)} matcher. Hittade odds för {odds_count} st.")

        h = (len(df) * 35) + 38
        
        tab1, tab2, tab3 = st.tabs(["💡 Kupong", "📊 Värdetabell", "🔍 Rådata"])
        
        with tab1:
            st.dataframe(
                df[['Match', 'Match_Rubrik', 'Tips', 'Analys', 'Streck_1', 'Streck_X', 'Streck_2']], 
                hide_index=True, use_container_width=True, height=h
            )

        with tab2:
            st.write("Positivt värde (Grönt) = Spelvärt. Negativt (Rött) = Överstreckat.")
            display_cols = ['Match', 'Match_Rubrik', 'Val_1', 'Val_X', 'Val_2', 'Odds_1', 'Odds_X', 'Odds_2']
            
            # Snyggare formatering av tabellen
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
