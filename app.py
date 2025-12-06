import streamlit as st
import google.generativeai as genai
import pandas as pd
from datetime import datetime, timedelta
import io
import time

# --- 1. SETUP ---
st.set_page_config(page_title="Global TV Guide", page_icon="📺", layout="wide")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("⚠️ API Key fehlt. Bitte in den Streamlit Secrets eintragen.")
    st.stop()

# --- 2. DIE INTELLIGENTE MODELL-SUCHE (WICHTIG!) ---

# Diese Liste probieren wir durch, bis einer antwortet
MODEL_CANDIDATES = [
    "gemini-1.5-flash",
    "gemini-1.5-flash-001",
    "gemini-1.5-pro",
    "gemini-1.5-pro-001",
    "gemini-pro"
]

def query_gemini_with_search_safe(prompt_text):
    """
    Probiert Modelle durch UND nutzt Google Search.
    """
    last_error = ""
    
    for model_name in MODEL_CANDIDATES:
        try:
            # Modell initialisieren
            model = genai.GenerativeModel(model_name)
            
            # Versuch: Anfrage MIT Search Tool senden
            # Wir nutzen hier 'google_search_retrieval' als Tool
            response = model.generate_content(
                prompt_text,
                tools='google_search_retrieval'
            )
            return response.text # Erfolg!
            
        except Exception as e:
            error_msg = str(e)
            # Wenn das Modell "not found" ist, probieren wir das nächste
            if "404" in error_msg or "not found" in error_msg:
                last_error = f"Modell {model_name} nicht gefunden."
                continue
            
            # Wenn es ein anderer Fehler ist (z.B. Search Tool nicht supported beim alten Pro Modell)
            # Dann probieren wir es OHNE Search Tool als Fallback
            try:
                response = model.generate_content(prompt_text)
                return response.text + "\n(Hinweis: Ohne Live-Suche generiert, da Modell Search nicht unterstützt)"
            except:
                last_error = error_msg
                continue

    return f"Error: Alle Modelle fehlgeschlagen. Letzter Fehler: {last_error}"

# --- 3. INHALT ---

LISTE_FUSSBALL = """
Suche den SPIELPLAN für HEUTE und MORGEN:
- Bundesliga (1. & 2.)
- Premier League
- La Liga, Serie A, Ligue 1
"""

LISTE_MIX = """
Suche den ZEITPLAN für HEUTE und MORGEN:
- Ski Alpin & Biathlon (Weltcup)
- Formel 1 (nur wenn Rennen ist)
- NFL, NBA, NHL
"""

LISTE_ENT = """
Suche das PRIMETIME TV-PROGRAMM (20:15) für HEUTE und MORGEN in DE, UK, US.
Fokus: Shows, Reality, Live-Events.
"""

# --- 4. LOGIK ---

def get_dates():
    # Einfache Zeitzonen-Korrektur
    now = datetime.utcnow() + timedelta(hours=1) 
    return now.strftime("%d.%m.%Y"), (now + timedelta(days=1)).strftime("%d.%m.%Y")

def smart_parser(raw_text):
    """Sucht nach Zeilen mit Trennzeichen '|'"""
    if not raw_text or "Error" in raw_text:
        return pd.DataFrame()

    data = []
    lines = raw_text.split('\n')
    
    for line in lines:
        # Bereinigen
        clean_line = line.strip().replace("*", "")
        parts = clean_line.split('|')
        
        # Wir akzeptieren Zeilen mit mind. 4 Teilen
        if len(parts) >= 4:
            # Check: Datum am Anfang?
            part0 = parts[0].strip()
            if any(c.isdigit() for c in part0):
                row = [p.strip() for p in parts]
                while len(row) < 6: row.append("-")
                data.append(row[:6])

    if data:
        cols = ["Datum", "Uhrzeit", "Sportart", "Wettbewerb", "Event / Titel", "Sender"]
        return pd.DataFrame(data, columns=cols)
    else:
        return pd.DataFrame()

# --- 5. FRONTEND ---

st.title("🌍 Live TV Guide (Safe Mode)")
st.caption(f"Datum: {get_dates()[0]} | System: Auto-Modell-Wahl + Search")

tab_sport, tab_ent, tab_debug = st.tabs(["⚽️ SPORT", "🎤 ENTERTAINMENT", "⚙️ DEBUG"])

# === SPORT ===
with tab_sport:
    if st.button("Lade Sport", key="btn_s"):
        with st.spinner("Suche Verbindung & Sportdaten..."):
            
            today, tomorrow = get_dates()
            base_prompt = f"""
            Du bist ein TV-Guide. Nutze Google Search für aktuelle Daten.
            Zeitraum: {today} und {tomorrow}.
            
            AUFGABE: Recherchiere Termine für: """
            
            format_instruction = """
            FORMAT-ANWEISUNG:
            Liste jedes Event in einer neuen Zeile genau so auf:
            DD.MM.YYYY | UHRZEIT | SPORTART | WETTBEWERB | EVENT/PAARUNG | SENDER
            Keine Einleitung, nur die Liste.
            """
            
            # Abfrage mit Safe-Funktion
            raw_foot = query_gemini_with_search_safe(base_prompt + LISTE_FUSSBALL + format_instruction)
            raw_mix = query_gemini_with_search_safe(base_prompt + LISTE_MIX + format_instruction)
            
            # Debug speichern
            st.session_state['raw_foot'] = raw_foot
            st.session_state['raw_mix'] = raw_mix
            
            # Parsen
            df = smart_parser(raw_foot + "\n" + raw_mix)
            
            if not df.empty:
                try: df = df.sort_values(by=["Datum", "Uhrzeit"])
                except: pass
                
                st.success(f"{len(df)} Events gefunden.")
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Event / Titel": st.column_config.TextColumn("Match", width="large"),
                        "Wettbewerb": st.column_config.TextColumn("Liga", width="medium"),
                    }
                )
            else:
                st.warning("Keine Daten extrahiert.")

# === ENTERTAINMENT ===
with tab_ent:
    if st.button("Lade Entertainment", key="btn_e"):
        with st.spinner("Suche Shows..."):
            
            today, tomorrow = get_dates()
            prompt = f"""
            Du bist ein TV-Guide. Nutze Google Search.
            Zeitraum: {today} und {tomorrow}.
            Thema: {LISTE_ENT}
            
            FORMAT-ANWEISUNG:
            DD.MM.YYYY | UHRZEIT | LAND | GENRE | TITEL | SENDER
            """
            
            raw_ent = query_gemini_with_search_safe(prompt)
            st.session_state['raw_ent'] = raw_ent
            
            df = smart_parser(raw_ent)
            
            if not df.empty:
                df.columns = ["Datum", "Uhrzeit", "Land", "Genre", "Titel", "Sender"]
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("Keine Shows gefunden.")

# === DEBUG ===
with tab_debug:
    st.write("Rohdaten:")
    if 'raw_foot' in st.session_state:
        with st.expander("Fußball Raw"): st.text(st.session_state['raw_foot'])
    if 'raw_mix' in st.session_state:
        with st.expander("Mix Sport Raw"): st.text(st.session_state['raw_mix'])
    if 'raw_ent' in st.session_state:
        with st.expander("Entertainment Raw"): st.text(st.session_state['raw_ent'])
