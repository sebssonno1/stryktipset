import streamlit as st
import pandas as pd
import re

# --- KONFIGURATION ---
ST_PAGE_TITLE = "🐻 Stryktipset: Bulletproof Edition"
SVENSKA_SPEL_URL = "https://www.svenskaspel.se/stryktipset"

# --- PLATSHÅLLARTEXT ---
PLACEHOLDER_TEXT = """Klistra in hela sidan (Ctrl+A) från den vanliga kupongvyn.
Se till att både streckprocent och odds kommer med."""

# --- 1. HJÄLPFUNKTIONER ---
def to_float(val_str):
    """Försöker konvertera en sträng till float, hanterar både komma och punkt."""
    try:
        # Ersätt komma med punkt och ta bort ev % eller mellanslag
        clean = val_str.replace(',', '.').replace('%', '').strip()
        return float(clean)
    except ValueError:
        return None

def clean_team_name(name):
    if not isinstance(name, str): return "-"
    # Tar bort inledande siffror (t.ex. "1. ") och 1X2-tecken
    name = re.sub(r'^\d+[\.\s]*', '', name) 
    name = name.replace("1X2", "").replace("1", "").replace("X", "").replace("2", "")
    return name.strip()

# --- 2. PARSER (Den nya, smartare logiken) ---
def parse_svenskaspel_paste(text_content):
    matches = []
    # Rensa bort tomma rader direkt
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    
    current_match = {}
    
    # Vi itererar genom alla rader
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # --- 1. HITTA MATCHNUMMER ---
        # Om raden är en siffra 1-13
        if line.isdigit() and 1 <= int(line) <= 13:
            # Spara föregående match om den är klar
            if current_match and 'Hemmalag' in current_match:
                matches.append(current_match)
            
            current_match = {'Match': int(line)}
            
            # --- 2. HITTA LAGNAMN (Leta i de närmaste 6 raderna) ---
            found_teams = False
            for offset in range(1, 7):
                if i + offset >= len(lines): break
                
                txt = lines[i+offset]
                # Kolla efter olika typer av bindestreck eller " - "
                if any(sep in txt for sep in ['-', '–', '—', ' vs ']):
                    # Om hela matchen står på en rad: "Lag A - Lag B"
                    separators = [' vs ', ' - ', '-', '–', '—']
                    for sep in separators:
                        if sep in txt:
                            parts = txt.split(sep, 1)
                            if len(parts) == 2:
                                current_match['Hemmalag'] = clean_team_name(parts[0])
                                current_match['Bortalag'] = clean_team_name(parts[1])
                                found_teams = True
                                break
                    if found_teams: break
                
                # Om bindestrecket ligger på en EGEN rad (vanligast vid Ctrl+A)
                # Exempel:
                # Ipswich
                # -
                # Preston
                elif txt in ['-', '–', '—'] and (i+offset+1 < len(lines)):
                    current_match['Hemmalag'] = clean_team_name(lines[i+offset-1])
                    current_match['Bortalag'] = clean_team_name(lines[i+offset+1])
                    found_teams = True
                    break
            
            # Nödlösning: Om vi inte hittade bindestreck, gissa att rad 1 och 3 efter numret är lagen
            if not found_teams and i + 3 < len(lines):
                # Detta fångar fallet om bindestrecket "försvunnit" eller är ett konstigt tecken
                # Förutsätter struktur: Matchnr -> Hemmalag -> (skräp) -> Bortalag
                pass 

        # --- 3. HITTA DATA (STRECK & ODDS) ---
        # Vi använder en "scanner" som tittar framåt när vi hittar nyckelord
        
        # Hitta STRECK (Svenska folket)
        if "Svenska folket" in line or "Svenska Folket" in line:
            values = []
            # Titta på de kommande 8 raderna efter siffror
            for offset in range(1, 9):
                if i + offset >= len(lines): break
                txt = lines[i+offset]
                
                # Hitta heltal (t.ex. 58%)
                nums = re.findall(r'(\d+)%', txt)
                if not nums and txt.isdigit(): nums = [txt] # Fånga "58" utan %
                
                for num in nums:
                    val = to_float(num)
                    if val is not None: values.append(val)
            
            if len(values) >= 3:
                current_match['Streck_1'] = values[0]
                current_match['Streck_X'] = values[1]
                current_match['Streck_2'] = values[2]

        # Hitta ODDS
        # Vi kollar om raden innehåller "Odds" men inte är en lång mening
        if "Odds" in line and len(line) < 30:
            values = []
            # Titta framåt efter decimaltal
            for offset in range(1, 9):
                if i + offset >= len(lines): break
                txt = lines[i+offset]
                
                # Regex som hittar "1,78", "1.78", "3,50" etc.
                # Tillåter både komma och punkt
                found = re.findall(r'(\d+[.,]\d+)', txt)
                
                for f in found:
                    val = to_float(f)
                    if val is not None: values.append(val)
                
                if len(values) >= 3:
                    current_match['Odds_1'] = values[0]
                    current_match['Odds_X'] = values[1]
                    current_match['Odds_2'] = values[2]
                    break

        i += 1
    
    # Lägg till sista matchen
    if current_match and 'Hemmalag' in current_match:
        matches.append(current_match)

    # Ta bort dubbletter och sortera
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
    # Sortera på VÄRDE (högst först)
    options.sort(key=lambda x: x[1], reverse=True) 
    
    best_sign = options[0]
    tecken = [best_sign[0]]
    status = "Neutral"

    if best_sign[1] > 10: status = f"💎 Fynd {best_sign[0]}"
    elif best_sign[1] < -10: status = "⚠️ Dåligt värde"

    # Garderings-logik
    # Hitta favoriten (högst sannolikhet)
    probs_sorted = sorted(options, key=lambda x: x[2], reverse=True)
    favorite = probs_sorted[0][0]

    # Om vårt "bästa värde" inte är favoriten, ta med favoriten (gardera)
    if best_sign[0] != favorite:
        tecken.append(favorite)
    elif best_sign[1] < 5: 
        # Om värdet är lågt på favoriten, ta med näst bästa
        tecken.append(options[1][0])

    return "".join(sorted(tecken)), status

# --- APP START ---
st.set_page_config(page_title="Stryktipset Bulletproof", layout="wide")
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
        st.error("Kunde inte hitta några matcher. Testa att kopiera igen.")
    else:
        df = pd.DataFrame(raw_data)
        
        # --- SÄKERSTÄLL DATATYPER (För att undvika krascher) ---
        # 1. Text
        if 'Hemmalag' not in df.columns: df['Hemmalag'] = "-"
        if 'Bortalag' not in df.columns: df['Bortalag'] = "-"
        df['Hemmalag'] = df['Hemmalag'].fillna("-").astype(str)
        df['Bortalag'] = df['Bortalag'].fillna("-").astype(str)

        # 2. Siffror (Fyll med 0 om de saknas)
        num_cols = ['Streck_1', 'Streck_X', 'Streck_2', 'Odds_1', 'Odds_X', 'Odds_2']
        for col in num_cols:
            if col not in df.columns: df[col] = 0.0
            df[col] = df[col].fillna(0.0)

        # --- BERÄKNINGAR ---
        probs = df.apply(calculate_probabilities, axis=1, result_type='expand')
        df[['Prob_1', 'Prob_X', 'Prob_2']] = probs
        
        df['Val_1'] = df['Prob_1'] - df['Streck_1']
        df['Val_X'] = df['Prob_X'] - df['Streck_X']
        df['Val_2'] = df['Prob_2'] - df['Streck_2']
        
        results = df.apply(suggest_sign_and_status, axis=1, result_type='expand')
        df['Tips'] = results[0]
        df['Analys'] = results[1]
        
        df['Match_Rubrik'] = df['Hemmalag'] + " - " + df['Bortalag']

        # --- VISNING ---
        matches_with_odds = df[df['Odds_1'] > 0].shape[0]
        st.success(f"Lyckades läsa in {len(df)} matcher. Odds hittades för {matches_with_odds} st.")
        
        if matches_with_odds == 0:
            st.warning("Hittade inga odds alls. Kontrollera att du klistrade in texten där 'Odds' och siffrorna (t.ex. 1,78) syns.")

        h = (len(df) * 35) + 38
        
        tab1, tab2, tab3 = st.tabs(["💡 Kupong", "📊 Värdetabell", "🔍 Rådata"])
        
        with tab1:
            st.dataframe(
                df[['Match', 'Match_Rubrik', 'Tips', 'Analys', 'Streck_1', 'Streck_X', 'Streck_2']], 
                hide_index=True, use_container_width=True, height=h
            )

        with tab2:
            st.write("Grönt = Bra värde (Spelvärt). Rött = Överstreckat.")
            display_cols = ['Match', 'Match_Rubrik', 'Val_1', 'Val_X', 'Val_2', 'Odds_1', 'Odds_X', 'Odds_2']
            
            # Formatera färger
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
