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

# --- 2. DIE MODELL-LISTE (Brute Force) ---
# Wir probieren diese Modelle nacheinander durch, bis eines antwortet.
MODEL_CANDIDATES = [
    "gemini-1.5-flash",       # Der Schnellste (Alias)
    "gemini-1.5-flash-001",   # Der Schnellste (Versioniert)
    "gemini-1.5-flash-latest",# Manchmal dieser Name
    "gemini-1.5-pro",         # Der Starke
    "gemini-pro"              # Der Klassiker (1.0) - Fallback, der fast immer geht
]

def query_gemini_safe(prompt_text):
    """Probiert alle Modell-Namen durch, bis einer klappt."""
    last_error = ""
    
    for model_name in MODEL_CANDIDATES:
        try:
            # Versuch mit aktuellem Modellnamen
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt_text)
            return response.text # Erfolg! Sofort zurückgeben.
            
        except Exception as e:
            # Fehler speichern und weitermachen
            last_error = str(e)
            continue # Nächster Modellname in der Liste
            
    # Wenn wir hier ankommen, haben alle Modelle versagt
    return f"Error: Alle Modelle fehlgeschlagen. Letzter Fehler: {last_error}"

# --- 3. INHALTS-DEFINITIONEN ---

# TEIL A: FUSSBALL
LISTE_FUSSBALL = """
DEUTSCHLAND: 1. & 2. Bundesliga, DFB Pokal.
ÖSTERREICH: 1. & 2. Bundesliga, ÖFB Pokal.
ENGLAND: Premier League, Championship, FA Cup, Carabao Cup.
EUROPA LIGEN: La Liga, Serie A, Ligue 1, Eredivisie, Liga Portugal, Süper Lig.
POKALE: Copa del Rey, Coupe de France, Coppa Italia.
INTERNATIONAL: Champions League, Europa League, Conference League.
USA: MLS.
"""

# TEIL B: MIX (Restliche Sportarten)
LISTE_MIX = """
TENNIS: ATP Turniere & Grand Slams.
WINTER: Ski Alpin, Biathlon, Skispringen.
MOTOR: Formel 1, MotoGP.
US-SPORT: NFL, NBA, NHL, MLB.
"""

# TEIL C: ENTERTAINMENT
LISTE_ENT = "UK, Deutschland, Österreich, USA, Japan, Südkorea"

# --- 4. HILFSFUNKTIONEN ---

def get_dates():
    now = datetime.now()
    return now.strftime("%d.%m.%Y"), (now + timedelta(days=1)).strftime("%d.%m.%Y")

def robust_parse(raw_text_list):
    """Macht aus Text-Schnipseln eine Tabelle"""
    all_data = []
    
    for raw_text in raw_text_list:
        if not raw_text or "Error" in raw_text: continue
        
        clean_text = raw_text.replace("```csv", "").replace("```", "").strip()
        lines = clean_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Semikolon Split
            parts = line.split(';')
            
            # Validierung: Mindestens 4-5 Spalten
            if len(parts) >= 4:
                # Datum Check (Erste Spalte muss Zahl enthalten)
                if len(parts[0]) > 0 and any(char.isdigit() for char in parts[0]):
                    clean_parts = [p.strip() for p in parts]
                    # Auffüllen auf 6 Spalten
                    while len(clean_parts) < 6: clean_parts.append("-")
                    all_data.append(clean_parts[:6])

    if all_data:
        cols = ["Datum", "Uhrzeit", "Sportart", "Wettbewerb", "Event / Match", "Sender"]
        return pd.DataFrame(all_data, columns=cols)
    else:
        return pd.DataFrame()

# --- 5. FRONTEND ---

st.title("🌍 Mein TV Planer")
st.caption(f"Daten für {get_dates()[0]} & {get_dates()[1]}")

tab_sport, tab_ent, tab_debug = st.tabs(["⚽️ SPORT", "🎤 ENTERTAINMENT", "⚙️ DEBUG"])

# === SPORT TAB ===
with tab_sport:
    if st.button("Lade Sport-Programm", key="btn_sport"):
        with st.spinner("Scanne Sport-Kanäle (probiere verschiedene KI-Modelle)..."):
            
            # Prompt bauen
            today, tomorrow = get_dates()
            base_prompt = f"""
            Rolle: TV-Datenbank. Zeitraum: {today} und {tomorrow}.
            AUFGABE: Suche Live-Events. 
            Regeln: NUR CSV. Trennzeichen Semikolon (;). Spalten: Datum;Uhrzeit;Sportart;Wettbewerb;Heim vs Gast;Sender.
            Keine Markdown-Blöcke. Zeit in MEZ.
            Suche nach: """
            
            # 1. Anfrage Fußball
            raw_foot = query_gemini_safe(base_prompt + LISTE_FUSSBALL)
            time.sleep(0.5)
            
            # 2. Anfrage Rest
            raw_mix = query_gemini_safe(base_prompt + LISTE_MIX)
            
            # Debug speichern
            st.session_state['dbg_foot'] = raw_foot
            st.session_state['dbg_mix'] = raw_mix
            
            # Tabelle bauen
            df = robust_parse([raw_foot, raw_mix])
            
            if not df.empty:
                try:
                    df = df.sort_values(by=["Datum", "Uhrzeit"])
                except:
                    pass
                
                st.success(f"{len(df)} Live-Events geladen.")
                st.dataframe(
                    df, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Event / Match": st.column_config.TextColumn("Paarung", width="large"),
                        "Wettbewerb": st.column_config.TextColumn("Liga", width="medium"),
                    }
                )
            else:
                st.warning("Keine Daten erkannt.")
                st.info("Falls Fehler 404 auftauchte, wurde er jetzt automatisch umgangen. Wenn trotzdem keine Daten da sind, hat die KI keine Events gefunden.")

# === ENTERTAINMENT TAB ===
with tab_ent:
    if st.button("Lade Entertainment", key="btn_ent"):
        with st.spinner("Scanne Shows..."):
            today, tomorrow = get_dates()
            prompt_ent = f"""
            Rolle: TV-Guide. Zeitraum: {today} und {tomorrow}.
            Länder: {LISTE_ENT}.
            Suche: Prime-Time Shows, Musik, Reality. KEINE Filme/Serien.
            Format: NUR CSV. Trennzeichen Semikolon (;).
            Spalten: Datum;Uhrzeit;Land;Genre;Titel;Sender.
            """
            
            raw_ent = query_gemini_safe(prompt_ent)
            st.session_state['dbg_ent'] = raw_ent
            
            df = robust_parse([raw_ent])
            
            if not df.empty:
                df.columns = ["Datum", "Uhrzeit", "Land", "Genre", "Titel", "Sender"]
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("Keine Daten gefunden.")

# === DEBUG TAB ===
with tab_debug:
    st.write("Rohdaten der KI:")
    if 'dbg_foot' in st.session_state:
        with st.expander("Fußball Raw"): st.text(st.session_state['dbg_foot'])
    if 'dbg_mix' in st.session_state:
        with st.expander("Mix Sport Raw"): st.text(st.session_state['dbg_mix'])
    if 'dbg_ent' in st.session_state:
        with st.expander("Entertainment Raw"): st.text(st.session_state['dbg_ent'])
