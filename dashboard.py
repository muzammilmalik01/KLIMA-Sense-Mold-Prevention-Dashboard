"""
KLIMA Sense Dashboard
=====================
A real-time mold prevention monitoring dashboard built with Streamlit.

Connects to sensor_network.db populated by data_logger.py.
Displays environmental data, mold risk analysis, and system health.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import datetime
from typing import List, Dict

# -----------------------------------------------
# HELPER: Custom JS/HTML Table Renderer
# -----------------------------------------------
def render_custom_table(df):
    """Renders a Pandas DataFrame as a beautiful HTML table."""
    html = '<div style="overflow-x: auto; -webkit-overflow-scrolling: touch; width: 100%;">'
    html += '<table class="styled-table">'
    
    # Header
    html += "<thead><tr>"
    for col in df.columns:
        html += f"<th>{col}</th>"
    html += "</tr></thead>"
    
    # Body
    html += "<tbody>"
    for _, row in df.iterrows():
        html += "<tr>"
        for val in row:
            html += f"<td>{val}</td>"
        html += "</tr>"
    html += "</tbody></table></div>"
    
    st.markdown(html, unsafe_allow_html=True)

# ==========================================
# 1. CONSTANTS & CONFIGURATION
# ==========================================

# Page Config
st.set_page_config(
    page_title="Mold Prevention Dashboard",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Color Palette (Biophilic Theme)
# Color Palette (KLIMA Sense - Earthy/Organic)
COLORS = {
    "primary": "#B7F397",       # Fern Green (Primary Accent)
    "surface": "#272820",       # Bark (Card Surface)
    "background": "#1C1C16",    # Dark Loam (App Background)
    "alert": "#E2A69A",         # Terracotta (Alerts)
    "text_main": "#E5E2DA",     # Cream (Main Text)
    "text_dim": "#AAA89E",      # Muted Cream (derived)
    "success": "#B7F397",       # Fern Green
    "warning": "#E6CD85",       # Wheat/Sand (Derived for Warning)
    "danger": "#E2A69A",        # Terracotta
    "info": "#97F3E8"           # Soft Cyan (Derived)
}

# Sensor Health Status Codes (Must match Firmware/Logger)
HEALTH_CODES = {
    0: {"msg": "Optimal Operation", "level": "ok", "color": COLORS["success"]},
    1: {"msg": "Sensor Drift (>5%)", "level": "warning", "color": COLORS["warning"]},
    2: {"msg": "Bus Error (SDA/SCL)", "level": "critical", "color": COLORS["danger"]},
    3: {"msg": "Sensor Missing", "level": "critical", "color": COLORS["danger"]},
    4: {"msg": "Power Failure", "level": "critical", "color": COLORS["danger"]},
    5: {"msg": "Data Fetch Failed", "level": "critical", "color": COLORS["warning"]},
    6: {"msg": "Hardware Fault", "level": "critical", "color": COLORS["danger"]},
    7: {"msg": "Internal Error (Humi)", "level": "critical", "color": COLORS["danger"]},
    8: {"msg": "Internal Error (Both)", "level": "critical", "color": COLORS["danger"]},
    9: {"msg": "Temp Out of Range", "level": "warning", "color": COLORS["warning"]},
    10: {"msg": "Humi Out of Range", "level": "warning", "color": COLORS["warning"]},
    11: {"msg": "Garbage Data", "level": "warning", "color": COLORS["warning"]}
}

# Mapping Definitions
MOLD_RISK_MAP = {
    0: {"label": "Clean", "color": "#B7F397", "icon": "🛡️"},
    1: {"label": "Warning", "color": "#E6CD85", "icon": "⚠️"},
    2: {"label": "Alert", "color": "#E2A69A", "icon": "🍄"},
    3: {"label": "CRITICAL", "color": "#FF5252", "icon": "☣️"}
}

# ==========================================
# RECOMMENDATION CASES (0-6)
# ==========================================
RECOMMENDATION_CASES = {
    0: {
        "headline": "Optimal Air Quality",
        "message": "Everything looks great! The air is clean and dry. No mold risk right now.",
        "action": "Keep doing what you're doing.",
        "color": "#B7F397",  # Green
        "banner_color": None,  # No banner
        "icon": "✅"
    },
    1: {
        "headline": "Humidity Alert",
        "message": "Heads up: It's a bit too humid. Mold hasn't started yet, but conditions are becoming favorable for it.",
        "action": "Time for Stoßlüften (Shock Ventilation): Open windows wide for 5 minutes to swap the air quickly without cooling down the walls. Avoid tilting windows ('Kippen').",
        "color": "#E6CD85",  # Yellow
        "banner_color": "#E6CD85",
        "icon": "💧"
    },
    2: {
        "headline": "Dormant Risk",
        "message": "Good news: Mold growth has stopped for now. However, previous spores are still present (dormant).",
        "action": "Keep humidity low to prevent them from waking up. It is safe to clean visible spots now while they are dry.",
        "color": "#FFA726",  # Orange
        "banner_color": "#FFA726",
        "icon": "💤"
    },
    3: {
        "headline": "Active Growth Detected",
        "message": "Conditions are wet enough that mold is actively growing right now.",
        "action": "Reduce humidity immediately. Increase ventilation or use a dehumidifier.",
        "color": "#FF7043",  # Orange-red
        "banner_color": "#FF7043",
        "icon": "⚠️"
    },
    4: {
        "headline": "Critical Mold Risk",
        "message": "High mold index detected. A significant colony is likely established.",
        "action": "Immediate intervention needed. Aggressive dehumidification required. Check behind furniture and corners for damp spots.",
        "color": "#FF5252",  # Red
        "banner_color": "#FF5252",
        "icon": "🚨"
    },
    5: {
        "headline": "Condensation Risk",
        "message": "It is chilly and damp. This is the perfect recipe for condensation on cold walls, which feeds mold.",
        "action": "Heat & Ventilate: Warm the room up (target 19–20°C). Warmer air holds more moisture and stops condensation. Don't tilt windows—it cools the walls. Open them fully for a short burst instead.",
        "color": "#64B5F6",  # Blue
        "banner_color": "#64B5F6",
        "icon": "❄️"
    },
    6: {
        "headline": "Improving",
        "message": "Great job! The mold index is dropping. Your ventilation efforts are working.",
        "action": "Stay the course until the risk hits zero.",
        "color": "#B7F397",  # Green
        "banner_color": None,  # No banner (positive)
        "icon": "📉"
    }
}

def get_mold_case(mold_index: float, growth_status: int, temp: float, humidity: float, rh_crit: float, prev_mold_index: float = None) -> int:
    """
    Determines the current mold risk case (0-6) based on environmental conditions.
    
    Parameters:
    - mold_index: Current mold growth index (0-6 scale)
    - growth_status: Growth status from sensor (0 = no growth, 1 = growth active)
    - temp: Current temperature in °C
    - humidity: Current relative humidity %
    - rh_crit: Critical humidity threshold from VTT model
    - prev_mold_index: Previous mold index for trend detection (optional)
    
    Returns: Case number 0-6
    """
    
    # CASE 5: Cold + humid (classic winter problem) - Check first as it's a special condition
    if temp < 16 and humidity > rh_crit:
        return 5
    
    # CASE 6: Declining mold (positive feedback)
    if prev_mold_index is not None and growth_status == 0 and mold_index > 0 and mold_index < prev_mold_index:
        return 6
    
    # CASE 4: Severe growth
    if growth_status == 1 and mold_index >= 3:
        return 4
    
    # CASE 3: Active growth (moderate)
    if growth_status == 1 and mold_index >= 1 and mold_index < 3:
        return 3
    
    # CASE 2: Dormant mold present
    if growth_status == 0 and mold_index > 0:
        return 2
    
    # CASE 1: Early warning (humidity above critical, or growth started with no mold yet)
    if growth_status == 1 and mold_index == 0:
        return 1
    if humidity > rh_crit and mold_index == 0:
        return 1
    
    # CASE 0: Ideal conditions
    return 0


# ==========================================
# 2. STYLING (CSS INJECTION)
# ==========================================

def inject_custom_css():
    st.markdown(f"""
    <style>
        /* Import Outfit as Google Sans fallback */
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@100;300;400;500;700;900&display=swap');
        
        /* Global Text Reset */
        html, body, [class*="css"], p, h1, h2, h3, h4, span, div {{
            font-family: 'Google Sans', 'Outfit', sans-serif !important;
            color: {COLORS['text_main']};
        }}
        
        /* App Background */
        .stApp {{
            background-color: {COLORS['background']};
        }}
        
        /* HEADER / BRANDING - STICKY */
        header {{visibility: hidden;}}
        
        .brand-header {{
            position: sticky;
            top: 0;
            z-index: 999;
            background-color: {COLORS['background']}; /* Ensure opacity */
            padding-bottom: 10px;
            border-bottom: 1px solid {COLORS['surface']};
            margin-bottom: 20px;
        }}
        
        /* Reduce Top Whitespace */
        .block-container {{
            padding-top: 1rem !important; /* Reduced further for sticky header */
        }}
        
        /* 
           METRIC CARD DESIGN (Dark Mode)
        */
        .metric-card {{
            background-color: {COLORS['surface']};
            border-radius: 16px; /* MD3 Standard */
            padding: 24px;
            border: 1px solid rgba(255,255,255,0.05); /* Subtle white border */
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            position: relative;
            overflow: hidden;
        }}
        /* Green Accent Line on Left */
        .metric-card::before {{
            content: "";
            position: absolute;
            left: 0;
            top: 15%;
            height: 70%;
            width: 4px;
            background-color: {COLORS['primary']};
            border-radius: 0 4px 4px 0;
            opacity: 0.7;
        }}
        
        .metric-card:hover {{
            border-color: {COLORS['primary']}55;
            box-shadow: 0 0 20px {COLORS['primary']}22;
        }}
        
        .metric-icon {{
            font-size: 1.5rem;
            color: {COLORS['primary']};
            margin-bottom: 8px;
        }}
        .metric-label {{
            font-size: 0.75rem;
            font-weight: 500;
            color: {COLORS['text_dim']} !important;
            text-transform: uppercase;
            letter-spacing: 0.15em;
        }}
        
        .metric-value {{
            font-size: 2.8rem;
            font-weight: 300; /* Thin font for elegance */
            color: #FFFFFF;
            line-height: 1.1;
        }}
        .metric-delta {{
            font-size: 0.85rem;
            font-weight: 400;
            display: flex;
            align-items: center;
            gap: 4px;
            margin-top: 12px;
            opacity: 0.9;
        }}

        /* REC CARD */
        .rec-card {{
            background: linear-gradient(145deg, {COLORS['surface']} 0%, #1A1E23 100%);
            border-radius: 24px;
            padding: 24px;
            border: 1px solid rgba(255,255,255,0.05);
            margin-bottom: 24px;
        }}
        .rec-title {{
            font-weight: 500;
            font-size: 1.2rem;
            color: {COLORS['primary']} !important;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        
        /* CHAT BUBBLE */
        .chat-bubble {{
            background-color: #1A1D21;
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 10px;
            border: 1px solid rgba(255,255,255,0.03);
            border-left-width: 3px;
        }}
        .chat-time {{
            color: {COLORS['text_dim']};
        }}
        
        /* 
           TABS CUSTOMIZATION 
           Style: Round Pills with Green Active State 
        */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 12px;
            background-color: transparent;
            padding: 10px 0;
            border: none;
        }}
        .stTabs [data-baseweb="tab"] {{
            height: 44px;
            border-radius: 30px; /* Fully Round */
            padding: 0 24px;
            font-weight: 500;
            color: {COLORS['text_dim']};
            background-color: {COLORS['surface']}; /* Dark background for inactive */
            border: 1px solid rgba(255,255,255,0.1);
            transition: all 0.2s;
        }}
        .stTabs [data-baseweb="tab"] p {{
            color: {COLORS['text_dim']} !important;
        }}
        /* Active Tab */
        .stTabs [aria-selected="true"] {{
            background-color: {COLORS['primary']} !important; /* Fern Green */
            color: #516b42 !important; /* Dark Forest Green for Contrast */
            box-shadow: 0 0 15px {COLORS['primary']}66; /* Green Glow */
            border: none !important;
            font-weight: 700;
        }}
        /* Remove Default Streamlit Underline/Border/Highlight decoration */
        .stTabs [data-baseweb="tab-border"],
        .stTabs [data-baseweb="tab-highlight"] {{
            display: none !important;
            background: none !important;
            height: 0 !important;
        }}
        /* Remove any remaining underlines */
        .stTabs [role="tablist"] {{
            border-bottom: none !important;
        }}
        .stTabs button[data-baseweb="tab"]::after {{
            display: none !important;
        }}
        
        /* 
           PILLS / CHIPS CUSTOMIZATION 
           Using correct Streamlit data-testid selectors
        */
        
        /* Inactive Room Pills */
        button[data-testid="stBaseButton-pills"] {{
            background-color: {COLORS['surface']} !important;
            color: {COLORS['text_dim']} !important;
            border: 1px solid rgba(255,255,255,0.1) !important;
            border-radius: 30px !important;
            font-weight: 500 !important;
        }}
        button[data-testid="stBaseButton-pills"] p {{
            color: {COLORS['text_dim']} !important;
        }}
        
        /* Active Room Pills - Green Style */
        button[data-testid="stBaseButton-pillsActive"] {{
            background-color: {COLORS['primary']} !important;
            color: #1D3D1D !important;
            border: none !important;
            border-radius: 30px !important;
            box-shadow: 0 0 15px {COLORS['primary']}66 !important;
            font-weight: 600 !important;
        }}
        button[data-testid="stBaseButton-pillsActive"] p {{
            color: #1D3D1D !important;
            font-weight: 600 !important;
        }}
        
        /* Tab Text - Ensure dark text on green background */
        button[data-baseweb="tab"][aria-selected="true"] p {{
            color: #1D3D1D !important;
            font-weight: 700 !important;
        }}
        
        /* Remove focus rings from pills */
        button[data-testid="stBaseButton-pills"]:focus,
        button[data-testid="stBaseButton-pills"]:focus-visible,
        button[data-testid="stBaseButton-pillsActive"]:focus,
        button[data-testid="stBaseButton-pillsActive"]:focus-visible {{
            outline: none !important;
        }}
        button[data-testid="stBaseButton-pillsActive"]:focus,
        button[data-testid="stBaseButton-pillsActive"]:focus-visible {{
            box-shadow: 0 0 15px {COLORS['primary']}66 !important;
        }}

        /* CUSTOM HTML TABLE STYLING (.styled-table) */
        .styled-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
            font-family: 'Google Sans', 'Outfit', sans-serif;
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.05); 
        }}
        .styled-table thead tr {{
            background-color: {COLORS['surface']};
            color: {COLORS['text_dim']};
            text-align: left;
            font-weight: 700;
            text-transform: uppercase;
            font-size: 0.85rem;
            border-bottom: 2px solid rgba(255,255,255,0.05);
        }}
        .styled-table th, .styled-table td {{
            padding: 12px 15px;
        }}
        .styled-table tbody tr {{
            border-bottom: 1px solid rgba(255,255,255,0.02);
            background-color: {COLORS['surface']}; /* Bark */
        }}
        .styled-table tbody tr:last-of-type {{
            border-bottom: none;
        }}
        .styled-table tbody tr:hover {{
            background-color: rgba(183, 243, 151, 0.05); /* Slight Green Tint on Hover */
        }}
        .styled-table td {{
             color: {COLORS['text_main']};
             font-size: 0.95rem;
             font-weight: 300;
        }}

        /* BRANDING HEADER */
        .brand-header {{
            display: flex;
            justify-content: space-between; /* Move status to right */
            align-items: center;
            flex-wrap: wrap; /* Allow wrapping on mobile */
            gap: 10px;
            margin-bottom: 30px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding-bottom: 15px;
        }}
        .brand-logo {{
            font-size: 2.2rem;
            font-weight: 900;
            letter-spacing: -0.03em;
            color: {COLORS['text_main']}; /* White */
        }}
        .brand-logo .dot {{
            color: {COLORS['primary']};
        }}
        .brand-logo .punchline {{
            color: {COLORS['text_dim']};
            font-weight: 400;
            font-size: 1.0rem;
            margin-left: 10px;
            letter-spacing: normal;
            text-transform: none;
        }}
        .brand-subtitle {{
            font-size: 0.9rem;
            color: {COLORS['text_dim']};
            font-weight: 400;
            text-align: right;
        }}
        
        /* MOBILE RESPONSIVE STYLES */
        @media screen and (max-width: 600px) {{
            .brand-header {{
                flex-direction: column;
                align-items: flex-start;
                gap: 8px;
            }}
            .brand-logo {{
                font-size: 1.6rem;
            }}
            .brand-logo .punchline {{
                font-size: 0.85rem;
                margin-left: 5px;
            }}
            .brand-subtitle {{
                text-align: left;
                font-size: 0.8rem;
            }}
            /* Compact table on mobile */
            .styled-table th, .styled-table td {{
                padding: 8px 10px;
                font-size: 0.8rem;
            }}
            .styled-table thead tr {{
                font-size: 0.7rem;
            }}
            /* Card spacing on mobile */
            .metric-card {{
                margin-bottom: 12px;
            }}
        }}
        
        /* 
           TOAST STYLING - Material Design 3 Pills
        */
        div[data-testid="stToast"] {{
            background: linear-gradient(135deg, {COLORS['surface']} 0%, #1E1F1A 100%) !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            border-radius: 50px !important;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), 0 0 0 1px rgba(255,255,255,0.05) !important;
            padding: 8px 16px !important;
            backdrop-filter: blur(10px) !important;
        }}
        div[data-testid="stToast"] > div {{
            font-family: 'Outfit', 'Google Sans', sans-serif !important;
            font-weight: 500 !important;
            font-size: 0.9rem !important;
            color: {COLORS['text_main']} !important;
        }}
        /* Success toasts */
        div[data-testid="stToast"]:has([data-testid="stToastIconSuccess"]) {{
            border-left: 4px solid {COLORS['primary']} !important;
        }}
        /* Warning/Error toasts */
        div[data-testid="stToast"]:has([data-testid="stToastIconWarning"]),
        div[data-testid="stToast"]:has([data-testid="stToastIconError"]) {{
            border-left: 4px solid {COLORS['danger']} !important;
        }}
    </style>
    """, unsafe_allow_html=True)


# ==========================================
# 3. MOCK DATABASE & DATA SIMULATION
# ==========================================

import sqlite3

class RealDatabase:
    """Connects to the real sensor_network.db SQLite database."""
    
    def __init__(self, db_path="sensor_network.db"):
        self.db_path = db_path
        self.rooms = self._fetch_known_rooms()
        
    def _fetch_known_rooms(self) -> List[str]:
        """Dynamically fetch rooms seen in the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT room_name FROM readings UNION SELECT DISTINCT room_name FROM device_health")
            rooms = [row[0] for row in cursor.fetchall()]
            conn.close()
            # Sort rooms to ensure stable order for widget indices (prevents resets on reload)
            return sorted(rooms) if rooms else ["Living Room"] 
        except:
             return ["Living Room"] 
        
    def get_connection(self):
        """Creates a thread-safe connection."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def generate_current_readings(self) -> pd.DataFrame:
        """Fetches the latest reading for EACH room."""
        conn = self.get_connection()
        
        # Query to get the last reading per room, but BACKFILL Mold/Risk with last non-null value
        query = """
            SELECT 
                r.timestamp,
                r.node_ip,
                r.room_name,
                r.temperature,
                r.humidity,
                r.is_simulated,
                -- Subquery for last known non-null mold_index
                COALESCE((SELECT mold_index 
                 FROM readings r2 
                 WHERE r2.room_name = r.room_name 
                   AND r2.mold_index IS NOT NULL 
                 ORDER BY r2.timestamp DESC LIMIT 1), 0) as mold_index,
                -- Subquery for last known non-null risk_level
                COALESCE((SELECT risk_level 
                 FROM readings r3 
                 WHERE r3.room_name = r.room_name 
                   AND r3.risk_level IS NOT NULL 
                 ORDER BY r3.timestamp DESC LIMIT 1), 0) as risk_level,
                -- Subquery for last known non-null rh_crit
                COALESCE((SELECT rh_crit 
                 FROM readings r4 
                 WHERE r4.room_name = r.room_name 
                   AND r4.rh_crit IS NOT NULL 
                 ORDER BY r4.timestamp DESC LIMIT 1), 80.0) as rh_crit,
                -- Subquery for last known non-null growth_status
                COALESCE((SELECT growth_status 
                 FROM readings r5 
                 WHERE r5.room_name = r.room_name 
                   AND r5.growth_status IS NOT NULL 
                 ORDER BY r5.timestamp DESC LIMIT 1), 0) as growth_status
            FROM readings r
            INNER JOIN (
                SELECT room_name, MAX(timestamp) as max_ts
                FROM readings
                GROUP BY room_name
            ) latest ON r.room_name = latest.room_name AND r.timestamp = latest.max_ts
        """
        
        try:
            df = pd.read_sql_query(query, conn)
            
            # Ensure timestamp is datetime
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # ------------------------------------------------------------------
            # ROBUSTNESS: Ensure ALL known rooms have a row (even if simulated/empty)
            # to prevent dashboard crashes when selecting a room with no readings.
            # ------------------------------------------------------------------
            if not df.empty:
                existing_rooms = df['room_name'].astype(str).unique().tolist()
            else:
                existing_rooms = []
                # If df is empty, needs columns to be set for concatenation
                df = pd.DataFrame(columns=['timestamp', 'node_ip', 'room_name', 'temperature', 
                                           'humidity', 'mold_index', 'risk_level', 'growth_status', 'rh_crit', 'is_simulated'])
                
            missing_rooms = set(self.rooms) - set(existing_rooms)
            
            if missing_rooms:
                dummy_data = []
                now = datetime.datetime.now()
                for room in missing_rooms:
                    dummy_data.append({
                        "timestamp": now,
                        "node_ip": "N/A", # Will be filled by Health DF ideally, or N/A
                        "room_name": room,
                        "temperature": 0.0,
                        "humidity": 0.0,
                        "mold_index": 0.0,
                        "risk_level": 0, # Healthy/Offline
                        "growth_status": 0,
                        "rh_crit": 80.0,
                        "is_simulated": 0
                    })
                dummy_df = pd.DataFrame(dummy_data)
                df = pd.concat([df, dummy_df], ignore_index=True)

            # CLEANUP: Handle NaNs and Ensure Types
            df['risk_level'] = df['risk_level'].fillna(0).astype(int)
            df['growth_status'] = df['growth_status'].fillna(0).astype(int) if 'growth_status' in df.columns else 0
            df['temperature'] = df['temperature'].fillna(0.0)
            df['humidity'] = df['humidity'].fillna(0.0)
            df['mold_index'] = df['mold_index'].fillna(0.0)
            df['rh_crit'] = df['rh_crit'].fillna(80.0) if 'rh_crit' in df.columns else 80.0

            conn.close()
            return df
        except Exception as e:
            st.error(f"DB Error (Readings): {e}")
            conn.close()
            return pd.DataFrame()

    def get_system_health(self) -> pd.DataFrame:
        """Fetches latest health status for each room from device_health."""
        conn = self.get_connection()
        # Robust Logic: Join on MAX(ID) to ensure we get the absolute latest written record
        # NOT timestamp, which might be duplicated or drift.
        query = """
            SELECT h.* 
            FROM device_health h
            INNER JOIN (
                SELECT room_name, MAX(id) as max_id
                FROM device_health
                GROUP BY room_name
            ) latest ON h.id = latest.max_id
        """
        try:
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df
        except Exception as e:
            st.error(f"DB Error (Health): {e}")
            conn.close()
            return pd.DataFrame()

    def get_latest_alerts(self, limit=20) -> List[Dict]:
        """Fetches latest system_alerts."""
        conn = self.get_connection()
        # Return lowercase columns to match previous mock behavior
        query = f"""
            SELECT timestamp, room_name, event_type, message
            FROM system_alerts
            ORDER BY id DESC
            LIMIT {limit}
        """
        try:
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df.to_dict('records')
        except Exception as e:
            conn.close()
            return []

    def generate_historical_data(self) -> pd.DataFrame:
        """Fetches readings for charts (no time limit)."""
        conn = self.get_connection()
        query = """
            SELECT timestamp, room_name, temperature, humidity, mold_index
            FROM readings
            ORDER BY timestamp ASC
        """
        try:
            df = pd.read_sql_query(query, conn)
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                # Data Cleaning - Forward fill per room to avoid cross-room contamination
                df['mold_index'] = df.groupby('room_name')['mold_index'].transform(lambda x: x.ffill().fillna(0).clip(lower=0))
                df['temperature'] = df['temperature'].fillna(0)
                df['humidity'] = df['humidity'].fillna(0).clip(lower=0)
                
            conn.close()
            return df
        except Exception as e:
            conn.close()
            return pd.DataFrame()

    def get_latest_node_events(self) -> Dict[str, Dict]:
        """
        Returns the absolute latest event info for every node.
        Format: { 'ip': {'event': 'SENSOR_FAIL', 'msg': '...', 'ts': ...} }
        """
        conn = self.get_connection()
        query = """
            SELECT node_ip, event_type, message, timestamp
            FROM system_alerts
            WHERE id IN (
                SELECT MAX(id)
                FROM system_alerts
                GROUP BY node_ip
            )
        """
        try:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            
            events = {}
            for row in rows:
                events[row[0]] = {
                    'event': row[1], 
                    'msg': row[2],
                    'ts': row[3]
                }
            return events
        except Exception as e:
            conn.close()
            return {}

    def get_active_alerts(self) -> List[Dict]:
        """
        Returns a list of currently active alerts based on latest events.
        """
        events = self.get_latest_node_events()
        active = []
        for ip, data in events.items():
            # If the latest event for a node is a FAIL/LOST type, it's active
            if "FAIL" in data['event'] or "LOST" in data['event']:
                active.append({
                    "room": "Unknown", # We'd need to join to get room, but for now type matters
                    "node_ip": ip,
                    "event_type": data['event'],
                    "description": data['msg']
                })
        return active

    def get_node_states(self) -> Dict[str, str]:
        """
        Determines the current state of every node (sensors + server).
        Returns: { 'node_ip': 'online' | 'offline' }
        """
        # Reuse the events helper for consistency
        events = self.get_latest_node_events()
        states = {}
        for ip, data in events.items():
            evt = data['event']
            if evt in ["node_lost", "NODE_LOST", "SERVER_LOST"]:
                 states[ip] = "offline"
            else:
                 # Even SENSOR_FAIL means the node itself is online
                 states[ip] = "online"
        return states

    def get_gateway_status(self) -> bool:
        """Checks if the Gateway (Server) is currently online."""
        states = self.get_node_states()
        # If SERVER not in logs, assume online (default)
        return states.get('SERVER', 'online') == 'online'

    def get_new_alerts(self, last_id=0) -> List[Dict]:
        """Fetches alerts newer than last_id."""
        conn = self.get_connection()
        query = f"""
            SELECT id, timestamp, node_ip, room_name, event_type, message
            FROM system_alerts
            WHERE id > {last_id}
            ORDER BY id ASC
        """
        try:
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df.to_dict('records')
        except Exception as e:
            conn.close()
            return []
            
    def get_latest_alert_id(self) -> int:
        """Get the highest ID in system_alerts."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(id) FROM system_alerts")
            res = cursor.fetchone()[0]
            conn.close()
            return res if res else 0
        except:
            conn.close()
            return 0
            
    def get_gateway_last_seen(self):
        """Returns the timestamp of the last SERVER event."""
        conn = self.get_connection()
        query = "SELECT timestamp FROM system_alerts WHERE node_ip = 'SERVER' ORDER BY id DESC LIMIT 1"
        try:
            cursor = conn.cursor()
            cursor.execute(query)
            row = cursor.fetchone()
            conn.close()
            if row:
                return pd.to_datetime(row[0])
            return datetime.datetime.now() # Default to now if never seen (or fresh init)
        except:
            conn.close()
            return datetime.datetime.now()
    def has_data(self) -> bool:
        """Check if the database has any readings data."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM readings")
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0
        except:
            return False
    
    def db_exists(self) -> bool:
        """Check if the database file exists."""
        import os
        return os.path.exists(self.db_path)
    
    def get_node_uptime_data(self, node_ip: str, hours: int = 6) -> List[int]:
        """
        Get activity trend for a node over the last N hours.
        Returns list of activity levels (0-100) for mini trend line.
        """
        conn = self.get_connection()
        
        # Query device_health for sensors, system_alerts for SERVER
        if node_ip == "SERVER":
            query = f"""
                SELECT timestamp FROM system_alerts 
                WHERE node_ip = 'SERVER' 
                  AND timestamp >= datetime('now', 'localtime', '-{hours} hours')
                ORDER BY timestamp ASC
            """
        else:
            query = f"""
                SELECT timestamp FROM device_health 
                WHERE node_ip = ? 
                  AND timestamp >= datetime('now', 'localtime', '-{hours} hours')
                ORDER BY timestamp ASC
            """
        
        try:
            if node_ip == "SERVER":
                df = pd.read_sql_query(query, conn)
            else:
                df = pd.read_sql_query(query, conn, params=[node_ip])
            conn.close()
            
            if df.empty:
                return [0] * hours  # No data
            
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            now = datetime.datetime.now()
            
            # Count readings per hour, normalize to 0-100
            trend = []
            for h in range(hours):
                hour_start = now - datetime.timedelta(hours=hours-h)
                hour_end = now - datetime.timedelta(hours=hours-h-1)
                count = len(df[(df['timestamp'] >= hour_start) & (df['timestamp'] < hour_end)])
                # Normalize: expect ~6 readings/hour, cap at 100%
                level = min(100, int((count / 6) * 100)) if count > 0 else 0
                trend.append(level)
            
            return trend
            
        except Exception as e:
            conn.close()
            return [50] * hours  # Unknown state
    
    def get_daily_uptime_percentages(self, days: int = 7) -> List[dict]:
        """
        Calculate real daily uptime percentages based on device_health data.
        Returns list of {"date": datetime, "uptime_pct": float} for last N days.
        Uptime = (hours with at least 1 health reading / 24) * 100
        """
        conn = self.get_connection()
        
        query = f"""
            SELECT DATE(timestamp) as day, 
                   strftime('%H', timestamp) as hour,
                   COUNT(*) as readings
            FROM device_health 
            WHERE timestamp >= datetime('now', 'localtime', '-{days} days')
            GROUP BY DATE(timestamp), strftime('%H', timestamp)
            ORDER BY day ASC
        """
        
        try:
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            if df.empty:
                return []
            
            # Calculate uptime per day
            results = []
            for day in df['day'].unique():
                day_data = df[df['day'] == day]
                # Count hours with at least 1 reading
                hours_active = len(day_data['hour'].unique())
                # Calculate uptime percentage
                uptime_pct = (hours_active / 24) * 100
                results.append({
                    "date": datetime.datetime.strptime(day, "%Y-%m-%d"),
                    "uptime_pct": round(uptime_pct, 1)
                })
            
            return results
            
        except Exception as e:
            conn.close()
            return []

# Instantiate REAL Database
db = RealDatabase()


# ==========================================
# 4. COMPONENT FUNCTIONS
# ==========================================

def render_metric_card(icon, label, value, delta, color_hex=None):
    """
    Renders a Material-style tile using HTML/CSS.
    Refactored for "White Card" look.
    """
    # Determine Color for Delta
    if "Stable" in delta:
        delta_color = "#9E9E9E" # Grey
        arrow = "●"
    elif "+" in delta or "High" in str(value): # Logic dependent on context, simplified here
        delta_color = "#E53935" if "Risk" in label else "#43A047" 
        arrow = "↑"
    else:
        delta_color = "#43A047" if "Risk" in label else "#E53935"
        arrow = "↓"
        
    # Override for specific risk colors
    value_style = f"color: {color_hex};" if color_hex else ""
    
    html = f"""
    <div class="metric-card">
        <div class="metric-header">
            <div class="metric-icon">{icon}</div>
            <div class="metric-label">{label}</div>
        </div>
        <div class="metric-body">
            <div class="metric-value" style="{value_style}">{value}</div>
            <div class="metric-delta" style="color: {delta_color};">
                <span>{arrow}</span> {delta}
            </div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def get_relative_time_string(timestamp):
    """Converts datetime to relative time string (e.g., '5 minutes ago')."""
    now = datetime.datetime.now()
    diff = now - timestamp
    seconds = int(diff.total_seconds())
    minutes = seconds // 60
    
    if minutes < 1:
        return "Just now"
    elif minutes == 1:
        return "1 minute ago"
    elif minutes < 60:
        return f"{minutes} minutes ago"
    elif minutes < 120:
        return "1 hour ago"
    else:
        return timestamp.strftime("%H:%M:%S")


def render_aesthetic_topology(is_server_online=True, sensor_network_status="online"):
    """
    Renders a clean, non-diagram aesthetic flow: Sensor -> Server -> Pi.
    sensor_network_status: 'online' | 'degraded' (nodes lost) | 'sensor_failure' (sensor hardware issues)
    """
    
    # Dynamic Link Styles (Server <-> Pi)
    if is_server_online:
        link_color = "#FFD600" # Yellow/Gold matching Pi
        link_style = "solid"
        link_opacity = "1"
        server_border = "#00B0FF"
        server_shadow = "rgba(0,176,255,0.2)"
        server_bg = COLORS['surface']
        server_opacity = "1"
        link_icon = "➤"
    else:
        link_color = "#FF5252" # Red
        link_style = "dashed" 
        link_opacity = "0.5"
        server_border = "#FF5252"
        server_shadow = "rgba(255, 82, 82, 0.4)"
        server_bg = "#2F302A"
        server_opacity = "0.5"
        link_icon = "❌"

    # Sensor Node Styles - If server is down, sensors are unreachable
    if not is_server_online:
        # Unreachable - Server is offline
        sensor_bg = "#2A2828"
        sensor_border = "#FF5252"
        sensor_shadow = "none"
        sensor_opacity = "0.4"
        sensor_icon = "❓"
        arrow1_color = "#FF525266"
    elif sensor_network_status == "degraded":
        # Greyed out / Faded - Node is dead
        sensor_bg = "#2F302A" # Darker greyish
        sensor_border = "#555"
        sensor_shadow = "none"
        sensor_opacity = "0.5"
        sensor_icon = "📡"
        arrow1_color = "#555"
    elif sensor_network_status == "sensor_failure":
        # Orange / Warning - Sensor hardware failure
        sensor_bg = COLORS['surface']
        sensor_border = COLORS['warning']  # Orange border
        sensor_shadow = f"0 0 15px {COLORS['warning']}44"  # Orange glow
        sensor_opacity = "1"
        sensor_icon = "⚠️"
        arrow1_color = COLORS['warning']
    else:
        # Normal - All good
        sensor_bg = COLORS['surface']
        sensor_border = COLORS['primary']
        sensor_shadow = "0 0 15px rgba(0,224,150,0.2)"
        sensor_opacity = "1"
        sensor_icon = "📡"
        arrow1_color = COLORS['text_dim']

    html = f"""
<div style="display: flex; align-items: center; justify-content: center; gap: 15px; padding: 20px 0; flex-wrap: wrap;">
<!-- Sensor Node -->
<div style="text-align: center; opacity: {sensor_opacity};">
<div style="background-color: {sensor_bg}; padding: 20px; border-radius: 16px; border: 1px solid {sensor_border}; width: 120px; display: flex; align-items: center; justify-content: center; box-shadow: {sensor_shadow};">
<div style="font-size: 2rem;">{sensor_icon}</div>
</div>
<div style="margin-top: 10px; font-weight: 700; font-size: 0.9rem; color: #FFF;">Sensor Node</div>
<div style="color: {COLORS['text_dim']}; font-size: 0.8rem;">nRF52840</div>
</div>
<!-- Arrow 1 -->
<div style="color: {arrow1_color}; font-size: 1.5rem;">➤</div>
<!-- Server Node -->
<div style="text-align: center; opacity: {server_opacity};">
<div style="background-color: {server_bg}; padding: 20px; border-radius: 16px; border: 1px solid {server_border}; width: 120px; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 15px {server_shadow};">
<div style="font-size: 2rem;">🛰️</div>
</div>
<div style="margin-top: 10px; font-weight: 700; font-size: 0.9rem; color: #FFF;">Server Node</div>
<div style="color: {COLORS['text_dim']}; font-size: 0.8rem;">nRF52840</div>
</div>
<!-- Arrow 2 (Dynamic Status) -->
<div style="color: {link_color}; font-size: 1.5rem; text-decoration: {link_style} 2px;">{link_icon}</div>
<!-- Pi -->
<div style="text-align: center;">
<div style="background-color: {COLORS['surface']}; padding: 20px; border-radius: 16px; border: 1px solid #FFD600; width: 120px; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 15px rgba(255,214,0,0.2);">
<div style="font-size: 2rem;">🍓</div>
</div>
<div style="margin-top: 10px; font-weight: 700; font-size: 0.9rem; color: #FFF;">Raspberry Pi</div>
<div style="color: {COLORS['text_dim']}; font-size: 0.8rem;">Hub / Gateway</div>
</div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)


def render_gauge(value, title, min_val, max_val, color_ranges, current_risk=0):
    """Renders a highly aesthetic, minimal gauge."""
    
    # Determine bar color based on value/ranges if not explicitly set
    bar_color = COLORS['primary']
    for rng in color_ranges:
        if rng['range'][0] <= value <= rng['range'][1]:
            bar_color = rng['color']
            break
            
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = value,
        domain = {'x': [0.1, 0.9], 'y': [0.15, 1]},
        title = {'text': title.upper(), 'font': {'size': 11, 'color': COLORS['text_dim'], 'family': "Outfit"}},
        number = {'font': {'size': 24, 'color': "white", 'family': "Outfit", 'weight': 300}, 'suffix': "", 'valueformat': '.1f'},
        gauge = {
            'axis': {'range': [min_val, max_val], 'visible': False}, # Hide ugly axis
            'bar': {'color': bar_color, 'thickness': 0.7}, # Thick colored bar
            'bgcolor': "#1A1D21", # Dark track background
            'borderwidth': 0,
            'steps': [], # Clean look, no steps background
            'threshold': {
                'line': {'color': "white", 'width': 2},
                'thickness': 0.7,
                'value': value
            }
        }
    ))
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', 
        font={'family': "Outfit"},
        margin=dict(l=10, r=10, t=30, b=0), # Minimal margins
        height=180, # Slightly taller
        width=200, # Fixed width
        uirevision='constant', # Keeps state to reduce flicker
    )
    # Unique key based on title ONLY to prevent re-mounting (blinking) on data change
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'staticPlot': True}, key=f"gauge_{title}")

def render_diagnostic_node(room_name, ip, status, recommendation, last_seen, s1_code=0, s2_code=0, show_sensors=True, is_node_dead=False, s1_msg=None, s2_msg=None):
    """
    Detailed Diagnostic Card.
    Includes specific Sensor A/B status.
    is_node_dead: When True, sensors show '-' in grey (unknown state)
    s1_msg/s2_msg: Custom error messages for sensors (overrides code display)
    """
    is_error = status not in ["Online"]
    
    # Visual Mapping
    if status == "Node Died":
        card_border = COLORS['danger']  # Red border for dead node
        status_color = COLORS['danger']  # Red status
        icon = "💀"
        bg_col = "rgba(255, 82, 82, 0.1)"  # Red tint
    elif status == "Sensor Failure":
        card_border = COLORS['warning']  # Orange border for sensor failure
        status_color = COLORS['warning']  # Orange status
        icon = "⚠️"
        bg_col = f"rgba(230, 205, 133, 0.1)"  # Orange tint
    elif is_error:
        card_border = COLORS['danger']
        status_color = COLORS['danger']
        icon = "🚨"
        bg_col = "rgba(255, 82, 82, 0.1)"
    else:
        card_border = "rgba(255,255,255,0.05)"
        status_color = COLORS['success']
        icon = "✅"
        bg_col = COLORS['surface']

    # Sensor Status Helpers
    def get_sensor_display(code, name, node_dead=False, custom_msg=None):
        if node_dead:
            # Node is dead - we don't know sensor status
            return f'<span style="color: {COLORS["text_dim"]};">{name}: -</span>'
        if custom_msg:
            # Custom error message provided
            return f'<span style="color: {COLORS["warning"]}; font-weight:bold;">● {name}: {custom_msg}</span>'
        if code == 0: 
            return f'<span style="color: {COLORS["success"]};">● {name}: OK</span>'
        return f'<span style="color: {COLORS["warning"]}; font-weight:bold;">● {name}: ERR {code}</span>'

    s1_html = get_sensor_display(s1_code, "Sensor A", is_node_dead, s1_msg)
    s2_html = get_sensor_display(s2_code, "Sensor B", is_node_dead, s2_msg)
    
    # Conditional Render
    sensor_block = ""
    if show_sensors:
        sensor_block = f"""
<div style="margin-top: 12px; margin-bottom: 12px; font-size: 0.8rem; font-family: monospace; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 8px;">
<div style="display: flex; justify-content: space-between;">
<div>{s1_html}</div>
<div>{s2_html}</div>
</div>
</div>
"""

    html = f"""
<div style="background-color: {bg_col}; padding: 20px; border-radius: 16px; border: 1px solid {card_border}; margin-bottom: 20px;">
<div style="display: flex; justify-content: space-between; align-items: flex-start;">
<div>
<div style="font-weight: 900; font-size: 1.1rem; color: #FFF; margin-bottom: 4px;">{room_name}</div>
<div style="font-size: 0.8rem; color: {COLORS['text_dim']}; font-family: monospace;">{ip}</div>
</div>
<div style="text-align: right;">
<div style="font-size: 1.5rem;">{icon}</div>
</div>
</div>
{sensor_block}
<div style="padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.1);">
<div style="display: flex; justify-content: space-between; align-items: center;">
<div>
<div style="font-size: 0.75rem; color: {COLORS['text_dim']}; text-transform: uppercase;">Status</div>
<div style="color: {status_color}; font-weight: 700; font-size: 0.95rem;">{status}</div>
</div>
<div style="text-align: right;">
<div style="font-size: 0.75rem; color: {COLORS['text_dim']}; text-transform: uppercase;">Last Seen</div>
<div style="color: #FFF; font-weight: 500; font-size: 0.95rem;">{last_seen}</div>
</div>
</div>
<div style="margin-top: 10px; font-size: 0.85rem; color: {COLORS['text_main']};">
<span style="opacity: 0.7;">Recommendation:</span> {recommendation}
</div>
</div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)


def render_diagnostic_card_v2(node_name, node_ip, status, last_seen, uptime_data, 
                               node_type="sensor", s1_status=None, s2_status=None,
                               s1_code=0, s2_code=0, is_node_dead=False):
    """Material Design 3 styled diagnostic card - Google Home inspired."""
    
    # M3 Color mapping
    if status == "Unreachable":
        # Server is down, can't reach sensors
        status_text = "Unreachable"
        status_dot = "#888888"  # Grey
        status_bg = "rgba(136, 136, 136, 0.15)"
    elif status == "Node Died" or status == "Offline":
        status_text = "Offline"
        status_dot = COLORS['danger']
        status_bg = "rgba(255, 82, 82, 0.15)"
    elif status == "Sensor Failure":
        status_text = "Sensor Failure"  # Changed from 'Warning'
        status_dot = COLORS['warning']
        status_bg = "rgba(230, 205, 133, 0.15)"
    else:
        status_text = "Online"
        status_dot = COLORS['success']
        status_bg = "rgba(183, 243, 151, 0.15)"
    
    # Uptime is now 100% if online, 0% if offline (based on current status)
    if status == "Online":
        uptime_color = COLORS['success']
        uptime_label = "Active"
    elif status == "Sensor Failure":
        uptime_color = COLORS['warning']
        uptime_label = "Degraded"
    elif status == "Unreachable":
        uptime_color = "#888888"
        uptime_label = "Unknown"
    else:
        uptime_color = COLORS['danger']
        uptime_label = "Down"
    
    # Build sensor status pills (M3 chips style) - now with error messages
    sensor_html = ""
    if node_type == "sensor":
        def get_sensor_chip(name, code, custom_msg, dead):
            if dead:
                return f'<div style="background: rgba(255,255,255,0.05); padding: 6px 12px; border-radius: 20px; font-size: 0.75rem; color: {COLORS["text_dim"]};">{name}: --</div>'
            elif custom_msg:
                # Show short error message
                short_msg = custom_msg[:15] + "..." if len(custom_msg) > 15 else custom_msg
                return f'<div style="background: rgba(255, 180, 50, 0.15); padding: 6px 12px; border-radius: 20px; font-size: 0.75rem; color: {COLORS["warning"]};">⚠ {short_msg}</div>'
            elif code != 0:
                return f'<div style="background: rgba(255, 180, 50, 0.15); padding: 6px 12px; border-radius: 20px; font-size: 0.75rem; color: {COLORS["warning"]};">⚠ {name}: Err {code}</div>'
            else:
                return f'<div style="background: rgba(183, 243, 151, 0.12); padding: 6px 12px; border-radius: 20px; font-size: 0.75rem; color: {COLORS["success"]};">✓ {name}</div>'
        
        s1_chip = get_sensor_chip("Sensor A", s1_code, s1_status, is_node_dead)
        s2_chip = get_sensor_chip("Sensor B", s2_code, s2_status, is_node_dead)
        sensor_html = f'<div style="display: flex; gap: 8px; margin-top: 12px;">{s1_chip}{s2_chip}</div>'
    
    # Build activity trend section with mini line graph
    trend_bars = ""
    if uptime_data and len(uptime_data) > 0:
        bar_width = 100 / len(uptime_data)
        for i, level in enumerate(uptime_data):
            bar_height = max(3, level * 0.24)  # Scale to max 24px, min 3px
            bar_color = uptime_color if level > 50 else (COLORS['warning'] if level > 0 else "rgba(255,255,255,0.1)")
            trend_bars += f'<rect x="{i * bar_width + 1}%" width="{bar_width - 2}%" y="{24 - bar_height}px" height="{bar_height}px" fill="{bar_color}" rx="2"/>'
    else:
        # No data - show flat line
        trend_bars = f'<rect x="0" width="100%" y="21px" height="3px" fill="rgba(255,255,255,0.1)" rx="1"/>'
    
    uptime_html = f'<div style="margin-top: 16px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.06);"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;"><span style="font-size: 0.7rem; color: {COLORS["text_dim"]}; text-transform: uppercase;">Activity (6h)</span><span style="font-size: 0.8rem; font-weight: 600; color: {uptime_color};">{uptime_label}</span></div><svg width="100%" height="24" style="display: block;">{trend_bars}</svg></div>'

    
    # Header with status badge
    header_html = f'<div style="display: flex; justify-content: space-between; align-items: flex-start;"><div><div style="font-size: 1.1rem; font-weight: 600; color: {COLORS["text_main"]}; margin-bottom: 4px;">{node_name}</div><div style="font-size: 0.7rem; color: {COLORS["text_dim"]}; font-family: monospace;">{node_ip if len(node_ip) < 20 else node_ip[:18] + "..."}</div></div><div style="background: {status_bg}; padding: 4px 10px; border-radius: 12px; display: flex; align-items: center; gap: 6px;"><div style="width: 6px; height: 6px; border-radius: 50%; background: {status_dot};"></div><span style="font-size: 0.7rem; font-weight: 500; color: {status_dot};">{status_text}</span></div></div>'
    
    # Last seen footer
    footer_html = f'<div style="margin-top: 12px; display: flex; justify-content: space-between; align-items: center;"><span style="font-size: 0.75rem; color: {COLORS["text_dim"]};">Last seen</span><span style="font-size: 0.75rem; color: {COLORS["text_main"]}; font-weight: 500;">{last_seen}</span></div>'
    
    # Complete M3 card
    html = f'<div style="background: {COLORS["surface"]}; border-radius: 20px; padding: 20px; margin-bottom: 12px; border: 1px solid rgba(255,255,255,0.04);">{header_html}{sensor_html}{uptime_html}{footer_html}</div>'
    
    st.markdown(html, unsafe_allow_html=True)



# ==========================================
# 5. MAIN DASHBOARD LOGIC
# ==========================================

def render_glance_tab(db, update_room, current_readings_df, historical_df):
    # Pills Here (Above Content)
    # Note: default=... is ignored if key exists in state, which we handled above
    st.pills("Select Room:", db.rooms, selection_mode="single", key="pills_t1", default=st.session_state.current_room, on_change=update_room, args=("pills_t1",))
        
    selected_room = st.session_state.current_room # Use state

    st.markdown("<h3 style='font-weight: 900; letter-spacing: -0.02em;'>Room Overview</h3>", unsafe_allow_html=True)
    
    # Filter data
    # Safe fetch for room data
    room_readings = current_readings_df[current_readings_df["room_name"] == selected_room]
    if not room_readings.empty:
        room_data = room_readings.iloc[0]
    else:
        st.warning(f"No data for {selected_room}")
        return

    # Metric Tiles Layout
    c1, c2, c3 = st.columns(3)

    # Temperature Card
    temp_val = room_data['temperature']
    prev_temp = historical_df[historical_df['room_name'] == selected_room]['temperature'].iloc[0] if len(historical_df) > 0 else temp_val
    delta_temp = temp_val - prev_temp
    
    with c1:
        render_metric_card("🌡️", "Temperature", f"{temp_val:.1f}°C", f"{delta_temp:+.1f}°C")

    # Humidity Card
    hum_val = room_data['humidity']
    prev_hum = historical_df[historical_df['room_name'] == selected_room]['humidity'].iloc[0] if len(historical_df) > 0 else hum_val
    delta_hum = hum_val - prev_hum
    
    with c2:
        render_metric_card("💧", "Humidity", f"{hum_val:.1f}%", f"{delta_hum:+.1f}%")

    # Risk Card
    mold_idx = room_data['mold_index']
    risk_lvl = int(room_data['risk_level'])
    
    # Get Risk Info
    risk_info = MOLD_RISK_MAP.get(risk_lvl, MOLD_RISK_MAP[0])
    
    with c3:
        render_metric_card(risk_info['icon'], "Mold Risk", risk_info['label'], f"Idx: {mold_idx:.1f}", color_hex=risk_info['color'])

    st.divider()

    # --- All Rooms Summary ---
    st.markdown("<h3 style='font-weight: 900; letter-spacing: -0.02em;'>All Rooms Summary</h3>", unsafe_allow_html=True)
    
    # Prepare Summary Data - dedupe by room_name to avoid duplicates
    summary_df = current_readings_df[['room_name', 'temperature', 'humidity', 'mold_index', 'risk_level']].copy()
    summary_df = summary_df.drop_duplicates(subset=['room_name'], keep='first')
    
    # Map Risk Level to Status Text
    risk_text_map = {0: "🛡️ Optimal", 1: "⚠️ Warning", 2: "🍄 Growth", 3: "☣️ CRITICAL"}
    summary_df['status'] = summary_df['risk_level'].map(risk_text_map).fillna("Unknown")
    
    summary_df = summary_df[['room_name', 'temperature', 'humidity', 'mold_index', 'status']]
    summary_df.columns = ["ROOM", "TEMP", "HUM%", "MOLD", "STATUS"]
    
    # Apply Status Styling
    def style_status_col(val):
        if "CRITICAL" in val:
            return f'<span style="color:{COLORS["danger"]}">{val}</span>'
        elif "Warning" in val or "Growth" in val:
            return f'<span style="color:{COLORS["warning"]}">{val}</span>' 
        else:
            return f'<span style="color:{COLORS["success"]}">{val}</span>'

    summary_df['STATUS'] = summary_df['STATUS'].apply(style_status_col)
    render_custom_table(summary_df)

def _render_waiting_screen(title, message, instructions, connection_events=None, show_events_always=False):
    """Renders a friendly waiting screen when no data is available."""
    
    # Build connection events HTML
    events_html = ""
    if connection_events and len(connection_events) > 0:
        events_items = ""
        for evt in connection_events:
            events_items += f'<div style="display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);"><span style="font-size: 1rem;">{evt["icon"]}</span><span style="color: {evt["color"]}; font-weight: 600; font-size: 0.85rem;">{evt["type"]}</span><span style="color: {COLORS["text_dim"]}; font-size: 0.8rem; flex: 1;">{evt["msg"][:50] if evt["msg"] else ""}</span></div>'
        
        events_html = f'<div style="background: {COLORS["surface"]}; padding: 15px 20px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.1); margin-top: 20px; width: 100%; max-width: 500px;"><div style="font-size: 0.85rem; color: {COLORS["text_dim"]}; text-transform: uppercase; margin-bottom: 10px;">Connection Events</div>{events_items}</div>'
    elif show_events_always:
        # Show empty state with "Waiting for Connections"
        events_html = f'<div style="background: {COLORS["surface"]}; padding: 15px 20px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.1); margin-top: 20px; width: 100%; max-width: 500px;"><div style="font-size: 0.85rem; color: {COLORS["text_dim"]}; text-transform: uppercase; margin-bottom: 10px;">Connection Events</div><div style="display: flex; align-items: center; gap: 10px; padding: 12px 0;"><span style="font-size: 1rem;">⏳</span><span style="color: {COLORS["text_dim"]}; font-size: 0.9rem;">Waiting for Connections...</span></div></div>'
    
    # Build instructions HTML
    steps_html = "".join([f'<div style="color: {COLORS["text_main"]}; margin: 8px 0; font-size: 0.95rem;">{step}</div>' for step in instructions])
    
    # Compact HTML
    html = f'''<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 70vh; text-align: center;">
<div style="font-size: 4rem; margin-bottom: 20px;">🌿</div>
<div style="font-size: 2.2rem; font-weight: 900; color: {COLORS['text_main']}; margin-bottom: 0px; letter-spacing: -0.03em;">KLIMA Sense<span style="color: {COLORS['primary']};">.</span></div>
<div style="font-size: 1rem; color: {COLORS['text_dim']}; font-weight: 400; margin-bottom: 25px;">Sense the unseen</div>
<div style="font-size: 1.5rem; font-weight: 700; color: {COLORS['warning']}; margin-bottom: 0px;">{title}</div>
<div style="font-size: 1rem; color: {COLORS['text_dim']}; margin-bottom: 30px; max-width: 500px;">{message}</div>
<div style="background: {COLORS['surface']}; padding: 20px 30px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.1); text-align: left;">
<div style="font-size: 0.85rem; color: {COLORS['text_dim']}; text-transform: uppercase; margin-bottom: 10px;">Next Steps</div>
{steps_html}
</div>
{events_html}
<div style="margin-top: 30px; font-size: 0.85rem; color: {COLORS['text_dim']};">⏳ Auto-refreshing every 3 seconds...</div>
</div>'''
    
    st.markdown(html, unsafe_allow_html=True)

def main():
    try:
        inject_custom_css()
        
        # --- EARLY CHECK: Database and Data Existence ---
        # Show friendly message if no data available yet
        if not db.db_exists():
            _render_waiting_screen(
                title="Database Not Found",
                message="The sensor database has not been created yet.",
                instructions=[
                    "1. Ensure data_logger.py is running.",
                    "2. Connect your sensor node and ensure it is powered on.",
                    "3. Connect your server node and ensure it is powered on.",
                    "4. Wait for sensor data to arrive."
                ]
            )
            time.sleep(5)
            st.rerun()
            return
            
        if not db.has_data():
            # Check for recent connection events even without readings
            recent_events = db.get_latest_alerts(limit=10)
            
            # Friendly event name mapping
            event_name_map = {
                'SERVER_RESTORED': 'Server Node Connected',
                'SERVER_LOST': 'Server Node Disconnected',
                'NODE_JOINED': 'Sensor Node Connected',
                'NODE_LOST': 'Sensor Node Disconnected',
                'SENSOR_FAIL': 'Sensor Failure',
                'SENSOR_FIXED': 'Sensor Fixed',
                'GATEWAY_LOST': 'Gateway Disconnected',
                'GATEWAY_RESTORED': 'Gateway Connected'
            }
            
            # Show toast for new connection events
            if "waiting_last_alert_id" not in st.session_state:
                st.session_state.waiting_last_alert_id = db.get_latest_alert_id()
            
            new_events = db.get_new_alerts(st.session_state.waiting_last_alert_id)
            for evt in new_events:
                if evt['id'] > st.session_state.waiting_last_alert_id:
                    st.session_state.waiting_last_alert_id = evt['id']
                
                e_type = evt.get('event_type', '')
                friendly_name = event_name_map.get(e_type, e_type)
                msg = evt.get('message', '')
                
                if 'JOIN' in e_type or 'CONNECT' in e_type or 'RESTORED' in e_type:
                    st.toast(friendly_name, icon="✅")
                elif 'LOST' in e_type or 'FAIL' in e_type:
                    st.toast(friendly_name, icon="🚨")
                else:
                    st.toast(friendly_name, icon="ℹ️")
            
            # Build connection status for display
            connection_status = []
            if recent_events:
                for evt in recent_events[:5]:  # Show last 5 events
                    e_type = evt.get('event_type', 'Unknown')
                    friendly_name = event_name_map.get(e_type, e_type)
                    msg = evt.get('message', '')
                    
                    if 'JOIN' in e_type or 'CONNECT' in e_type or 'RESTORED' in e_type:
                        icon = "🟢"
                        color = COLORS['success']
                    elif 'LOST' in e_type or 'FAIL' in e_type:
                        icon = "🔴"
                        color = COLORS['danger']
                    else:
                        icon = "🔵"
                        color = COLORS['info']
                    
                    connection_status.append({
                        'icon': icon,
                        'type': friendly_name,
                        'msg': msg,
                        'color': color
                    })
            
            _render_waiting_screen(
                title="Waiting for Sensor Data",
                message="The dashboard is connected, but no sensor readings have been received yet.",
                instructions=[
                    "1. Ensure data_logger.py is running.",
                    "2. Connect your sensor node and ensure it is powered on.",
                    "3. Connect your server node and ensure it is powered on.",
                    "4. Wait for sensor data to arrive."
                ],
                connection_events=connection_status,
                show_events_always=True  # Always show the events block
            )
            time.sleep(3)
            st.rerun()
            return
        
        # --- Shared Room Logic & Callback ---
        # Robustness: Ensure rooms exist and current selection is valid
        if not db.rooms:
            db.rooms = ["Living Room"] # Fallback

        if "current_room" not in st.session_state or st.session_state.current_room not in db.rooms:
            st.session_state.current_room = db.rooms[0]
    
        def update_room(source_key):
            """Syncs the selected room across tabs."""
            selected = st.session_state[source_key]
            if selected is None:
                return  # Ignore empty selections
            st.session_state.current_room = selected
            
            # Sync the OTHER key so it reflects the change immediately
            if source_key == "pills_t1":
                st.session_state["pills_t2"] = selected
            elif source_key == "pills_t2":
                st.session_state["pills_t1"] = selected
    
        # Ensure widget keys exist in state to prevent KeyErrors on first run sync attempts
        if "pills_t1" not in st.session_state: st.session_state["pills_t1"] = st.session_state.current_room
        if "pills_t2" not in st.session_state: st.session_state["pills_t2"] = st.session_state.current_room
    
        # --- Data Fetching ---
        current_readings_df = db.generate_current_readings()
        historical_df = db.generate_historical_data()
        current_health_df = db.get_system_health()
        alerts_list = db.get_latest_alerts()
        
        # Determine Global Status
        active_alerts = db.get_active_alerts() 
        node_states = db.get_node_states()
        
        offline_nodes = [ip for ip, st in node_states.items() if st == 'offline' and ip != 'SERVER']
        failed_sensors = current_health_df[current_health_df['sensor_a_status'] >= 2] if not current_health_df.empty else pd.DataFrame()

        is_gateway_online = node_states.get('SERVER', 'online') == 'online'
        any_node_offline = len(offline_nodes) > 0
        any_hardware_fault = not failed_sensors.empty
        
        if "GATEWAY_LOST" in [a['event_type'] for a in active_alerts]:
            is_gateway_online = False
            
        # ALERT TRACKING (Cursor)
        if "last_alert_id" not in st.session_state:
            st.session_state.last_alert_id = db.get_latest_alert_id()
            
        # ALERT DEDUPLICATION (Active Failures)
        if "active_failures" not in st.session_state:
            st.session_state.active_failures = set()
        
        # --- Toast Loop for NEW Alerts ---
        new_alerts = db.get_new_alerts(st.session_state.last_alert_id)
        if new_alerts:
            shown_types = set()
            for alert in new_alerts:
                 # Update cursor
                 if alert['id'] > st.session_state.last_alert_id:
                     st.session_state.last_alert_id = alert['id']
                 
                 e_type = alert['event_type']
                 room = alert.get('room_name', 'Unknown')
                 dedup_key = f"{room}_{e_type}" # Unique key for this specific failure type in this room
    
                 # DEDUPLICATION LOGIC
                 should_show = True
                 
                 if e_type == "SENSOR_FAIL":
                     if dedup_key in st.session_state.active_failures:
                         should_show = False # Already shown this failure, suppress spam
                     else:
                         st.session_state.active_failures.add(dedup_key)
                         should_show = True
    
                 elif e_type == "SENSOR_FIXED":
                     # Clear the failure flag so we can show it again next time it fails
                     # Construct the key for the FAIL event to match and remove
                     fail_key = f"{room}_SENSOR_FAIL"
                     if fail_key in st.session_state.active_failures:
                         st.session_state.active_failures.remove(fail_key)
                     should_show = True
                 
                 # Dedup 2: Only show one toast per event type per batch (Visual Cleanup)
                 if e_type in shown_types:
                     should_show = False
                
                 if should_show:
                     shown_types.add(e_type)
    
                     # Human-readable event messages
                     event_messages = {
                         'SERVER_RESTORED': 'Server node is back online',
                         'SERVER_LOST': 'Server node disconnected',
                         'NODE_JOINED': f'{room} sensor node connected',
                         'NODE_LOST': f'{room} sensor node disconnected',
                         'NODE_RESTORED': f'{room} sensor node reconnected',
                         'SENSOR_FAIL': f'Sensor issue detected in {room}',
                         'SENSOR_FIXED': f'Sensor fixed in {room}',
                         'GATEWAY_LOST': 'Gateway connection lost',
                         'GATEWAY_RESTORED': 'Gateway reconnected'
                     }
                     
                     msg_text = event_messages.get(e_type, alert['message'])
                     icon = "ℹ️"
                     if "LOST" in e_type or "FAIL" in e_type:
                         icon = "🚨"
                     elif "RESTORED" in e_type or "JOINED" in e_type or "FIXED" in e_type:
                         icon = "✅"
                         
                     st.toast(msg_text, icon=icon)
    
        # --- Sidebar / Header Logic ---
        hour = datetime.datetime.now().hour
        if hour < 12:
            greeting = "Good Morning"
        elif hour < 18:
            greeting = "Good Afternoon"
        else:
            greeting = "Good Evening"
    
        # CRITICAL BANNER (Gateway) - Use Placeholder to prevent Layout Shift (Tab Reset)
        banner_ph = st.empty()
        
        if not is_gateway_online:
            banner_ph.error("🚨 CRITICAL: Gateway Disconnected. Check USB Connection.")
        elif any_node_offline:
            banner_ph.warning(f"⚠️ SYSTEM DEGRADED: {len(offline_nodes)} Sensor Node(s) Lost.")
        elif any_hardware_fault:
            banner_ph.warning("⚠️ HARDWARE ALERT: Sensor Malfunction Detected.")
    
        # Status Config for Header
        if not is_gateway_online:
            sys_status_html = f'<span style="color:{COLORS["danger"]}; font-weight: 700;">● OFFLINE</span>'
        elif any_node_offline or any_hardware_fault:
            sys_status_html = f'<span style="color:{COLORS["warning"]}; font-weight: 700;">● Action Required</span>'
        else:
            sys_status_html = f'<span style="color:{COLORS["success"]}">● Online</span>'
    
        # BRANDED HEADER
        st.markdown(f"""
        <div class="brand-header">
            <div class="brand-logo">KLIMA Sense<span class="dot"> . |</span><span class="punchline"> Sense the unseen</span></div>
            <div class="brand-subtitle">{greeting} | System Status: {sys_status_html}</div>
        </div>
        """, unsafe_allow_html=True)
        
        # --- GLOBAL MOLD RISK BANNER (Visible on all tabs) ---
        # Calculate worst case across all rooms
        worst_case = 0
        worst_room = None
        worst_rec = RECOMMENDATION_CASES[0]
        
        for _, row in current_readings_df.iterrows():
            r_temp = row['temperature']
            r_hum = row['humidity']
            r_mold = row['mold_index']
            r_growth = int(row.get('growth_status', 0)) if 'growth_status' in row.index else 0
            r_rh_crit = row.get('rh_crit', 80.0) if 'rh_crit' in row.index else 80.0
            r_case = get_mold_case(r_mold, r_growth, r_temp, r_hum, r_rh_crit, None)
            if r_case > worst_case:
                worst_case = r_case
                worst_room = row['room_name']
                worst_rec = RECOMMENDATION_CASES.get(r_case, RECOMMENDATION_CASES[0])
        
        # Display global banner if worst case has a banner color
        if worst_rec['banner_color'] is not None and worst_room is not None:
            global_banner_html = f"""
            <div style="
                background: linear-gradient(135deg, {worst_rec['banner_color']}22 0%, {worst_rec['banner_color']}11 100%);
                border: 1px solid {worst_rec['banner_color']};
                border-radius: 12px;
                padding: 12px 16px;
                margin-bottom: 16px;
                display: flex;
                align-items: center;
                gap: 12px;
            ">
                <span style="font-size: 1.5rem;">{worst_rec['icon']}</span>
                <div>
                    <div style="color: {worst_rec['color']}; font-weight: 700; font-size: 1rem;">{worst_rec['headline']} — {worst_room}</div>
                    <div style="color: {COLORS['text_dim']}; font-size: 0.85rem; margin-top: 2px;">{worst_rec['action']}</div>
                </div>
            </div>
            """
            st.markdown(global_banner_html, unsafe_allow_html=True)
        
        # --- Layout: Tabs FIRST ---
        tab1, tab2, tab3 = st.tabs(["At a Glance", "Environmental Data", "System Health"])
    
        # ---------------------------
        # TAB 1: AT A GLANCE
        # ---------------------------
        with tab1:
            render_glance_tab(db, update_room, current_readings_df, historical_df)
    
        # ---------------------------
        # TAB 2: ENVIRONMENTAL DATA
        # ---------------------------
        with tab2:
            # Pills Here (Synced)
            st.pills("Select Room:", db.rooms, selection_mode="single", key="pills_t2", default=st.session_state.current_room, on_change=update_room, args=("pills_t2",))
                
            selected_room_t2 = st.session_state.current_room
            room_data_t2 = current_readings_df[current_readings_df["room_name"] == selected_room_t2].iloc[0]
            
            # Pre-compute case for banner display
            _temp = room_data_t2['temperature']
            _hum = room_data_t2['humidity']
            _mold = room_data_t2['mold_index']
            _growth = int(room_data_t2.get('growth_status', 0)) if 'growth_status' in room_data_t2.index else 0
            _rh_crit = room_data_t2.get('rh_crit', 80.0) if 'rh_crit' in room_data_t2.index else 80.0
            _case = get_mold_case(_mold, _growth, _temp, _hum, _rh_crit, None)
            _rec = RECOMMENDATION_CASES.get(_case, RECOMMENDATION_CASES[0])
    
            st.markdown(f"<h3 style='font-weight: 900; letter-spacing: -0.02em;'>Real-Time Metrics</h3>", unsafe_allow_html=True)
            
            # 1. METERS (GAUGES) - Top
            g1, g2, g3 = st.columns(3)
            with g1:
                render_gauge(room_data_t2['temperature'], "Temperature (°C)", 0, 50, [
                    {'range': [0, 18], 'color': COLORS['info']}, {'range': [18, 28], 'color': COLORS['success']}, {'range': [28, 50], 'color': COLORS['alert']}
                ])
            with g2:
                 render_gauge(room_data_t2['humidity'], "Humidity (%)", 0, 100, [
                    {'range': [0, 30], 'color': COLORS['warning']}, {'range': [30, 60], 'color': COLORS['success']}, {'range': [60, 100], 'color': COLORS['info']}
                ])
            with g3:
                 render_gauge(max(0, room_data_t2['mold_index']), "Mold Index", 0, 6, [
                    {'range': [0, 1], 'color': COLORS['success']}, {'range': [1, 3], 'color': COLORS['warning']}, {'range': [3, 6], 'color': COLORS['alert']}
                ])
                
            st.markdown("<br>", unsafe_allow_html=True)
    
            # 2. DETAILS GRID (2x2)
            # Prepare Data
            risk = int(room_data_t2['risk_level'])
            status_text = MOLD_RISK_MAP.get(risk)['label']
            status_color = MOLD_RISK_MAP.get(risk)['color']
            
            # Relative Time
            last_seen_str = get_relative_time_string(room_data_t2['timestamp'])
            
            node_ip = room_data_t2['node_ip']
            is_sim_bool = bool(room_data_t2['is_simulated'])
            sim_text = "True" if is_sim_bool else "False"
            sim_color = COLORS['warning'] if is_sim_bool else COLORS['text_dim']
            
            # Recommendation Logic - Use New Case System
            pd_temp = room_data_t2['temperature']
            pd_hum = room_data_t2['humidity']
            pd_mold_idx = room_data_t2['mold_index']
            pd_rh_crit = room_data_t2.get('rh_crit', 80.0) if 'rh_crit' in room_data_t2.index else 80.0
            
            # Get previous mold index for trend detection
            prev_mold_key = f"prev_mold_{selected_room_t2}"
            prev_mold_idx = st.session_state.get(prev_mold_key, None)
            st.session_state[prev_mold_key] = pd_mold_idx  # Store for next iteration
            
            # Calculate current case
            pd_growth = int(room_data_t2.get('growth_status', 0)) if 'growth_status' in room_data_t2.index else 0
            current_case = get_mold_case(
                mold_index=pd_mold_idx,
                growth_status=pd_growth,
                temp=pd_temp,
                humidity=pd_hum,
                rh_crit=pd_rh_crit,
                prev_mold_index=prev_mold_idx
            )
            
            # Get recommendation data from RECOMMENDATION_CASES
            rec_data = RECOMMENDATION_CASES.get(current_case, RECOMMENDATION_CASES[0])
            rec_title = rec_data['headline']
            rec_msg = rec_data['message']
            rec_action = rec_data['action']
            rec_icon = rec_data['icon']
            rec_color = rec_data['color']
            rec_banner_color = rec_data['banner_color']
            
            # Track case changes for toast notifications
            case_key = f"mold_case_{selected_room_t2}"
            prev_case = st.session_state.get(case_key, 0)
            if prev_case != current_case:
                st.session_state[case_key] = current_case
                # Show toast on case change
                if current_case > prev_case:
                    st.toast(f"⚠️ {selected_room_t2}: {rec_data['headline']}", icon="🚨")
                elif current_case < prev_case and current_case == 0:
                    st.toast(f"✅ {selected_room_t2}: Conditions normalized!", icon="✅")
                elif current_case == 6:
                    st.toast(f"📉 {selected_room_t2}: Mold risk is declining!", icon="✅")
    
            # Helper to render card with MD3 / 16px radius
            def card_html(title, main_text, sub_text, accent_color, sub_color=COLORS['text_main']):
                return f"""
                <div style="background-color: {COLORS['surface']}; padding: 15px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.05); height: 100%; display: flex; flex-direction: column; justify-content: space-between; margin-bottom: 12px;">
                    <div style="color: {COLORS['text_dim']}; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;">{title}</div>
                    <div style="color: {accent_color}; font-size: 1.1rem; font-weight: 700; margin-top: 8px;">{main_text}</div>
                    <div style="color: {sub_color}; font-size: 0.85rem; font-weight: 300; margin-top: 4px;">{sub_text}</div>
                </div>
                """
    
            r1c1, r1c2 = st.columns(2)
            
            with r1c1:
                st.markdown(card_html("Recommendation", f"{rec_icon} {rec_title}", rec_msg, rec_color), unsafe_allow_html=True)
            with r1c2:
                st.markdown(card_html("Current Status", status_text, "Mold Risk Level", status_color), unsafe_allow_html=True)
                
            st.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True) # Explicit Gap
            
            r2c1, r2c2 = st.columns(2)
            
            with r2c1:
                st.markdown(card_html("Node Info", node_ip, f"Simulation Mode: <span style='color:{sim_color}'>{sim_text}</span>", COLORS['text_main'], COLORS['text_dim']), unsafe_allow_html=True)
            with r2c2:
                # Change: Display Time as Main, Relative as Sub
                time_str = room_data_t2['timestamp'].strftime("%H:%M:%S")
                rel_str = get_relative_time_string(room_data_t2['timestamp'])
                st.markdown(card_html("Last Seen", time_str, rel_str, COLORS['text_main']), unsafe_allow_html=True)
    
            st.divider()
            
            # 3. CHARTS (Stacked 3 Rows)
            st.markdown("<h4 style='font-weight: 700; letter-spacing: -0.01em;'>24h Trends</h4>", unsafe_allow_html=True)
            room_history = historical_df[historical_df["room_name"] == selected_room_t2]
            
            # Common chart config
            chart_config = {'displayModeBar': False, 'staticPlot': False} # staticPlot=True disables ALL interactions including tooltips, maybe user just wants buttons gone. displayModeBar: False removes buttons.
            
            # Chart 1: Temp
            fig_temp = px.area(room_history, x="timestamp", y="temperature", title="Temperature", color_discrete_sequence=[COLORS['primary']])
            fig_temp.update_traces(line_shape='spline', fill='tozeroy')
            fig_temp.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_family="Outfit", height=200, margin=dict(l=0, r=0, t=30, b=0))
            fig_temp.update_xaxes(showgrid=False)
            fig_temp.update_yaxes(showgrid=False, range=[10, 40])
            st.plotly_chart(fig_temp, width='stretch', config=chart_config, key=f"chart_temp_{selected_room_t2}")
            
            # Chart 2: Humidity
            fig_hum = px.area(room_history, x="timestamp", y="humidity", title="Humidity", color_discrete_sequence=["#00B0FF"]) 
            fig_hum.update_traces(line_shape='spline', fill='tozeroy')
            fig_hum.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_family="Outfit", height=200, margin=dict(l=0, r=0, t=30, b=0))
            fig_hum.update_xaxes(showgrid=False)
            fig_hum.update_yaxes(showgrid=False, range=[0, 100])
            st.plotly_chart(fig_hum, width='stretch', config=chart_config, key=f"chart_hum_{selected_room_t2}")
    
            # Chart 3: Mold Index
            fig_mold = px.area(room_history, x="timestamp", y="mold_index", title="Mold Index", color_discrete_sequence=[COLORS['danger']])
            fig_mold.update_traces(line_shape='spline', fill='tozeroy')
            fig_mold.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_family="Outfit", height=200, margin=dict(l=0, r=0, t=30, b=0))
            fig_mold.update_xaxes(showgrid=False)
            fig_mold.update_yaxes(showgrid=False, range=[0, 6])
            st.plotly_chart(fig_mold, width='stretch', config=chart_config, key=f"chart_mold_{selected_room_t2}")
    
        # ---------------------------
        # TAB 3: SYSTEM HEALTH
        # ---------------------------
        with tab3:
            # 1. Aesthetic Topology
            st.markdown("<h3 style='font-weight: 900; letter-spacing: -0.02em;'>Network Architecture</h3>", unsafe_allow_html=True)
            
            # Determine topology status
            # Priority: degraded (node lost) > sensor_failure > online
            if any_node_offline:
                topo_status = "degraded"
            elif any_hardware_fault:
                topo_status = "sensor_failure"
            else:
                topo_status = "online"
            render_aesthetic_topology(is_server_online=is_gateway_online, sensor_network_status=topo_status)
            
            st.divider()
            st.markdown("<h4 style='font-weight: 700; letter-spacing: -0.01em; margin-bottom: 15px;'>Diagnostic Status</h4>", unsafe_allow_html=True)
    
            # ============================================
            # SERVER NODE - Full Width at Top
            # ============================================
            
            # Get last seen timestamp from recent health data
            latest_health_ts = None
            if not current_health_df.empty and 'timestamp' in current_health_df.columns:
                latest_health_ts = pd.to_datetime(current_health_df['timestamp']).max()
            
            # Determine last seen time
            if latest_health_ts is not None:
                gw_last = latest_health_ts
            else:
                gw_last = db.get_gateway_last_seen()
            
            gw_rel = get_relative_time_string(gw_last)
            # Use the real-time is_gateway_online from node_states (set earlier in the code)
            gw_status = "Online" if is_gateway_online else "Offline"
            
            # Get server uptime data
            server_uptime = db.get_node_uptime_data("SERVER", hours=24)
            
            # Render Server Card (full width)
            render_diagnostic_card_v2(
                node_name="Server Node",
                node_ip="SERVER",
                status=gw_status,
                last_seen=gw_rel,
                uptime_data=server_uptime,
                node_type="server"
            )
            
            # ============================================
            # SENSOR NODES - 2-Column Grid
            # ============================================
            
            rooms = db.rooms
            latest_events = db.get_latest_node_events()
            
            # Create 2-column layout for sensor nodes
            col1, col2 = st.columns(2)
            
            for i, room in enumerate(rooms):
                try:
                    # Get readings and health data
                    r_data = current_readings_df[current_readings_df["room_name"] == room].iloc[0]
                    h_data = current_health_df[current_health_df["room_name"] == room].iloc[0]
                    
                    node_ip = r_data['node_ip']
                    
                    # Get timestamp for Last Seen
                    if 'timestamp' in h_data:
                        ts = pd.to_datetime(h_data['timestamp'])
                    else:
                        ts = pd.to_datetime(r_data['timestamp'])
                    last_seen_str = get_relative_time_string(ts)
                    
                    # Sensor status codes
                    s1_c = int(h_data['sensor_a_status'])
                    s2_c = int(h_data['sensor_b_status'])
                    
                    # Check system alerts
                    evt_data = latest_events.get(node_ip)
                    
                    status = "Online"
                    is_node_dead = False
                    s1_msg = None
                    s2_msg = None
                    
                    if evt_data:
                        e_type = evt_data['event']
                        
                        if e_type == "NODE_LOST":
                            status = "Node Died"
                            is_node_dead = True
                        elif e_type == "SENSOR_FAIL":
                            status = "Sensor Failure"
                            full_msg = evt_data['msg']
                            parts = [p.strip() for p in full_msg.split("|")]
                            for part in parts:
                                if "Sensor A:" in part:
                                    s1_msg = part.split("Sensor A:")[-1].strip()
                                    if s1_c == 0: s1_c = 99
                                elif "Sensor B:" in part:
                                    s2_msg = part.split("Sensor B:")[-1].strip()
                                    if s2_c == 0: s2_c = 99
                        elif e_type == "SERVER_LOST":
                            status = "Offline"
                            is_node_dead = True
                        elif e_type in ["SENSOR_FIXED", "NODE_JOINED", "NODE_RESTORED"]:
                            status = "Online"
                    
                    # Timeout check
                    time_diff = datetime.datetime.now() - ts
                    if time_diff.total_seconds() > 90 and status == "Online":
                        status = "Node Died"
                        is_node_dead = True
                    
                    # If server is offline, sensors are unreachable
                    if not is_gateway_online:
                        status = "Unreachable"
                        is_node_dead = True
                    
                    # Get uptime data for this node
                    node_uptime = db.get_node_uptime_data(node_ip, hours=6)
                    
                    # Alternate columns
                    target_col = col1 if i % 2 == 0 else col2
                    
                    with target_col:
                        render_diagnostic_card_v2(
                            node_name=room,
                            node_ip=node_ip,
                            status=status,
                            last_seen=last_seen_str,
                            uptime_data=node_uptime,
                            node_type="sensor",
                            s1_status=s1_msg,
                            s2_status=s2_msg,
                            s1_code=s1_c,
                            s2_code=s2_c,
                            is_node_dead=is_node_dead
                        )
                
                except Exception as e:
                    target_col = col1 if i % 2 == 0 else col2
                    with target_col:
                        st.error(f"Error rendering {room}: {e}")
                    continue
    
            st.divider()
            
            # 3. Uptime Charts - Real Data
            st.markdown("<h4 style='font-weight: 700; letter-spacing: -0.01em;'>Network Uptime</h4>", unsafe_allow_html=True)
            
            # Get real uptime data from database
            uptime_records = db.get_daily_uptime_percentages(days=14)
            
            if uptime_records:
                up_df = pd.DataFrame(uptime_records)
                up_df.columns = ["Date", "Uptime"]
                
                fig_up = px.line(up_df, x="Date", y="Uptime", title="Daily Network Uptime (%)", 
                                markers=True, color_discrete_sequence=[COLORS['success']])
                fig_up.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
                                    font_family="Outfit", height=250)
                fig_up.update_yaxes(range=[0, 105], showgrid=False, ticksuffix="%")
                fig_up.update_xaxes(showgrid=False)
                st.plotly_chart(fig_up, width='stretch', config={'displayModeBar': False})
            else:
                st.info("📊 Not enough data yet to show uptime history. Keep the system running to build uptime statistics.")
    
            # 4. Raw Logs
            st.divider()
            st.markdown("<h4 style='font-weight: 700; letter-spacing: -0.01em;'>System Alerts Log</h4>", unsafe_allow_html=True)
            
            log_df = pd.DataFrame(alerts_list)
            if not log_df.empty:
                # Human-readable event type mapping
                event_display_names = {
                    'SERVER_RESTORED': 'Server Restored',
                    'SERVER_LOST': 'Server Disconnected',
                    'NODE_JOINED': 'Node Connected',
                    'NODE_LOST': 'Node Disconnected',
                    'NODE_RESTORED': 'Node Restored',
                    'SENSOR_FAIL': 'Sensor Failure',
                    'SENSOR_FIXED': 'Sensor Fixed',
                    'GATEWAY_LOST': 'Gateway Disconnected',
                    'GATEWAY_RESTORED': 'Gateway Restored'
                }
                
                # Robust renaming
                rename_map = {
                    "timestamp": "Timestamp", 
                    "room_name": "Room", 
                    "event_type": "Event", 
                    "message": "Message"
                }
                log_df = log_df.rename(columns=rename_map)
                
                # Ensure only these columns exist and in order
                target_cols = ["Timestamp", "Room", "Event", "Message"]
                available_cols = [c for c in target_cols if c in log_df.columns]
                log_df = log_df[available_cols]
                
                # Convert event codes to readable names and add visual indicators
                def format_event(row):
                    event_code = row['Event']
                    readable_name = event_display_names.get(event_code, event_code.replace('_', ' ').title())
                    
                    if row['Room'] == "Gateway":
                        return f"{readable_name}"
                    return readable_name
                
                if "Event" in log_df.columns:
                    log_df['Event'] = log_df.apply(format_event, axis=1)
    
                render_custom_table(log_df)
            else:
                st.info("No active alerts.")
    
        # --- Global Alerts & Refresh ---
        # Check for dead nodes
        for _, row in current_health_df.iterrows():
             if row['sensor_a_status'] >= 2:
                 err_info = HEALTH_CODES.get(row['sensor_a_status'], HEALTH_CODES[6])
                 st.toast(f"⚠️ {row['room_name']}: {err_info['msg']}", icon="🚨")
    
        # Auto Refresh
        time.sleep(3)
        st.rerun()

    except Exception as e:
        # FATAL ERROR CATCHER
        # If something crashes the script, show it instead of resetting
        st.error(f"FATAL DASHBOARD ERROR: {e}")
        st.stop()

if __name__ == "__main__":
    main()
