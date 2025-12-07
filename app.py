import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- KONFIGURATION ---
st.set_page_config(page_title="Minimal API TV Guide", page_icon="⚡️", layout="wide")

TSDB_KEY = "3" 
TSDB_BASE = f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}"

# Stark reduzierte Liste basierend auf den Vorgaben:
LEAGUE_IDS = {
    "🇩🇪 Bundesliga": "4331",
    "🇦🇹 Bundesliga": "4333",
    "🇬🇧 Premier League": "4328",
    "🇪🇸 La Liga": "4335",
    "🇮🇹 Serie A": "4337",
    "🏎️ Formel 1 (F1)": "4370",
    "🏍️ Moto GP": "4392",
    "🎿 Ski Alpin": "4403", 
    "🎯 Biathlon": "4410"
}

# --- DATUMSFUNKTIONEN ---

def get_dates():
    # Wir holen die Daten für heute und morgen
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    return today, tomorrow

# --- SPORT DATENABRUF ---

def fetch_sports_data():
    """Holt die nächsten 15 Events jeder Liga, filtert auf Heute/Morgen und verwendet API-Spalten."""
    today, tomorrow = get_dates()
    all_events = []
    
    st.info("ℹ️ Hinweis: Die Zeitangaben der API sind oft lokale Zeit des Events oder UTC.")
    progress_bar = st.progress(0)
    total_leagues = len(LEAGUE_IDS)
    
    for idx, (league_name, league_id) in enumerate(LEAGUE_IDS.items()):
        # Abfrage: Nächste Events der Liga (funktioniert gut mit dem Test-Key)
        url = f"{TSDB_BASE}/eventsnextleague.php?id={league_id}"
        
        try:
            r = requests.get(url, timeout=5)
            data = r.json()
            
            if data and "events" in data and data["events"]:
                for e in data["events"]:
                    event_date_str = e.get("dateEvent")
                    if not event_date_str: continue
                    
                    event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
                    
                    # Filterung auf Heute/Morgen
                    if event_date == today or event_date == tomorrow:
                        
                        # Wir verwenden direkt die API-Spalten (z.B. strEvent)
                        all_events.append({
                            "Datum": event_date.strftime("%d.%m.%Y"),
                            "Uhrzeit (API)": e.get("strTime", "00:00")[:5], 
                            "Sportart": e.get("strSport", "Sport"),
                            "Wettbewerb": league_name,
                            "Paarung / Titel": e.get("strEvent", e.get("strEventAlternate")),
                            "TV Sender (Int.)": e.get("strTVStation", "-")
                        })
        except Exception as err:
            st.warning(f"Fehler bei {league_name} (API nicht erreichbar).")
            
        progress_bar.progress((idx + 1) / total_leagues)

    progress_bar.empty()
    return pd.DataFrame(all_events)

# --- ENTERTAINMENT DATENABRUF ---

def fetch_tv_entertainment(country_code):
    """Holt das TV Schedule von TVMaze für heute"""
    today, _ = get_dates()
    today_str = today.strftime("%Y-%m-%d")
    
    # TVMaze API: Schedule für das gewählte Land
    url = f"https://api.tvmaze.com/schedule?country={country_code}&date={today_str}"
    
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status() # Löst HTTPError für 4xx/5xx Antworten aus
        data = r.json()
        
        show_list = []
        for item in data:
            show = item.get("show", {})
            
            # Wir verwenden die Spalten, die TVMaze liefert
            show_list.append({
                "Uhrzeit": item.get("airtime", "00:00"),
                "Sender": item.get("airing_on_channel", item.get("network", {}).get("name", "N/A")), # Versuch, Kanal zu finden
                "Titel der Show": show.get("name"),
                "Genre": ", ".join(show.get("genres", [])),
                "Typ": show.get("type", "-"),
                "Episode": item.get("name", "N/A")
            })
            
        return pd.DataFrame(show_list)
        
    except requests.exceptions.RequestException as e:
        st.error(f"Fehler bei TVMaze (Land '{country_code}'): Daten konnten nicht abgerufen werden.")
        st.caption(f"Details: {e}")
        return pd.DataFrame()

# --- FRONTEND ---

st.title("⚡️ API TV Guide (Minimal Scope)")
st.caption("Daten für heute, den {} | Sport von TheSportsDB, Entertainment von TVMaze".format(datetime.now().strftime("%d.%m.%Y")))

tab_sport, tab_ent = st.tabs(["⚽️ SPORT (Top Ligen)", "🎬 ENTERTAINMENT (Highlights)"])

# === SPORT TAB ===
with tab_sport:
    if st.button("Lade Sport-Daten (Echtzeit)", key="sport_btn"):
        with st.spinner("Frage Sport-Datenbank ab..."):
            df = fetch_sports_data()
            
            if not df.empty:
                df = df.sort_values(by=["Datum", "Uhrzeit (API)"])
                
                st.success(f"{len(df)} Events gefunden.")
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning("Keine Events für Heute/Morgen in den gewählten Top-Ligen gefunden.")

# === ENTERTAINMENT TAB ===
with tab_ent:
    col1, col2 = st.columns([1,3])
    with col1:
        # Länderauswahl für TVMaze
        country_code, country_name = st.selectbox("Land wählen", [
            ("DE", "Deutschland"),
            ("AT", "Österreich"),
            ("CH", "Schweiz"),
            ("US", "USA"), 
            ("GB", "Grossbritannien"), 
            ("JP", "Japan"),
            ("KR", "Südkorea")
        ], format_func=lambda x: x[1])
    
    with col2:
        st.write("") 
        st.write("")
        load_ent = st.button(f"Lade TV Programm für {country_name}", key="ent_btn")

    if load_ent:
        with st.spinner(f"Lade Programm für {country_name}..."):
            df_ent = fetch_tv_entertainment(country_code)
            
            if not df_ent.empty:
                
                # Wir filtern hier nur die Primetime (19:00 - 23:00)
                df_ent = df_ent[(df_ent["Uhrzeit"] >= "19:00") & (df_ent["Uhrzeit"] <= "23:59")]
                df_ent = df_ent.sort_values(by="Uhrzeit")
                
                st.subheader("📺 Shows & Highlights (Primetime)")
                st.dataframe(
                    df_ent,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning("Keine Daten für dieses Land gefunden oder es läuft nichts zur Primetime.")
