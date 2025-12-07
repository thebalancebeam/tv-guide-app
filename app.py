import streamlit as st
import google.generativeai as genai
import pandas as pd
from datetime import datetime, timedelta
import time

# --- 1. SETUP & KONFIGURATION ---
st.set_page_config(page_title="Ultimate Live Guide", page_icon="📺", layout="wide")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("⚠️ API Key fehlt. Bitte in den Streamlit Secrets eintragen.")
    st.stop()

# --- 2. ROBUSTE MODELL-VERBINDUNG ---
# Wir probieren alle Varianten durch, bis eine funktioniert und Search unterstützt
MODEL_CANDIDATES = [
    "gemini-1.5-flash-001",
    "gemini-1.5-flash",
    "gemini-1.5-pro-001",
    "gemini-1.5-pro"
]

def get_live_data(prompt_topic, region_context="DACH (Deutschland, Österreich, Schweiz)"):
    """
    Verbindet sich mit Gemini + Google Search Tool.
    Gibt den Rohtext zurück.
    """
    today = datetime.now().strftime("%d.%m.%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
    
    # Der Prompt ist das Wichtigste: Er zwingt die KI zur Recherche der SENDER.
    full_prompt = f"""
    Du bist ein TV-Guide-Experte. Nutze das Google Search Tool, um ECHTZEIT-DATEN zu finden.
    Datum: HEUTE ({today}) und MORGEN ({tomorrow}).
    Ziel-Region für TV-Sender: {region_context}.
    
    AUFGABE:
    Recherchiere die genauen Sendezeiten und TV-SENDER für:
    {prompt_topic}
    
    WICHTIGE REGELN FÜR DIE AUSGABE:
    1. Suche gezielt nach Sendern wie Sky, DAZN, ORF, ARD/ZDF, BBC, ESPN (je nach Region).
    2. Wenn ein Spiel/Event nicht im TV läuft, schreibe "Stream" oder "-".
    3. Gib mir die Daten als TABELLE im Format:
       DATUM | UHRZEIT | SPORTART/GENRE | EVENT / TITEL | SENDER
    4. Nutze "|" als Trennzeichen.
    5. Sei präzise. Erfinde nichts.
    """
    
    last_error = ""
    
    for model_name in MODEL_CANDIDATES:
        try:
            model = genai.GenerativeModel(model_name)
            # Wir aktivieren das Search Tool
            response = model.generate_content(
                full_prompt,
                tools='google_search_retrieval'
            )
            return response.text
        except Exception as e:
            last_error = str(e)
            continue # Nächster Versuch
            
    return f"ERROR: Keine Verbindung möglich. Details: {last_error}"

def parse_to_dataframe(raw_text):
    """
    Versucht, den Text in eine Tabelle zu wandeln.
    Wenn das nicht klappt, geben wir None zurück (und zeigen den Text roh an).
    """
    try:
        data = []
        lines = raw_text.split('\n')
        for line in lines:
            # Bereinigung
            line = line.strip().replace("*", "")
            if "|" in line:
                parts = [p.strip() for p in line.split('|')]
                # Wir brauchen mind. 4 Spalten (Datum, Zeit, Event, Sender)
                if len(parts) >= 4:
                    # Header ignorieren (wenn "Datum" im Text steht)
                    if "Datum" in parts[0] or "---" in parts[0]:
                        continue
                    # Check ob Datum halbwegs valide aussieht (Zahl enthalten)
                    if any(c.isdigit() for c in parts[0]):
                        # Auffüllen auf 5 Spalten
                        while len(parts) < 5: parts.append("-")
                        data.append(parts[:5])
        
        if data:
            return pd.DataFrame(data, columns=["Datum", "Uhrzeit", "Kategorie", "Event / Titel", "Sender"])
        return None
    except:
        return None

# --- 3. FRONTEND ---

st.title("📺 Live TV & Stream Guide")
st.caption("Powered by Google Search Grounding")

tab_sport, tab_ent = st.tabs(["⚽️ SPORT (Live)", "🎬 ENTERTAINMENT (Prime Time)"])

# === TAB SPORT ===
with tab_sport:
    st.write("Fokus: Top-Ligen Fußball, F1, Wintersport.")
    if st.button("🔴 LIVE-CHECK SPORT STARTEN", key="btn_s"):
        
        with st.status("Recherchiere TV-Rechte & Spielpläne...", expanded=True) as status:
            
            # 1. Fußball Top Ligen
            st.write("Suche Fußball (Bundesliga, PL, La Liga)...")
            prompt_foot = """
            Spielplan für HEUTE und MORGEN für:
            - 1. Bundesliga & 2. Bundesliga (Deutschland)
            - Österreichische Bundesliga
            - Premier League (UK)
            - La Liga (Spanien), Serie A (Italien)
            Suche explizit nach TV-Sendern in DACH (Sky, DAZN, Sat.1, ORF).
            """
            raw_foot = get_live_data(prompt_foot)
            
            # 2. Motorsport & Winter
            st.write("Suche Motorsport & Wintersport...")
            prompt_mix = """
            Zeitplan für HEUTE und MORGEN für:
            - Wintersport: Ski Alpin, Biathlon (Weltcup).
            - Motorsport: Formel 1, MotoGP.
            - US Sport: NFL (aktuelle Spiele).
            """
            raw_mix = get_live_data(prompt_mix)
            
            status.update(label="Daten empfangen!", state="complete", expanded=False)

        # Verarbeitung & Anzeige
        st.subheader("📅 Ergebnisse")
        
        # Versuch 1: Als schöne Tabelle
        df_foot = parse_to_dataframe(raw_foot)
        df_mix = parse_to_dataframe(raw_mix)
        
        if df_foot is not None and not df_foot.empty:
            st.dataframe(df_foot, use_container_width=True, hide_index=True)
        else:
            # Fallback: Text anzeigen
            st.info("Konnte Fußball-Tabelle nicht formatieren, hier der Rohtext:")
            st.markdown(raw_foot)

        if df_mix is not None and not df_mix.empty:
            st.dataframe(df_mix, use_container_width=True, hide_index=True)
        else:
            st.info("Konnte Mix-Tabelle nicht formatieren, hier der Rohtext:")
            st.markdown(raw_mix)


# === TAB ENTERTAINMENT ===
with tab_ent:
    st.write("Fokus: Prime Time (20:15) in DE/AT, UK & US Highlights.")
    
    col1, col2 = st.columns(2)
    with col1:
        region = st.selectbox("Region wählen:", ["Deutschland / Österreich", "UK (Großbritannien)", "USA"])
    
    if st.button("🔴 LIVE-CHECK ENTERTAINMENT", key="btn_e"):
        with st.spinner(f"Suche TV-Programm für {region}..."):
            
            prompt_ent = f"""
            Suche das TV-Programm zur PRIME TIME (20:15 Uhr lokale Zeit) für HEUTE und MORGEN in {region}.
            Fokus auf:
            - Große Shows (Live-Events, Casting, Quiz)
            - Reality TV Highlights
            - Musik / Konzerte
            - Blockbuster Filme
            
            WICHTIG: Nenne unbedingt den SENDER (z.B. RTL, ProSieben, BBC One, ITV, NBC).
            """
            
            raw_ent = get_live_data(prompt_ent, region_context=region)
            
            # Anzeige
            df_ent = parse_to_dataframe(raw_ent)
            
            if df_ent is not None and not df_ent.empty:
                st.dataframe(df_ent, use_container_width=True, hide_index=True)
            else:
                st.markdown("### Programm-Übersicht")
                st.markdown(raw_ent)
