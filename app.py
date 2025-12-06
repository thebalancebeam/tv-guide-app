import streamlit as st
import requests
import pandas as pd
import pytz
from datetime import datetime, timedelta
from lxml import etree
import io

st.set_page_config(page_title="TV Guide Debug", layout="wide")

EPG_SOURCES = {
    "DE":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/de.xml",
    "AT":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/at.xml",
    "CH":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/ch.xml",
    "UK":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/uk.xml",
    "US":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/us.xml",
    "JP":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/jp.xml",
    "KR":"https://raw.githubusercontent.com/iptv-org/epg/master/guides/kr.xml"
}

TARGET_TZ = pytz.timezone("Europe/Vienna")

def load_xml(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return etree.parse(io.BytesIO(r.content))
    except Exception as e:
        st.warning(f"EPG Fehler bei {url}: {e}")
        return None

def parse_epg(tree, country):
    rows = []
    if tree is None:
        return pd.DataFrame()
    for ev in tree.findall(".//programme"):
        start = ev.get("start")
        stop = ev.get("stop")
        title = (ev.findtext("title") or "").strip()
        # description optional
        desc = (ev.findtext("desc") or "").strip()
        channel = ev.get("channel","")
        try:
            dt_s = datetime.strptime(start[:14], "%Y%m%d%H%M%S")
            dt_e = datetime.strptime(stop[:14],  "%Y%m%d%H%M%S")
            dt_s = pytz.UTC.localize(dt_s).astimezone(TARGET_TZ)
            dt_e = pytz.UTC.localize(dt_e).astimezone(TARGET_TZ)
        except Exception:
            continue
        rows.append({
            "country": country,
            "channel": channel,
            "title": title,
            "description": desc,
            "start": dt_s,
            "end": dt_e
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=600)
def load_all_epg():
    dfs = []
    stats = []
    for c, url in EPG_SOURCES.items():
        tree = load_xml(url)
        df = parse_epg(tree, c)
        stats.append((c, url, len(df)))
        dfs.append(df)
    if dfs:
        return pd.concat(dfs, ignore_index=True), stats
    else:
        return pd.DataFrame(), stats

st.header("🌐 EPG Debug Übersicht")
df_all, stats = load_all_epg()
for c, url, cnt in stats:
    st.write(f"Quelle {c}: {url} → Programme gefunden: {cnt}")

if df_all.empty:
    st.error("⚠️ Keine EPG-Daten insgesamt geladen.")
    st.stop()

st.write("Erste 20 Programme (unabhängig vom Zeitfenster):")
st.dataframe(df_all.head(20))

# Zeitfilter
now = datetime.now(TARGET_TZ)
end = now + timedelta(hours=24)
df_24 = df_all[(df_all["start"] >= now) & (df_all["start"] <= end)]

st.write(f"Programme in nächster 24h: {len(df_24)}")
st.dataframe(df_24.head(20))

# Weiterer Filter (z. B. Entertainment)
df_ent = df_24[~df_24["title"].str.contains("Sport|News|Film|Serie|Thriller|Drama", case=False, na=False)]
st.write("Entertainment (gefiltert):")
st.dataframe(df_ent.head(20))

# Sport-Filter
df_sport = df_24[df_24["title"].str.contains("Sport|Cup|Liga|UEFA|Champions|Football|Soccer", case=False, na=False)]
st.write("Sport (gefiltert):")
st.dataframe(df_sport.head(20))
