import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
import google.generativeai as genai

st.set_page_config(page_title="Global TV Guide", page_icon="📺", layout="wide")

# -------------------------------------------------------
#                SECRETS / API KEYS
# -------------------------------------------------------
try:
    GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_KEY)
except:
    st.error("❌ Gemini API Key fehlt in secrets.toml")
    st.stop()

try:
    THESPORTSDB_KEY = st.secrets["THESPORTSDB_API_KEY"]
except:
    st.error("❌ TheSportsDB API Key fehlt in secrets.toml")
    st.stop()

# -------------------------------------------------------
#              KONFIGURATION
# -------------------------------------------------------

EPG_SOURCES = [
    # Beispiel-URLs
    "https://raw.githubusercontent.com/iptv-org/epg/master/guides/de.xml",
    "https://raw.githubusercontent.com/iptv-org/epg/master/guides/uk.xml",
    # Weitere Quellen kannst du später hinzufügen
]

SPORT_LEAGUES = {
    "UEFA Champions League": "4328",
    "German Bundesliga": "4331",
    "Italian Serie A": "4332",
    "Spanish La Liga": "4335",
    "French Ligue 1": "4344",
    "Austrian Bundesliga": "4373",
    "Premier League": "4328",
    "NBA": "4387",
    "NFL": "4391",
}

TARGET_TIMEZONE = pytz.timezone("Europe/Vienna")

# -------------------------------------------------------
#              FUNKTION: EPG LADEN
# -------------------------------------------------------

def load_epg():
    """
    Lädt mehrere XMLTV-EPG-Dateien und kombiniert sie.
    """
    programs = []

    for url in EPG_SOURCES:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            xml_data = r.content

            root = ET.fromstring(xml_data)
            for prog in root.findall("programme"):
                start_raw = prog.attrib.get("start")
                stop_raw = prog.attrib.get("stop")
                channel = prog.attrib.get("channel")

                title = prog.findtext("title") or ""
                desc = prog.findtext("desc") or ""

                try:
                    start_dt = datetime.strptime(start_raw[:14], "%Y%m%d%H%M%S")
                    stop_dt = datetime.strptime(stop_raw[:14], "%Y%m%d%H%M%S")

                    # MEZ konvertieren
                    start_dt = pytz.utc.localize(start_dt).astimezone(TARGET_TIMEZONE)
                    stop_dt = pytz.utc.localize(stop_dt).astimezone(TARGET_TIMEZONE)
                except:
                    continue

                programs.append({
                    "title": title,
                    "description": desc,
                    "channel": channel,
                    "start": start_dt,
                    "end": stop_dt
                })
        except:
            pass

    return pd.DataFrame(programs)

# -------------------------------------------------------
#         SPORT-EVENTS VIA THESPORTSDB
# -------------------------------------------------------

def load_sport_events():
    df_list = []

    now = datetime.now(TARGET_TIMEZONE)
    end = now + timedelta(hours=24)

    for league_name, league_id in SPORT_LEAGUES.items():
        url = f"https://www.thesportsdb.com/api/v1/json/{THESPORTSDB_KEY}/eventsnextleague.php?id={league_id}"
        try:
            data = requests.get(url).json()
            events = data.get("events", [])
            for e in events:
                event_time_str = f"{e['dateEvent']} {e['strTime']}"
                event_dt = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                event_dt = TARGET_TIMEZONE.localize(event_dt)

                if now <= event_dt <= end:
                    df_list.append({
                        "title": e.get("strEvent"),
                        "sport": e.get("strSport"),
                        "league": league_name,
                        "home": e.get("strHomeTeam"),
                        "away": e.get("strAwayTeam"),
                        "start": event_dt,
                        "end": event_dt + timedelta(hours=2),
                        "channel": "n/a (Sports API)"
                    })
        except:
            pass

    if not df_list:
        return pd.DataFrame()

    return pd.DataFrame(df_list)

# -------------------------------------------------------
#      KURZBESCHREIBUNG MIT GEMINI (max 10 Wörter)
# -------------------------------------------------------

def generate_short_desc(title):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"Formuliere eine Kurzbeschreibung mit maximal 10 Wörtern für: {title}"
    try:
        res = model.generate_content(prompt)
        return res.text.strip()
    except:
        return ""

# -------------------------------------------------------
#                    UI
# -------------------------------------------------------

st.title("📺 Global TV Guide – 24h")
st.write("TV-Programm aus EPG + Sportdaten aus SportsDB + Kurzbeschreibung aus Gemini")

tab_ent, tab_sport, tab_debug = st.tabs(["🎭 Entertainment", "⚽ Sport", "⚙ Debug"])

# ---------- ENTERTAINMENT ----------
with tab_ent:
    if st.button("🔄 Entertainment laden"):
        epg_df = load_epg()

        # Zeitfilter
        now = datetime.now(TARGET_TIMEZONE)
        end = now + timedelta(hours=24)
        epg_df = epg_df[(epg_df["start"] >= now) & (epg_df["start"] <= end)]

        # Entertainment-Filter
        ent_df = epg_df[~epg_df["title"].str.contains("News|Sport|Serie|Movie|Film|Thriller|Drama", case=False, na=False)]

        # Kurzbeschreibung
        ent_df["short_description"] = ent_df["title"].apply(generate_short_desc)

        st.dataframe(ent_df)

# ---------- SPORT ----------
with tab_sport:
    if st.button("🏆 Sport laden"):
        sport_df = load_sport_events()

        if not sport_df.empty:
            sport_df["short_description"] = sport_df["title"].apply(generate_short_desc)
            st.dataframe(sport_df)
        else:
            st.warning("⚠️ Keine Sportevents in den nächsten 24h gefunden.")

# ---------- DEBUG ----------
with tab_debug:
    st.write("EPG-Quellen:")
    st.json(EPG_SOURCES)

    st.write("Sport-Ligen:")
    st.json(SPORT_LEAGUES)
