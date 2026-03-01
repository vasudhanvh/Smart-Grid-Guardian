import streamlit as st
import pandas as pd
import requests
import time
import plotly.graph_objects as go
from datetime import datetime

# ==========================================
# 1. PAGE CONFIG & STYLING
# ==========================================
st.set_page_config(
    page_title="Smart Grid Guardian", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS: Forces black text on white cards and adds better spacing
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    html, body, [class*="css"]  { font-family: 'Inter', sans-serif; }
    
    /* STYLE THE METRIC CARDS */
    div[data-testid="stMetric"] {
        background-color: #ffffff !important;
        border: 1px solid #e0e0e0;
        padding: 15px 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        color: #000000 !important;
    }

    /* FORCE TEXT COLORS INSIDE METRICS TO BE BLACK */
    [data-testid="stMetricLabel"] {
        color: #666666 !important;
        font-size: 14px !important;
    }
    [data-testid="stMetricValue"] {
        color: #000000 !important;
        font-weight: 700 !important;
    }

    /* STATUS BANNERS */
    .status-box {
        padding: 25px; 
        border-radius: 12px; 
        text-align: center;
        font-weight: bold; 
        font-size: 24px; 
        margin-bottom: 25px; 
        color: white;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .status-safe { 
        background: linear-gradient(135deg, #00b09b, #96c93d); 
        border: 2px solid #82c91e;
    }
    .status-danger { 
        background: linear-gradient(135deg, #ff416c, #ff4b2b); 
        border: 2px solid #ff0000;
        animation: pulse 1.5s infinite; 
    }
    
    @keyframes pulse { 
        0% { box-shadow: 0 0 0 0 rgba(255, 65, 108, 0.7); transform: scale(1); } 
        50% { box-shadow: 0 0 0 15px rgba(255, 65, 108, 0); transform: scale(1.01); } 
        100% { box-shadow: 0 0 0 0 rgba(255, 65, 108, 0); transform: scale(1); } 
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. CONFIGURATION & RANGES
# ==========================================

KNOWN_DEVICES = sorted([
    '1 LIGHT', 'EMPTY', '2 LIGHTS', 'PHONE', 'LAPTOP', 
    'LIGHT+LAPTOP', 'PHONE+LIGHT', 'LAPTOP+PHONE', 'LIGHT+LAPTOP+PHONE'
])

SAFE_RANGES = {
    'EMPTY':              (0.0, 0.0),    
    'PHONE':              (5.0, 28.0),    
    '1 LIGHT':            (34.0, 45.5),   
    'PHONE+LIGHT':        (34.0, 68.0),   
    'LAPTOP':             (15.0, 47.0),   
    'LAPTOP+PHONE':       (27.0, 75.0),
    '2 LIGHTS':           (75.0, 86.0),   
    'LIGHT+LAPTOP':       (50.0, 86.0),  
    'LIGHT+LAPTOP+PHONE': (0.2, 109.0)   
}

if 'live_log' not in st.session_state:
    st.session_state['live_log'] = pd.DataFrame(
        columns=['Time', 'Device', 'Volts', 'Amps', 'Watts', 'Freq', 'PF', 'Status']
    )

# ==========================================
# 3. SIDEBAR CONTROLS
# ==========================================
with st.sidebar:
    st.title("Settings")
    
    # Run Control
    if "running" not in st.session_state: 
        st.session_state.running = False

    def toggle_run():
        st.session_state.running = not st.session_state.running

    btn_label = "🔴 STOP MONITORING" if st.session_state.running else "▶️ START MONITORING"
    btn_type = "primary" if not st.session_state.running else "secondary"
    st.button(btn_label, on_click=toggle_run, type=btn_type, use_container_width=True)

    st.markdown("---")
    
    CHANNEL_ID = st.text_input("Channel ID", value="3196030")
    READ_API_KEY = st.text_input("Read API Key", value="CGBKLIAKA7MA07AM", type="password")
    
    with st.expander("🛠️ Map Fields", expanded=False):
        ts_fields = ["field1", "field2", "field3", "field4", "field5", "field6", "field7", "field8"]
        f_volt = st.selectbox("Voltage (V)", ts_fields, index=0)
        f_curr = st.selectbox("Current (A)", ts_fields, index=1)
        f_pow  = st.selectbox("Power (W)",  ts_fields, index=2)
        f_freq = st.selectbox("Frequency (Hz)", ts_fields, index=3)
        f_pf   = st.selectbox("PF", ts_fields, index=4)
        f_egy  = st.selectbox("Energy", ts_fields, index=5)

    st.markdown("### 🔌 Device Context")
    selected_device = st.selectbox("What is connected?", KNOWN_DEVICES)
    
    st.markdown("---")
    refresh_rate = st.slider("Update Speed (s)", 2, 60, 15)

# ==========================================
# 4. LOGIC FUNCTIONS
# ==========================================
def fetch_data():
    try:
        url = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds/last.json?api_key={READ_API_KEY}"
        r = requests.get(url, timeout=3)
        return r.json() if r.status_code == 200 else None
    except: return None

def check_physics_rules(data_json):
    def get(f): return float(data_json.get(f, 0)) if data_json.get(f) and data_json.get(f) != 'null' else 0.0
    
    v, i, p = get(f_volt), get(f_curr), get(f_pow)
    f, pf, e = get(f_freq), get(f_pf), get(f_egy)
    
    is_theft = False
    reason = "Normal Usage"
    
    if selected_device in SAFE_RANGES:
        min_w, max_w = SAFE_RANGES[selected_device]
        if p < min_w:
            is_theft = True
            reason = f"Under-Power (Read {p:.1f}W, Expected >{min_w}W)"
        elif p > max_w:
            is_theft = True
            reason = f"Over-Power (Read {p:.1f}W, Expected <{max_w}W)"
            
    apparent_power = v * i
    if (apparent_power - p) > 50.0 and p > 5.0:
        is_theft = True
        reason = "Current Bypass Detected (V*I >> W)"

    return is_theft, reason, v, i, p, f, pf, e

# ==========================================
# 5. DASHBOARD LAYOUT
# ==========================================
st.title("⚡ Smart Grid Guardian")
st.caption(f"**Mode:** Hybrid CNN-LSTM + Isolation Forest | **Monitoring:** `{selected_device}`")

# Placeholders
top_banner = st.empty()
st.markdown("<br>", unsafe_allow_html=True)

# Metrics Row
c1, c2, c3 = st.columns(3)
with c1: card_v = st.empty()
with c2: card_i = st.empty()
with c3: card_p = st.empty()

st.markdown("<br>", unsafe_allow_html=True)

# --- CHART SECTION (Full Width) ---
st.subheader("📈 Power Consumption Trend")
chart_plot = st.empty()

st.markdown("<br>", unsafe_allow_html=True)

# --- LOG SECTION (Full Width) ---
st.subheader("📋 Live Analysis Log")
log_table = st.empty()

# ==========================================
# 6. RUN LOGIC
# ==========================================

if st.session_state.running:
    raw_data = fetch_data()
    
    if raw_data:
        is_theft, reason, v, i, p, f, pf, e = check_physics_rules(raw_data)
        
        # 1. Update Banner
        if is_theft:
            top_banner.markdown(f"""
            <div class="status-box status-danger">
                🚨 THEFT DETECTED <br>
                <span style="font-size:16px; font-weight:normal; opacity:0.9">{reason}</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            top_banner.markdown(f"""
            <div class="status-box status-safe">
                ✅ SYSTEM NORMAL <br>
                <span style="font-size:16px; font-weight:normal; opacity:0.9">Power usage within {selected_device} range</span>
            </div>
            """, unsafe_allow_html=True)

        # 2. Update Cards
        card_v.metric("Voltage (V)", f"{v:.1f} V")
        card_i.metric("Current (A)", f"{i:.3f} A")
        card_p.metric("Power (W)", f"{p:.1f} W", delta=None)
        
        # 3. Update Log (Added Volts, Amps, Freq, PF)
        new_row = {
            'Time': datetime.now().strftime("%H:%M:%S"),
            'Device': selected_device,
            'Volts': f"{v:.1f}",
            'Amps': f"{i:.3f}",
            'Watts': f"{p:.1f}",
            'Freq': f"{f:.1f}",
            'PF': f"{pf:.2f}",
            'Status': "🚨 THEFT" if is_theft else "✅ OK"
        }
        
        # Add to history
        st.session_state['live_log'] = pd.concat(
            [pd.DataFrame([new_row]), st.session_state['live_log']], 
            ignore_index=True
        ).head(15) 
        
        # Styling
        def highlight_status(val):
            color = '#ffeba8' if val == '🚨 THEFT' else '#cdf0ea'
            return f'background-color: {color}; color: black; border-radius: 5px'

        # Display Table with all columns
        log_table.dataframe(
            st.session_state['live_log'].style.applymap(highlight_status, subset=['Status']), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Time": st.column_config.TextColumn("Time", width="small"),
                "Device": st.column_config.TextColumn("Device", width="medium"),
            }
        )
        
        # 4. Update Chart
        chart_data = st.session_state['live_log'].iloc[::-1]
        fig = go.Figure()
        
        if selected_device in SAFE_RANGES:
            min_w, max_w = SAFE_RANGES[selected_device]
            fig.add_hrect(y0=min_w, y1=max_w, line_width=0, fillcolor="green", opacity=0.1, annotation_text="Safe Zone")

        fig.add_trace(go.Scatter(
            x=chart_data['Time'], 
            y=pd.to_numeric(chart_data['Watts']),
            fill='tozeroy',
            mode='lines+markers',
            line=dict(width=3, color='#ff4b4b' if is_theft else '#2ecc71'),
            name='Power (W)'
        ))
        
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=10, b=0),
            height=300,
            xaxis=dict(showgrid=False, color='gray'),
            yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)', color='gray')
        )
        chart_plot.plotly_chart(fig, use_container_width=True)
        
    else:
        top_banner.warning("📡 Connecting to Smart Meter (ThingSpeak)...")

    time.sleep(refresh_rate)
    st.rerun()

else:
    top_banner.info("👈 Select settings in the sidebar and click 'START MONITORING'")
