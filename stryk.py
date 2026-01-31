import streamlit as st
import pandas as pd
import re

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset: Svenska Spel Odds Edition"
SVENSKA_SPEL_URL = "https://www.svenskaspel.se/stryktipset"

# --- PLATSHÅLLARTEXT ---
PLACEHOLDER_TEXT = """Klistra in hela sidan (Ctrl+A) från den vanliga kupongvyn.
Se till att både streckprocent och odds kommer med."""

# --- 1. HJÄLPFUNKTION: STÄDA NAMN ---
def clean_team_name(name):
    name = re.sub(r'^\d+[\.\s]*', '', name) 
    name = name.replace("1X2", "").replace("1", "").replace("X", "").replace("2", "")
    return name.strip()

# --- 2. LÄS PASTE (NU MED ODDS-HÄMNING) ---
def parse_svenskaspel_paste(text_content):
    matches = []
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    current_match = {}
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Hitta matchnummer (1-13)
        if line.isdigit() and 1 <= int(line) <= 13:
            # Om vi har en påbörjad match men hittar ett nytt nummer, spara den gamla
            if current_match and 'Match' in current_match:
                 # Spara bara om vi har minst lagnamn
                 if 'Hemmalag' in current_match:
                     matches.append(current_match)
            
            # Starta ny match
            current_match = {'Match': int(line)}
            
            # Försök hitta lagnamn i raderna strax efter numret
            found_teams = False
            for offset in range(1, 6):
                if i + offset < len(lines):
                    txt = lines[i+offset]
                    # Fall 1: "Lag A - Lag B"
                    if '-' in txt and len(txt) > 3:
                        parts = txt.split('-')
                        current_match['Hemmalag'] = clean_team_name(parts[0])
                        current_match['Bortalag'] = clean_team_name(parts[1])
                        found_teams = True
                        break
                    # Fall 2: Lag A (rad) - (rad) Lag B
                    elif txt == '-' and (i+offset+1) < len(lines):
                        current_match['Hemmalag'] = clean_team_name(lines[i+offset-1])
                        current_match['Bortalag'] = clean_team_name(lines[i+offset+1])
                        found_teams = True
                        break
            
        # Hitta Streckfördelning (Svenska folket)
        if current_match and ("Svenska Folket" in line or "Svenska folket" in line):
            try:
                temp_pcts = []
                # Leta i de kommande 5 raderna efter procenttal
                for offset in range(1, 6):
                    if i + offset < len(lines):
                        # Hitta tal som slutar med % eller bara är siffror om vi är i det blocket
                        row_txt = lines[i+offset]
                        found = re.findall(r'(\d+)%', row_txt)
                        if not found and row_txt.isdigit(): # Ibland tappar man % i kopieringen
                            found = [row_txt]
                        
                        for val in found: 
                            temp_pcts.append(int(val))
                        
                        if len(temp_pcts) >= 3:
                            break
                            
                if len(temp_pcts) >= 3:
                    current_match.update({
                        'Streck_1': temp_pcts[0], 
                        'Streck_X': temp_pcts[1], 
                        'Streck_2': temp_pcts[2]
                    })
            except Exception: pass

        # Hitta Odds (Svenska Spel)
        # Vi letar efter ordet "Odds" och sedan decimaltal (t.ex. 1,78)
        if current_match and "Odds" in line and len(line) < 20:
            try:
                temp_odds = []
                for offset in range(1, 6): # Leta i kommande rader
                    if i + offset < len(lines):
                        val = lines[i+offset].replace(',', '.').strip()
                        # Kolla om det är ett decimaltal (t.ex. 1.78 eller 1.5)
                        if re.match(r'^\d+\.\d+$', val):
                            temp_odds.append(float(val))
                        
                        if len(temp_odds) == 3:
                            current_match.update({
                                'Odds_1': temp_odds[0],
                                'Odds_X': temp_odds[1],
                                'Odds_2': temp_odds[2]
                            })
                            break
            except Exception: pass

        i += 1
    
    # Lägg till sista matchen om den är klar
    if current_match and 'Hemmalag' in current_match:
        matches.append(current_match)

    # Rensa dubbletter baserat på matchnummer och sortera
    unique_matches = {m['Match']: m for m in matches}.values()
    return sorted(list(unique_matches), key=lambda x: x['Match'])

# --- 3. BERÄKNINGAR ---
def calculate_probabilities(row):
    # Använd Svenska Spels odds
    o1 = row.get('Odds_1', 0)
    ox = row.get('Odds_X', 0)
    o2 = row.get('Odds_2', 0)
    
    if o1 == 0 or ox == 0 or o2 == 0: 
        return 0, 0, 0
    
    # Beräkna sannolikhet från odds (inverterat odds)
    # Normalisera för att få bort "bookie margin" så summan blir 100%
    raw_1, raw_x, raw_2 = 1/o1, 1/ox, 1/o2
    total = raw_1 + raw_x + raw_2
    
    p1 = (raw_1 / total) * 100
    px = (raw_x / total) * 100
    p2 = (raw_2 / total) * 100
    
    return round(p1, 1), round(px, 1), round(p2, 1)

def suggest_sign_and_status(row):
    tecken = []
    status = ""
    prob1 = row.get('Prob_1', 0)
    
    if prob1 == 0: return "❓", "Saknar Odds"

    val1, valx, val2 = row.get('Val_1', 0), row.get('Val_X', 0), row.get('Val_2', 0)

    # Värdebaserad algoritm
    values = [('1', val1, row['Prob_1']), ('X', valx, row['Prob_X']), ('2', val2, row['Prob_2'])]
    # Sortera på värde
    values.sort(key=lambda x: x[1], reverse=True) 
    
    # Ta tecknet med bäst värde först
    best_sign = values[0]
    tecken.append(best_sign[0])
    
    # Sätt status baserat på bästa värdet
    if best_sign[1] > 10: status = f"💎 Fynd {best_sign[0]}"
    elif best_sign[1] < -10: status = "⚠️ Varning"
    else: status = "Neutral"
    
    # Gardera?
    # Om favoriten (högst sannolikhet) inte är med, eller om vi behöver gardera
    probs = [('1', row['Prob_1']), ('X', row['Prob_X']), ('2', row['Prob_2'])]
    probs.sort(key=lambda x: x[1], reverse=True)
    favorite = probs[0][0]
    
    # Om vårt värdetecken inte är favoriten, gardera med favoriten
    if best_sign[0] != favorite:
        tecken.append(favorite)
    elif values[0][1] < 5: # Om värdet är svagt på favoriten, ta med näst bästa värdet
        tecken.append(values[1][0])

    return "".join(sorted(tecken)), status

# --- APP LAYOUT ---
st.set_page_config(page_title="Stryktipset Odds Edition", layout="wide")
st.title(ST_PAGE_TITLE)

with st.expander("ℹ️ Instruktioner", expanded=True):
    col1, col2 = st.columns([2, 1])
    with col1:
        st.write("1. Markera allt (Ctrl+A) på Svenska Spel Stryktipset.")
        st.write("2. Kopiera (Ctrl+C).")
        st.write("3. Klistra in nedan. Scriptet läser nu oddsen direkt från din text!")
    with col2:
        st.link_button("Öppna Stryktipset ↗️", SVENSKA_SPEL_URL, use_container_width=True)

# --- FORMULÄR ---
with st.form("input_form"):
    text_input = st.text_area("Klistra in kupongen här:", height=300, placeholder=PLACEHOLDER_TEXT)
    submitted = st.form_submit_button("🚀 Kör Analys", type="primary", use_container_width=True)

if submitted and text_input:
    matches_data = parse_svenskaspel_paste(text_input)
    
    if not matches_data: 
        st.error("Hittade inga matcher. Kopierade du hela sidan?")
    else:
        df = pd.DataFrame(matches_data)
        
        # Kolla om vi fick med några odds
        if 'Odds_1' not in df.columns:
            st.warning("⚠️ Hittade inga odds i texten. Se till att du kopierat raderna där det står 'Odds' och siffrorna under.")
            # Skapa tomma kolumner för att inte krascha
            df['Odds_1'] = 0; df['Odds_X'] = 0; df['Odds_2'] = 0
        else:
            # Fyll NaN med 0
            df = df.fillna(0)

        # Beräkningar
        probs = df.apply(calculate_probabilities, axis=1, result_type='expand')
        df[['Prob_1', 'Prob_X', 'Prob_2']] = probs
        
        # Beräkna Värde (Sannolikhet - Streckprocent)
        # Positivt värde = Understreckat (Bra spel)
        # Negativt värde = Överstreckat (Dåligt spel)
        df['Val_1'] = df['Prob_1'] - df['Streck_1']
        df['Val_X'] = df['Prob_X'] - df['Streck_X']
        df['Val_2'] = df['Prob_2'] - df['Streck_2']
        
        results = df.apply(suggest_sign_and_status, axis=1, result_type='expand')
        df['Tips'] = results[0]
        df['Analys'] = results[1]
        
        df['Match_Rubrik'] = df['Hemmalag'] + " - " + df['Bortalag']

        def color_value(val):
            if pd.isna(val) or val == 0: return ''
            if val > 7: return 'background-color: #90ee90; color: black' # Grönt för bra värde
            if val < -10: return 'background-color: #ffcccb; color: black' # Rött för överstreckat
            return ''

        st.success(f"Analyserade {len(df)} matcher baserat på Svenska Spels odds.")

        table_height = (len(df) * 35) + 38 
        
        tab1, tab2, tab3 = st.tabs(["💡 Kupong", "📊 Värde & Odds", "🔧 Rådata"])
        
        with tab1:
            kupong_view = df[['Match', 'Match_Rubrik', 'Tips', 'Analys', 'Streck_1', 'Streck_X', 'Streck_2']].copy()
            st.dataframe(kupong_view, hide_index=True, use_container_width=True, height=table_height)
            
        with tab2:
            st.write("Värde = Sannolikhet (enligt odds) minus Folkets streck. Högt tal är bra!")
            val_view = df[['Match', 'Match_Rubrik', 'Val_1', 'Val_X', 'Val_2', 'Odds_1', 'Odds_X', 'Odds_2']].copy()
            styled_df = val_view.style.format({
                'Val_1': '{:.1f}', 'Val_X': '{:.1f}', 'Val_2': '{:.1f}',
                'Odds_1': '{:.2f}', 'Odds_X': '{:.2f}', 'Odds_2': '{:.2f}'
            }).map(color_value, subset=['Val_1', 'Val_X', 'Val_2'])
            st.dataframe(styled_df, hide_index=True, use_container_width=True, height=table_height)
            
        with tab3:
            st.dataframe(df, hide_index=True, use_container_width=True)
