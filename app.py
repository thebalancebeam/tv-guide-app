import streamlit as st
import google.generativeai as genai
import pandas as pd
from datetime import datetime, timedelta
import io
import time

# --- 1. SETUP ---
st.set_page_config(page_title="Global TV Guide", page_icon="📺", layout="wide")

# API Key laden
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("⚠️ API Key fehlt. Bitte in den Streamlit Secrets eintragen.")
    st.stop()

# --- 2. MODELL CONFIG ---
@st.cache_resource
def get_model():
    # Wir versuchen, das Flash-Modell zu erzwingen (schnell & gut für Listen)
    return genai.GenerativeModel('gemini-1.5-flash')

# --- 3. INHALTS-DEFINITIONEN (Deine neue Liste) ---

# TEIL A: FUSSBALL (Die großen Ligen)
LISTE_FUSSBALL = """
DEUTSCHLAND: 1. & 2. Bundesliga, DFB Pokal, Frauen-Bundesliga.
ÖSTERREICH: 1. & 2. Bundesliga, ÖFB Pokal.
ENGLAND: Premier League, Championship, FA Cup, Carabao Cup, Women's Super League.
EUROPA (Ligen): La Liga (ES), Serie A (IT), Ligue 1 (FR), Eredivisie (NL), Liga Portugal, Belgian Pro League, Allsvenskan (SE), Süper Lig (TR).
EUROPA (Pokale): Copa del Rey, Coupe de France, Coppa Italia.
INTERNATIONAL: Champions League, Europa League, Conference League, Women's CL.
LÄNDERSPIELE: UEFA & FIFA Länderspiele.
USA: MLS.
"""

# TEIL B: MIX (US-Sport, Motor, Tennis, Winter)
LISTE_MIX = """
TENNIS: Alle größeren ATP Turniere & Grand Slams (Männer/Frauen).
WINTERSPORT: Ski Alpin, Biathlon, Skispringen, Langlauf.
MOTORSPORT: Formel 1, MotoGP.
US-SPORT: NFL (Football), NBA (Basketball), NHL (Eishockey), MLB (Baseball).
"""

# TEIL C: ENTERTAINMENT (Länderfokus)
LISTE_ENT = "UK, Deutschland, Österreich, Schweiz, USA, Japan, Südkorea"

# --- 4. HILFSFUNKTIONEN ---

def get_dates():
    now = datetime.now()
    return now.strftime("%d.%m.%Y"), (now + timedelta(days=1)).strftime("%d.%m.%Y")

def clean_csv_line(line):
    """Hilft, unsaubere Zeilen der KI zu reparieren"""
    # Entfernt Markdown-Reste am Anfang/Ende der Zeile
    return line.replace("|", "").strip()

def robust_parse(raw_text_list):
    """Nimmt eine Liste von Texten (Fußball + Mix) und macht EINE saubere Tabelle"""
    all_data = []
    
    for raw_text in raw_text_list:
        if not raw_text or "Error" in raw_text: continue
        
        # Grobe Bereinigung
        clean_text = raw_text.replace("```csv", "").replace("```", "").strip()
        lines = clean_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Wir splitten am Semikolon
            parts = line.split(';')
            
            # Validierung: Wir erwarten ca. 6 Spalten
            # Datum;Uhrzeit;Sportart;Wettbewerb;Paarung/Titel;Sender
            if len(parts) >= 5:
                # Zusatz-Check: Beginnt die Zeile mit einer Zahl? (Datum)
                if len(parts[0]) > 0 and parts[0][0].isdigit():
                    # Leerzeichen um die Daten bereinigen
                    clean_parts = [p.strip() for p in parts]
                    # Wenn Sender fehlt, füllen wir auf
                    while len(clean_parts) < 6: clean_parts.append("-")
                    # Wir nehmen nur die ersten 6 Spalten (falls KI mehr liefert)
                    all_data.append(clean_parts[:6])

    if all_data:
        cols = ["Datum", "Uhrzeit", "Sportart", "Wettbewerb", "Event / Match", "Sender"]
        return pd.DataFrame(all_data, columns=cols)
    else:
        return pd.DataFrame()

# --- 5. KI ABFRAGE LOGIK ---

def query_gemini(prompt_context, category_mode="Sport"):
    today, tomorrow = get_dates()
    model = get_model()
    
    if category_mode == "Sport":
        prompt = f"""
        Rolle: TV-Datenbank. Zeitraum: {today} und {tomorrow}.
        
        AUFGABE: Suche Live-Events im TV für:
        {prompt_context}
        
        REGELN:
        1. Listung: Jedes Match einzeln. Titel MUSS "Heim vs Gast" sein.
        2. Sender: Internationale Sender oder DACH-Sender nennen.
        3. Zeit: Zwingend MEZ.
        4. WICHTIG: Wenn für eine Liga heute/morgen NICHTS läuft, lass sie weg. Erfinde nichts.
        
        FORMAT (CSV):
        Datum;Uhrzeit;Sportart;Wettbewerb;Heim vs Gast;Sender
        (Gib mir NUR die CSV-Zeilen, keine Überschriften, kein Markdown).
        """
    else:
        prompt = f"""
        Rolle: TV-Guide Entertainment. Zeitraum: {today} und {tomorrow}.
        Fokus Länder: {prompt_context}.
        
        AUFGABE: Suche nach:
        - Großen Shows (Prime Time)
        - Musik/Konzerten
        - Reality TV Highlights
        - Exklusiven Dokus
        (Keine Serien, keine Filme, keine News).
        
        FORMAT (CSV):
        Datum;Uhrzeit;Land;Genre;Titel der Show;Sender
        (Gib mir NUR die CSV-Zeilen, keine Überschriften, kein Markdown).
        """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# --- 6. FRONTEND ---

st.title("🌍 Mein TV Planer")
st.caption(f"Daten für {get_dates()[0]} & {get_dates()[1]}")

tab_sport, tab_ent, tab_debug = st.tabs(["⚽️ SPORT", "🎤 ENTERTAINMENT", "⚙️ DEBUG"])

# === TAB SPORT ===
with tab_sport:
    if st.button("Lade Sport (Fußball & Mix)", key="btn_sport"):
        with st.spinner("Scanne Fußball-Ligen und Sport-Events..."):
            # 1. Anfrage Fußball
            raw_foot = query_gemini(LISTE_FUSSBALL, "Sport")
            time.sleep(0.5) # Kurze Pause für API
            
            # 2. Anfrage Rest
            raw_mix = query_gemini(LISTE_MIX, "Sport")
            
            # Speichern für Debug
            st.session_state['dbg_foot'] = raw_foot
            st.session_state['dbg_mix'] = raw_mix
            
            # Verarbeiten
            df = robust_parse([raw_foot, raw_mix])
            
            if not df.empty:
                # Sortieren nach Uhrzeit
                try:
                    df = df.sort_values(by=["Datum", "Uhrzeit"])
                except:
                    pass # Falls Sortierung fehlschlägt, egal
                
                st.success(f"{len(df)} Live-Events gefunden.")
                st.dataframe(
                    df, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Event / Match": st.column_config.TextColumn("Paarung", width="large"),
                        "Wettbewerb": st.column_config.TextColumn("Liga/Turnier", width="medium"),
                        "Sender": st.column_config.TextColumn("TV", width="medium"),
                    }
                )
            else:
                st.warning("Keine Daten erkannt. (Vielleicht läuft heute nichts aus deiner Liste?)")
                st.info("Check den 'DEBUG' Tab für Details.")

# === TAB ENTERTAINMENT ===
with tab_ent:
    if st.button("Lade Entertainment", key="btn_ent"):
        with st.spinner("Suche Shows..."):
            raw_ent = query_gemini(LISTE_ENT, "Entertainment")
            st.session_state['dbg_ent'] = raw_ent
            
            # Parser wiederverwenden (Spaltennamen passen wir gleich an)
            df = robust_parse([raw_ent])
            
            if not df.empty:
                # Spaltennamen für Ent anpassen (der Parser nutzt Sport-Namen standardmäßig)
                df.columns = ["Datum", "Uhrzeit", "Land", "Genre", "Titel", "Sender"]
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("Keine Daten gefunden.")

# === TAB DEBUG ===
with tab_debug:
    st.write("Hier siehst du, was Google Gemini wirklich geantwortet hat:")
    
    if 'dbg_foot' in st.session_state:
        with st.expander("Rohdaten: Fußball"):
            st.text(st.session_state['dbg_foot'])
            
    if 'dbg_mix' in st.session_state:
        with st.expander("Rohdaten: Mix Sport"):
            st.text(st.session_state['dbg_mix'])
            
    if 'dbg_ent' in st.session_state:
        with st.expander("Rohdaten: Entertainment"):
            st.text(st.session_state['dbg_ent'])
