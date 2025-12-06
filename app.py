import streamlit as st
import google.generativeai as genai
import pandas as pd
from datetime import datetime, timedelta
import io
import time

# --- 1. SETUP ---
st.set_page_config(page_title="Global TV Guide", page_icon="🌍", layout="wide")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("⚠️ API Key fehlt. Bitte in den Streamlit Secrets eintragen.")
    st.stop()

# --- 2. MODELL-SUCHE ---
@st.cache_resource
def get_model():
    # Wir nehmen Flash, da es schnell ist und Search Grounding unterstützt
    # Wir definieren das Modell hier, aber das Tool aktivieren wir beim Aufruf
    return genai.GenerativeModel('gemini-1.5-flash')

# --- 3. INHALTS-DEFINITIONEN ---

LISTE_FUSSBALL = """
Suche den exakten Spielplan für HEUTE und MORGEN für:
DEUTSCHLAND: 1. Bundesliga, 2. Bundesliga.
ENGLAND: Premier League, Championship.
EUROPA: La Liga (Spanien), Serie A (Italien), Ligue 1 (Frankreich).
"""

LISTE_MIX = """
Suche den exakten Zeitplan für HEUTE und MORGEN für:
WINTERSPORT: Ski Alpin Weltcup, Biathlon Weltcup (Orte & Zeiten).
MOTORSPORT: Formel 1 (Nur wenn Rennwochenende ist), MotoGP.
US-SPORT: NFL, NBA, NHL (Nur Spiele, die in MEZ heute/morgen laufen).
"""

LISTE_ENT = """
Suche das TV-Programm (Prime Time 20:15) für HEUTE und MORGEN in Deutschland, UK und USA.
Fokus: Große Shows, Live-Events, Reality-TV Highlights.
"""

# --- 4. HILFSFUNKTIONEN ---

def get_dates():
    now = datetime.now()
    return now.strftime("%d.%m.%Y"), (now + timedelta(days=1)).strftime("%d.%m.%Y")

def robust_parse(raw_text_list):
    all_data = []
    for raw_text in raw_text_list:
        if not raw_text or "Error" in raw_text: continue
        
        # Markdown entfernen
        clean_text = raw_text.replace("```csv", "").replace("```", "").strip()
        lines = clean_text.split('\n')
        
        for line in lines:
            if not line.strip(): continue
            parts = line.split(';')
            
            # Wir akzeptieren Zeilen, die wie Daten aussehen (mind. 4 Spalten)
            if len(parts) >= 4:
                # Datum-Check (erste Spalte sollte Zahl enthalten)
                if len(parts[0]) > 0 and any(c.isdigit() for c in parts[0]):
                    clean_parts = [p.strip() for p in parts]
                    # Auffüllen auf 6 Spalten falls Sender fehlt
                    while len(clean_parts) < 6: clean_parts.append("-")
                    all_data.append(clean_parts[:6])
                
    if all_data:
        cols = ["Datum", "Uhrzeit", "Sportart", "Wettbewerb", "Event / Match", "Sender"]
        return pd.DataFrame(all_data, columns=cols)
    else:
        return pd.DataFrame()

def run_query_with_search(prompt_context, mode="Sport"):
    model = get_model()
    today, tomorrow = get_dates()
    
    # Der Prompt zwingt die KI jetzt zur Recherche
    base_prompt = f"""
    Du bist ein Echtzeit-TV-Guide. Nutze Google Search, um die aktuellen Daten zu finden.
    Datum heute: {today}. Zeitraum: {today} und {tomorrow}.
    
    AUFGABE:
    Recherchiere die genauen Ansetzungen und TV-Sender für:
    {prompt_context}
    
    WICHTIGSTE REGEL: 
    - Nenne NUR Events, die wirklich heute oder morgen stattfinden.
    - Wenn eine Liga pausiert (z.B. Winterpause), lass sie weg. Erfinde NICHTS.
    - Uhrzeiten zwingend in MEZ.
    
    FORMAT:
    Gib mir das Ergebnis NUR als CSV (Semikolon getrennt).
    Spalten: Datum;Uhrzeit;Sportart;Wettbewerb;Heim vs Gast (oder Titel);Sender
    """
    
    try:
        # HIER IST DER FIX: tools='google_search_retrieval'
        # Das zwingt Gemini, im Internet nachzusehen!
        response = model.generate_content(
            base_prompt,
            tools='google_search_retrieval'
        )
        return response.text
    except Exception as e:
        # Fallback, falls Search Tool nicht verfügbar ist (passiert bei manchen Keys)
        return f"Error: {str(e)}"

# --- 5. FRONTEND ---

st.title("🌍 Mein Live TV Planer (Echtzeit)")
st.caption(f"Datenabruf via Google Search Grounding | {get_dates()[0]}")

tab_sport, tab_ent, tab_debug = st.tabs(["⚽️ SPORT", "🎤 ENTERTAINMENT", "⚙️ DEBUG"])

# === SPORT ===
with tab_sport:
    if st.button("Lade Sport (Live Check)", key="btn_sport"):
        with st.spinner("Recherchiere im Internet nach aktuellen Spielen..."):
            
            # 1. Fußball
            raw_foot = run_query_with_search(LISTE_FUSSBALL, "Sport")
            # 2. Mix
            raw_mix = run_query_with_search(LISTE_MIX, "Sport")
            
            st.session_state['df_foot'] = raw_foot
            st.session_state['df_mix'] = raw_mix
            
            df = robust_parse([raw_foot, raw_mix])
            
            if not df.empty:
                # Sortieren
                try: df = df.sort_values(by=["Datum", "Uhrzeit"])
                except: pass
                
                st.success(f"{len(df)} bestätigte Live-Events gefunden.")
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
                st.warning("Keine Events gefunden. (Oder die Google Suche war nicht erreichbar).")
                st.info("Tipp: Wenn hier nichts steht, findet Google für heute keine Spiele in den genannten Ligen.")

# === ENTERTAINMENT ===
with tab_ent:
    if st.button("Lade Entertainment (Live Check)", key="btn_ent"):
        with st.spinner("Recherchiere TV-Programm..."):
            raw_ent = run_query_with_search(LISTE_ENT, "Ent")
            st.session_state['df_ent'] = raw_ent
            
            df = robust_parse([raw_ent])
            
            if not df.empty:
                df.columns = ["Datum", "Uhrzeit", "Land", "Genre", "Titel", "Sender"]
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("Keine Daten gefunden.")

# === DEBUG ===
with tab_debug:
    st.write("Rohdaten der KI (mit Search Grounding):")
    if 'df_foot' in st.session_state: st.text(st.session_state['df_foot'])
    if 'df_mix' in st.session_state: st.text(st.session_state['df_mix'])
    if 'df_ent' in st.session_state: st.text(st.session_state['df_ent'])
