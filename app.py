import streamlit as st
import google.generativeai as genai
import pandas as pd
from datetime import datetime, timedelta
import io

# --- 1. SETUP & KONFIGURATION ---
st.set_page_config(page_title="Global TV Master", page_icon="🌍", layout="wide")

# API Key Check
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("⚠️ API Key fehlt. Bitte in den Streamlit Secrets eintragen.")
    st.stop()

# --- 2. DEINE DEFINITIONEN (Die "White-List") ---

COUNTRIES_ENT = "UK, Deutschland, Österreich, Schweiz, USA, Japan, Südkorea"

# Damit der Prompt nicht platzt, fassen wir zusammen, aber bleiben präzise
SPORT_LISTE = """
FUSSBALL:
- DE: 1. & 2. Bundesliga, DFB Pokal, Frauen-Bundesliga
- AT: 1. & 2. Bundesliga, ÖFB Pokal
- UK: Premier League, Championship, League One, League Two, National League, FA Cup, Carabao Cup, WSL (Frauen)
- ES: La Liga, Copa del Rey
- IT: Serie A, Coppa Italia
- FR: Ligue 1, Coupe de France
- INT: Champions League (M/F), Europa League, Conference League, Länderspiele (UEFA/FIFA), Arab Cup, Asian Cup
- ROW: MLS, Brasilien Serie A, Argentinien Primera, Saudi Pro League, Allsvenskan, Eredivisie, Belgien Pro League, Portugal Liga, Türkei Süper Lig, AFCON.

TENNIS: Alle ATP/WTA Turniere, Grand Slams.
WINTER: Ski Alpin (M/F), Biathlon, Skispringen, Langlauf.
MOTOR: Formel 1, Moto GP, Rallye.
US-SPORT: NFL, NBA, NHL, MLB.
"""

IGNORE_LIST = "Keine Serien, keine Filme (Movies), keine Nachrichten, keine Talkshows, keine Wiederholungen."

# --- 3. KI-FUNKTIONEN ---

def get_date_str():
    now = datetime.now()
    # Wir schauen immer für heute und morgen
    return now.strftime("%d.%m.%Y"), (now + timedelta(days=1)).strftime("%d.%m.%Y")

@st.cache_data(ttl=3600) # Cache 1 Stunde
def fetch_data(category):
    today, tomorrow = get_date_str()
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    if category == "Sport":
        prompt = f"""
        Rolle: TV-Sport-Datenbank. 
        Zeitraum: HEUTE ({today}) und MORGEN ({tomorrow}).
        Uhrzeiten: Zwingend in MEZ (Mitteleuropäische Zeit).
        
        Aufgabe: Suche Live-Übertragungen für folgende Wettbewerbe:
        {SPORT_LISTE}
        
        REGELN:
        1. Listung: Jedes Match einzeln. Nenne IMMER beide Teams (Heim vs Gast). Keine generischen Titel wie "Sonntagsspiel".
        2. Sender: Nenne den Sender in DE/AT/CH oder den internationalen Hauptsender (z.B. Sky, DAZN, ORF, ESPN, BBC).
        3. Ignoriere alles, was nicht live ist.
        
        FORMAT (CSV):
        Datum;Uhrzeit;Sportart;Wettbewerb;Heim;Gast;Sender
        """
    else: # Entertainment
        prompt = f"""
        Rolle: TV-Entertainment-Guide.
        Zeitraum: HEUTE ({today}) und MORGEN ({tomorrow}).
        Uhrzeiten: Zwingend in MEZ.
        Länder-Fokus: {COUNTRIES_ENT}.
        
        Aufgabe: Suche NUR nach:
        - Großen Prime-Time Shows (z.B. Wetten dass..?, Strictly Come Dancing)
        - Musik-Events & Konzerten
        - Exklusiven Dokus
        - Reality-TV Highlights (z.B. Jungle Camp, Bachelor - Finale/Start)
        - Korean/Japanese Variety Shows (auf Sendern wie KBS World, NHK, Arirang oder lokalen Sendern).
        
        VERBOTEN: {IGNORE_LIST}
        
        FORMAT (CSV):
        Datum;Uhrzeit;Land;Genre;Titel;Beschreibung;Sender
        """

    prompt += "\nGib mir NUR die CSV-Rohdaten zurück. Trennzeichen Semikolon (;). Kein Markdown."

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# --- 4. DATA CLEANING ---

def process_csv(raw_text, columns):
    clean = raw_text.replace("```csv", "").replace("```", "").strip()
    try:
        df = pd.read_csv(io.StringIO(clean), sep=";", names=columns, header=None, skiprows=1)
        return df
    except:
        return pd.DataFrame()

# --- 5. APP UI ---

st.title("🌍 Global Live Guide")
st.markdown(f"**Status:** {datetime.now().strftime('%H:%M')} MEZ | **Fokus:** {COUNTRIES_ENT}")

tab_sport, tab_ent = st.tabs(["⚽️ SPORT (Alle Ligen)", "🎤 ENTERTAINMENT (Weltweit)"])

# === TAB 1: SPORT ===
with tab_sport:
    if st.button("Lade Sport-Daten", key="btn_sport"):
        with st.spinner("Scanne weltweite Sport-Ligen..."):
            raw = fetch_data("Sport")
            if "Error" in raw:
                st.error(raw)
            else:
                cols = ["Datum", "Uhrzeit", "Sportart", "Wettbewerb", "Heim", "Gast", "Sender"]
                df_sport = process_csv(raw, cols)
                
                if not df_sport.empty:
                    # Filter
                    sports = st.multiselect("Sportart filtern:", df_sport["Sportart"].unique())
                    if sports:
                        df_sport = df_sport[df_sport["Sportart"].isin(sports)]
                    
                    st.dataframe(
                        df_sport, 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={
                            "Heim": st.column_config.TextColumn("Heimteam", width="medium"),
                            "Gast": st.column_config.TextColumn("Auswärtsteam", width="medium"),
                            "Wettbewerb": st.column_config.TextColumn("Liga/Cup", width="small"),
                        }
                    )
                else:
                    st.warning("Keine Daten gefunden oder Format-Fehler.")

# === TAB 2: ENTERTAINMENT ===
with tab_ent:
    if st.button("Lade Entertainment-Daten", key="btn_ent"):
        with st.spinner("Suche Shows in UK, USA, Asien & DACH..."):
            raw = fetch_data("Entertainment")
            if "Error" in raw:
                st.error(raw)
            else:
                cols = ["Datum", "Uhrzeit", "Land", "Genre", "Titel", "Beschreibung", "Sender"]
                df_ent = process_csv(raw, cols)
                
                if not df_ent.empty:
                    # Filter nach Land
                    countries = st.multiselect("Land filtern:", df_ent["Land"].unique())
                    if countries:
                        df_ent = df_ent[df_ent["Land"].isin(countries)]
                    
                    st.dataframe(
                        df_ent,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Titel": st.column_config.TextColumn("Show Name", width="medium"),
                            "Beschreibung": st.column_config.TextColumn("Info", width="large"),
                        }
                    )
                else:
                    st.warning("Keine passenden Shows gefunden.")
