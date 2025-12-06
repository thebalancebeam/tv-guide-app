import streamlit as st
import google.generativeai as genai
import pandas as pd
from datetime import datetime, timedelta
import io
import time

# --- 1. SETUP ---
st.set_page_config(page_title="Global TV Master", page_icon="🌍", layout="wide")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("⚠️ API Key fehlt. Bitte in den Streamlit Secrets eintragen.")
    st.stop()

# --- 2. MODELL CONFIG ---
@st.cache_resource
def get_model():
    # Wir nehmen Flash für Geschwindigkeit
    return genai.GenerativeModel('gemini-1.5-flash')

# --- 3. LISTEN ---
# Wir teilen die Listen auf, damit die KI nicht überfordert ist

LISTE_FUSSBALL = """
DEUTSCHLAND: 1. Bundesliga, 2. Bundesliga, DFB Pokal.
ENGLAND: Premier League, FA Cup, Championship.
EUROPA: La Liga (ES), Serie A (IT), Ligue 1 (FR), Eredivisie (NL).
INTERNATIONAL: Champions League, Europa League.
"""

LISTE_MIX = """
US-SPORT: NFL (Football), NBA (Basketball), NHL (Eishockey).
WINTERSPORT: Ski Alpin Weltcup, Biathlon, Skispringen.
MOTORSPORT: Formel 1, MotoGP.
TENNIS: Grand Slams, ATP Finals.
"""

ENT_COUNTRIES = "UK, USA, DE, AT, KR (Südkorea), JP (Japan)"

# --- 4. DATA FETCHING ---
def get_dates():
    now = datetime.now()
    return now.strftime("%d.%m.%Y"), (now + timedelta(days=1)).strftime("%d.%m.%Y")

def query_gemini(prompt_content):
    """Hilfsfunktion für die reine Abfrage"""
    today, tomorrow = get_dates()
    model = get_model()
    
    full_prompt = f"""
    Rolle: TV-Datenbank. Datum heute: {today}. Betrachteter Zeitraum: {today} und {tomorrow}.
    
    AUFGABE:
    Erstelle eine Liste der TV-Übertragungen für:
    {prompt_content}
    
    REGELN:
    - Uhrzeiten MÜSSEN in MEZ (Mitteleuropäische Zeit) sein.
    - Format: Reine CSV-Daten.
    - Trennzeichen: Semikolon (;)
    - Spalten: Datum;Uhrzeit;Sportart;Wettbewerb;Titel_oder_Match;Sender
    - WICHTIG: Keine Markdown-Blöcke (kein ```), keine Überschriften.
    - Bei Fußball: Titel muss "Heim vs Gast" sein.
    """
    
    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

@st.cache_data(ttl=3600)
def fetch_all_sports():
    # 1. Abfrage Fußball
    raw_foot = query_gemini(LISTE_FUSSBALL)
    time.sleep(1) # Kurze Atempause für die API
    
    # 2. Abfrage Rest
    raw_mix = query_gemini(LISTE_MIX)
    
    return raw_foot, raw_mix

@st.cache_data(ttl=3600)
def fetch_entertainment():
    prompt = f"""
    Fokus Länder: {ENT_COUNTRIES}.
    Suche: Prime-Time Shows, Musik/Konzerte, Reality-TV Highlights, Dokus.
    Ignoriere: Nachrichten, Talkshows, fiktionale Serien/Filme.
    """
    return query_gemini(prompt)

# --- 5. PARSER ---
def parse_mixed_csv(raw_text_list):
    """Nimmt eine LISTE von Roh-Texten und macht EINE Tabelle daraus"""
    all_rows = []
    
    # Wir gehen alle Roh-Antworten durch (z.B. Fußball Text + Mix Text)
    for raw_text in raw_text_list:
        if "Error" in raw_text: continue
        
        # Säubern
        clean = raw_text.replace("```csv", "").replace("```", "").strip()
        lines = clean.split('\n')
        
        for line in lines:
            if not line.strip(): continue
            parts = line.split(';')
            
            # Validierung: Wir brauchen mind. 5 Spalten, damit es Sinn macht
            if len(parts) >= 5:
                # Datum Check (Spalte 0 sollte Zahlen enthalten)
                if any(char.isdigit() for char in parts[0]):
                    all_rows.append(parts)

    if all_rows:
        # Wir definieren die Spaltennamen fest
        cols = ["Datum", "Uhrzeit", "Sportart", "Wettbewerb", "Event / Titel", "Sender"]
        # Falls die KI mehr Spalten liefert, schneiden wir ab oder füllen auf
        structured_data = []
        for r in all_rows:
            # Wir nehmen nur die ersten 6 Spalten oder füllen auf
            row_fixed = r[:6] 
            while len(row_fixed) < 6: row_fixed.append("-")
            structured_data.append(row_fixed)
            
        return pd.DataFrame(structured_data, columns=cols)
    else:
        return pd.DataFrame()

# --- 6. FRONTEND ---
st.title("🌍 Global TV Guide")
st.caption(f"Daten für {get_dates()[0]} & {get_dates()[1]}")

tab_sport, tab_ent, tab_debug = st.tabs(["⚽️ SPORT", "🎤 ENTERTAINMENT", "⚙️ DEBUG"])

# === SPORT ===
with tab_sport:
    if st.button("Lade Sport-Programm (Dual-Scan)", key="btn_sport"):
        with st.spinner("Frage Fußball-Datenbank ab..."):
            # Wir holen beide Texte
            txt_foot, txt_mix = fetch_all_sports()
            
            # Wir speichern sie für Debugging
            st.session_state['debug_foot'] = txt_foot
            st.session_state['debug_mix'] = txt_mix
            
            # Wir parsen beide zusammen
            df = parse_mixed_csv([txt_foot, txt_mix])
            
            if not df.empty:
                # Sortieren nach Uhrzeit (Trick: String-Sortierung reicht meistens grob)
                df = df.sort_values(by=["Datum", "Uhrzeit"])
                
                st.success(f"{len(df)} Events gefunden!")
                st.dataframe(
                    df, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Event / Titel": st.column_config.TextColumn("Match / Event", width="large"),
                        "Wettbewerb": st.column_config.TextColumn("Liga", width="medium"),
                    }
                )
            else:
                st.error("Keine Tabelle erkannt.")
                st.warning("Schau in den 'DEBUG' Tab, um zu sehen, was schiefging.")

# === ENTERTAINMENT ===
with tab_ent:
    if st.button("Lade Entertainment", key="btn_ent"):
        with st.spinner("Suche Shows..."):
            txt_ent = fetch_entertainment()
            st.session_state['debug_ent'] = txt_ent
            
            df = parse_mixed_csv([txt_ent])
            
            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("Keine Daten gefunden.")

# === DEBUG TAB ===
with tab_debug:
    st.write("Hier siehst du die Rohantworten der KI.")
    if 'debug_foot' in st.session_state:
        with st.expander("Rohdaten: Fußball"):
            st.text(st.session_state['debug_foot'])
    if 'debug_mix' in st.session_state:
        with st.expander("Rohdaten: Mix Sport"):
            st.text(st.session_state['debug_mix'])
    if 'debug_ent' in st.session_state:
        with st.expander("Rohdaten: Entertainment"):
            st.text(st.session_state['debug_ent'])
