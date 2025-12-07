import streamlit as st
import google.generativeai as genai
import pandas as pd
from datetime import datetime, timedelta

# --- 1. SETUP ---
st.set_page_config(page_title="Ultimate TV Guide (Auto-Fix)", page_icon="📡", layout="wide")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("⚠️ API Key fehlt. Bitte in den Streamlit Secrets eintragen.")
    st.stop()

# --- 2. THE FIX: AUTOMATISCHE MODELL-ERKENNUNG ---
@st.cache_resource
def get_best_available_model():
    """
    Fragt die API nach verfügbaren Modellen und wählt das beste aus.
    Verhindert 404-Fehler durch falsche Namen.
    """
    try:
        # Wir fragen die API: "Was hast du?"
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        if not available_models:
            return None, "Keine Modelle gefunden."

        # Wir suchen bevorzugt nach Flash (schnell) oder Pro 1.5
        # Die API gibt Namen zurück wie "models/gemini-1.5-flash"
        chosen_model = None
        
        # Priorität 1: Flash 1.5
        for m in available_models:
            if "1.5-flash" in m:
                chosen_model = m
                break
        
        # Priorität 2: Pro 1.5
        if not chosen_model:
            for m in available_models:
                if "1.5-pro" in m:
                    chosen_model = m
                    break
                    
        # Fallback: Einfach das erste verfügbare nehmen
        if not chosen_model:
            chosen_model = available_models[0]
            
        return chosen_model, None

    except Exception as e:
        return None, str(e)

# --- 3. DATEN ABRUFEN ---

def get_live_data(prompt_topic, region_context="DACH (Deutschland, Österreich, Schweiz)"):
    
    # 1. Das richtige Modell holen
    model_name, error = get_best_available_model()
    
    if not model_name:
        return f"CRITICAL ERROR: {error}"
    
    # Modell initialisieren mit dem gefundenen Namen
    model = genai.GenerativeModel(model_name)
    
    today = datetime.now().strftime("%d.%m.%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
    
    full_prompt = f"""
    Du bist ein TV-Guide-Experte. Nutze Google Search (Grounding), um AKTUELLE ECHTZEIT-DATEN zu finden.
    Datum: HEUTE ({today}) und MORGEN ({tomorrow}).
    Region: {region_context}.
    
    AUFGABE:
    Recherchiere Sendezeiten und SENDER für: {prompt_topic}
    
    REGELN:
    1. Suche gezielt nach Sendern (Sky, DAZN, ORF, ARD/ZDF, RTL, Pro7).
    2. Formatierung als TABELLE mit Trennzeichen '|'.
    3. Spalten: DATUM | UHRZEIT | EVENT | SENDER
    4. Erfinde nichts. Wenn keine Daten da sind, schreibe "Keine Events".
    """
    
    try:
        # Versuch 1: MIT Google Suche (Grounding)
        response = model.generate_content(
            full_prompt,
            tools='google_search_retrieval'
        )
        return response.text
    except Exception as e:
        # Versuch 2: Ohne Google Suche (Fallback, falls Modell keine Tools unterstützt)
        try:
            fallback_prompt = full_prompt + "\n(Hinweis: Antworte basierend auf deinem Wissen, da Search nicht verfügbar ist.)"
            response = model.generate_content(fallback_prompt)
            return response.text + "\n\n⚠️ (Daten ohne Live-Suche generiert)"
        except Exception as e2:
            return f"API ERROR mit Modell '{model_name}': {str(e)}"

# --- 4. PARSER ---
def parse_to_dataframe(raw_text):
    if not raw_text: return None
    data = []
    lines = raw_text.split('\n')
    for line in lines:
        line = line.strip().replace("*", "")
        if "|" in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4:
                # Header ignorieren
                if "Datum" in parts[0] or "---" in parts[0]: continue
                # Datum Check
                if any(c.isdigit() for c in parts[0]):
                    while len(parts) < 4: parts.append("-")
                    data.append(parts[:4]) # Datum, Zeit, Event, Sender
    
    if data:
        return pd.DataFrame(data, columns=["Datum", "Uhrzeit", "Event / Titel", "Sender"])
    return None

# --- 5. FRONTEND ---

st.title("📺 Live TV Guide (Auto-Config)")

# Info Box welches Modell läuft
model_name, err = get_best_available_model()
if model_name:
    st.caption(f"✅ Verbunden mit: `{model_name}`")
else:
    st.error(f"❌ Keine Verbindung: {err}")
    st.stop()

tab_sport, tab_ent = st.tabs(["⚽️ SPORT", "🎬 ENTERTAINMENT"])

# === SPORT ===
with tab_sport:
    if st.button("Lade Sport (Live)", key="s"):
        with st.status("Lade Daten...", expanded=True):
            st.write("Suche Fußball...")
            # Einfacherer Prompt
            raw_foot = get_live_data("1. & 2. Bundesliga, Premier League, La Liga, Serie A")
            st.write("Suche Motorsport & US-Sport...")
            raw_mix = get_live_data("Formel 1, MotoGP, NFL, NBA")
            
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Fußball")
            df = parse_to_dataframe(raw_foot)
            if df is not None: st.dataframe(df, hide_index=True)
            else: st.markdown(raw_foot)
            
        with col2:
            st.subheader("Mix Sport")
            df = parse_to_dataframe(raw_mix)
            if df is not None: st.dataframe(df, hide_index=True)
            else: st.markdown(raw_mix)

# === ENTERTAINMENT ===
with tab_ent:
    region = st.selectbox("Region", ["Deutschland", "USA", "UK"])
    if st.button("Lade Entertainment", key="e"):
        with st.spinner("Suche Shows..."):
            raw_ent = get_live_data("Prime Time Shows (20:15), Reality TV, Musik", region_context=region)
            
            df = parse_to_dataframe(raw_ent)
            if df is not None:
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.markdown(raw_ent)
