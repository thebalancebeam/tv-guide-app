# app.py - TV Guide (EPG + TheSportsDB + Gemini short descriptions)
import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
import google.generativeai as genai
import traceback

st.set_page_config(page_title="Global TV Guide", page_icon="📺", layout="wide")

# -------------------------
# SECRETS / CONFIG
# -------------------------
try:
    GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_KEY)
except Exception:
    st.error("❌ Bitte setze GEMINI_API_KEY in Streamlit Secrets.")
    st.stop()

# TheSportsDB key (free tier often uses '1' or your real key)
THESPORTSDB_KEY = st.secrets.get("THESPORTSDB_API_KEY", "1")

# EPG sources - passe hier deine favorisierten XMLTV URLs an
EPG_SOURCES = [
    # iptv-org guides (Beispiele). Ersetze/ergänze mit epgshare01 URLs falls gewünscht.
    "https://raw.githubusercontent.com/iptv-org/epg/master/guides/de.xml",
    "https://raw.githubusercontent.com/iptv-org/epg/master/guides/uk.xml",
    "https://raw.githubusercontent.com/iptv-org/epg/master/guides/us.xml",
]

# League / keyword list to filter sport events (string fragments matched against strLeague / strEvent)
SPORT_LEAGUE_KEYWORDS = [
    "Champions League", "Bundesliga", "Premier League", "La Liga", "Serie A", "Ligue 1",
    "Europa League", "Conference League", "DFB-Pokal", "ÖFB", "FA Cup", "Carabao Cup",
    "Copa del Rey", "Coppa", "Women's Super League", "Frauen-Bundesliga", "MLS",
    "Allsvenskan", "Eredivisie", "Belgian Pro League", "Liga Portugal", "Süper Lig",
    "UEFA", "FIFA", "ATP", "WTA", "Grand Slam", "Formula 1", "MotoGP", "NFL", "NBA", "NHL", "MLB",
    # weitere Schlagwörter kannst du hinzufügen
]

TARGET_TZ = pytz.timezone("Europe/Vienna")

# -------------------------
# HELPERS
# -------------------------
def safe_request_json(url, params=None, timeout=12):
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.warning(f"Request failed: {url} -> {str(e)}")
        return None

def safe_request_bytes(url, timeout=12):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception as e:
        st.warning(f"EPG download failed: {url} -> {str(e)}")
        return None

# -------------------------
# EPG LADEN & PARSEN
# -------------------------
def parse_xmltv_programs(xml_bytes):
    """
    Parst ein XMLTV-File (bytes) und gibt eine Liste dicts mit keys:
    title, description, channel, start (datetime tz-aware), end (datetime tz-aware)
    """
    out = []
    if not xml_bytes:
        return out
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as e:
        # Falls Namespaces/Encoding Probleme auftreten, versuchen wir es tolerant
        try:
            txt = xml_bytes.decode('utf-8', errors='ignore')
            root = ET.fromstring(txt)
        except Exception:
            st.warning("XML parsing failed.")
            return out

    # Suche nach allen <programme> Elementen (tolerant)
    for prog in root.findall('.//programme'):
        try:
            start_raw = prog.attrib.get('start') or prog.attrib.get('from') or ""
            stop_raw = prog.attrib.get('stop') or prog.attrib.get('to') or ""
            channel = prog.attrib.get('channel') or prog.attrib.get('channel_id') or ""

            # Title / desc - tolerant mit namespace
            title = ""
            desc = ""
            t = prog.find('title')
            if t is None:
                # Suche mit any namespace
                for child in prog:
                    if child.tag.lower().endswith('title'):
                        t = child
                        break
            if t is not None and t.text:
                title = t.text.strip()

            d = prog.find('desc')
            if d is None:
                for child in prog:
                    if child.tag.lower().endswith('desc'):
                        d = child
                        break
            if d is not None and d.text:
                desc = d.text.strip()

            # Parse start/stop (XMLTV times are often like "20251231203000 +0000" or "20251231203000")
            def parse_xmltv_dt(s):
                if not s:
                    return None
                s = s.strip()
                # take first 14 chars as yyyymmddHHMMSS
                core = s[:14]
                try:
                    dt = datetime.strptime(core, "%Y%m%d%H%M%S")
                    # If original string contains timezone offset, try to handle it
                    if '+' in s or '-' in s[14:]:
                        # assume time provided in UTC offset specified; for simplicity, treat as UTC then convert
                        dt = pytz.utc.localize(dt)
                    else:
                        # assume UTC if no info
                        dt = pytz.utc.localize(dt)
                    # convert to TARGET_TZ
                    return dt.astimezone(TARGET_TZ)
                except Exception:
                    return None

            start_dt = parse_xmltv_dt(start_raw)
            stop_dt = parse_xmltv_dt(stop_raw)

            if start_dt is None or stop_dt is None:
                # überspringe unvollständige Einträge
                continue

            out.append({
                "title": title,
                "description": desc,
                "channel": channel,
                "start": start_dt,
                "end": stop_dt
            })
        except Exception:
            # ignoriere einzelne fehlerhafte programme
            continue

    return out

def load_epg_all():
    """
    Lädt alle EPG_SOURCES und gibt ein DataFrame mit Spalten title, description, channel, start, end.
    Liefert immer ein DataFrame (auch wenn leer).
    """
    rows = []
    for url in EPG_SOURCES:
        xmlb = safe_request_bytes(url)
        if not xmlb:
            continue
        parsed = parse_xmltv_programs(xmlb)
        rows.extend(parsed)

    if not rows:
        # leeres DataFrame mit definierten Spalten (vermeidet KeyError)
        return pd.DataFrame(columns=["title","description","channel","start","end"])
    df = pd.DataFrame(rows)
    # deduplizieren
    df = df.drop_duplicates(subset=["title","channel","start"])
    return df

# -------------------------
# SPORT: TheSportsDB (events on a day)
# -------------------------
def load_sport_events_thesportsdb():
    """
    Holt Events für heute und morgen via TheSportsDB eventsday.php (falls verfügbar).
    Filtert nach SPORT_LEAGUE_KEYWORDS.
    """
    all_events = []
    now = datetime.now(TARGET_TZ)
    dates = [
        (now).strftime("%Y-%m-%d"),
        (now + timedelta(days=1)).strftime("%Y-%m-%d")
    ]

    base = "https://www.thesportsdb.com/api/v1/json/{key}/eventsday.php"
    for date_str in dates:
        url = base.format(key=THESPORTSDB_KEY)
        params = {"d": date_str}
        try:
            js = safe_request_json(url, params=params)
            if not js:
                continue
            events = js.get("events") or []
            for e in events:
                # e contains dateEvent and strTime usually; some fields can be None
                date_event = e.get("dateEvent")
                time_event = e.get("strTime") or e.get("strTimeLocal") or ""
                league = e.get("strLeague") or ""
                sport = e.get("strSport") or ""
                title = e.get("strEvent") or f"{e.get('strHomeTeam','?')} vs {e.get('strAwayTeam','?')}"
                home = e.get("strHomeTeam") or ""
                away = e.get("strAwayTeam") or ""

                # filter by league keywords OR by sport tags (e.g. 'Soccer','Tennis','Motorsport','American Football')
                matches_keyword = any(k.lower() in (league + title).lower() for k in SPORT_LEAGUE_KEYWORDS)
                # allow important sports too
                allowed_sport = sport.lower() in ("soccer","football","tennis","motorsport","american football","basketball","ice hockey","baseball")

                if not (matches_keyword or allowed_sport):
                    continue

                # build datetime
                try:
                    if not date_event:
                        continue
                    if time_event:
                        dt_naive = datetime.strptime(f"{date_event} {time_event}", "%Y-%m-%d %H:%M")
                    else:
                        # fallback: treat midnight unknown time
                        dt_naive = datetime.strptime(date_event + " 00:00", "%Y-%m-%d %H:%M")
                    # TheSportsDB times are usually in the event's local TZ; we will localize as UTC then convert
                    # (this is a pragmatic approach for a prototype)
                    dt_utc = pytz.utc.localize(dt_naive)
                    dt_local = dt_utc.astimezone(TARGET_TZ)
                    if now <= dt_local <= (now + timedelta(hours=24)):
                        all_events.append({
                            "title": title,
                            "league": league,
                            "sport": sport,
                            "home": home,
                            "away": away,
                            "start": dt_local,
                            "end": dt_local + timedelta(hours=2),
                            "channel": e.get("strTVStation") or ""
                        })
                except Exception:
                    continue
        except Exception:
            continue

    if not all_events:
        return pd.DataFrame(columns=["title","league","sport","home","away","start","end","channel"])
    return pd.DataFrame(all_events)

# -------------------------
# Gemini: Kurzbeschreibung (max 10 Wörter)
# -------------------------
def generate_short_description(text, max_words=10):
    if not text:
        return ""
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"Formuliere eine sehr kurze (max {max_words} Wörter) Kurzbeschreibung für: {text}"
        res = model.generate_content(prompt)
        # res.text kann None sein; defensiv parsen
        txt = getattr(res, "text", None) or ""
        txt = txt.strip().replace("\n"," ")
        # reduce to max_words
        words = txt.split()
        return " ".join(words[:max_words])
    except Exception as e:
        # nicht kritisch, gib leeren String zurück
        return ""

# -------------------------
# STREAMLIT UI
# -------------------------
st.title("📺 Global TV Guide (EPG + Sport APIs)")
st.write("Quellen: konfigurierbare EPG-Feeds (z.B. EPGShare / iptv-org) + TheSportsDB für Sportevents. Kurzbeschreibung per Gemini.")

tab_ent, tab_sport, tab_debug = st.tabs(["🎭 Entertainment", "⚽ Sport", "⚙ Debug"])

# ENTERTAINMENT
with tab_ent:
    if st.button("🔄 Entertainment (24h) laden"):
        try:
            epg_df = load_epg_all()
            # filter next 24h
            now = datetime.now(TARGET_TZ)
            end = now + timedelta(hours=24)
            # falls start Spalte nicht vorhanden (sehr unwahrscheinlich), DataFrame ist vorbereitet
            if "start" not in epg_df.columns:
                st.warning("EPG liefert keine Startzeiten.")
                epg_df = pd.DataFrame(columns=["title","description","channel","start","end"])

            mask = (epg_df["start"] >= now) & (epg_df["start"] <= end)
            epg_24 = epg_df.loc[mask].copy()

            # Entertainment-Filter: entferne Sport-, News-, Film-Titel (grob)
            ent_mask = ~epg_24["title"].str.contains("News|Sport|Serie|Movie|Film|Thriller|Drama|Reportage|Nachrichten", case=False, na=False)
            ent_df = epg_24.loc[ent_mask].copy()

            if ent_df.empty:
                st.warning("Keine Entertainment-Programme in den nächsten 24 Stunden (laut EPG-Quellen).")
            else:
                # Kurzbeschreibung mit Gemini (asynchrones Chunking vermeiden — kleines Limit)
                ent_df["short_description"] = ent_df["title"].apply(lambda t: generate_short_description(t, max_words=10))
                # Anzeige
                display = ent_df[["start","end","title","channel","short_description","description"]].sort_values("start")
                # Formatierung von datetime
                display["start"] = display["start"].dt.strftime("%d.%m.%Y %H:%M")
                display["end"] = display["end"].dt.strftime("%d.%m.%Y %H:%M")
                st.dataframe(display.reset_index(drop=True), use_container_width=True)
        except Exception as e:
            st.error("Fehler beim Laden der Entertainment-Daten. Schau in die Logs.")
            st.exception(traceback.format_exc())

# SPORT
with tab_sport:
    if st.button("🏆 Sport (24h) laden"):
        try:
            sport_df = load_sport_events_thesportsdb()

            if sport_df.empty:
                st.warning("⚠️ Keine Sportevents in den nächsten 24 Stunden gefunden (TheSportsDB).")
                # Hinweis: das kann an TheSportsDB Coverage liegen. Prüfe Logs / API-Key.
            else:
                sport_df["short_description"] = sport_df["title"].apply(lambda t: generate_short_description(t, max_words=10))
                out = sport_df[["start","end","league","sport","home","away","channel","short_description"]].sort_values("start")
                out["start"] = out["start"].dt.strftime("%d.%m.%Y %H:%M")
                out["end"] = out["end"].dt.strftime("%d.%m.%Y %H:%M")
                st.dataframe(out.reset_index(drop=True), use_container_width=True)
        except Exception:
            st.error("Fehler beim Laden der Sportdaten. Schau in die Logs.")
            st.exception(traceback.format_exc())

# DEBUG
with tab_debug:
    st.write("EPG Quellen (konfiguriert):")
    for u in EPG_SOURCES:
        st.write("-", u)
    st.write("TheSportsDB key (first 4 chars):", THESPORTSDB_KEY[:4] if THESPORTSDB_KEY else "(leer)")
