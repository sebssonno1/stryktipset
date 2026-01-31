import streamlit as st
import pandas as pd
import re

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset: Budget Optimizer (Corrected)"
SVENSKA_SPEL_URL = "https://www.svenskaspel.se/stryktipset"

# --- HJÄLPFUNKTIONER ---
def to_float(val_str):
    """Gör om '1,78' till 1.78. Returnerar None om det inte är ett decimaltal."""
    try:
        clean = val_str.replace(',', '.').replace('%', '').strip()
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

# --- OPTIMERINGS-MOTOR ---
def calculate_cost(df):
    """Räknar ut priset på systemet."""
    cost = 1
    for tip in df['Tips']:
        cost *= len(tip)
    return cost

def optimize_system(df, max_budget):
    """Bantar ner systemet tills det passar budgeten."""
    current_cost = calculate_cost(df)
    
    # Loopa tills vi är under budget
    while current_cost > max_budget:
        # Hitta garderingar (längd > 1) som vi kan ta bort
        mask = df['Tips'].apply(len) > 1
        candidates = df[mask].copy()
        
        if candidates.empty:
            break # Kan inte banta mer (bara spikar kvar)
            
        # Strategi: Hitta den gardering där FAVORITEN är starkast (minst risk att spika).
        best_safety_score = -1
        index_to_shave = -1
        best_sign_to_keep = ""
        
        for idx, row in candidates.iterrows():
            # Hitta vilket tecken som har högst sannolikhet (Odds)
            probs = {'1': row['Prob_1'], 'X': row['Prob_X'], '2': row['Prob_2']}
            best_sign = max(probs, key=probs.get)
            safety = probs[best_sign]
            
            # Vi vill spika den match som är "säkrast" att spika
            if safety > best_safety_score:
                best_safety_score = safety
                index_to_shave = idx
                best_sign_to_keep = best_sign
        
        # Verkställ ändringen: Ändra gardering till spik
        if index_to_shave != -1:
            df.at[index_to_shave, 'Tips'] = best_sign_to_keep
            df.at[index_to_shave, 'Analys'] = "🔒 Spikad (Budget)" # Markera att vi ändrat
        
        current_cost = calculate_cost(df)
        
    return df, current_cost

# --- PARSER ---
def parse_svenskaspel_paste(text_content):
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    match_indices = {}
    current_target = 1
    
    for i, line in enumerate(lines):
        if line == str(current_target):
            is_real_match = True
            if i + 1 < len(lines):
                next_line = lines[i+1]
                if next_line in ['X', '-', '–', '1X2'] or "Tipsinfo" in next_line:
                    is_real_match = False
            if i > 0:
                prev_line = lines[i-1]
                if prev_line in ['X'] or "Tipsinfo" in prev_line:
                    is_real_match = False

            if is_real_match:
                match_indices[current_target] = i
                current_target += 1
                if current_target > 13: break 

    if len(match_indices) < 13:
        st.error(f"Hittade bara {len(match_indices)} av 13 matcher.")
        return []

    matches = []
    for m_num in range(1, 14):
        start_idx = match_indices[m_num]
        if m_num < 13: end_idx = match_indices[m_num + 1]
        else: end_idx = min(len(lines), start_idx + 60)
            
        block = lines[start_idx:end_idx]
        current_match = {'Match': m_num}
        
        # Lagnamn
        found_names = False
        if len(block) > 3:
            for offset in [1, 2, 3]:
                if offset < len(block) and block[offset] in ['-', '–', '—', 'vs']:
                    current_match['Hemmalag'] = clean_team_name(block[offset-1])
                    current_match['Bortalag'] = clean_team_name(block[offset+1])
                    found_names = True
                    break
        if not found_names: current_match['Hemmalag'] = "-"; current_match['Bortalag'] = "-"

        # Streck
        streck_values = []
        capture_streck = False
        for line in block:
            if '%' in line:
                try: streck_values.append(int(line.replace('%', '').strip()))
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
        else: current_match['Streck_1'] = 0; current_match['Streck_X'] = 0; current_match['Streck_2'] = 0

        # Odds
        odds_values = []
        capture_odds = False
        for line in block:
            if "Odds" in line: capture_odds = True; continue
            if capture_odds:
                if re.match(r'^\d+[.,]\d{2}$', line):
                    val = to_float(line)
                    if val: odds_values.append(val)
                if len(odds_values) >= 3: break
        if len(odds_values) >= 3:
            current_match['Odds_1'] = odds_values[0]
            current_match['Odds_X'] = odds_values[1]
            current_match['Odds_2'] = odds_values[2]
        else: current_match['Odds_1'] = 0; current_match['Odds_X'] = 0; current_match['Odds_2'] = 0

        matches.append(current_match)
    return matches

# --- BERÄKNINGAR ---
def calculate_probabilities(row):
    o1, ox, o2 = row.get('Odds_1', 0), row.get('Odds_X', 0), row.get('Odds_2', 0)
    if o1 == 0 or ox == 0 or o2 == 0: return 0, 0, 0
    raw = [1/o1, 1/ox, 1/o2]
    total = sum(raw)
    return tuple(round((r/total)*100, 1) for r in raw)

def suggest_initial_tips(row):
    if row['Prob_1'] == 0: return "❓", "Saknar Odds"

    val1, valx, val2 = row['Val_1'], row['Val_X'], row['Val_2']
    options = [('1', val1, row['Prob_1']), ('X', valx, row['Prob_X']), ('2', val2, row['Prob_2'])]
    
    # Sortera på VÄRDE först
    options.sort(key=lambda x: x[1], reverse=True) 
    
    best_sign = options[0]
    tecken = [best_sign[0]]
    status = "Neutral"

    if best_sign[1] > 7: status = f"💎 Fynd {best_sign[0]}"
    elif best_sign[1] < -10: status = "⚠️ Dåligt värde"

    # Gardera med favoriten om den inte redan är vald
    probs_sorted = sorted(options, key=lambda x: x[2], reverse=True)
    favorite = probs_sorted[0][0]

    if best_sign[0] != favorite:
        tecken.append(favorite)
    elif best_sign[1] < 5: 
        tecken.append(options[1][0])

    return "".join(sorted(tecken)), status

# --- APP LAYOUT ---
st.set_page_config(page_title="Stryktipset Budget", layout="wide")
st.title(ST_PAGE_TITLE)

with st.expander("ℹ️ Instruktioner", expanded=True):
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info(f"1. Markera allt (Ctrl+A) på Svenska Spel.\n2. Kopiera (Ctrl+C).\n3. Klistra in nedan.\n4. Välj din budget och kör.")
    with col2:
        st.link_button("Öppna Stryktipset ↗️", SVENSKA_SPEL_URL, use_container_width=True)

with st.form("input_form"):
    # HÄR ÄR DEN RÄTTADE RADEN:
    user_budget = st.number_input(
        "💰 Max budget för systemet (kr):", 
        min_value=1, 
        value=600, 
        step=10, 
        help="Scriptet tar bort garderingar på de 'säkraste' matcherna tills priset är under din budget."
    )
    
    text_input = st.text_area("Klistra in kupongen här:", height=300)
    submitted = st.form_submit_button("🚀 Kör Analys & Optimering", type="primary", use_container_width=True)

if submitted and text_input:
    raw_data = parse_svenskaspel_paste(text_input)
    
    if raw_data:
        df = pd.DataFrame(raw_data)
        for col in ['Streck_1', 'Streck_X', 'Streck_2', 'Odds_1', 'Odds_X', 'Odds_2']:
            if col not in df.columns: df[col] = 0.0
        
        # 1. Grundberäkningar
        probs = df.apply(calculate_probabilities, axis=1, result_type='expand')
        df[['Prob_1', 'Prob_X', 'Prob_2']] = probs
        
        df['Val_1'] = df['Prob_1'] - df['Streck_1']
        df['Val_X'] = df['Prob_X'] - df['Streck_X']
        df['Val_2'] = df['Prob_2'] - df['Streck_2']
        
        df['Match_Rubrik'] = df['Hemmalag'] + " - " + df['Bortalag']

        # 2. Ta fram "Drömsystemet" (Ofiltrerat baserat på värde)
        results = df.apply(suggest_initial_tips, axis=1, result_type='expand')
        df['Tips'] = results[0]
        df['Analys'] = results[1]
        
        original_cost = calculate_cost(df)
        
        # 3. Optimera mot ANVÄNDARENS budget
        df_optimized, final_cost = optimize_system(df.copy(), user_budget)
        
        # Presentation
        col_res1, col_res2 = st.columns(2)
        with col_res1:
            st.metric(label="Ursprungligt värde-system", value=f"{original_cost} kr")
        with col_res2:
            delta_color = "normal" if final_cost <= user_budget else "inverse"
            st.metric(label=f"Optimerat system (Max {user_budget} kr)", value=f"{final_cost} kr", delta=f"-{original_cost-final_cost} kr", delta_color=delta_color)

        h = (len(df) * 35) + 38
        
        # --- FLIKAR ---
        tab1, tab2, tab3, tab4 = st.tabs(["💡 Färdig Kupong", "📊 Värdetabell", "⚖️ Odds vs Folket", "🔍 Rådata"])
        
        with tab1:
            st.write(f"Tipsen nedan är optimerade för **{user_budget} kr**. '🔒' betyder att garderingen togs bort för att spara pengar.")
            st.dataframe(
                df_optimized[['Match', 'Match_Rubrik', 'Tips', 'Analys']], 
                hide_index=True, use_container_width=True, height=h
            )

        with tab2:
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
            
        with tab3:
            comp_df = df[['Match', 'Hemmalag', 'Prob_1', 'Streck_1', 'Prob_X', 'Streck_X', 'Prob_2', 'Streck_2']].copy()
            comp_df.columns = ['Match', 'Lag', 'Odds 1 (%)', 'Folk 1 (%)', 'Odds X (%)', 'Folk X (%)', 'Odds 2 (%)', 'Folk 2 (%)']
            st.dataframe(comp_df.style.format("{:.1f}", subset=['Odds 1 (%)', 'Odds X (%)', 'Odds 2 (%)']), hide_index=True, use_container_width=True, height=h)

        with tab4:
            st.dataframe(df, use_container_width=True)
