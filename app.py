import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import pytz
import time

# --- KONFIGURATION ---
st.set_page_config(page_title="Hybrid TV Guide", page_icon="⚽️", layout="wide")

# 1. API KEYS
FOOTBALL_DATA_KEY = "a1d1af300332400287c7765a19b34c01" # Dein Key

# Google API Key aus Secrets laden
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("⚠️ Google Gemini API Key fehlt in den Streamlit Secrets.")
    st.stop()

# 2. DEFINITIONEN
HEADERS = {'X-Auth-Token': FOOTBALL_DATA_KEY}
MEZ = pytz.timezone('Europe/Berlin')

LEAGUES = {
    "🇩🇪 Bundesliga": "BL1",
    "🇩🇪 2. Bundesliga": "BL2",
    "🇬🇧 Premier League": "PL",
    "🇪🇺 Champions League": "CL",
    "🇪🇸 La Liga": "PD",
    "🇮🇹 Serie A": "SA",
    "🇫🇷 Ligue 1": "FL1"
}

# --- FUNKTIONEN ---

def get_confirmed_matches():
    """
    Holt den Spielplan von football-data.org (Die 'Wahrheit').
    """
    today = datetime.now().strftime("%Y-%m-%d")
    next_days = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d") # Heute + Morgen
    
    all_matches_text = []
    
    # Progress Bar für API Abruf
    bar = st.progress(0, text="Hole offiziellen Spielplan...")
    
    for i, (name, code) in enumerate(LEAGUES.items()):
        url = f"https://api.football-data.org/v4/competitions/{code}/matches?dateFrom={today}&dateTo={next_days}"
        
        try:
            r = requests.get(url, headers=HEADERS, timeout=5)
            if r.status_code == 200:
                data = r.json()
                matches = data.get("matches", [])
                
                for m in matches:
                    # Zeit umrechnen
                    utc_dt = datetime.strptime(m["utcDate"], "%Y-%m-%dT%H:%M:%SZ")
                    mez_dt = utc_dt.replace(tzinfo=pytz.utc).astimezone(MEZ)
                    
                    if m["status"] in ["SCHEDULED", "TIMED", "IN_PLAY"]:
                        # Wir bauen einen String für die KI
                        match_str = f"{mez_dt.strftime('%d.%m. %H:%M')} | {name} | {m['homeTeam']['shortName']} vs {m['awayTeam']['shortName']}"
                        all_matches_text.append(match_str)
            else:
                print(f"Fehler bei {name}: {r.status_code}")
                
        except Exception as e:
            print(f"API Fehler: {e}")
        
        bar.progress((i + 1) / len(LEAGUES))
        
    bar.empty()
    return all_matches_text

def enrich_with_google(match_list_text):
    """
    Nimmt die Liste der Spiele und lässt Google die Sender suchen.
    """
    # Wir nehmen das Flash Modell (schnell & unterstützt Search)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Wir machen aus der Liste einen einzigen Textblock
    matches_context = "\n".join(match_list_text)
    
    prompt = f"""
    Du bist ein TV-Guide-Assistent. Ich gebe dir eine Liste von OFFIZIELL BESTÄTIGTEN Fußballspielen.
    
    DEINE AUFGABE:
    Nutze Google Search (Grounding), um für JEDES dieser Spiele herauszufinden, welcher TV-Sender (in Deutschland/Österreich) es überträgt.
    Suche nach: Sky, DAZN, Sat.1, Sport1, ORF, Amazon Prime, RTL.
    
    HIER IST DER SPIELPLAN (Ändere daran nichts, füge nur den Sender hinzu):
    {matches_context}
    
    FORMAT-ANWEISUNG:
    Gib mir eine Tabelle zurück. Trennzeichen: Pipe (|).
    Spalten: Datum/Zeit | Wettbewerb | Paarung | SENDER
    
    WICHTIG:
    - Wenn du keinen Sender findest, schreibe "-".
    - Gib NUR die Tabelle zurück.
    """
    
    try:
        response = model.generate_content(
            prompt,
            tools='google_search_retrieval'
        )
        return response.text
    except Exception as e:
        return f"Error bei Google Suche: {str(e)}"

def parse_final_table(raw_text):
    data = []
    lines = raw_text.split('\n')
    for line in lines:
        if "|" in line:
            parts = [p.strip() for p in line.split('|')]
            # Wir erwarten ca. 4 Spalten
            if len(parts) >= 4:
                # Header ignorieren
                if "Datum" in parts[0] or "---" in parts[0]: continue
                # Validierung: Beginnt mit Zahl (Datum)?
                if any(c.isdigit() for c in parts[0]):
                    data.append(parts[:4])
    
    if data:
        return pd.DataFrame(data, columns=["Datum/Zeit", "Liga", "Paarung", "TV Sender (Google Search)"])
    return None

# --- FRONTEND ---

st.title("⚽️ Smart TV Guide (API + AI)")
st.caption(f"Spielplan: football-data.org | TV-Recherche: Google Gemini Live-Suche")

if st.button("🚀 Live-Check starten", key="start"):
    
    # 1. API DATEN HOLEN
    match_list = get_confirmed_matches()
    
    if not match_list:
        st.warning("Keine Spiele für Heute/Morgen in den Top-Ligen gefunden (oder API Limit).")
    else:
        st.info(f"{len(match_list)} Spiele gefunden. Starte TV-Recherche via Google... (Dauer ca. 5-10 Sek)")
        
        # 2. GOOGLE RECHERCHE
        with st.spinner("Google sucht die Sender..."):
            raw_result = enrich_with_google(match_list)
            
            # 3. ANZEIGE
            df = parse_final_table(raw_result)
            
            if df is not None:
                st.success("Fertig!")
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.error("Formatierungsfehler. Hier ist der Rohtext:")
                st.text(raw_result)
