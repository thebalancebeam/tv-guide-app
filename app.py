import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- KONFIGURATION ---
st.set_page_config(page_title="API TV Guide (Reduced Scope)", page_icon="📡", layout="wide")

# TheSportsDB Test Key
TSDB_KEY = "3" 
TSDB_BASE = f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}"

# REDUZIERTE LEAGUE MAPPING
# Wir fokussieren uns auf die Top-Ligen (die besten Datenqualität haben)
LEAGUE_IDS = {
    "🇩🇪 Bundesliga": "4331",
    "🇦🇹 Bundesliga": "4333",
    "🇬🇧 Premier League": "4328",
    "🇪🇸 La Liga": "4335",
    "🇮🇹 Serie A": "4337",
    "🏎️ Motorsport (F1)": "4370"
}

# TVMaze Country Codes
COUNTRY_CODES = [
    ("DE", "Deutschland"), 
    ("AT", "Österreich"), 
    ("CH", "Schweiz"),
    ("US", "USA"), 
    ("GB", "Grossbritannien"),
    ("JP", "Japan"),
    ("KR", "Südkorea")
]

# --- FUNKTIONEN ---

def get_dates():
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    return today, tomorrow

## API SPORT DATEN FUNKTION
def fetch_sports_data():
    """Holt die nächsten 15 Events jeder Liga und filtert auf Heute/Morgen"""
    today, tomorrow = get_dates()
    all_events = []
    
    progress_bar = st.progress(0)
    total_leagues = len(LEAGUE_IDS)
    
    for idx, (league_name, league_id) in enumerate(LEAGUE_IDS.items()):
        url = f"{TSDB_BASE}/eventsnextleague.php?id={league_id}"
        
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status() # Raise exception for bad status codes
            data = r.json()
            
            if data.get("events"):
                for e in data["events"]:
                    event_date_str = e.get("dateEvent")
                    if not event_date_str: continue
                    
                    event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
                    
                    if event_date == today or event_date == tomorrow:
                        
                        # API-BASIERTE SPALTEN
                        all_events.append({
                            "Datum": event_date.strftime("%d.%m.%Y"),
                            "Uhrzeit (MEZ)": e.get("strTime", "00:00")[:5],
                            "Sport": e.get("strSport", "Fußball"),
                            "Wettbewerb": league_name,
                            "Match / Event": e.get("strEvent", "n.a."),
                            "Heim": e.get("strHomeTeam", "-"),
                            "Gast": e.get("strAwayTeam", "-"),
                            "TV Sender (Int.)": e.get("strTVStation", "-")
                        })
        except requests.exceptions.RequestException as err:
            st.error(f"Fehler bei API-Abruf für {league_name}: {err}")
            
        progress_bar.progress((idx + 1) / total_leagues)

    progress_bar.empty()
    return pd.DataFrame(all_events)

## API ENTERTAINMENT DATEN FUNKTION
def fetch_tv_entertainment(country_code):
    """Holt TV Schedule von TVMaze (Offene API)"""
    today, _ = get_dates() 
    today_str = today.strftime("%Y-%m-%d")
    
    url = f"https://api.tvmaze.com/schedule?country={country_code}&date={today_str}"
    
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        
        show_list = []
        for item in data:
            show = item.get("show", {})
            
            # API-BASIERTE SPALTEN
            show_list.append({
                "Uhrzeit": item.get("airtime", "00:00"),
                "Sender": item.get("network", {}).get("name", "n.a."),
                "Land": country_code,
                "Show Titel": show.get("name"),
                "Episoden Titel": item.get("name", "n.a."),
                "Genre": ", ".join(show.get("genres", ["n.a."])),
                "Typ": show.get("type", "n.a.")
            })
            
        return pd.DataFrame(show_list)
        
    except requests.exceptions.RequestException as e:
        st.error(f"Fehler bei TVMaze API-Abruf für {country_code}: {e}")
        return pd.DataFrame()

# --- FRONTEND ---

st.title("📡 API-Basierter TV Guide")
st.caption("Datenquelle: TheSportsDB (Sport) & TVMaze (Entertainment)")

tab_sport, tab_ent = st.tabs(["⚽️ SPORT (Top Ligen)", "🎬 ENTERTAINMENT"])

# === SPORT TAB ===
with tab_sport:
    st.subheader("Fokus: Top-Fußball-Ligen & Formel 1")
    st.info("⚠️ Wintersport und allgemeine Highlights sind in dieser Sport-API (TheSportsDB) nicht verlässlich abgebildet. Wir fokussieren uns auf strukturierte Ligen.")
    
    if st.button("Lade Sport-Daten", key="sport_btn"):
        with st.spinner("Frage Sport-Datenbank ab..."):
            df = fetch_sports_data()
            
            if not df.empty:
                # Sortieren
                df = df.sort_values(by=["Datum", "Uhrzeit (MEZ)"])
                
                st.success(f"{len(df)} Live-Events für heute & morgen gefunden.")
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning("Keine Spiele für Heute/Morgen in den gewählten Top-Ligen gefunden.")

# ---
# === ENTERTAINMENT TAB ===
with tab_ent:
    st.subheader("Globale Shows & Programm-Highlights")
    col1, col2 = st.columns([1,3])
    
    with col1:
        # Länderauswahl
        selected_country = st.selectbox(
            "Programm für Land wählen", 
            COUNTRY_CODES, 
            format_func=lambda x: f"{x[1]} ({x[0]})"
        )
    
    with col2:
        st.write("") 
        st.write("")
        load_ent = st.button("Lade TV Programm", key="ent_btn")

    if load_ent:
        with st.spinner(f"Lade Programm für {selected_country[1]}..."):
            df_ent = fetch_tv_entertainment(selected_country[0])
            
            if not df_ent.empty:
                st.subheader(f"Highlights in {selected_country[1]} am {get_dates()[0].strftime('%d.%m.')}")
                
                # Filter auf Uhrzeit (ab 18:00 für Primetime)
                df_ent_prime = df_ent[df_ent["Uhrzeit"] >= "18:00"].copy()
                df_ent_prime = df_ent_prime.sort_values(by="Uhrzeit")
                
                # Wir filtern die Spalten, um nur die relevantesten zu zeigen
                display_cols = ["Uhrzeit", "Sender", "Show Titel", "Episoden Titel", "Genre", "Typ"]
                
                st.dataframe(
                    df_ent_prime[display_cols],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning(f"Keine Programm-Daten für {selected_country[1]} gefunden.")
