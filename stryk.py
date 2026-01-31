import streamlit as st
import pandas as pd
import re

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset: Block Parser Edition"
SVENSKA_SPEL_URL = "https://www.svenskaspel.se/stryktipset"

# --- 1. HJÄLPFUNKTIONER ---
def to_float(val_str):
    """Konverterar text till decimaltal (hanterar både 1,50 och 1.50)."""
    try:
        clean = val_str.replace(',', '.').replace('%', '').strip()
        return float(clean)
    except ValueError:
        return None

def clean_team_name(name):
    """Städar bort skräptecken från lagnamn."""
    if not isinstance(name, str): return "-"
    name = re.sub(r'^\d+[\.\s]*', '', name) # Ta bort inledande siffror
    name = name.replace("1X2", "").replace("1", "").replace("X", "").replace("2", "")
    return name.strip()

# --- 2. DEN NYA PARSERN (Block-metod) ---
def parse_svenskaspel_paste(text_content):
    # 1. Städa input: Ta bort tomma rader
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    
    # 2. Hitta var varje match börjar (radnummer där det står "1", "2" osv)
    match_starts = []
    for i, line in enumerate(lines):
        if line.isdigit() and 1 <= int(line) <= 13:
            # En extra koll så vi inte tror att ett odds typ "2,00" som råkar stå som "2" är matchnummer
            # Matchnumret står oftast ensamt och följs av text, inte siffror
            match_starts.append((int(line), i))
    
    # Sortera för säkerhets skull
    match_starts.sort(key=lambda x: x[0])
    
    matches = []
    
    # 3. Loopa igenom varje match-block
    for k in range(len(match_starts)):
        match_num, start_index = match_starts[k]
        
        # Bestäm slutindex för detta block (starten på nästa match, eller slutet på filen)
        if k < len(match_starts) - 1:
            end_index = match_starts[k+1][1]
        else:
            end_index = len(lines)
            
        # Hämta alla rader som hör till DENNA match
        block = lines[start_index:end_index]
        
        current_match = {'Match': match_num}
        
        # --- A. Lagnamn ---
        # Leta efter bindestreck i de första 6 raderna av blocket
        found_teams = False
        for j in range(min(len(block), 8)):
            txt = block[j]
            if txt in ['-', '–', '—', 'vs'] and j > 0 and j < len(block)-1:
                # Fall: Lagnamn - [radbrytning] - - [radbrytning] - Lagnamn
                current_match['Hemmalag'] = clean_team_name(block[j-1])
                current_match['Bortalag'] = clean_team_name(block[j+1])
                found_teams = True
                break
            elif '-' in txt and len(txt) > 2:
                # Fall: "Lag A - Lag B" på samma rad
                parts = txt.split('-')
                current_match['Hemmalag'] = clean_team_name(parts[0])
                current_match['Bortalag'] = clean_team_name(parts[-1])
                found_teams = True
                break
        
        if not found_teams:
            # Nödlösning: Om inget streck hittas, ta rad 1 och 3 (rad 0 är numret)
            if len(block) > 3:
                current_match['Hemmalag'] = clean_team_name(block[1])
                current_match['Bortalag'] = clean_team_name(block[3])

        # --- B. Odds ---
        # Leta efter ordet "Odds" och ta de 3 första decimaltalen som kommer efter det
        odds_values = []
        odds_found_start = False
        
        for line in block:
            if "Odds" in line:
                odds_found_start = True
                continue # Hoppa till nästa rad för att leta siffror
            
            if odds_found_start:
                # Regex för att hitta "1,78" eller "1.78"
                found = re.findall(r'(\d+[.,]\d{2})', line) 
                for f in found:
                    val = to_float(f)
                    if val: odds_values.append(val)
                
                # Om vi hittat 3 odds är vi klara
                if len(odds_values) >= 3:
                    break
        
        if len(odds_values) >= 3:
            current_match['Odds_1'] = odds_values[0]
            current_match['Odds_X'] = odds_values[1]
            current_match['Odds_2'] = odds_values[2]
        else:
            # Om vi inte hittade odds via "Odds"-ordet, scanna hela blocket efter decimaltal
            # Detta är en fallback
            all_decimals = []
            for line in block:
                found = re.findall(r'(\d+[.,]\d{2})', line)
                for f in found: all_decimals.append(to_float(f))
            
            # Antag att de sista 3 decimaltalen i blocket är oddsen (oftast sant)
            if len(all_decimals) >= 3:
                current_match['Odds_1'] = all_decimals[-3]
                current_match['Odds_X'] = all_decimals[-2]
                current_match['Odds_2'] = all_decimals[-1]
            else:
                current_match['Odds_1'] = 0; current_match['Odds_X'] = 0; current_match['Odds_2'] = 0

        # --- C. Streck (Svenska Folket) ---
        streck_values = []
        for line in block:
            # Leta efter tal som slutar med %
            pcts = re.findall(r'(\d+)%', line)
            for p in pcts: streck_values.append(int(p))
        
        # Om vi inte hittade %, leta efter heltal under 100 som kommer efter texten "Svenska folket"
        if len(streck_values) < 3:
             scanning_streck = False
             for line in block:
                 if "Svenska folket" in line: scanning_streck = True
                 if scanning_streck:
                     if line.isdigit() and int(line) <= 100:
                         streck_values.append(int(line))
        
        # Ta de 3 första vi hittade
        if len(streck_values) >= 3:
            current_match['Streck_1'] = streck_values[0]
            current_match['Streck_X'] = streck_values[1]
            current_match['Streck_2'] = streck_values[2]
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
    
    # Sortera på VÄRDE
    options.sort(key=lambda x: x[1], reverse=True) 
    
    best_sign = options[0]
    tecken = [best_sign[0]]
    status = "Neutral"

    if best_sign[1] > 7: status = f"💎 Fynd {best_sign[0]}"
    elif best_sign[1] < -10: status = "⚠️ Dåligt värde"

    # Gardering: Ta alltid med favoriten om den inte är vårt värdedrag
    probs_sorted = sorted(options, key=lambda x: x[2], reverse=True)
    favorite = probs_sorted[0][0]

    if best_sign[0] != favorite:
        tecken.append(favorite)
    elif best_sign[1] < 5: 
        tecken.append(options[1][0])

    return "".join(sorted(tecken)), status

# --- APP START ---
st.set_page_config(page_title="Stryktipset V3", layout="wide")
st.title(ST_PAGE_TITLE)

with st.expander("ℹ️ Instruktioner", expanded=True):
    col1, col2 = st.columns([3, 1])
    with col1:
        st.write("Klistra in hela sidan (Ctrl+A -> Ctrl+C). Denna version delar upp texten i block och missar inte odds.")
    with col2:
        st.link_button("Öppna Svenska Spel ↗️", SVENSKA_SPEL_URL, use_container_width=True)

with st.form("input_form"):
    text_input = st.text_area("Klistra in här:", height=300)
    submitted = st.form_submit_button("🚀 Kör Analys", type="primary", use_container_width=True)

if submitted and text_input:
    raw_data = parse_svenskaspel_paste(text_input)
    
    if not raw_data:
        st.error("Hittade inga matcher.")
    else:
        df = pd.DataFrame(raw_data)
        
        # Data-städning (undvik krasch)
        if 'Hemmalag' not in df.columns: df['Hemmalag'] = "-"
        if 'Bortalag' not in df.columns: df['Bortalag'] = "-"
        df['Hemmalag'] = df['Hemmalag'].fillna("-").astype(str)
        df['Bortalag'] = df['Bortalag'].fillna("-").astype(str)
        
        for col in ['Streck_1', 'Streck_X', 'Streck_2', 'Odds_1', 'Odds_X', 'Odds_2']:
            if col not in df.columns: df[col] = 0.0
            df[col] = df[col].fillna(0.0)

        # Beräkningar
        probs = df.apply(calculate_probabilities, axis=1, result_type='expand')
        df[['Prob_1', 'Prob_X', 'Prob_2']] = probs
        
        df['Val_1'] = df['Prob_1'] - df['Streck_1']
        df['Val_X'] = df['Prob_X'] - df['Streck_X']
        df['Val_2'] = df['Prob_2'] - df['Streck_2']
        
        results = df.apply(suggest_sign_and_status, axis=1, result_type='expand')
        df['Tips'] = results[0]
        df['Analys'] = results[1]
        
        df['Match_Rubrik'] = df['Hemmalag'] + " - " + df['Bortalag']

        # Statistik
        odds_count = df[df['Odds_1'] > 0].shape[0]
        st.success(f"Läste in {len(df)} matcher. Hittade odds på {odds_count} st.")

        h = (len(df) * 35) + 38
        
        tab1, tab2, tab3 = st.tabs(["💡 Kupong", "📊 Värdetabell", "🔍 Rådata"])
        
        with tab1:
            st.dataframe(
                df[['Match', 'Match_Rubrik', 'Tips', 'Analys', 'Streck_1', 'Streck_X', 'Streck_2']], 
                hide_index=True, use_container_width=True, height=h
            )

        with tab2:
            st.write("Grönt = Bra värde. Rött = Överstreckat.")
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
