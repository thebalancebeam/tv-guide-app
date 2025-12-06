# app.py — Global TV Guide (ohne Gemini)

import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import gzip
from datetime import datetime, timedelta
import pytz
import traceback

# ------------------------------------------------------
# CONFIG
# ------------------------------------------------------

st.set_page_config(page_title="Global TV Guide", page_icon="📺", layout="wide")

TARGET_TZ = pytz.timezone("Europe/Vienna")

EPG_SOURCES = [
    "https://epgshare01.online/epgshare01/epg_rsn_de.xml.gz",
    "https://epgshare01.online/epgshare01/epg_rsn_at.xml.gz",
    "https://epgshare01.online/epgshare01/epg_rsn_ch.xml.gz",
    "https://epgshare01.online/epgshare01/epg_rsn_uk.xml.gz",
    "https://epgshare01.online/epgshare01/epg_rsn_us.xml.gz",
    "https://epgshare01.online/epgshare01/epg_rsn_jp.xml.gz",
    "https://epgshare01.online/epgshare01/epg_rsn_kr.xml.gz"
]

# ------------------------------------------------------
# HELPERS
# ------------------------------------------------------

def load_xml_gz(url):
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return gzip.decompress(r.content)
    except Exception as e:
        st.warning(f"EPG Fehler: {url} → {e}")
        return None


def parse_xmltv(xml):
    rows = []
    if not xml:
        return rows

    try:
        root = ET.fromstring(xml)
    except:
        return rows

    for p in root.findall(".//programme"):

        try:
            start_raw = p.attrib.get("start","")
            stop_raw = p.attrib.get("stop","")

            if len(start_raw) < 14 or len(stop_raw) < 14:
                continue

            sdt = datetime.strptime(start_raw[:14],"%Y%m%d%H%M%S")
            edt = datetime.strptime(stop_raw [:14],"%Y%m%d%H%M%S")

            sdt = pytz.utc.localize(sdt).astimezone(TARGET_TZ)
            edt = pytz.utc.localize(edt).astimezone(TARGET_TZ)

            title = ""
            desc = ""

            for c in p:
                tag = c.tag.lower()
                if tag.endswith("title") and c.text:
                    title = c.text.strip()
                if tag.endswith("desc") and c.text:
                    desc = c.text.strip()

            rows.append({
                "title": title,
                "description": desc,
                "start": sdt,
                "end": edt,
                "channel": p.attrib.get("channel","")
            })

        except:
            continue

    return rows


def load_epg():
    rows = []
    for url in EPG_SOURCES:
        rows.extend(parse_xmltv(load_xml_gz(url)))

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["title","description","channel","start","end"])
    return df.drop_duplicates()


# ------------------------------------------------------
# SPORT DATA
# ------------------------------------------------------

def load_sport():
    rows = []
    now = datetime.now(TARGET_TZ)
    end = now + timedelta(hours=24)

    for d in (0,1):
        date = (now + timedelta(days=d)).strftime("%Y-%m-%d")

        try:
            js = requests.get(
                "https://www.thesportsdb.com/api/v1/json/1/eventsday.php",
                params={"d": date},
                timeout=10
            ).json()
        except:
            continue

        for e in js.get("events",[]):
            try:
                t1 = e.get("strHomeTeam","")
                t2 = e.get("strAwayTeam","")
                title = e.get("strEvent", f"{t1} vs {t2}")

                dt_str = e.get("dateEvent","") + " " + (e.get("strTime") or "00:00")

                dt = datetime.strptime(dt_str,"%Y-%m-%d %H:%M")
                dt = pytz.utc.localize(dt).astimezone(TARGET_TZ)

                if not (now <= dt <= end):
                    continue

                rows.append({
                    "start": dt,
                    "end": dt + timedelta(hours=2),
                    "title": title,
                    "league": e.get("strLeague",""),
                    "home": t1,
                    "away": t2,
                    "channel": e.get("strTVStation","")
                })
            except:
                continue

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["start","end","title","league","home","away","channel"])
    return df


# ------------------------------------------------------
# UI
# ------------------------------------------------------

st.title("📺 Global TV Guide — EPG + Sports (ohne KI)")

tab_ent, tab_sport, tab_dbg = st.tabs(["🎭 Entertainment","⚽ Sport","⚙ Debug"])


# ------------------------------------------------------
# ENTERTAINMENT
# ------------------------------------------------------

with tab_ent:
    if st.button("Lade Entertainment (24h)"):

        try:
            df = load_epg()
            now = datetime.now(TARGET_TZ)
            end = now + timedelta(hours=24)

            df = df[(df["start"]>=now)&(df["start"]<=end)]

            # Filtere Unerwünschtes
            df = df[
                ~df["title"].str.contains(
                    "Sport|News|Film|Serie|Thriller|Drama|Nachrichten",
                    case=False,
                    na=False
                )
            ]

            if df.empty:
                st.info("Keine Entertainment-Programme gefunden.")
            else:
                out = df.sort_values("start")
                out["start"] = out["start"].dt.strftime("%d.%m %H:%M")
                out["end"] = out["end"].dt.strftime("%H:%M")

                st.dataframe(out, use_container_width=True)

        except:
            st.error("Fehler Entertainment")
            st.exception(traceback.format_exc())


# ------------------------------------------------------
# SPORT
# ------------------------------------------------------

with tab_sport:
    if st.button("Lade Sport (24h)"):

        try:
            df = load_sport()
            if df.empty:
                st.info("Keine Sportevents gefunden.")
            else:
                df["start"] = df["start"].dt.strftime("%d.%m %H:%M")
                df["end"] = df["end"].dt.strftime("%H:%M")
                st.dataframe(df, use_container_width=True)

        except:
            st.error("Fehler Sport")
            st.exception(traceback.format_exc())


# ------------------------------------------------------
# DEBUG
# ------------------------------------------------------

with tab_dbg:
    st.write("EPG Quellen:")
    for u in EPG_SOURCES:
        st.write("-", u)
