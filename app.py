import streamlit as st
import google.generativeai as genai
import pandas as pd
from datetime import datetime, timedelta
import re
import time

# --- 1. SETUP ---
st.set_page_config(page_title="Global TV Guide", page_icon="📺", layout="wide")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("⚠️ API Key fehlt. Bitte in den Streamlit Secrets eintragen.")
    st.stop()

# --- 2. INHALT ---

LISTE_FUSSBALL = """
Suche den SPIELPLAN für HEUTE und MORGEN:
- Bundesliga (1. & 2.)
- Premier League
- La Liga, Serie A
- Ligue 1
"""

LISTE_MIX = """
Suche den ZEITPLAN für HEUTE und MORGEN:
- Ski Alpin & Biathlon (Weltcup)
- Formel 1 (falls Rennen ist)
- NFL, NBA, NHL
"""

LISTE_ENT = """
Suche das PRIMETIME TV-PROGRAMM (20:15) für HEUTE und MORGEN in DE, UK, US.
Fokus: Shows, Reality, Live-Events.
"""

# --- 3. LOGIK ---

def get_dates():
    # Einfache Zeitzonen-Korrektur (Server sind oft UTC, wir wollen MEZ grob simulieren)
    now = datetime.utcnow() + timedelta(hours=1) 
    return now.strftime("%d.%m.%Y"), (now + timedelta(days=1)).strftime("%d.%m.%Y")

def run_query_grounded(topic_prompt, mode="Sport"):
    """Nutzt Google Search und bittet um ein robustes Format"""
    today, tomorrow = get_dates()
    
    # Wir bitten um Pipe-Trennung (|), da das bei Search-Ergebnissen stabiler ist als CSV
    base_prompt = f"""
    Du bist ein TV-Guide Assistent. Nutze Google Search für aktuelle Daten.
    Datum heute: {today}. Zeitraum: {today} und {tomorrow}.
    
    AUFGABE:
    Recherchiere die Termine für: {topic_prompt}
    
    WICHTIG:
    - Suche nach echten Ansetzungen.
    - Uhrzeiten in MEZ (lokale deutsche Zeit).
    
    FORMAT-ANWEISUNG:
    Liste jedes Event in einer neuen Zeile genau so auf:
    DD.MM.YYYY | UHRZEIT | SPORTART | WETTBEWERB | EVENT/PAARUNG | SENDER
    
    Beispiel:
    06.12.2025 | 15:30 | Fussball | Bundesliga | Team A vs Team B | Sky
    
    Schreibe keine Einleitung, liste einfach die Events.
    """
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    try:
        # Wir aktivieren das Search Tool
        response = model.generate_content(
            base_prompt,
            tools='google_search_retrieval'
        )
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

def smart_parser(raw_text):
    """
    Sucht mit Regex nach Zeilen, die wie unser Format aussehen:
    Datum | Zeit | ...
    """
    if not raw_text or "Error" in raw_text:
        return pd.DataFrame()

    data = []
    
    # Regex Erklärung:
    # \d{2}\.\d{2}\.\d{4}  -> Findet Datum (06.12.2025)
    # \s*\|\s* -> Findet den Trennstrich mit Leerzeichen
    # \d{1,2}:\d{2}        -> Findet Uhrzeit (15:30 oder 9:00)
    # .* -> Nimmt den Rest der Zeile
    
    # Wir splitten den Text in Zeilen
    lines = raw_text.split('\n')
    
    for line in lines:
        # Bereinigen
        clean_line = line.strip().replace("*", "") # Markdown fett entfernen
        
        # Wir suchen einfach nach dem Trennzeichen "|", das ist am sichersten
        parts = clean_line.split('|')
        
        if len(parts) >= 5:
            # Check: Ist der erste Teil ein Datum?
            part0 = parts[0].strip()
            # Einfacher Check: Hat es Punkte und Zahlen?
            if "." in part0 and any(c.isdigit() for c in part0):
                
                # Wir bauen die Zeile sauber zusammen
                row = [p.strip() for p in parts]
                
                # Wenn Sender fehlt, füllen wir auf
                while len(row) < 6: row.append("n.a.")
                
                # Wir nehmen nur die ersten 6 Spalten
                data.append(row[:6])

    if data:
        cols = ["Datum", "Uhrzeit", "Sportart", "Wettbewerb", "Event / Titel", "Sender"]
        return pd.DataFrame(data, columns=cols)
    else:
        return pd.DataFrame()

# --- 4. FRONTEND ---

st.title("🌍 Live TV Guide (Grounding V2)")
st.caption(f"Datum: {get_dates()[0]} | Methode: Google Search + Smart Regex")

tab_sport, tab_ent, tab_debug = st.tabs(["⚽️ SPORT", "🎤 ENTERTAINMENT", "⚙️ DEBUG"])

# === SPORT ===
with tab_sport:
    if st.button("Lade Sport (Live)", key="btn_s"):
        with st.spinner("Recherchiere im Web... (Das dauert ca. 5-10 Sek)"):
            
            # Abfrage
            raw_foot = run_query_grounded(LISTE_FUSSBALL)
            raw_mix = run_query_grounded(LISTE_MIX)
            
            # Debug speichern
            st.session_state['raw_foot'] = raw_foot
            st.session_state['raw_mix'] = raw_mix
            
            # Parsen
            df = smart_parser(raw_foot + "\n" + raw_mix)
            
            if not df.empty:
                # Sortieren versuchen
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
                st.error("Keine Events extrahiert.")
                st.info("Das bedeutet: Google Search hat Text geliefert, aber unser Parser hat die Struktur nicht erkannt. Schau in den DEBUG Tab!")

# === ENTERTAINMENT ===
with tab_ent:
    if st.button("Lade Entertainment (Live)", key="btn_e"):
        with st.spinner("Recherchiere Shows..."):
            raw_ent = run_query_grounded(LISTE_ENT)
            st.session_state['raw_ent'] = raw_ent
            
            df = smart_parser(raw_ent)
            
            if not df.empty:
                df.columns = ["Datum", "Uhrzeit", "Land", "Genre", "Titel", "Sender"]
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("Keine Shows gefunden.")

# === DEBUG ===
with tab_debug:
    st.write("Hier ist der Rohtext, den Google geliefert hat:")
    if 'raw_foot' in st.session_state:
        with st.expander("Fußball Raw"): st.text(st.session_state['raw_foot'])
    if 'raw_mix' in st.session_state:
        with st.expander("Mix Sport Raw"): st.text(st.session_state['raw_mix'])
    if 'raw_ent' in st.session_state:
        with st.expander("Entertainment Raw"): st.text(st.session_state['raw_ent'])
