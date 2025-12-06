import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- KONFIGURATION ---
st.set_page_config(page_title="API TV Guide", page_icon="📡", layout="wide")

# TheSportsDB nutzt "3" als öffentlichen Test-Key für Entwickler.
# Falls der mal nicht geht, müsste man einen eigenen holen (Patreon), aber meistens läuft er.
TSDB_KEY = "3" 
TSDB_BASE = f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}"

# Mapping: Welche Ligen willst du sehen? (ID kommt von TheSportsDB)
LEAGUE_IDS = {
    "🇩🇪 Bundesliga": "4331",
    "🇩🇪 2. Bundesliga": "4332",
    "🇬🇧 Premier League": "4328",
    "🇪🇸 La Liga": "4335",
    "🇮🇹 Serie A": "4332", # Achtung: Serie A ID checken, oft 4335/4332 varriert
    "🇮🇹 Serie A (Correct)": "4337",
    "🇫🇷 Ligue 1": "4334",
    "🇪🇺 Champions League": "4480",
    "🇺🇸 NFL": "4391",
    "🇺🇸 NBA": "4387",
    "🇺🇸 NHL": "4380",
    "🏎️ Formel 1": "4370"
}

# --- FUNKTIONEN ---

def get_dates():
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    return today, tomorrow

def fetch_sports_data():
    """Holt die nächsten 15 Events jeder Liga und filtert auf Heute/Morgen"""
    today, tomorrow = get_dates()
    all_events = []
    
    progress_bar = st.progress(0)
    total_leagues = len(LEAGUE_IDS)
    
    for idx, (league_name, league_id) in enumerate(LEAGUE_IDS.items()):
        # API: Next 15 events for league
        url = f"{TSDB_BASE}/eventsnextleague.php?id={league_id}"
        
        try:
            r = requests.get(url, timeout=5)
            data = r.json()
            
            if data and "events" in data and data["events"]:
                for e in data["events"]:
                    event_date_str = e.get("dateEvent")
                    if not event_date_str: continue
                    
                    # Datum parsen (YYYY-MM-DD)
                    event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
                    
                    # FILTER: Nur Heute und Morgen
                    if event_date == today or event_date == tomorrow:
                        
                        # Zeit formatieren (kommt oft als UTC oder lokale Zeit)
                        time_str = e.get("strTime", "00:00")[:5] # Nur HH:MM
                        
                        # TV Sender extrahieren (TheSportsDB liefert das manchmal)
                        # Falls leer, schreiben wir "-"
                        channels = e.get("strTVStation")
                        if not channels: channels = "-"
                        
                        all_events.append({
                            "Datum": event_date.strftime("%d.%m.%Y"),
                            "Uhrzeit": time_str,
                            "Sportart": e.get("strSport", "Sport"),
                            "Wettbewerb": league_name,
                            "Match / Event": e.get("strEvent", e.get("strEventAlternate")),
                            "Sender (Int.)": channels
                        })
        except Exception as err:
            print(f"Fehler bei {league_name}: {err}")
            
        # Update Progress
        progress_bar.progress((idx + 1) / total_leagues)

    progress_bar.empty()
    return pd.DataFrame(all_events)

def fetch_tv_entertainment(country_code):
    """Holt TV Schedule von TVMaze (Offene API)"""
    today, _ = get_dates() # TVMaze erlaubt oft nur den aktuellen Tag im Free Tier Batch
    today_str = today.strftime("%Y-%m-%d")
    
    url = f"https://api.tvmaze.com/schedule?country={country_code}&date={today_str}"
    
    try:
        r = requests.get(url, timeout=5)
        data = r.json()
        
        show_list = []
        for item in data:
            show = item.get("show", {})
            # Filter: Wir wollen nur Primetime oder populäre Sachen (grob gefiltert)
            
            # Genres prüfen
            genres = show.get("genres", [])
            # Wir schließen Kinderprogramm oder reines Drama aus, wenn gewünscht, 
            # aber hier nehmen wir erstmal alles und filtern später im UI.
            
            show_list.append({
                "Uhrzeit": item.get("airtime", "00:00"),
                "Sender": show.get("network", {}).get("name", "Web"),
                "Titel": show.get("name"),
                "Episode": item.get("name"),
                "Genre": ", ".join(genres),
                "Typ": show.get("type", "Scripted")
            })
            
        return pd.DataFrame(show_list)
        
    except Exception as e:
        st.error(f"Fehler bei TVMaze: {e}")
        return pd.DataFrame()

# --- FRONTEND ---

st.title("📡 Live Data TV Guide")
st.caption("Datenquelle: TheSportsDB (Sport) & TVMaze (Entertainment)")

tab_sport, tab_ent = st.tabs(["⚽️ SPORT (API)", "🎬 ENTERTAINMENT (API)"])

# === SPORT TAB ===
with tab_sport:
    if st.button("Lade Sport-Daten (Echtzeit)", key="sport_btn"):
        with st.spinner("Frage Sport-Datenbank ab..."):
            df = fetch_sports_data()
            
            if not df.empty:
                # Sortieren
                df = df.sort_values(by=["Datum", "Uhrzeit"])
                
                st.success(f"{len(df)} Live-Events für heute & morgen gefunden.")
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Match / Event": st.column_config.TextColumn("Paarung", width="large"),
                        "Sender (Int.)": st.column_config.TextColumn("TV Info", width="medium"),
                    }
                )
            else:
                st.warning("Keine Spiele für Heute/Morgen in den gewählten Ligen gefunden.")
                st.info("Hinweis: Es kann sein, dass in diesen Ligen gerade Spielpause ist oder der Test-API-Key limitiert wurde.")

# === ENTERTAINMENT TAB ===
with tab_ent:
    col1, col2 = st.columns([1,3])
    with col1:
        # Länderauswahl für TVMaze
        country = st.selectbox("Land wählen", [
            ("US", "USA"), 
            ("GB", "Grossbritannien"), 
            ("DE", "Deutschland"),
            ("FR", "Frankreich"),
            ("JP", "Japan"),
            ("KR", "Südkorea")
        ], format_func=lambda x: x[1])
    
    with col2:
        st.write("") # Spacer
        st.write("")
        load_ent = st.button("Lade TV Programm", key="ent_btn")

    if load_ent:
        with st.spinner(f"Lade Programm für {country[1]}..."):
            df_ent = fetch_tv_entertainment(country[0])
            
            if not df_ent.empty:
                # Filter-Logik: Wir wollen eher "Reality", "Game Show" etc.
                # TVMaze liefert "Scripted" (Serien) und "Reality"/"Game Show" etc.
                
                # Wir sortieren Scripted (Serien) eher aus oder markieren sie
                st.subheader("📺 Shows & Reality (Primetime & Highlights)")
                
                # Filter auf Uhrzeit (ab 18:00)
                df_ent = df_ent[df_ent["Uhrzeit"] >= "18:00"]
                df_ent = df_ent.sort_values(by="Uhrzeit")
                
                st.dataframe(
                    df_ent,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning("Keine Daten für dieses Land gefunden.")
