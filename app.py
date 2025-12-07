import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import pytz

# --- KONFIGURATION ---
st.set_page_config(page_title="Ultimate TV Guide", page_icon="📺", layout="wide")

# 1. API KEYS
FOOTBALL_DATA_KEY = "a1d1af300332400287c7765a19b34c01"

# Google API Key
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

# --- FUNKTION 1: MODELL-FIX (Gegen den 404 Fehler) ---
@st.cache_resource
def get_working_model():
    """
    Sucht automatisch den richtigen Modellnamen für deinen Key.
    """
    try:
        # Wir fragen Google: "Welche Modelle gibt es?"
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                # Wir suchen nach Flash oder Pro
                if 'flash' in m.name: return m.name
                if 'pro' in m.name: return m.name
        
        # Fallback
        return "models/gemini-1.5-flash"
    except:
        return "gemini-1.5-flash"

# --- FUNKTION 2: SPORT API (Die Wahrheit) ---
def get_confirmed_matches():
    today = datetime.now().strftime("%Y-%m-%d")
    next_days = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    all_matches_text = []
    
    for name, code in LEAGUES.items():
        url = f"https://api.football-data.org/v4/competitions/{code}/matches?dateFrom={today}&dateTo={next_days}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=5)
            if r.status_code == 200:
                data = r.json()
                for m in data.get("matches", []):
                    # UTC zu MEZ
                    utc_dt = datetime.strptime(m["utcDate"], "%Y-%m-%dT%H:%M:%SZ")
                    mez_dt = utc_dt.replace(tzinfo=pytz.utc).astimezone(MEZ)
                    
                    if m["status"] in ["SCHEDULED", "TIMED", "IN_PLAY"]:
                        match_str = f"{mez_dt.strftime('%d.%m. %H:%M')} | {name} | {m['homeTeam']['shortName']} vs {m['awayTeam']['shortName']}"
                        all_matches_text.append(match_str)
        except:
            continue
    return all_matches_text

# --- FUNKTION 3: KI RECHERCHE (TV Sender) ---
def enrich_with_google(match_list_text):
    # Hier nutzen wir den fixierten Modellnamen
    model_name = get_working_model()
    model = genai.GenerativeModel(model_name)
    
    matches_context = "\n".join(match_list_text)
    
    prompt = f"""
    Du bist ein TV-Guide. Hier ist der OFFIZIELLE SPIELPLAN:
    {matches_context}
    
    AUFGABE:
    Nutze Google Search (Grounding), um für diese Spiele den TV-SENDER in Deutschland/Österreich zu finden (Sky, DAZN, Sat.1, RTL, Amazon).
    
    FORMAT:
    Gib mir eine Tabelle zurück (Trennzeichen |).
    Spalten: Datum/Zeit | Wettbewerb | Paarung | SENDER
    Wenn kein Sender auffindbar: "-"
    """
    
    try:
        response = model.generate_content(prompt, tools='google_search_retrieval')
        return response.text
    except:
        # Fallback ohne Tools
        try:
            return model.generate_content(prompt).text
        except Exception as e:
            return f"Error: {str(e)}"

# --- FUNKTION 4: ENTERTAINMENT (TVMaze API) ---
def fetch_entertainment_24h(country_code):
    now = datetime.now(MEZ)
    end_time = now + timedelta(hours=24)
    dates = [now.date(), (now + timedelta(days=1)).date()]
    dates = sorted(list(set(dates)))
    
    all_shows = []
    
    for d in dates:
        url = f"https://api.tvmaze.com/schedule?country={country_code}&date={d}"
        try:
            r = requests.get(url, timeout=4)
            if r.status_code == 200:
                for item in r.json():
                    # Zeit konvertieren
                    try:
                        show_dt = datetime.fromisoformat(item.get("airstamp")).astimezone(MEZ)
                    except:
                        continue
                        
                    if now <= show_dt <= end_time:
                        show = item.get("show", {})
                        stype = show.get("type", "Unknown")
                        
                        # Filter für Entertainment
                        if stype in ["Reality", "Game Show", "Variety", "Talk Show", "Award Show", "Talent"]:
                            net = show.get("network")
                            sender = net.get("name") if net else "Web"
                            
                            all_shows.append({
                                "Uhrzeit": show_dt.strftime("%H:%M"),
                                "Sender": sender,
                                "Titel": show.get("name"),
                                "Typ": stype
                            })
        except:
            continue
            
    return pd.DataFrame(all_shows)

def parse_sport_table(raw_text):
    data = []
    lines = raw_text.split('\n')
    for line in lines:
        if "|" in line and "Datum" not in line and "---" not in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4 and any(c.isdigit() for c in parts[0]):
                data.append(parts[:4])
    return pd.DataFrame(data, columns=["Zeit", "Liga", "Paarung", "Sender"]) if data else None

# --- FRONTEND ---
st.title("📺 Hybrid TV Guide")
st.caption(f"Sport: API + AI | Entertainment: TVMaze API | Zeit: {datetime.now(MEZ).strftime('%H:%M')}")

tab_sport, tab_ent = st.tabs(["⚽️ SPORT (Live)", "🎬 ENTERTAINMENT (24h)"])

# === SPORT TAB ===
with tab_sport:
    if st.button("Lade Sport (API + Google Check)", key="s"):
        
        # 1. API
        with st.status("Hole offiziellen Spielplan (Football-Data)...", expanded=True) as status:
            matches = get_confirmed_matches()
            if not matches:
                status.update(label="Keine Spiele gefunden (API leer/Limit).", state="error")
            else:
                status.update(label=f"{len(matches)} Spiele gefunden! Suche TV-Sender...", state="running")
                
                # 2. AI
                raw_result = enrich_with_google(matches)
                status.update(label="Fertig!", state="complete", expanded=False)
                
                df = parse_sport_table(raw_result)
                if df is not None:
                    st.success(f"{len(df)} Live-Übertragungen.")
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.text(raw_result)

# === ENTERTAINMENT TAB ===
with tab_ent:
    country = st.selectbox("Land", ["DE", "US", "GB", "AT"])
    if st.button("Lade 24h Programm", key="e"):
        with st.spinner("Lade TVMaze API..."):
            df = fetch_entertainment_24h(country)
            if not df.empty:
                df = df.sort_values("Uhrzeit")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("Keine passenden Shows in den nächsten 24h.")
