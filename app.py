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

st.set_page_config(page_title="TV Guide", layout="wide")

EPG_SOURCES = {
    "DE":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/de.xml",
    "AT":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/at.xml",
    "CH":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/ch.xml",
    "UK":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/uk.xml",
    "US":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/us.xml",
    "JP":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/jp.xml",
    "KR":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/kr.xml"
}

SPORT_KEYWORDS = [
    "football","fußball","soccer","cup","liga","champions","uefa",
    "f1","motogp","tennis","nba","nfl","nhl","mlb","biathlon",
    "ski","snow","hockey","sport"
]

ENTERTAINMENT_KEYWORDS = [
    "show","reality","music","documentary","live","concert",
    "talent","game","event","variety"
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
        return None


def parse_epg(tree, country):
    records = []

    if tree is None:
        return pd.DataFrame()

    for ev in tree.findall(".//programme"):

        try:
            start = ev.get("start")
            stop = ev.get("stop")
            channel = ev.get("channel")

            title = (ev.findtext("title") or "").strip()
            desc  = (ev.findtext("desc") or "").strip()

            dt_start = datetime.strptime(start[:14], "%Y%m%d%H%M%S")
            dt_end   = datetime.strptime(stop[:14], "%Y%m%d%H%M%S")

            dt_start = dt_start.replace(tzinfo=pytz.UTC).astimezone(pytz.timezone("Europe/Berlin"))
            dt_end   = dt_end.replace(tzinfo=pytz.UTC).astimezone(pytz.timezone("Europe/Berlin"))

            records.append({
                "country": country,
                "channel": channel,
                "title": title,
                "description": desc,
                "start": dt_start,
                "end": dt_end
            })

        except:
            continue

    return pd.DataFrame(records)

# ----------------------------------------------------------
# Load all data
# ----------------------------------------------------------

@st.cache_data(ttl=600)
def load_all():
    dfs = []

    for c,url in EPG_SOURCES.items():
        tree = load_xml(url)
        df = parse_epg(tree,c)
        dfs.append(df)

    if len(dfs)==0:
        return pd.DataFrame()

    return pd.concat(dfs, ignore_index=True)

# ----------------------------------------------------------
# Filters
# ----------------------------------------------------------

def is_sport(t):
    t = t.lower()
    return any(k in t for k in SPORT_KEYWORDS)

def is_entertainment(t):
    t = t.lower()
    return any(k in t for k in ENTERTAINMENT_KEYWORDS)

# ----------------------------------------------------------
# UI
# ----------------------------------------------------------

st.title("📺 Global TV Guide – EPG ohne LLM")

now = datetime.now(pytz.timezone("Europe/Berlin"))
end = now + timedelta(hours=24)

df = load_all()

if df.empty:
    st.error("Keine Daten geladen.")
    st.stop()

# Only next 24h
df = df[(df["start"]>=now) & (df["start"]<=end)]

# Split
df_sport = df[df["title"].apply(lambda x: is_sport(x))]
df_ent   = df[df["title"].apply(lambda x: is_entertainment(x))]

tab1, tab2 = st.tabs(["⚽ Sport","🎭 Entertainment"])


# ----------------------------------------------------------
# SPORT
# ----------------------------------------------------------
with tab1:
    st.subheader("Sport Events (24h)")
    if df_sport.empty:
        st.warning("Keine Sport-Events gefunden.")
    else:
        st.dataframe(df_sport.sort_values("start"), use_container_width=True)

# ----------------------------------------------------------
# ENTERTAINMENT
# ----------------------------------------------------------
with tab2:
    st.subheader("Entertainment Events (24h)")
    if df_ent.empty:
        st.warning("Keine Unterhaltung gefunden.")
    else:
        st.dataframe(df_ent.sort_values("start"), use_container_width=True)



# ----------------------------------------------------------
# Debug
# ----------------------------------------------------------
with st.expander("Debug rohdaten"):
    st.write(df.head(200))
