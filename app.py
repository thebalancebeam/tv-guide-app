import streamlit as st
import google.generativeai as genai
import pandas as pd
from datetime import datetime, timedelta

# --- 1. SETUP ---
st.set_page_config(page_title="Global TV Guide", page_icon="📺", layout="wide")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("⚠️ API Key fehlt. Bitte in den Streamlit Secrets eintragen.")
    st.stop()

# --- 2. MODELLAUSWAHL ---

MODEL_CANDIDATES = [
    "gemini-1.5-flash",
    "gemini-1.5-flash-001",
    "gemini-1.5-pro",
    "gemini-1.5-pro-001",
    "gemini-pro"
]

def query_gemini(prompt_text):
    """
    Sichere Gemini-Abfrage ohne Tools, kompatibel mit Streamlit Cloud.
    Probiert mehrere Modelle durch, bis eines funktioniert.
    """
    last_error = ""

    for model_name in MODEL_CANDIDATES:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt_text)
            return response.text  # Erfolg
        except Exception as e:
            last_error = str(e)
            continue

    return f"Error: Alle Modelle fehlgeschlagen. Letzter Fehler: {last_error}"

# --- 3. PROMPT-LISTEN ---

LISTE_FUSSBALL = """
Suche den SPIELPLAN für HEUTE und MORGEN:
- Bundesliga (1. & 2.)
- Premier League
- La Liga
- Serie A
- Ligue 1
"""

LISTE_MIX = """
Suche den ZEITPLAN für HEUTE und MORGEN:
- Ski Alpin & Biathlon (Weltcup)
- Formel 1 (nur wenn ein Rennen oder Qualifying ist)
- NFL
- NBA
- NHL
"""

LISTE_ENT = """
Suche das PRIMETIME TV-PROGRAMM um 20:15 für HEUTE und MORGEN in:
- Deutschland
- UK
- USA

Fokus: Shows, Reality, Live-Events.
"""

# --- 4. LOGIK ---

def get_dates():
    now = datetime.utcnow() + timedelta(hours=1)
    return now.strftime("%d.%m.%Y"), (now + timedelta(days=1)).strftime("%d.%m.%Y")

def smart_parser(raw_text):
    """Extrahiert Zeilen im Format: A | B | C | D | E | F"""
    if not raw_text or "Error" in raw_text:
        return pd.DataFrame()

    data = []
    lines = raw_text.split('\n')

    for line in lines:
        clean_line = line.strip().replace("*", "")
        parts = clean_line.split('|')

        if len(parts) >= 4:
            part0 = parts[0].strip()
            if any(c.isdigit() for c in part0):
                row = [p.strip() for p in parts]
                while len(row) < 6: 
                    row.append("-")
                data.append(row[:6])

    if data:
        cols = ["Datum", "Uhrzeit", "Sportart", "Wettbewerb", "Event / Titel", "Sender"]
        return pd.DataFrame(data, columns=cols)
    else:
        return pd.DataFrame()

# --- 5. FRONTEND ---

st.title("🌍 Live TV Guide (Stable Gemini Mode)")
st.caption(f"Datum: {get_dates()[0]} | Modell-Auto-Auswahl")

tab_sport, tab_ent, tab_debug = st.tabs(["⚽️ SPORT", "🎤 ENTERTAINMENT", "⚙️ DEBUG"])

# === SPORT ===
with tab_sport:
    if st.button("Lade Sportdaten", key="btn_s"):
        with st.spinner("Gemini lädt aktuelle Sportereignisse..."):

            today, tomorrow = get_dates()

            base_prompt = f"""
            Du bist ein professioneller TV-Guide.
            Zeitraum: {today} und {tomorrow}.
            Gib die Daten in strukturiertem Listenformat zurück.
            """

            format_instruction = """
            FORMAT:
            DD.MM.YYYY | UHRZEIT | SPORTART | WETTBEWERB | EVENT/PAARUNG | SENDER

            WICHTIG:
            - KEIN Fließtext
            - KEINE Einleitung
            - NUR die Liste
            """

            raw_foot = query_gemini(base_prompt + LISTE_FUSSBALL + format_instruction)
            raw_mix = query_gemini(base_prompt + LISTE_MIX + format_instruction)

            st.session_state['raw_foot'] = raw_foot
            st.session_state['raw_mix'] = raw_mix

            df = smart_parser(raw_foot + "\n" + raw_mix)

            if not df.empty:
                try: 
                    df = df.sort_values(by=["Datum", "Uhrzeit"])
                except:
                    pass

                st.success(f"{len(df)} Events gefunden.")
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Event / Titel": st.column_config.TextColumn("Match", width="large"),
                        "Wettbewerb": st.column_config.TextColumn("Liga", width="medium"),
                    }
                )
            else:
                st.warning("Keine strukturierten Daten gefunden.")

# === ENTERTAINMENT ===
with tab_ent:
    if st.button("Lade Entertainment", key="btn_e"):
        with st.spinner("Gemini lädt Primetime-Shows..."):

            today, tomorrow = get_dates()

            prompt = f"""
            Du bist ein professioneller TV-Guide.
            Zeitraum: {today} und {tomorrow}.
            Thema: {LISTE_ENT}

            FORMAT:
            DD.MM.YYYY | UHRZEIT | LAND | GENRE | TITEL | SENDER

            Nur Listenformat. Keine Beschreibung, keine Einleitung.
            """

            raw_ent = query_gemini(prompt)
            st.session_state['raw_ent'] = raw_ent

            df = smart_parser(raw_ent)

            if not df.empty:
                df.columns = ["Datum", "Uhrzeit", "Land", "Genre", "Titel", "Sender"]
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("Keine strukturierten Entertainment-Daten gefunden.")

# === DEBUG ===
with tab_debug:
    st.write("🔍 Rohdaten Debug:")

    if 'raw_foot' in st.session_state:
        with st.expander("⚽ Fußball RAW"):
            st.text(st.session_state['raw_foot'])

    if 'raw_mix' in st.session_state:
        with st.expander("🎿 Mix Sport RAW"):
            st.text(st.session_state['raw_mix'])

    if 'raw_ent' in st.session_state:
        with st.expander("🎤 Entertainment RAW"):
            st.text(st.session_state['raw_ent'])
