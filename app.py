import streamlit as st
import google.generativeai as genai
import pandas as pd
from datetime import datetime, timedelta
import io

# --- 1. SETUP ---
st.set_page_config(page_title="Global TV Master", page_icon="🌍", layout="wide")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("⚠️ API Key fehlt. Bitte in den Streamlit Secrets eintragen.")
    st.stop()

# --- 2. MODELL-AUTO-ERKENNUNG ---
@st.cache_resource
def get_best_model_name():
    try:
        # Wir versuchen zuerst das stabilste Modell direkt zu nutzen
        # (Das Listen der Modelle macht bei manchen Keys Probleme)
        return "gemini-1.5-flash" 
    except:
        return "gemini-pro"

# --- 3. INHALTE ---
COUNTRIES_ENT = "UK, Deutschland, Österreich, Schweiz, USA, Japan, Südkorea"

SPORT_LISTE = """
FUSSBALL:
- DE: 1. & 2. Bundesliga, DFB Pokal
- UK: Premier League, FA Cup
- ES: La Liga
- IT: Serie A
- INT: Champions League, Europa League
- US: MLS

WINTERSPORT: Ski Alpin, Biathlon.
MOTOR: Formel 1, MotoGP.
US-SPORT: NFL, NBA, NHL.
"""

# --- 4. KI ABFRAGE ---
def get_date_str():
    now = datetime.now()
    return now.strftime("%d.%m.%Y"), (now + timedelta(days=1)).strftime("%d.%m.%Y")

@st.cache_data(ttl=3600)
def fetch_data(category):
    today, tomorrow = get_date_str()
    model_name = get_best_model_name()
    model = genai.GenerativeModel(model_name)
    
    # Der Prompt wurde verschärft, damit er weniger "quatscht"
    if category == "Sport":
        prompt = f"""
        Du bist eine TV-Datenbank API. Antworte NUR mit Daten.
        Zeitraum: {today} und {tomorrow}.
        
        Suche Live-Sport-Events (Fokus: {SPORT_LISTE}).
        
        FORMAT PFLICHT:
        - Gebe NUR CSV-Zeilen zurück.
        - Trennzeichen: Semikolon (;)
        - Keine Überschriften, keine Einleitung, kein "Hier ist die Liste".
        - Datumsformat: DD.MM.YYYY
        
        SPALTEN:
        Datum;Uhrzeit;Sportart;Wettbewerb;Heim;Gast;Sender
        """
    else:
        prompt = f"""
        Du bist eine TV-Datenbank API. Antworte NUR mit Daten.
        Zeitraum: {today} und {tomorrow}.
        Fokus: Entertainment, Shows, Reality (UK, US, DE, KR, JP).
        
        FORMAT PFLICHT:
        - Gebe NUR CSV-Zeilen zurück.
        - Trennzeichen: Semikolon (;)
        - Keine Überschriften.
        
        SPALTEN:
        Datum;Uhrzeit;Land;Genre;Titel;Beschreibung;Sender
        """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# --- 5. ROBUSTER PARSER (Das ist neu!) ---
def robust_parse_csv(raw_text, expected_columns):
    """Liest den Text Zeile für Zeile und rettet, was zu retten ist."""
    
    # 1. Markdown entfernen
    clean_text = raw_text.replace("```csv", "").replace("```", "").strip()
    
    valid_rows = []
    lines = clean_text.split('\n')
    
    expected_count = len(expected_columns)
    
    for line in lines:
        # Leere Zeilen überspringen
        if not line.strip(): 
            continue
            
        parts = line.split(';')
        
        # Bereinigung: Manchmal macht die KI Leerzeichen um die Semikolons
        parts = [p.strip() for p in parts]
        
        # Prüfung: Hat die Zeile die richtige Anzahl Spalten?
        if len(parts) == expected_count:
            # Check: Ist die erste Spalte wirklich ein Datum? (Grobfilter gegen Text)
            # Wenn die erste Spalte länger als 15 Zeichen ist, ist es wahrscheinlich Gelaber der KI
            if len(parts[0]) < 20: 
                valid_rows.append(parts)
        else:
            # Fallback: Manchmal nutzt die KI Kommas statt Semikolons
            parts_comma = line.split(',')
            if len(parts_comma) == expected_count:
                valid_rows.append([p.strip() for p in parts_comma])
    
    if valid_rows:
        return pd.DataFrame(valid_rows, columns=expected_columns)
    else:
        return pd.DataFrame()

# --- 6. FRONTEND ---
st.title("🌍 Global Live Guide")
st.markdown(f"**Daten für:** {get_date_str()[0]} & {get_date_str()[1]}")

tab_sport, tab_ent = st.tabs(["⚽️ SPORT", "🎤 ENTERTAINMENT"])

# === SPORT TAB ===
with tab_sport:
    if st.button("Lade Sport", key="s"):
        with st.spinner("Lade..."):
            raw = fetch_data("Sport")
            
            # Debugging: Wir speichern die Rohdaten, um sie unten anzuzeigen
            st.session_state['raw_sport'] = raw
            
            if "Error" in raw:
                st.error(raw)
            else:
                cols = ["Datum", "Uhrzeit", "Sportart", "Wettbewerb", "Heim", "Gast", "Sender"]
                df = robust_parse_csv(raw, cols)
                
                if not df.empty:
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.warning("Keine Tabelle erkannt.")
                    st.info("Das hat die KI geantwortet (siehe unten bei 'Rohdaten').")

# === ENTERTAINMENT TAB ===
with tab_ent:
    if st.button("Lade Shows", key="e"):
        with st.spinner("Lade..."):
            raw = fetch_data("Entertainment")
            st.session_state['raw_ent'] = raw
            
            if "Error" in raw:
                st.error(raw)
            else:
                cols = ["Datum", "Uhrzeit", "Land", "Genre", "Titel", "Beschreibung", "Sender"]
                df = robust_parse_csv(raw, cols)
                
                if not df.empty:
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.warning("Keine Tabelle erkannt.")

# --- 7. DEBUGGING BEREICH ---
st.divider()
with st.expander("🛠️ Analyse & Rohdaten (Klick mich bei Fehlern)"):
    st.write("Falls die Tabelle leer bleibt, siehst du hier, was die KI wirklich gesendet hat:")
    
    if 'raw_sport' in st.session_state:
        st.caption("Letzte Antwort Sport:")
        st.code(st.session_state['raw_sport'], language='text')
        
    if 'raw_ent' in st.session_state:
        st.caption("Letzte Antwort Entertainment:")
        st.code(st.session_state['raw_ent'], language='text')
