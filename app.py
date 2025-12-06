import streamlit as st
import requests
import pandas as pd
import pytz
from datetime import datetime, timedelta
from lxml import etree
import io


# ----------------------------------------------------------
# CONFIG
# ----------------------------------------------------------

st.set_page_config(page_title="Global TV Guide", layout="wide")

EPG_SOURCES = {
    "DE": "https://raw.githubusercontent.com/globetvapp/epg/main/Germany/de.xml",
    "AT": "https://raw.githubusercontent.com/globetvapp/epg/main/Austria/at.xml",
    "CH": "https://raw.githubusercontent.com/globetvapp/epg/main/Switzerland/ch.xml",
    "UK": "https://raw.githubusercontent.com/globetvapp/epg/main/UnitedKingdom/uk.xml",
    "US": "https://raw.githubusercontent.com/globetvapp/epg/main/USA/us.xml",
    "JP": "https://raw.githubusercontent.com/globetvapp/epg/main/Japan/jp.xml",
    "KR": "https://raw.githubusercontent.com/globetvapp/epg/main/SouthKorea/kr.xml",
}

TZ = pytz.timezone("Europe/Berlin")


SPORT_KEYWORDS = [
    "football","fußball","soccer","cup","liga","champions","uefa",
    "f1","motogp","tennis","nba","nfl","nhl","mlb","ski","biathlon"
]

ENT_KEYWORDS = [
    "show","reality","music","concert","documentary",
    "talent","event","live","variety","special"
]


# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------

def load_xml(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return etree.parse(io.BytesIO(r.content))
    except Exception as e:
        st.warning(f"EPG Fehler → {url} → {e}")
        return None


def parse_tree(tree, country):
    data = []

    if tree is None:
        return pd.DataFrame()

    for ev in tree.findall(".//programme"):
        try:
            start = ev.get("start")
            end   = ev.get("stop")

            ts = datetime.strptime(start[:14], "%Y%m%d%H%M%S")
            te = datetime.strptime(end[:14],   "%Y%m%d%H%M%S")

            ts = pytz.UTC.localize(ts).astimezone(TZ)
            te = pytz.UTC.localize(te).astimezone(TZ)

            data.append({
                "country": country,
                "channel": ev.get("channel"),
                "title": (ev.findtext("title") or "").strip(),
                "description": (ev.findtext("desc") or "").strip(),
                "start": ts,
                "end": te
            })

        except:
            continue

    return pd.DataFrame(data)



# ----------------------------------------------------------
# Load + cache
# ----------------------------------------------------------

@st.cache_data(ttl=600)
def load_all():
    dfs = []
    for c,u in EPG_SOURCES.items():
        dfs.append(parse_tree(load_xml(u), c))

    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)



# ----------------------------------------------------------
# Filters
# ----------------------------------------------------------

def is_sport(t):
    t = (t or "").lower()
    return any(w in t for w in SPORT_KEYWORDS)

def is_entertainment(t):
    t = (t or "").lower()
    return any(w in t for w in ENT_KEYWORDS)



# ----------------------------------------------------------
# UI
# ----------------------------------------------------------

st.title("📺 Global TV Guide (EPG only)")

df = load_all()

if df.empty:
    st.error("Keine EPG Daten geladen.")
    st.stop()


now = datetime.now(TZ)
end = now + timedelta(hours=24)

df_24 = df[(df.start >= now) & (df.start <= end)]

st.write(f"Zeitraum: **{now} bis {end}**")
st.write(f"Alle Events: {len(df_24)}")

tab_sport, tab_ent, tab_debug = st.tabs(["⚽ Sport", "🎭 Entertainment", "🛠 Debug"])



# ----------------------------------------------------------
# SPORT
# ----------------------------------------------------------
with tab_sport:
    s = df_24[df_24.title.apply(is_sport)]

    if s.empty:
        st.warning("Keine Sport Events gefunden.")
    else:
        st.dataframe(s.sort_values("start"), use_container_width=True)



# ----------------------------------------------------------
# ENTERTAINMENT
# ----------------------------------------------------------
with tab_ent:
    e = df_24[df_24.title.apply(is_entertainment)]

    if e.empty:
        st.warning("Keine Entertainment Events gefunden.")
    else:
        st.dataframe(e.sort_values("start"), use_container_width=True)



# ----------------------------------------------------------
# DEBUG
# ----------------------------------------------------------
with tab_debug:
    st.subheader("Alle rohen Events")
    st.dataframe(df.head(200))

    st.subheader("24h Events")
    st.dataframe(df_24.head(200))
