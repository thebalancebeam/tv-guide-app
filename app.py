import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- KONFIGURATION ---
st.set_page_config(page_title="Pure API TV Guide", page_icon="📡", layout="wide")

# TheSportsDB API Konfiguration (Public Test Key "3")
TSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"

# WICHTIG: Die IDs der Ligen in der TheSportsDB Datenbank
# Wir beschränken uns auf deine Wunschliste.
LEAGUE_MAP = {
    # FUSSBALL
    "🇩🇪 Bundesliga": "4331",
    "🇩🇪 2. Bundesliga": "4332",
    "🇦🇹 Bundesliga": "4333",
    "🇬🇧 Premier League": "4328",
    "🇪🇸 La Liga": "4335",
    "🇮🇹 Serie A": "4337",
    "🇫🇷 Ligue 1": "4334",
    # MOTORSPORT
    "🏎️ Formel 1": "4370",
    "🏍️ MotoGP": "4392",
    # WINTERSPORT (IDs können im Test-Key variieren, wir versuchen die Standard-IDs)
    "🎿 Ski Alpin (Men)": "4403",
    "🎿 Ski Alpin (Women)": "4404",
    "🎯 Biathlon": "4410"
}

# --- FUNKTIONEN ---

def get_dates():
    """Gibt heute und morgen als Datumsobjekte zurück"""
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    return today, tomorrow

def fetch_sports_schedule():
    """
    Fragt TheSportsDB für jede Liga ab.
    Endpunkt: eventsnextleague.php (Liefert die nächsten 15 Events einer Liga)
    """
    today, tomorrow = get_dates()
    all_events = []
    
    # Ladebalken für User-Feedback
    progress_text = "Lade Ligen..."
    my_bar = st.progress(0, text=progress_text)
    total = len(LEAGUE_MAP)
    
    for i, (league_name, league_id) in enumerate(LEAGUE_MAP.items()):
        url = f"{TSDB_BASE}/eventsnextleague.php?id={league_id}"
        
        try:
            r = requests.get(url, timeout=3)
            data = r.json()
            
            if data and "events" in data and data["events"]:
                for e in data["events"]:
                    # Datum parsen (Format YYYY-MM-DD)
                    date_str = e.get("dateEvent", "")
                    if not date_str: continue
                    
                    try:
                        event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    except:
                        continue
                        
                    # FILTER: Ist das Event heute oder morgen?
                    if event_date == today or event_date == tomorrow:
                        
                        # Uhrzeit sauber machen (nur HH:MM)
                        time_str = e.get("strTime", "00:00")[:5]
                        
                        # TV Sender Logik
                        # TheSportsDB hat ein Feld 'strTVStation'. Das ist oft leer oder international.
                        tv_stations = e.get("strTVStation")
                        if not tv_stations:
                            tv_stations = "k.A."
                        
                        all_events.append({
                            "Datum": event_date.strftime("%d.%m.%Y"),
                            "Uhrzeit": time_str,
                            "Sportart": e.get("strSport", "Sport"),
                            "Wettbewerb": league_name,
                            "Paarung / Event": e.get("strEvent", e.get("strEventAlternate", "Event")),
                            "Sender (Info)": tv_stations
                        })
                        
        except Exception as err:
            print(f"Fehler bei {league_name}: {err}")
            
        # Balken aktualisieren
        my_bar.progress((i + 1) / total, text=f"Lade {league_name}...")
        
    my_bar.empty()
    return pd.DataFrame(all_events)

def fetch_entertainment_schedule(country_code, country_name):
    """
    Fragt TVMaze API ab.
    Endpunkt: /schedule (Liefert das komplette Tagesprogramm eines Landes)
    """
    today, _ = get_dates() # TVMaze Free erlaubt Batch meist nur für einen Tag
    date_str = today.strftime("%Y-%m-%d")
    
    url = f"https://api.tvmaze.com/schedule?country={country_code}&date={date_str}"
    
    try:
        r = requests.get(url, timeout=4)
        if r.status_code != 200:
            return pd.DataFrame()
            
        data = r.json()
        show_list = []
        
        for item in data:
            show = item.get("show", {})
            
            # --- FILTER LOGIK ---
            # Du wolltest KEINE Filme/Serien, nur Entertainment/Shows.
            # TVMaze hat ein Feld 'type'.
            # Typische Types: "Scripted" (Serie), "Reality", "Game Show", "Talk Show", "News", "Variety"
            
            show_type = show.get("type", "Unknown")
            
            # Wir definieren eine "Erlaubt"-Liste basierend auf deinen Wünschen
            ALLOWED_TYPES = ["Reality", "Game Show", "Variety", "Award Show", "Panel Show", "Talent"]
            
            # Zusätzlich schließen wir News aus, behalten aber "Show"-artige Formate
            if show_type in ALLOWED_TYPES:
                
                # SENDER FINDEN
                # Entweder 'network' (TV) oder 'webChannel' (Streaming)
                network = show.get("network")
                web_channel = show.get("webChannel")
                
                sender_name = "-"
                if network: sender_name = network.get("name")
                elif web_channel: sender_name = web_channel.get("name")
                
                # UHRZEIT FILTER (Nur Primetime/Abendprogramm ab 18:00)
                airtime = item.get("airtime", "00:00")
                if airtime >= "18:00":
                    show_list.append({
                        "Datum": today.strftime("%d.%m.%Y"),
                        "Uhrzeit": airtime,
                        "Land": country_name,
                        "Sender": sender_name,
                        "Titel": show.get("name"),
                        "Typ": show_type,
                        "Episode": item.get("name")
                    })
                    
        return pd.DataFrame(show_list)

    except Exception as e:
        return pd.DataFrame()

# --- FRONTEND UI ---

st.title("📡 Live TV Guide (Pure API)")
st.caption(f"Daten für Heute ({datetime.now().strftime('%d.%m.%Y')}) und Morgen.")

tab_sport, tab_ent = st.tabs(["⚽️ SPORT (TheSportsDB)", "🎤 ENTERTAINMENT (TVMaze)"])

# === TAB SPORT ===
with tab_sport:
    if st.button("Lade Sport-Daten", key="btn_sport"):
        df = fetch_sports_schedule()
        
        if not df.empty:
            # Sortieren nach Datum und Uhrzeit
            df = df.sort_values(by=["Datum", "Uhrzeit"])
            
            st.success(f"{len(df)} Events in den Top-Ligen gefunden.")
            
            # Tabelle anzeigen
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Paarung / Event": st.column_config.TextColumn("Match / Event", width="large"),
                    "Sender (Info)": st.column_config.TextColumn("TV Info (Int.)", width="medium"),
                }
            )
        else:
            st.warning("Keine Live-Events für heute/morgen in den konfigurierten Ligen gefunden.")
            st.info("Hinweis: Dies kann an einer Spielpause liegen oder der kostenlose API-Key liefert für diese Nischen-Liga gerade keine Daten.")

# === TAB ENTERTAINMENT ===
with tab_ent:
    col1, col2 = st.columns([1, 4])
    
    with col1:
        # Mapping Land -> ISO Code für TVMaze
        country_select = st.selectbox("Land", [
            ("DE", "Deutschland"),
            ("US", "USA"),
            ("GB", "Grossbritannien"),
            ("AT", "Österreich") # TVMaze hat AT Daten, aber oft weniger als DE
        ], format_func=lambda x: x[1])
    
    with col2:
        st.write("") # Spacer
        st.write("")
        btn_ent = st.button("Lade Abendprogramm", key="btn_ent")
        
    if btn_ent:
        code, name = country_select
        with st.spinner(f"Lade Shows für {name}..."):
            df_ent = fetch_entertainment_schedule(code, name)
            
            if not df_ent.empty:
                df_ent = df_ent.sort_values(by="Uhrzeit")
                
                st.success(f"{len(df_ent)} Primetime-Sendungen gefunden (Typ: Reality, Game Show, Variety).")
                st.dataframe(
                    df_ent,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning(f"Keine passenden Shows (Reality/Game/Variety) ab 18:00 Uhr für {name} gefunden.")
                st.caption("TVMaze liefert hauptsächlich Serien (Scripted). Wenn heute Abend nur Serien laufen, bleibt diese Liste leer, da wir Serien herausgefiltert haben.")
