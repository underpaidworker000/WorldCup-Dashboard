import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import pytz

# --- Configuration & Styling ---
st.set_page_config(
    page_title="World Cup 2026 Prediction Dashboard",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for modern dark theme aesthetics
st.markdown("""
<style>
    /* Dark Theme Optimization */
    .stApp {
        background-color: #0e1117;
        color: #fafafa;
    }
    .metric-card {
        background: linear-gradient(145deg, #1e222b, #191c24);
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        margin-bottom: 20px;
        border: 1px solid #2d3340;
        transition: transform 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
    }
    .live-match {
        border: 2px solid #ff4b4b;
        box-shadow: 0 0 15px rgba(255, 75, 75, 0.4);
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0% { box-shadow: 0 0 15px rgba(255, 75, 75, 0.4); }
        50% { box-shadow: 0 0 25px rgba(255, 75, 75, 0.7); }
        100% { box-shadow: 0 0 15px rgba(255, 75, 75, 0.4); }
    }
    .team-name {
        font-size: 1.5rem;
        font-weight: 700;
        color: #ffffff;
    }
    .score {
        font-size: 2.5rem;
        font-weight: 800;
        color: #00ffaa;
        text-align: center;
    }
    .elapsed {
        color: #ff4b4b;
        font-weight: bold;
        text-align: center;
        margin-bottom: 15px;
    }
    .live-dot {
        height: 10px;
        width: 10px;
        background-color: #ff4b4b;
        border-radius: 50%;
        display: inline-block;
        margin-right: 5px;
        animation: blinker 1s linear infinite;
    }
    @keyframes blinker {
        50% { opacity: 0; }
    }
    .probability-bar {
        height: 8px;
        border-radius: 4px;
        background-color: #333;
        margin-top: 10px;
        overflow: hidden;
        display: flex;
    }
    .prob-home { background-color: #00ffaa; }
    .prob-draw { background-color: #888888; }
    .prob-away { background-color: #ff4b4b; }
    .odds-display {
        font-size: 0.85rem;
        color: #cccccc;
        margin-top: -10px;
        margin-bottom: 10px;
        text-align: center;
        background-color: #161920;
        padding: 5px;
        border-radius: 4px;
        border: 1px solid #333;
    }
</style>
""", unsafe_allow_html=True)

# --- Data Pipelines ---

@st.cache_data(ttl=86400)
def fetch_elo_ratings():
    """Scrape Eloratings.net for current team ratings."""
    url = "https://www.eloratings.net/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    ratings = {}
    try:
        tsv_url = "https://www.eloratings.net/World.tsv"
        response = requests.get(tsv_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        for line in response.text.split('\n'):
            parts = line.split('\t')
            if len(parts) >= 3:
                team_name = parts[1].strip()
                try:
                    rating = float(parts[2].strip())
                    ratings[team_name] = rating
                except ValueError:
                    continue
                    
        if not ratings:
            raise ValueError("TSV parsing yielded no ratings.")
            
    except Exception as e:
        ratings = {
            "Argentina": 2140, "France": 2110, "Spain": 2040, "England": 2020,
            "Brazil": 2010, "Portugal": 2000, "Netherlands": 1980, "Belgium": 1950,
            "USA": 1800, "Mexico": 1780, "Germany": 1940, "Italy": 1930
        }
    return ratings

def fetch_world_cup_matches():
    """Fetch live and upcoming matches from Football-Data.org."""
    try:
        api_key = st.secrets["FOOTBALL_DATA_API_KEY"]
    except Exception:
        st.error("FOOTBALL_DATA_API_KEY not found in secrets. Please configure your API key in .streamlit/secrets.toml.")
        return []

    url = "https://api.football-data.org/v4/competitions/2000/matches"
    headers = {
        "X-Auth-Token": api_key
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            st.error(f"Football-Data.org API Error (HTTP {response.status_code}): {response.text}")
            return []
            
        data = response.json()
        matches = data.get("matches", [])
        return matches
    except Exception as e:
        st.error(f"Connection Error: Failed to fetch matches from Football-Data.org: {e}")
        return []

@st.cache_data(ttl=3600)
def fetch_market_odds():
    """Fetch live market odds from The Odds API."""
    try:
        api_key = st.secrets.get("THE_ODDS_API_KEY")
        if not api_key:
            return {}
    except Exception:
        return {}

    url = f"https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds/?apiKey={api_key}&regions=eu,us&markets=h2h&oddsFormat=decimal"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return {}
            
        data = response.json()
        odds_dict = {}
        
        for event in data:
            home = event.get('home_team')
            away = event.get('away_team')
            bookmakers = event.get('bookmakers', [])
            
            if bookmakers:
                # Use the first available bookmaker for simplicity
                market = bookmakers[0].get('markets', [])
                if market:
                    outcomes = market[0].get('outcomes', [])
                    
                    h_odd, d_odd, a_odd = None, None, None
                    for out in outcomes:
                        if out['name'] == home: h_odd = out['price']
                        elif out['name'] == away: a_odd = out['price']
                        elif out['name'] == 'Draw': d_odd = out['price']
                        
                    if h_odd and d_odd and a_odd:
                        h_imp = 1 / h_odd
                        d_imp = 1 / d_odd
                        a_imp = 1 / a_odd
                        total = h_imp + d_imp + a_imp
                        
                        odds_dict[f"{home}-{away}"] = {
                            "home_prob": h_imp / total,
                            "draw_prob": d_imp / total,
                            "away_prob": a_imp / total,
                            "home_odd": h_odd,
                            "draw_odd": d_odd,
                            "away_odd": a_odd
                        }
        return odds_dict
    except Exception:
        return {}

def get_match_odds(home_team, away_team, market_odds):
    """Fuzzy matching to align team names between data providers."""
    key = f"{home_team}-{away_team}"
    if key in market_odds:
        return market_odds[key]
        
    for m_key, odds in market_odds.items():
        if '-' in m_key:
            m_home, m_away = m_key.split('-', 1)
            # Basic partial string match
            if (m_home in home_team or home_team in m_home) and (m_away in away_team or away_team in m_away):
                return odds
    return None

# --- Mathematical Modeling ---

def calculate_win_probability(home_rating, away_rating):
    """Calculate Elo win probabilities."""
    home_rating_adjusted = home_rating + 100
    dr = home_rating_adjusted - away_rating
    
    we_home = 1 / (10 ** (-dr / 400) + 1)
    we_away = 1 - we_home
    
    return we_home, we_away

# --- UI Layout ---

def render_match_card(match, elo_ratings, market_odds, elo_weight):
    home_team_data = match.get("homeTeam", {})
    away_team_data = match.get("awayTeam", {})
    
    home_team = home_team_data.get("shortName") or home_team_data.get("name", "TBD")
    away_team = away_team_data.get("shortName") or away_team_data.get("name", "TBD")
    
    score_data = match.get("score", {}).get("fullTime", {})
    home_goals = score_data.get("home") if score_data.get("home") is not None else "-"
    away_goals = score_data.get("away") if score_data.get("away") is not None else "-"
    
    status = match.get("status", "SCHEDULED")
    
    is_live = status in ["IN_PLAY", "PAUSED"]
    live_class = " live-match" if is_live else ""
    
    minute = match.get("minute", "")
    if is_live:
        time_display = f"""<span class="live-dot"></span> LIVE {minute + "'" if minute else ""}"""
    elif status in ["TIMED", "SCHEDULED"]:
        utc_date_str = match.get("utcDate", "")
        try:
            est = pytz.timezone("US/Eastern")
            dt_utc = datetime.strptime(utc_date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
            dt_est = dt_utc.astimezone(est)
            time_display = dt_est.strftime("%I:%M %p EST")
        except Exception:
            time_display = status
    else:
        time_display = status
    
    # Elo Baseline
    home_elo = elo_ratings.get(home_team, 1500)
    away_elo = elo_ratings.get(away_team, 1500)
    elo_home_prob, elo_away_prob = calculate_win_probability(home_elo, away_elo)
    
    # Market & Hybrid Logic
    match_odds = get_match_odds(home_team, away_team, market_odds)
    
    odds_html = ""
    if match_odds:
        m_home_prob = match_odds["home_prob"]
        m_draw_prob = match_odds["draw_prob"]
        m_away_prob = match_odds["away_prob"]
        
        # Display Bookmaker Odds
        odds_html = f'''<div class="odds-display">
    <strong>Decimal Odds (Market):</strong> {home_team} <b>{match_odds["home_odd"]}</b> | Draw <b>{match_odds["draw_odd"]}</b> | {away_team} <b>{match_odds["away_odd"]}</b>
</div>'''
        
        # Blend probabilities
        w_elo = elo_weight / 100.0
        w_mkt = 1.0 - w_elo
        
        h_hybrid = (elo_home_prob * w_elo) + (m_home_prob * w_mkt)
        a_hybrid = (elo_away_prob * w_elo) + (m_away_prob * w_mkt)
        d_hybrid = (0.0 * w_elo) + (m_draw_prob * w_mkt) # Elo has 0% draw
        
        total = h_hybrid + a_hybrid + d_hybrid
        if total > 0:
            h_final = h_hybrid / total
            d_final = d_hybrid / total
            a_final = a_hybrid / total
        else:
            h_final, d_final, a_final = elo_home_prob, 0.0, elo_away_prob
    else:
        h_final = elo_home_prob
        d_final = 0.0
        a_final = elo_away_prob

    # Construct the bars and text
    st.markdown(f'''<div class="metric-card{live_class}">
<div style="display: flex; justify-content: space-between; align-items: center;">
    <span class="team-name">{home_team}</span>
    <span class="score">{home_goals} - {away_goals}</span>
    <span class="team-name">{away_team}</span>
</div>
<div class="elapsed">{time_display}</div>
{odds_html}
<div style="font-size: 0.9rem; color: #a0a0a0; margin-bottom: 5px;">
    Hybrid Prediction Model (Home / Draw / Away)
</div>
<div style="display: flex; justify-content: space-between; font-weight: bold; font-size: 0.85rem;">
    <span style="color: #00ffaa;">{h_final*100:.1f}%</span>
    <span style="color: #888888;">{d_final*100:.1f}%</span>
    <span style="color: #ff4b4b;">{a_final*100:.1f}%</span>
</div>
<div class="probability-bar">
    <div class="prob-home" style="width: {h_final*100}%;"></div>
    <div class="prob-draw" style="width: {d_final*100}%;"></div>
    <div class="prob-away" style="width: {a_final*100}%;"></div>
</div>
</div>''', unsafe_allow_html=True)


def main():
    st.title("🏆 Live FIFA World Cup 2026 Prediction Dashboard")
    st.markdown("Real-time match tracking and hybrid win probabilities based on live Elo ratings and Market Odds.")

    st.sidebar.header("Hybrid Engine Settings")
    elo_weight = st.sidebar.slider("Model Weighting (0% Market -> 100% Elo)", 0, 100, 50, help="100 means pure Elo Math. 0 means pure Market Sentiment.")
    
    st.sidebar.markdown("---")
    st.sidebar.header("Data Sources")
    st.sidebar.markdown("- **Match Data:** [Football-Data.org](https://www.football-data.org/)")
    st.sidebar.markdown("- **Ratings:** [Eloratings.net](https://www.eloratings.net/)")
    st.sidebar.markdown("- **Market Odds:** [The Odds API](https://the-odds-api.com/)")

    elo_ratings = fetch_elo_ratings()
    market_odds = fetch_market_odds()
    
    # Refresh button
    if st.button("Refresh Match Data"):
        st.rerun()
        
    all_matches = fetch_world_cup_matches()

    if not all_matches:
        st.info("No match data available at the moment.")
    else:
        # Separate today's matches from others (EST timezone)
        est = pytz.timezone("US/Eastern")
        today_date = datetime.now(est).date()
        today_str = today_date.strftime("%Y-%m-%d")
        
        today_matches = []
        other_matches = []
        
        def sort_status(match):
            status = match.get("status", "")
            if status in ["IN_PLAY", "PAUSED"]: return 0
            if status == "TIMED": return 1
            return 2

        for match in all_matches:
            utc_date_str = match.get("utcDate", "")
            try:
                dt_utc = datetime.strptime(utc_date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
                dt_est = dt_utc.astimezone(est)
                is_today = (dt_est.date() == today_date)
            except Exception:
                is_today = utc_date_str.startswith(datetime.utcnow().strftime("%Y-%m-%d"))

            if is_today:
                today_matches.append(match)
            else:
                other_matches.append(match)
                
        today_matches.sort(key=sort_status)
        other_matches.sort(key=sort_status)
        
        st.header(f"📅 Today's Matches ({today_str})")
        if not today_matches:
            st.write("No matches scheduled for today.")
        else:
            cols = st.columns(2)
            for i, match in enumerate(today_matches):
                with cols[i % 2]:
                    render_match_card(match, elo_ratings, market_odds, elo_weight)
                    
        st.header("🔮 Other Matches")
        if not other_matches:
            st.write("No other matches available.")
        else:
            cols = st.columns(2)
            for i, match in enumerate(other_matches):
                with cols[i % 2]:
                    render_match_card(match, elo_ratings, market_odds, elo_weight)

    with st.sidebar.expander("Current Elo Ratings (Top 10)"):
        sorted_ratings = sorted(elo_ratings.items(), key=lambda x: x[1], reverse=True)[:10]
        df = pd.DataFrame(sorted_ratings, columns=["Team", "Rating"])
        df.index = df.index + 1
        st.dataframe(df, use_container_width=True)

if __name__ == "__main__":
    main()
