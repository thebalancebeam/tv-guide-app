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

# --- 2. DIE LÖSUNG: DYNAMISCHE MODELL-SUCHE ---
@st.cache_resource
def get_working_model():
    """
    Fragt Google: 'Welche Modelle hast du für mich?'
    und nimmt das erste, das Text generieren kann.
    """
    status_text = []
    try:
        # Wir fragen die API direkt nach der Liste
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        if not available_models:
            return None, "Keine Modelle gefunden. API Key prüfen."

        # Wir suchen bevorzugt nach Flash oder Pro
        chosen_model = None
        
        # Priorität 1: Flash (schnell)
        for m in available_models:
            if "flash" in m:
                chosen_model = m
                break
        
        # Priorität 2: Pro (stark)
        if not chosen_model:
            for m in available_models:
                if "pro" in m:
                    chosen_model = m
                    break
        
        # Fallback: Einfach das erste nehmen
        if not chosen_model:
            chosen_model = available_models[0]
            
        return genai.GenerativeModel(chosen_model), f"✅ Verbunden mit: {chosen_model}"

    except Exception as e:
        return None, f"❌ Kritischer Fehler bei Modellsuche: {str(e)}"

# Modell initialisieren
model, model_status = get_working_model()

# --- 3. INHALTS-DEFINITIONEN ---

LISTE_FUSSBALL = """
DEUTSCHLAND: 1. & 2. Bundesliga, DFB Pokal.
ÖSTERREICH: 1. & 2. Bundesliga, ÖFB Pokal.
ENGLAND: Premier League, Championship, FA Cup.
EUROPA: La Liga, Serie A, Ligue 1, Champions League, Europa League.
"""

LISTE_MIX = """
TENNIS: Grand Slams & ATP.
WINTER: Ski Alpin, Biathlon.
MOTOR: Formel 1, MotoGP.
US-SPORT: NFL, NBA, NHL.
"""

LISTE_ENT = "UK, Deutschland, USA (Shows, Musik, Reality)"

# --- 4. HILFSFUNKTIONEN ---

def get_dates():
    now = datetime.now()
    return now.strftime("%d.%m.%Y"), (now + timedelta(days=1)).strftime("%d.%m.%Y")

def robust_parse(raw_text_list):
    all_data = []
    for raw_text in raw_text_list:
        if not raw_text or "Error" in raw_text: continue
        clean_text = raw_text.replace("```csv", "").replace("```", "").strip()
        lines = clean_text.split('\n')
        for line in lines:
            if not line.strip(): continue
            parts = line.split(';')
            if len(parts) >= 4 and len(parts[0]) > 0 and any(c.isdigit() for c in parts[0]):
                clean_parts = [p.strip() for p in parts]
                while len(clean_parts) < 6: clean_parts.append("-")
                all_data.append(clean_parts[:6])
                
    if all_data:
        cols = ["Datum", "Uhrzeit", "Sportart", "Wettbewerb", "Event", "Sender"]
        return pd.DataFrame(all_data, columns=cols)
    else:
        return pd.DataFrame()

def run_query(prompt_context, mode="Sport"):
    if not model:
        return "Error: Kein Modell verfügbar."
    
    today, tomorrow = get_dates()
    
    if mode == "Sport":
        prompt = f"""
        Rolle: TV-Datenbank. Zeitraum: {today} und {tomorrow}.
        AUFGABE: Suche Live-Events für: {prompt_context}
        FORMAT: NUR CSV (Semikolon getrennt).
        Spalten: Datum;Uhrzeit;Sportart;Wettbewerb;Heim vs Gast;Sender
        """
    else:
        prompt = f"""
        Rolle: TV-Guide. Zeitraum: {today} und {tomorrow}.
        Länder: {prompt_context}. Suche: Prime-Time Shows, Reality.
        FORMAT: NUR CSV (Semikolon getrennt).
        Spalten: Datum;Uhrzeit;Land;Genre;Titel;Sender
        """
        
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# --- 5. FRONTEND ---

st.title("🌍 Mein TV Planer")
st.caption(model_status) # Zeigt oben an, welches Modell gefunden wurde!

if not model:
    st.error("Die App konnte keine Verbindung zu Google herstellen. Siehe Status oben.")
    st.stop()

tab_sport, tab_ent, tab_debug = st.tabs(["⚽️ SPORT", "🎤 ENTERTAINMENT", "⚙️ DEBUG"])

# === SPORT ===
with tab_sport:
    if st.button("Lade Sport", key="btn_sport"):
        with st.spinner("Lade Daten..."):
            raw_foot = run_query(LISTE_FUSSBALL, "Sport")
            time.sleep(1)
            raw_mix = run_query(LISTE_MIX, "Sport")
            
            st.session_state['d_foot'] = raw_foot
            st.session_state['d_mix'] = raw_mix
            
            df = robust_parse([raw_foot, raw_mix])
            
            if not df.empty:
                try: df = df.sort_values(by=["Datum", "Uhrzeit"])
                except: pass
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("Keine Daten gefunden.")

# === ENTERTAINMENT ===
with tab_ent:
    if st.button("Lade Entertainment", key="btn_ent"):
        with st.spinner("Lade Shows..."):
            raw_ent = run_query(LISTE_ENT, "Ent")
            st.session_state['d_ent'] = raw_ent
            
            df = robust_parse([raw_ent])
            if not df.empty:
                df.columns = ["Datum", "Uhrzeit", "Land", "Genre", "Titel", "Sender"]
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("Keine Daten gefunden.")

# === DEBUG ===
with tab_debug:
    if 'd_foot' in st.session_state: st.text(st.session_state['d_foot'])
    if 'd_mix' in st.session_state: st.text(st.session_state['d_mix'])
    if 'd_ent' in st.session_state: st.text(st.session_state['d_ent'])
