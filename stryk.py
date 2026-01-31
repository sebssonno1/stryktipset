import streamlit as st
import pandas as pd
import re

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset: Context Aware Edition"
SVENSKA_SPEL_URL = "https://www.svenskaspel.se/stryktipset"

# --- HJÄLPFUNKTIONER ---
def to_float(val_str):
    """Gör om '1,78' eller '1.78' till float 1.78. Returnerar None om det inte är ett tal."""
    try:
        clean = val_str.replace(',', '.').replace('%', '').strip()
        return float(clean)
    except ValueError:
        return None

def clean_team_name(name):
    """Städar bort skräptecken från lagnamn."""
    if not isinstance(name, str): return "-"
    # Ta bort inledande siffror och 1X2
    name = re.sub(r'^\d+[\.\s]*', '', name) 
    name = name.replace("1X2", "").replace("1", "").replace("X", "").replace("2", "")
    return name.strip()

# --- DEN NYA PARSERN (MED KONTEXT-KOLL) ---
def parse_svenskaspel_paste(text_content):
    # Rensa tomma rader
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    
    match_indices = {}
    current_target = 1
    
    # 1. Hitta matchstarter (1-13) men undvik "falska" siffror (som 1 X 2 under Tipsinfo)
    for i, line in enumerate(lines):
        if line == str(current_target):
            # --- HÄR ÄR FIXEN ---
            # En riktig matchstart följs oftast av ett lagnamn, inte av "X" eller "Tipsinfo"
            # Vi kollar raden efter (i+1) och raden innan (i-1)
            
            is_real_match = True
            
            # Koll framåt: Om nästa rad är "X", "-", "Tipsinfo" eller "1X2" är det INTE en matchstart
            if i + 1 < len(lines):
                next_line = lines[i+1]
                if next_line in ['X', '-', '–', '1X2'] or "Tipsinfo" in next_line:
                    is_real_match = False
            
            # Koll bakåt: Om förra raden var "X" eller "Tipsinfo", är detta troligen en rubrik
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
        
        # Bestäm slut på blocket
        if m_num < 13:
            end_idx = match_indices[m_num + 1]
        else:
            end_idx = min(len(lines), start_idx + 50) # Ta med tillräckligt många rader på slutet
            
        block = lines[start_idx:end_idx]
        current_match = {'Match': m_num}
        
        # --- A. LAGNAMN ---
        # Leta i början av blocket. Rad 0 är siffran. Rad 1 och 3 är oftast lagen.
        # Format: 1 -> Lag -> - -> Lag
        found_names = False
        if len(block) > 3:
            # Kolla om rad 2 eller 3 är ett bindestreck
            for offset in [1, 2, 3]:
                if offset < len(block) and block[offset] in ['-', '–', '—', 'vs']:
                    # Lagen finns runt bindestrecket
                    current_match['Hemmalag'] = clean_team_name(block[offset-1])
                    current_match['Bortalag'] = clean_team_name(block[offset+1])
                    found_names = True
                    break
        
        if not found_names:
             current_match['Hemmalag'] = "-"
             current_match['Bortalag'] = "-"

        # --- B. STRECK (Svenska folket) ---
        # Vi letar efter rader med "%"
        streck_values = []
        for line in block:
            if '%' in line:
                val = to_float(line)
                if val is not None: streck_values.append(int(val))
        
        # Fallback: Om inga % hittas, leta efter tal under "Svenska folket" som INTE är odds
        if len(streck_values) < 3:
            capture_streck = False
            for line in block:
                if "Svenska folket" in line: capture_streck = True
                if "Odds" in line: capture_streck = False # Sluta leta när vi når Odds
                
                if capture_streck and line.isdigit():
                    val = int(line)
                    if val <= 100: streck_values.append(val)

        if len(streck_values) >= 3:
            current_match['Streck_1'] = streck_values[0]
            current_match['Streck_X'] = streck_values[1]
            current_match['Streck_2'] = streck_values[2]
        else:
            current_match['Streck_1'] = 0; current_match['Streck_X'] = 0; current_match['Streck_2'] = 0

        # --- C. ODDS ---
        # Vi letar strikt efter ordet "Odds" och tar decimaltalen som kommer EFTER det
        odds_values = []
        capture_odds = False
        
        for line in block:
            if "Odds" in line:
                capture_odds = True
                continue
            
            if capture_odds:
                # Regex för att hitta "1,78" eller "1.78" (måste innehålla decimaltecken)
                # Vi ignorerar heltal här för att inte råka ta streck-värden
                if re.match(r'^\d+[.,]\d{2}$', line):
                    val = to_float(line)
                    if val: odds_values.append(val)
                
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
    raw = [1/o1, 1/ox, 1/o2]
    total = sum(raw)
    return tuple(round((r/total)*100, 1) for r in raw)

def suggest_sign_and_status(row):
    if row['Prob_1'] == 0: return "❓", "Saknar Odds"

    val1, valx, val2 = row['Val_1'], row['Val_X'], row['Val_2']
    options = [('1', val1, row['Prob_1']), ('X', valx, row['Prob_X']), ('2', val2, row['Prob_2'])]
    
    # Sortera på VÄRDE
    options.sort(key=lambda x: x[1], reverse=True) 
    
    best_sign = options[0]
    tecken = [best_sign[0]]
    status = "Neutral"

    if best_sign[1] > 7: status = f"💎 Fynd {best_sign[0]}"
    elif best_sign[1] < -10: status = "⚠️ Dåligt värde"

    # Gardering: Ta alltid med favoriten om den inte är vårt förstaval
    probs_sorted = sorted(options, key=lambda x: x[2], reverse=True)
    favorite = probs_sorted[0][0]

    if best_sign[0] != favorite:
        tecken.append(favorite)
    elif best_sign[1] < 5: 
        tecken.append(options[1][0])

    return "".join(sorted(tecken)), status

# --- APP START ---
st.set_page_config(page_title="Stryktipset Final Fix", layout="wide")
st.title(ST_PAGE_TITLE)

with st.expander("ℹ️ Instruktioner", expanded=True):
    st.info("Klistra in hela sidan (Ctrl+A -> Ctrl+C).")

with st.form("input_form"):
    text_input = st.text_area("Klistra in här:", height=300)
    submitted = st.form_submit_button("🚀 Kör Analys", type="primary", use_container_width=True)

if submitted and text_input:
    raw_data = parse_svenskaspel_paste(text_input)
    
    if raw_data:
        df = pd.DataFrame(raw_data)
        
        # Fyll nollor där data saknas för att undvika krasch
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
        
        odds_count = df[df['Odds_1'] > 0].shape[0]
        st.success(f"Analys klar! Hittade odds för {odds_count} av {len(df)} matcher.")

        h = (len(df) * 35) + 38
        
        tab1, tab2, tab3 = st.tabs(["💡 Kupong", "📊 Värdetabell", "🔍 Rådata"])
        
        with tab1:
            st.dataframe(
                df[['Match', 'Match_Rubrik', 'Tips', 'Analys', 'Streck_1', 'Streck_X', 'Streck_2']], 
                hide_index=True, use_container_width=True, height=h
            )

        with tab2:
            st.write("Positivt (Grönt) = Spelvärt. Negativt (Rött) = Överstreckat.")
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
