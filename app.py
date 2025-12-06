# app.py — Global TV Guide
# EPG: EPGShare01 (7 Länder)
# Sport: TheSportsDB
# Kurzbeschreibung: Gemini
# Anzeige: Streamlit

import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import gzip
import io
from datetime import datetime, timedelta
import pytz
import google.generativeai as genai
import traceback

# ------------------------------------------------------
# CONFIG
# ------------------------------------------------------

st.set_page_config(page_title="Global TV Guide", page_icon="📺", layout="wide")

# API Keys
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("Gemini API Key fehlt – in Streamlit Secrets eintragen.")
    st.stop()

THESPORTSDB_KEY = st.secrets.get("THESPORTSDB_API_KEY","1")

TARGET_TZ = pytz.timezone("Europe/Vienna")

# EPGShare Quellen (7 Länder)
EPG_SOURCES = [
    "https://epgshare01.online/epgshare01/epg_rsn_de.xml.gz",
    "https://epgshare01.online/epgshare01/epg_rsn_at.xml.gz",
    "https://epgshare01.online/epgshare01/epg_rsn_ch.xml.gz",
    "https://epgshare01.online/epgshare01/epg_rsn_uk.xml.gz",
    "https://epgshare01.online/epgshare01/epg_rsn_us.xml.gz",
    "https://epgshare01.online/epgshare01/epg_rsn_jp.xml.gz",
    "https://epgshare01.online/epgshare01/epg_rsn_kr.xml.gz",
]

# ------------------------------------------------------
# DOWNLOAD + DECOMPRESSION
# ------------------------------------------------------

def load_xml_gz(url):
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return gzip.decompress(r.content)
    except Exception as e:
        st.warning(f"EPG Fehler: {url} → {e}")
        return None

# ------------------------------------------------------
# XMLTV PARSER
# ------------------------------------------------------

def parse_xmltv(xml_bytes):
    rows = []
    if not xml_bytes:
        return rows
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return rows

    for p in root.findall(".//programme"):
        try:
            start = p.attrib.get("start","")
            stop  = p.attrib.get("stop","")
            ch    = p.attrib.get("channel","")

            def parse_dt(s):
                if len(s) < 14:
                    return None
                try:
                    dt = datetime.strptime(s[:14],"%Y%m%d%H%M%S")
                    dt = pytz.utc.localize(dt)
                    return dt.astimezone(TARGET_TZ)
                except:
                    return None

            start_dt = parse_dt(start)
            end_dt   = parse_dt(stop)

            if not start_dt or not end_dt:
                continue

            title = ""
            desc  = ""

            for c in p:
                t = c.tag.lower()
                if t.endswith("title") and c.text:
                    title = c.text.strip()
                if t.endswith("desc") and c.text:
                    desc = c.text.strip()

            rows.append({
                "title": title,
                "description": desc,
                "channel": ch,
                "start": start_dt,
                "end": end_dt
            })

        except:
            continue

    return rows

# ------------------------------------------------------
# LOAD ALL EPG
# ------------------------------------------------------

def load_epg():
    rows = []
    for url in EPG_SOURCES:
        xml = load_xml_gz(url)
        rows.extend(parse_xmltv(xml))

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["title","description","channel","start","end"])
    return df.drop_duplicates()

# ------------------------------------------------------
# SPORT: TheSportsDB
# ------------------------------------------------------

def load_sport_events():
    now = datetime.now(TARGET_TZ)
    limit = now + timedelta(hours=24)

    rows = []

    for delta in (0,1):
        date = (now + timedelta(days=delta)).strftime("%Y-%m-%d")

        url = f"https://www.thesportsdb.com/api/v1/json/{THESPORTSDB_KEY}/eventsday.php"
        js = requests.get(url, params={"d":date}).json()
        ev = js.get("events") or []

        for e in ev:
            try:
                team1 = e.get("strHomeTeam","")
                team2 = e.get("strAwayTeam","")
                title = e.get("strEvent", f"{team1} vs {team2}")

                dt_str = e.get("dateEvent","") + " " + (e.get("strTime") or "00:00")
                dt = datetime.strptime(dt_str,"%Y-%m-%d %H:%M")
                dt = pytz.utc.localize(dt).astimezone(TARGET_TZ)

                if not (now <= dt <= limit):
                    continue

                rows.append({
                    "start": dt,
                    "end": dt + timedelta(hours=2),
                    "title": title,
                    "league": e.get("strLeague",""),
                    "home": team1,
                    "away": team2,
                    "channel": e.get("strTVStation",""),
                })

            except:
                pass

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["start","end","title","league","home","away","channel"])
    return df

# ------------------------------------------------------
# GEMINI SHORT DESCRIPTION
# ------------------------------------------------------

def short(text):
    if not text:
        return ""
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        res = model.generate_content(
            f"Erstelle eine sehr kurze Beschreibung (max 10 Wörter) für:\n{text}"
        )
        words = (res.text or "").split()
        return " ".join(words[:10])
    except:
        return ""

# ------------------------------------------------------
# STREAMLIT UI
# ------------------------------------------------------

st.title("📺 Global TV Guide – EPG + Sport + AI")

t_ent, t_sport, t_dbg = st.tabs(["🎭 Entertainment","⚽ Sport","⚙ Debug"])

# ------------------------------------------------------
# ENTERTAINMENT
# ------------------------------------------------------
with t_ent:
    if st.button("Lade Entertainment (24h)"):
        try:
            df = load_epg()
            now = datetime.now(TARGET_TZ)
            end = now + timedelta(hours=24)

            df = df[(df["start"]>=now)&(df["start"]<=end)]

            # Filter
            df = df[
                ~df["title"].str.contains(
                    "Sport|News|Serie|Film|Thriller|Drama|Reportage",
                    case=False,
                    na=False
                )
            ]

            df["short"] = df["title"].apply(short)

            if df.empty:
                st.info("Keine Entertainmentprogramme gefunden.")
            else:
                out = df.sort_values("start")[
                    ["start","end","title","channel","short","description"]
                ]
                out["start"] = out["start"].dt.strftime("%d.%m %H:%M")
                out["end"] = out["end"].dt.strftime("%H:%M")

                st.dataframe(out, use_container_width=True)

        except:
            st.error("Fehler Entertainment")
            st.exception(traceback.format_exc())

# ------------------------------------------------------
# SPORT
# ------------------------------------------------------
with t_sport:
    if st.button("Lade Sport (24h)"):
        try:
            df = load_sport_events()
            df["short"] = df["title"].apply(short)

            if df.empty:
                st.info("Keine Sportevents gefunden.")
                st.write("Hinweis: TheSportsDB deckt nicht jede Liga ab.")
            else:
                df["start"] = df["start"].dt.strftime("%d.%m %H:%M")
                df["end"] = df["end"].dt.strftime("%H:%M")

                st.dataframe(
                    df[["start","end","league","title","home","away","channel","short"]],
                    use_container_width=True
                )

        except:
            st.error("Fehler Sport")
            st.exception(traceback.format_exc())

# ------------------------------------------------------
# DEBUG
# ------------------------------------------------------
with t_dbg:
    st.write("EPG Quellen:")
    for u in EPG_SOURCES:
        st.write(u)
