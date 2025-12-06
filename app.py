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
    n
