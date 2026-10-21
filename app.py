import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, time as dtime
from html import escape

import pandas as pd
import streamlit as st

import agent_core as core

# =========================================================
# NEXUSAGENT — PRESCRIPTION READER AGENT (CareBridge format)
# AI reads  ->  Doctor verifies  ->  Code schedules  ->  Agent monitors daily
# =========================================================

st.set_page_config(
    page_title="NexusAgent | Prescription Reader Agent",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

GEMINI_MODEL_DEFAULT = "gemini-2.5-flash"


def get_secret(name, default=""):
    """Read a secret from Streamlit secrets or environment without displaying it."""
    try:
        value = st.secrets.get(name, "")
        if value:
            return str(value).strip()
    except Exception:
        pass
    return os.getenv(name, default).strip()


core.TZ_NAME = get_secret("APP_TIMEZONE", core.TZ_NAME) or core.TZ_NAME


@st.cache_resource
def _init_db_once():
    core.init_db()
    return True


_init_db_once()

st.session_state.setdefault("user_id", None)
st.session_state.setdefault("lang", "English")

# --------------------- PREMIUM CSS ----------------------

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

    :root {
        --bg: #070B14;
        --panel: #0D1424;
        --panel2: #111B2E;
        --line: #202D43;
        --cyan: #38E8FF;
        --purple: #A78BFA;
        --green: #45E6A5;
        --pink: #FB70C8;
        --text: #F1F5FF;
        --muted: #91A0BA;
    }

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    .stApp {
        background:
            radial-gradient(ellipse at 5% 0%, rgba(35, 112, 180, .13), transparent 36%),
            radial-gradient(ellipse at 95% 5%, rgba(126, 67, 206, .12), transparent 32%),
            var(--bg);
        color: var(--text);
    }

    [data-testid="stHeader"] {
        background: rgba(7, 11, 20, .88);
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0B1220 0%, #080D17 100%);
        border-right: 1px solid #1C2A40;
    }

    [data-testid="stSidebar"] > div {
        padding-top: 1.5rem;
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: #A9B7D0;
    }

    h1, h2, h3 {
        font-family: 'Space Grotesk', sans-serif !important;
        letter-spacing: -0.7px;
        color: #F4F7FF;
    }

    h1 {
        font-weight: 700 !important;
    }

    p, label, li {
        color: #B8C4D9;
    }

    .brand {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.45rem;
        font-weight: 700;
        letter-spacing: -0.8px;
        color: #F4F7FF;
    }

    .brand span {
        color: var(--cyan);
    }

    .brand-mark {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 43px;
        height: 43px;
        border-radius: 14px;
        margin-right: 10px;
        color: #06111D;
        font-size: 1.35rem;
        font-weight: 900;
        background: linear-gradient(135deg, #38E8FF, #A78BFA);
        box-shadow: 0 0 25px rgba(56, 232, 255, .2);
        vertical-align: middle;
    }

    .eyebrow {
        color: var(--cyan);
        text-transform: uppercase;
        letter-spacing: 2.3px;
        font-size: .72rem;
        font-weight: 700;
        margin-bottom: 10px;
    }

    .hero {
        position: relative;
        overflow: hidden;
        padding: 30px 32px;
        border: 1px solid #263750;
        border-radius: 24px;
        background:
            radial-gradient(ellipse at 85% 10%, rgba(56,232,255,.13), transparent 32%),
            radial-gradient(ellipse at 70% 100%, rgba(167,139,250,.16), transparent 40%),
            linear-gradient(120deg, #111A2C, #0D1423 75%);
        margin-bottom: 25px;
        box-shadow: 0 18px 60px rgba(0,0,0,.16);
    }

    .hero h1 {
        font-size: clamp(1.8rem, 3vw, 2.7rem);
        line-height: 1.12;
        margin: 8px 0 12px;
    }

    .hero p {
        max-width: 650px;
        font-size: .98rem;
        line-height: 1.7;
        color: #A9B9D1;
    }

    .hero-glow {
        color: var(--cyan);
        text-shadow: 0 0 25px rgba(56,232,255,.28);
    }

    .section-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.23rem;
        font-weight: 700;
        color: #F1F5FF;
        margin: 18px 0 5px;
    }

    .section-subtitle {
        color: #8FA0BA;
        font-size: .88rem;
        margin-bottom: 17px;
    }

    .metric-card {
        min-height: 144px;
        padding: 20px;
        border-radius: 18px;
        background: linear-gradient(145deg, #111B2D, #0C1321);
        border: 1px solid #223149;
        box-shadow: 0 10px 28px rgba(0,0,0,.12);
        transition: border-color .2s ease, transform .2s ease;
    }

    .metric-card:hover {
        border-color: #3A6680;
        transform: translateY(-2px);
    }

    .metric-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
    }

    .metric-label {
        color: #A0AEC5;
        font-size: .83rem;
        font-weight: 600;
    }

    .metric-icon {
        width: 34px;
        height: 34px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 11px;
        font-size: 1.05rem;
        background: #16263A;
    }

    .metric-value {
        color: #F3F7FF;
        font-family: 'Space Grotesk', sans-serif;
        font-weight: 700;
        font-size: 2rem;
        margin-top: 13px;
        line-height: 1;
    }

    .metric-note {
        color: #8799B4;
        font-size: .76rem;
        margin-top: 10px;
    }

    .panel {
        background: linear-gradient(145deg, #10192A, #0B1220);
        border: 1px solid #202F46;
        border-radius: 19px;
        padding: 22px;
        margin-bottom: 14px;
    }

    .panel-title {
        font-family: 'Space Grotesk', sans-serif;
        color: #EEF3FF;
        font-weight: 700;
        font-size: 1.02rem;
        margin-bottom: 7px;
    }

    .panel-caption {
        color: #8FA0BA;
        font-size: .84rem;
        line-height: 1.6;
    }

    .status-pill {
        display: inline-block;
        border-radius: 999px;
        padding: 5px 10px;
        font-size: .73rem;
        font-weight: 700;
        background: #17263A;
        color: #91E8FF;
        border: 1px solid #2B4A60;
    }

    .divider {
        border: 0;
        border-top: 1px solid #202D43;
        margin: 20px 0;
    }

    .empty-state {
        text-align: center;
        padding: 35px 20px;
        border: 1px dashed #30415C;
        border-radius: 17px;
        background: rgba(14, 22, 37, .65);
    }

    .empty-icon {
        font-size: 2rem;
        margin-bottom: 10px;
    }

    .empty-title {
        color: #F1F5FF;
        font-weight: 700;
        font-size: 1rem;
    }

    .empty-text {
        color: #91A0BA;
        font-size: .85rem;
        margin-top: 7px;
    }

    .stButton > button,
    .stFormSubmitButton > button {
        border-radius: 11px;
        border: 1px solid #30425B;
        background: #152239;
        color: #EAF5FF;
        font-weight: 600;
        min-height: 42px;
        transition: all .2s ease;
    }

    .stButton > button:hover,
    .stFormSubmitButton > button:hover {
        border-color: var(--cyan);
        color: var(--cyan);
        background: #172941;
    }

    .stButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"] {
        color: #07121C;
        border: none;
        background: linear-gradient(100deg, #38E8FF, #86B8FF 60%, #A78BFA);
        font-weight: 800;
        box-shadow: 0 5px 22px rgba(56,232,255,.13);
    }

    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover {
        color: #07121C;
        filter: brightness(1.08);
        box-shadow: 0 5px 28px rgba(56,232,255,.24);
    }

    .stTextInput input,
    .stTextArea textarea,
    .stDateInput input,
    .stSelectbox div[data-baseweb="select"] > div,
    .stFileUploader section {
        background: #0B1423 !important;
        color: #EAF1FF !important;
        border-color: #2A3B54 !important;
        border-radius: 11px !important;
    }

    .stTextInput input:focus,
    .stTextArea textarea:focus {
        border-color: #38E8FF !important;
        box-shadow: 0 0 0 1px rgba(56,232,255,.2) !important;
    }

    [data-testid="stFileUploader"] {
        border: 1px dashed #344A67;
        border-radius: 15px;
        background: rgba(11,20,35,.5);
        padding: 8px;
    }

    [data-testid="stProgressBar"] > div > div {
        background: linear-gradient(90deg, #38E8FF, #A78BFA, #FB70C8);
    }

    [data-testid="stAlert"] {
        border-radius: 12px;
    }

    [data-testid="stMetric"] {
        background: #101A2A;
        border: 1px solid #263750;
        padding: 15px;
        border-radius: 14px;
    }

    [data-testid="stMetricValue"] {
        color: #38E8FF;
    }

    .footer {
        color: #65758F;
        font-size: .76rem;
        text-align: center;
        padding: 20px 0 8px;
    }

    #MainMenu, footer {
        visibility: hidden;
    }

    @media (max-width: 700px) {
        .hero { padding: 22px; }
        .metric-card { min-height: 125px; padding: 15px; }
        .metric-value { font-size: 1.7rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------- HEALTHCARE MOTION DESIGN LAYER ---------------------
# Lightweight CSS-only motion: no animation libraries or extra dependencies.
st.markdown(
    """
    <style>
    :root {
      --health-mint: #53F0C2;
      --health-blue: #54C8FF;
      --health-violet: #B39BFF;
    }

    /* Ambient clinical-tech glow */
    .stApp {
      background-image:
        radial-gradient(ellipse at 12% 16%, rgba(42, 205, 188, .10), transparent 31%),
        radial-gradient(ellipse at 88% 28%, rgba(91, 111, 255, .11), transparent 30%),
        radial-gradient(ellipse at 54% 100%, rgba(38, 181, 255, .06), transparent 38%),
        linear-gradient(135deg, #070B14 0%, #0A1020 48%, #080D18 100%);
      background-size: 140% 140%;
      animation: cb-ambient 22s ease-in-out infinite alternate;
    }

    @keyframes cb-ambient {
      0% { background-position: 0% 0%; }
      100% { background-position: 100% 80%; }
    }

    /* Refined entrance motion for the workspace */
    [data-testid="stMainBlockContainer"] {
      animation: cb-enter .55s cubic-bezier(.2,.75,.25,1) both;
    }
    @keyframes cb-enter {
      from { opacity: 0; transform: translateY(9px); }
      to { opacity: 1; transform: translateY(0); }
    }

    /* Glassy, premium dashboard surfaces */
    .metric-card, .hero, .empty-state {
      position: relative;
      overflow: hidden;
      isolation: isolate;
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
    }
    .metric-card {
      border-color: rgba(91, 132, 171, .25) !important;
      background: linear-gradient(145deg, rgba(17, 29, 48, .94), rgba(10, 17, 30, .91)) !important;
      box-shadow: 0 10px 32px rgba(0,0,0,.13), inset 0 1px 0 rgba(255,255,255,.025);
      transition: transform .24s ease, border-color .24s ease, box-shadow .24s ease;
    }
    .metric-card::before {
      content: ""; position: absolute; inset: 0 auto 0 0; width: 2px;
      background: linear-gradient(180deg, var(--health-mint), var(--health-blue), transparent);
      opacity: .7; z-index: -1;
    }
    .metric-card:hover {
      transform: translateY(-4px);
      border-color: rgba(83, 240, 194, .55) !important;
      box-shadow: 0 16px 36px rgba(0,0,0,.25), 0 0 22px rgba(83,240,194,.055);
    }
    .metric-icon {
      border-radius: 13px;
      background: rgba(83, 240, 194, .065);
      box-shadow: 0 0 22px rgba(83, 240, 194, .045);
    }
    .hero {
      border: 1px solid rgba(92, 145, 179, .27) !important;
      background: linear-gradient(115deg, rgba(15, 31, 48, .98), rgba(15, 20, 41, .94) 58%, rgba(28, 24, 54, .88)) !important;
      box-shadow: 0 20px 55px rgba(0,0,0,.18), inset 0 1px 0 rgba(255,255,255,.035);
    }
    .hero::after {
      content: ""; pointer-events: none; position: absolute;
      right: -42px; top: -48px; width: 300px; height: 220px; border-radius: 50%;
      background: radial-gradient(ellipse, rgba(61, 219, 208, .12), rgba(98, 103, 255, .06) 44%, transparent 72%);
      filter: blur(5px); z-index: -1; animation: cb-orb 8s ease-in-out infinite alternate;
    }
    @keyframes cb-orb { from { transform: translate3d(0,0,0) scale(.94); } to { transform: translate3d(-18px,13px,0) scale(1.08); } }

    /* ECG-inspired accent on the hero: decorative, not a live health signal */
    .hero::before {
      content: ""; pointer-events: none; position: absolute; right: 18px; bottom: 15px;
      width: min(38%, 300px); height: 42px; opacity: .22;
      background-repeat: no-repeat; background-position: center; background-size: 100% 100%;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 320 48'%3E%3Cpath d='M0 26 H72 L88 26 L100 15 L113 39 L129 4 L145 32 L157 26 H205 L218 26 L229 18 L241 34 L253 26 H320' fill='none' stroke='%2353F0C2' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
    }

    /* Buttons feel responsive without overdoing motion */
    .stButton > button, .stDownloadButton > button {
      transition: transform .16s ease, box-shadow .2s ease, border-color .2s ease !important;
      border-radius: 12px !important;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 22px rgba(53, 205, 211, .11);
    }
    .stButton > button:active, .stDownloadButton > button:active { transform: translateY(0) scale(.99); }

    /* Inputs get a crisp focus ring for accessibility */
    [data-testid="stTextInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus,
    [data-testid="stDateInput"] input:focus {
      border-color: rgba(83,240,194,.75) !important;
      box-shadow: 0 0 0 2px rgba(83,240,194,.12) !important;
    }

    /* Sidebar brand glow and gentle navigation feedback */
    .brand-mark { box-shadow: 0 0 24px rgba(83,240,194,.20); }
    [data-testid="stSidebar"] [role="radiogroup"] label {
      transition: background .18s ease, border-color .18s ease, transform .18s ease;
      border-radius: 11px;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:hover { transform: translateX(3px); }

    /* Reduced-motion support respects a user's operating-system preference */
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation-duration: .01ms !important; animation-iteration-count: 1 !important;
        scroll-behavior: auto !important; transition-duration: .01ms !important;
      }
    }
    @media (max-width: 700px) {
      .hero::before { width: 34%; opacity: .12; }
      .hero::after { width: 180px; height: 160px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <style>
    /* full-width buttons without version-specific arguments */
    .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button { width: 100%; }
    .chip { display:inline-block; border-radius:999px; padding:4px 11px; font-size:.74rem; font-weight:700; border:1px solid; }
    .chip-Taken { color:#45E6A5; background:rgba(69,230,165,.10); border-color:rgba(69,230,165,.35); }
    .chip-Missed { color:#FB70C8; background:rgba(251,112,200,.10); border-color:rgba(251,112,200,.35); }
    .chip-Skipped { color:#A78BFA; background:rgba(167,139,250,.10); border-color:rgba(167,139,250,.35); }
    .chip-Pending { color:#38E8FF; background:rgba(56,232,255,.08); border-color:rgba(56,232,255,.30); }
    .dose-time { font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:1.25rem; color:#F1F5FF; }
    .dose-name { font-weight:700; font-size:1.05rem; color:#F1F5FF; }
    .dose-meta { color:#91A0BA; font-size:.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------- HELPERS --------------------------

EN = {
    "Morning": "Morning", "Afternoon": "Afternoon", "Night": "Night",
    "before_food": "Before food", "after_food": "After food", "with_food": "With food", "any_time": "",
    "Take": "✓ Take", "Skip": "Skip", "Later": "Later",
    "Taken": "Taken", "Missed": "Missed", "Skipped": "Skipped", "Pending": "Pending",
    "upcoming": "Not time yet", "snoozed": "Reminder snoozed until",
    "missed_note": "Dose missed. Please contact your doctor about it.",
    "today": "Today's medicines", "none_today": "No doses scheduled for today.",
}
TA = {
    "Morning": "காலை", "Afternoon": "மதியம்", "Night": "இரவு",
    "before_food": "சாப்பிடுவதற்கு முன்", "after_food": "சாப்பிட்ட பிறகு", "with_food": "சாப்பிடும்போது", "any_time": "",
    "Take": "✓ எடுத்துக்கொண்டேன்", "Skip": "தவிர்", "Later": "பிறகு",
    "Taken": "எடுத்தாயிற்று", "Missed": "தவறியது", "Skipped": "தவிர்த்தது", "Pending": "நிலுவையில்",
    "upcoming": "இன்னும் நேரம் ஆகவில்லை", "snoozed": "நினைவூட்டல் தள்ளிவைப்பு:",
    "missed_note": "மருந்து தவறிவிட்டது. உங்கள் மருத்துவரிடம் தெரிவிக்கவும்.",
    "today": "இன்றைய மருந்துகள்", "none_today": "இன்று மருந்துகள் எதுவும் இல்லை.",
}


def tr(key):
    table = TA if st.session_state.get("lang") == "தமிழ்" else EN
    return table.get(key, key)


def safe_text(value):
    return escape(str(value))


def fmt_time(iso_str):
    return datetime.fromisoformat(iso_str).strftime("%I:%M %p").lstrip("0")


def fmt_dt(iso_str):
    return datetime.fromisoformat(iso_str).strftime("%d %b, %I:%M %p").lstrip("0")


def render_metric(label, value, icon, color, note):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-top">
                <div class="metric-label">{safe_text(label)}</div>
                <div class="metric-icon" style="color:{color}">{icon}</div>
            </div>
            <div class="metric-value">{safe_text(value)}</div>
            <div class="metric-note">{safe_text(note)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(title, message, icon="✦"):
    st.markdown(
        f"""
        <div class="empty-state">
            <div class="empty-icon">{icon}</div>
            <div class="empty-title">{safe_text(title)}</div>
            <div class="empty-text">{safe_text(message)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_header(eyebrow, title, description):
    # `title` may contain our own <span class='hero-glow'> markup (never user data).
    st.markdown(
        f"""<div class="hero"><div class="eyebrow">{safe_text(eyebrow)}</div>
        <h1>{title}</h1><p>{safe_text(description)}</p></div>""",
        unsafe_allow_html=True,
    )


def flash(kind, message):
    st.session_state["_flash"] = (kind, message)


def show_flash():
    item = st.session_state.pop("_flash", None)
    if item:
        getattr(st, item[0])(item[1])


def adherence_panel(patient_id, days=7):
    s = core.adherence_stats(patient_id, days)
    c1, c2, c3, c4 = st.columns(4, gap="medium")
    c1.metric("Taken", s["Taken"])
    c2.metric("Skipped", s["Skipped"])
    c3.metric("Missed", s["Missed"])
    c4.metric("Adherence", f"{s['pct']}%" if s["pct"] is not None else "–")
    breakdown = core.daily_breakdown(patient_id, days)
    if any(r["Taken"] or r["Skipped"] or r["Missed"] for r in breakdown):
        df = pd.DataFrame(breakdown).set_index("Day")
        st.bar_chart(df, color=["#45E6A5", "#A78BFA", "#FB70C8"])
    else:
        st.caption("No recorded doses yet.")


def dose_history_table(patient_id):
    rows = core.recent_doses(patient_id)
    if not rows:
        return
    df = pd.DataFrame([
        {"When": fmt_dt(r["scheduled_at"]), "Medicine": r["name"], "Slot": r["slot"], "Status": r["status"]}
        for r in rows
    ])
    st.dataframe(df, hide_index=True)


# --------------------- ACCOUNT ACCESS ---------------------

user = core.get_user(st.session_state.user_id) if st.session_state.user_id else None

if user is None:
    show_header("SECURE WORKSPACE", "Read it. Verify it. <span class='hero-glow'>Follow it up.</span>",
                "An AI agent reads the prescription, the doctor approves it, and the agent follows up on every dose.")
    tab_login, tab_register = st.tabs(["Sign in", "Create account"])
    with tab_login:
        with st.form("login_form"):
            login_username = st.text_input("Username")
            login_password = st.text_input("Password", type="password")
            login_submit = st.form_submit_button("Sign in", type="primary")
        if login_submit:
            account = core.authenticate(login_username, login_password)
            if account:
                st.session_state.user_id = account["id"]
                st.rerun()
            else:
                st.error("Username or password is incorrect.")
    with tab_register:
        with st.form("register_form"):
            reg_name = st.text_input("Full name")
            reg_username = st.text_input("Create username").strip().lower()
            reg_role = st.selectbox("Account type", ["Patient", "Doctor"])
            reg_password = st.text_input("Create password", type="password")
            reg_password2 = st.text_input("Confirm password", type="password")
            reg_submit = st.form_submit_button("Create account", type="primary")
        if reg_submit:
            if not reg_name.strip() or not re.fullmatch(r"[a-zA-Z0-9_.-]{3,40}", reg_username):
                st.error("Enter your name and a username of 3-40 letters, numbers, dots, underscores or hyphens.")
            elif len(reg_password) < 8:
                st.error("Use a password with at least 8 characters.")
            elif reg_password != reg_password2:
                st.error("Passwords do not match.")
            else:
                try:
                    account = core.create_user(reg_username, reg_name, reg_password, reg_role)
                    st.session_state.user_id = account["id"]
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("That username is already registered.")
    st.info("Prototype notice: use fake / de-identified data only. This is an adherence-reminder tool, "
            "not a medical device or an emergency service.")
    st.stop()

# --------------------- AGENT RUNS ON EVERY LOAD ---------------------
try:
    st.session_state["last_agent_result"] = core.agent_check()
except Exception as exc:  # never block the UI because of the agent
    st.session_state["last_agent_result"] = {"error": str(exc)}

is_doctor = user["role"] == "Doctor"

# --------------------- SIDEBAR --------------------------

DOCTOR_PAGES = ["Dashboard", "Prescriptions", "Patients", "Agent Activity", "About"]
PATIENT_PAGES = ["Today", "Upload Prescription", "My Medicines", "My Adherence", "Link Doctor", "Agent Activity", "About"]
pages = DOCTOR_PAGES if is_doctor else PATIENT_PAGES

with st.sidebar:
    st.markdown(
        """
        <div style="padding: 0 0 24px;">
            <div><span class="brand-mark">✦</span><span class="brand">Nexus<span>Agent</span></span></div>
            <div style="color:#7789A5;font-size:.75rem;margin:10px 0 0 4px;letter-spacing:1.6px;text-transform:uppercase;">
                Prescription Reader Agent
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(f"**{safe_text(user['full_name'])}** · {user['role']}")
    st.markdown('<div class="eyebrow">WORKSPACE</div>', unsafe_allow_html=True)
    selected_page = st.radio("Navigation", pages, label_visibility="collapsed", key="nav_radio")

    if not is_doctor:
        st.radio("Language / மொழி", ["English", "தமிழ்"], key="lang", horizontal=True)

    notes = core.get_notifications(user["id"])
    unread = sum(1 for n in notes if not n["is_read"])
    with st.expander(f"🔔 Notifications ({unread})"):
        if not notes:
            st.caption("Nothing yet.")
        for n in notes:
            st.markdown(f"{'🔹' if not n['is_read'] else '▫️'} {safe_text(n['message'])}")
            st.caption(fmt_dt(n["created_at"]))
        if unread and st.button("Mark all read", key="notif_read"):
            core.mark_notifications_read(user["id"])
            st.rerun()

    if get_secret("DEMO_CLOCK", "1") != "0":
        with st.expander("🎬 Demo clock (presentation only)"):
            st.caption(f"App time: **{core.now().strftime('%d %b %Y, %I:%M %p')}**")
            st.caption("Moves time forward so the agent's daily check can be shown live. "
                       "Affects every user of this demo. It does not undo missed doses.")
            b1, b2 = st.columns(2)
            if b1.button("+1 hour", key="clk_h"):
                core.set_clock_offset(core.get_clock_offset() + 60); st.rerun()
            if b2.button("+1 day", key="clk_d"):
                core.set_clock_offset(core.get_clock_offset() + 1440); st.rerun()
            if st.button("Reset to real time", key="clk_r"):
                core.set_clock_offset(0); st.rerun()

    if st.button("Sign out", key="signout"):
        st.session_state.user_id = None
        st.rerun()

    gemini_ready = bool(get_secret("GEMINI_API_KEY"))
    st.markdown(
        f"""<div class="panel" style="padding:16px;"><div class="panel-title">✦ AI Status</div>
        <div class="panel-caption">Prescription vision</div>
        <div style="margin-top:12px;"><span class="status-pill">● {'Gemini configured' if gemini_ready else 'GEMINI_API_KEY missing'}</span></div></div>
        <div style="font-size:.76rem;color:#72829D;line-height:1.7;"><b style="color:#B9C8E0;">Emergency?</b><br>
        This app is not an emergency service. Call <b>112</b> for urgent help.</div>""",
        unsafe_allow_html=True,
    )

page = selected_page
show_flash()


# =========================================================
# SHARED: upload + AI read
# =========================================================
def handle_upload(up, patient_id, doctor_id, uploader_id):
    data = up.getvalue()
    mime = up.type or ""
    if mime not in core.ALLOWED_MIME:
        raise ValueError("Please upload a JPG, PNG, WEBP or PDF file.")
    if len(data) > core.MAX_FILE_BYTES:
        raise ValueError("File is larger than 10 MB.")
    prepared, pmime = core.prepare_image(data, mime)
    error = None
    try:
        extracted = core.gemini_extract(
            prepared, pmime, get_secret("GEMINI_API_KEY"),
            get_secret("GEMINI_MODEL", GEMINI_MODEL_DEFAULT) or GEMINI_MODEL_DEFAULT,
        )
    except Exception as exc:
        extracted = {"items": [], "unreadable_overall": True}
        error = str(exc)
    extracted["error"] = error
    pid = core.create_prescription(
        patient_id, doctor_id, uploader_id, os.path.basename(up.name), mime, data,
        "manual" if error else "ai", extracted,
    )
    return pid, error


# =========================================================
# DOCTOR PAGES
# =========================================================
def doctor_dashboard():
    show_header("DOCTOR WORKSPACE", "Verify once. <span class='hero-glow'>The agent follows up daily.</span>",
                "The agent reads prescriptions and tracks every dose. You approve, and you decide about any change.")
    ov = core.doctor_overview(user["id"])
    c1, c2, c3, c4 = st.columns(4, gap="medium")
    with c1: render_metric("Linked patients", ov["patients"], "☺", "#38E8FF", "Patients who shared their code")
    with c2: render_metric("Awaiting approval", ov["pending"], "◷", "#FB70C8", "Nothing runs until you approve")
    with c3: render_metric("Medicines tracked", ov["active_meds"], "✚", "#45E6A5", "With upcoming doses")
    with c4: render_metric("Open alerts", ov["alerts"], "!", "#A78BFA", "Missed / skipped doses, course ends")

    st.markdown('<div class="section-title">Agent check</div>', unsafe_allow_html=True)
    res = st.session_state.get("last_agent_result", {})
    if st.button("▶ Run agent check now", type="primary"):
        res = core.agent_check()
        flash("success", f"Agent check done: {res['missed']} dose(s) marked missed, "
                         f"{res['alerts']} adherence alert(s), {res['ending']} course-ending notice(s).")
        st.rerun()
    st.caption("The check also runs every time the app opens. In production this would run from a scheduler.")

    st.markdown('<div class="section-title">Alerts</div>', unsafe_allow_html=True)
    alerts = core.open_alerts(user["id"])
    if not alerts:
        render_empty_state("No open alerts", "The agent will alert you here when doses are missed or a course is ending.", "✓")
    for a in alerts:
        with st.container(border=True):
            left, right = st.columns([4, 1])
            left.markdown(f"**{'⚠ Adherence' if a['kind'] == 'adherence' else '⏳ Course ending'}** · {safe_text(a['patient_name'])}")
            left.write(a["message"])
            left.caption(fmt_dt(a["created_at"]))
            if right.button("Mark seen", key=f"alert_{a['id']}"):
                core.mark_alert_read(a["id"], user["id"])
                st.rerun()

    st.markdown('<div class="section-title">Awaiting your approval</div>', unsafe_allow_html=True)
    pend = core.pending_prescriptions(user["id"])
    if not pend:
        st.caption("No prescriptions waiting.")
    for p in pend:
        st.markdown(f"• **{safe_text(p['patient_name'])}** · uploaded {fmt_dt(p['created_at'])} · open **Prescriptions** to review")

    st.markdown('<div class="section-title">Adherence · last 7 days</div>', unsafe_allow_html=True)
    patients = core.linked_patients(user["id"])
    if not patients:
        st.caption("No linked patients yet. Share your join code from the Patients page.")
    else:
        rows = []
        for p in patients:
            s = core.adherence_stats(p["id"])
            rows.append({"Patient": p["full_name"], "Taken": s["Taken"], "Skipped": s["Skipped"],
                         "Missed": s["Missed"], "Adherence": f"{s['pct']}%" if s["pct"] is not None else "–"})
        st.dataframe(pd.DataFrame(rows), hide_index=True)


FOOD_OPTIONS = [""] + core.FOOD_CODES


def review_prescription(rx):
    pid = rx["id"]
    extracted = json.loads(rx["extracted_json"] or "{}")
    ai_items = extracted.get("items", [])
    if extracted.get("error"):
        st.warning(f"AI could not read this file ({extracted['error']}). Enter the medicines manually from the original.")
    elif extracted.get("unreadable_overall"):
        st.warning("AI could not read this prescription clearly. Enter the medicines manually from the original.")
    if rx["source"] == "sample":
        st.info("SAMPLE DATA: fake demo prescription. It was not read from an image.")

    left, right = st.columns([1, 2], gap="large")
    with left:
        st.markdown("**Original prescription**")
        full = core.get_prescription_file(pid, user)
        if full and full["file_data"] and (full["mime_type"] or "").startswith("image/"):
            st.image(bytes(full["file_data"]))
        elif full and full["file_data"]:
            st.download_button("Download original", data=bytes(full["file_data"]),
                               file_name=full["filename"] or "prescription", key=f"dl_{pid}")
        else:
            st.caption("No file attached.")
    with right:
        st.markdown("**AI-read details. Check every field. Red warnings were unreadable or missing, and AI did not guess them.**")
        extra_key = f"rx{pid}_extra"
        st.session_state.setdefault(extra_key, 0 if ai_items else 1)
        total_rows = len(ai_items) + st.session_state[extra_key]
        blank = {k: None for k in core.FIELDS}
        blank.update({"confidence": "low", "note": "Added manually"})
        rows, all_problems = [], []
        for i in range(total_rows):
            src = ai_items[i] if i < len(ai_items) else blank
            k = lambda f, i=i: f"rx{pid}_r{i}_{f}"
            with st.container(border=True):
                h1, h2 = st.columns([3, 1])
                h1.markdown(f"**Medicine {i + 1}** · AI confidence: `{src.get('confidence', 'low')}`")
                include = h2.checkbox("Include", value=True, key=k("inc"))
                missed = [k_ for k_ in core.FIELDS if not src.get(k_)] if i < len(ai_items) else []
                if missed:
                    st.warning("AI could not read: " + ", ".join(missed))
                if src.get("note"):
                    st.caption(f"AI note: {src['note']}")
                c1, c2, c3 = st.columns(3)
                name = c1.text_input("Medicine name", value=src.get("medicine") or "", key=k("name"))
                strength = c2.text_input("Strength", value=src.get("strength") or "", key=k("strength"))
                dose = c3.text_input("Dose (e.g. 1 tablet)", value=src.get("dose") or "", key=k("dose"))
                c4, c5, c6 = st.columns(3)
                freq = c4.text_input("Frequency as written", value=src.get("frequency") or "", key=k("freq"))
                food_default = FOOD_OPTIONS.index(src["food"]) if src.get("food") in core.FOOD_CODES else 0
                food = c5.selectbox("Food instruction", FOOD_OPTIONS, index=food_default, key=k("food"),
                                    format_func=lambda c: "— choose —" if c == "" else core.FOOD_LABEL[c])
                days = c6.number_input("Duration (days)", min_value=0, max_value=365, step=1,
                                       value=core.parse_duration_days(src.get("duration")) or 0, key=k("days"))
                slots = st.multiselect("Dose times (you confirm these)", core.SLOTS,
                                       default=core.parse_frequency(src.get("frequency")) or [], key=k("slots"))
                row = {"name": name, "strength": strength, "dose": dose, "frequency": freq,
                       "food": food or None, "days": int(days), "slots": slots}
                if include:
                    problems = core.validate_row(row)
                    if problems:
                        st.error("Still needed before approval: " + ", ".join(problems))
                        all_problems.extend(problems)
                    rows.append(row)
        if st.button("+ Add a medicine row manually", key=f"addrow_{pid}"):
            st.session_state[extra_key] += 1
            st.rerun()

        dups = core.duplicate_names(rows)
        if dups:
            st.warning("Possible duplicate medicine in this prescription: " + ", ".join(dups) + ". Please check.")

        st.markdown("**Dose times and start date**")
        t1, t2, t3, t4 = st.columns(4)
        slot_times = {}
        for col, slot in zip((t1, t2, t3), core.SLOTS):
            h, m = [int(x) for x in core.DEFAULT_SLOT_TIMES[slot].split(":")]
            tv = col.time_input(slot, value=dtime(h, m), key=f"rx{pid}_t_{slot}")
            slot_times[slot] = tv.strftime("%H:%M")
        start = t4.date_input("Start date", value=core.now().date(), key=f"rx{pid}_start")

        confirm = st.checkbox(
            "I have checked every medicine against the original prescription and I approve it as the treating doctor.",
            key=f"rx{pid}_confirm")
        ready = bool(rows) and not all_problems and confirm
        a1, a2 = st.columns(2)
        if a1.button("✓ Approve and create schedule", type="primary", disabled=not ready, key=f"approve_{pid}"):
            try:
                out = core.approve_prescription(pid, user["id"], rows, slot_times, start)
                for key in [k_ for k_ in st.session_state if str(k_).startswith(f"rx{pid}_")]:
                    del st.session_state[key]
                flash("success", f"Approved. {out['medicines']} medicine(s), {out['doses']} dose reminders created by rules.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if a2.button("Reject: ask for a clearer copy", key=f"reject_{pid}"):
            core.reject_prescription(pid, user["id"], "Please upload a clearer copy.")
            flash("warning", "Rejected. The patient was notified and no schedule was created.")
            st.rerun()
        if not ready:
            st.caption("The approve button unlocks when every included medicine is complete and you tick the confirmation.")


def doctor_prescriptions():
    show_header("PRESCRIPTIONS", "AI reads. <span class='hero-glow'>You decide.</span>",
                "Nothing becomes a reminder until you verify and approve it.")
    patients = core.linked_patients(user["id"])
    pend = core.pending_prescriptions(user["id"])
    with st.expander("➕ Upload a new prescription", expanded=not pend):
        if not patients:
            st.info("No linked patients yet. Ask your patient to enter your join code (see Patients page).")
        else:
            opts = {f"{p['full_name']} (@{p['username']})": p["id"] for p in patients}
            label = st.selectbox("Patient", list(opts), key="up_patient")
            with st.form("doctor_upload", clear_on_submit=True):
                up = st.file_uploader("Prescription photo or PDF (fake / de-identified data only)",
                                      type=["jpg", "jpeg", "png", "webp", "pdf"])
                go = st.form_submit_button("✦ Read with AI", type="primary")
            if go:
                if not up:
                    st.error("Choose a file first.")
                else:
                    try:
                        with st.spinner("Agent is reading the prescription..."):
                            _, err = handle_upload(up, opts[label], user["id"], user["id"])
                        flash("warning" if err else "success",
                              "Saved, but AI could not read it. Enter details manually below." if err
                              else "AI finished reading. Please review below. Nothing is active yet.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            if st.button("Use SAMPLE prescription (fake data, backup for demos)", key="use_sample"):
                core.create_prescription(opts[label], user["id"], user["id"], "", "", b"", "sample",
                                         {"items": core.SAMPLE_ITEMS, "unreadable_overall": False})
                flash("info", "Sample (fake) prescription loaded for review.")
                st.rerun()

    st.markdown('<div class="section-title">Awaiting your review</div>', unsafe_allow_html=True)
    if not pend:
        render_empty_state("Nothing to review", "Upload a prescription above, or wait for a patient upload.", "✓")
        return
    labels = {f"#{p['id']} · {p['patient_name']} · {fmt_dt(p['created_at'])}": p for p in pend}
    chosen = st.selectbox("Choose prescription", list(labels))
    review_prescription(labels[chosen])


def doctor_patients():
    show_header("PATIENTS", "Your patients, <span class='hero-glow'>one adherence view.</span>",
                "Patients link to you by entering your code, which also means they consent to share.")
    st.markdown(
        f"""<div class="panel"><div class="panel-title">Your join code</div>
        <div class="dose-time">{safe_text(user['join_code'])}</div>
        <div class="panel-caption">Give this code to your patient. They enter it on the Link Doctor page.</div></div>""",
        unsafe_allow_html=True)
    patients = core.linked_patients(user["id"])
    if not patients:
        render_empty_state("No patients yet", "Once a patient enters your code they appear here.", "☺")
        return
    opts = {f"{p['full_name']} (@{p['username']})": p["id"] for p in patients}
    pid = opts[st.selectbox("Patient", list(opts))]
    adherence_panel(pid)
    st.markdown('<div class="section-title">Medicines</div>', unsafe_allow_html=True)
    meds = core.active_medicines(pid)
    if not meds:
        st.caption("No approved medicines yet.")
    for m in meds:
        slots = ", ".join(json.loads(m["slots"]))
        st.markdown(f"• **{safe_text(m['name'])} {safe_text(m['strength'])}** · {safe_text(m['dose'])} · "
                    f"{slots} · {core.FOOD_LABEL.get(m['food'], '')} · {m['remaining']} dose(s) remaining")
    st.markdown('<div class="section-title">Recent doses</div>', unsafe_allow_html=True)
    dose_history_table(pid)


# =========================================================
# PATIENT PAGES
# =========================================================
def patient_today():
    show_header("TODAY", "Your medicines, <span class='hero-glow'>one tap at a time.</span>",
                "Tap when you take a dose. Your doctor is told only if doses are missed.")
    for p in core.patient_prescriptions(user["id"]):
        if p["status"] == "needs_review":
            st.info(f"Waiting for Dr {p['doctor_name']} to verify your prescription. Reminders start after approval.")
    doses = core.todays_doses(user["id"])
    st.markdown(f'<div class="section-title">{safe_text(tr("today"))} · {core.now().strftime("%d %b")}</div>',
                unsafe_allow_html=True)
    if not doses:
        render_empty_state(tr("none_today"), "Your schedule appears here after your doctor approves a prescription.", "◷")
        return
    done = sum(1 for d in doses if d["status"] == "Taken")
    st.progress(done / len(doses), text=f"{done} / {len(doses)}")
    now_dt = core.now()
    for d in doses:
        sched = datetime.fromisoformat(d["scheduled_at"])
        with st.container(border=True):
            c1, c2, c3 = st.columns([1.2, 3, 1.3])
            c1.markdown(f'<div class="dose-time">{safe_text(fmt_time(d["scheduled_at"]))}</div>'
                        f'<div class="dose-meta">{safe_text(tr(d["slot"]))}</div>', unsafe_allow_html=True)
            food = tr(d["food"])
            c2.markdown(f'<div class="dose-name">{safe_text(d["name"])} {safe_text(d["strength"])}</div>'
                        f'<div class="dose-meta">{safe_text(d["dose"])}{" · " + safe_text(food) if food else ""}</div>',
                        unsafe_allow_html=True)
            c3.markdown(f'<span class="chip chip-{d["status"]}">{safe_text(tr(d["status"]))}</span>', unsafe_allow_html=True)
            if d["status"] == "Missed":
                st.caption(tr("missed_note"))
            elif d["status"] == "Pending":
                if sched - now_dt > timedelta(minutes=core.TAKE_WINDOW_MINUTES):
                    st.caption(tr("upcoming"))
                else:
                    if d["snoozed_until"] and d["snoozed_until"] > core.iso(now_dt):
                        st.caption(f"{tr('snoozed')} {fmt_time(d['snoozed_until'])}")
                    b1, b2, b3 = st.columns(3)
                    action = None
                    if b1.button(tr("Take"), key=f"take_{d['id']}", type="primary"): action = "take"
                    if b2.button(tr("Skip"), key=f"skip_{d['id']}"): action = "skip"
                    if b3.button(tr("Later"), key=f"later_{d['id']}"): action = "later"
                    if action:
                        try:
                            core.log_dose_action(d["id"], user["id"], action)
                        except ValueError as exc:
                            flash("error", str(exc))
                        st.rerun()


def patient_upload():
    show_header("UPLOAD", "Share a prescription <span class='hero-glow'>for verification.</span>",
                "Your doctor checks what the AI read. Reminders start only after approval.")
    docs = core.linked_doctors(user["id"])
    if not docs:
        st.info("Link your doctor first on the Link Doctor page.")
        return
    opts = {f"Dr {d['full_name']}": d["id"] for d in docs}
    label = st.selectbox("Send to", list(opts))
    with st.form("patient_upload", clear_on_submit=True):
        up = st.file_uploader("Prescription photo or PDF (fake / de-identified data only)",
                              type=["jpg", "jpeg", "png", "webp", "pdf"])
        go = st.form_submit_button("✦ Read and send to doctor", type="primary")
    if go:
        if not up:
            st.error("Choose a file first.")
        else:
            try:
                with st.spinner("Agent is reading the prescription..."):
                    _, err = handle_upload(up, user["id"], opts[label], user["id"])
                flash("warning" if err else "success",
                      "Sent to your doctor. AI could not read it, so the doctor will enter it manually." if err
                      else "Sent to your doctor for verification.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def patient_medicines():
    show_header("MEDICINES", "What your doctor <span class='hero-glow'>approved.</span>",
                "Only doctor-approved medicines appear here.")
    for p in core.patient_prescriptions(user["id"]):
        label = {"needs_review": "Waiting for doctor", "approved": "Approved", "rejected": "Rejected"}[p["status"]]
        st.markdown(f"**Prescription #{p['id']}** · Dr {safe_text(p['doctor_name'])} · {fmt_dt(p['created_at'])} · `{label}`")
    meds = core.active_medicines(user["id"])
    if not meds:
        render_empty_state("No approved medicines yet", "They appear after your doctor approves a prescription.", "✚")
    for m in meds:
        with st.container(border=True):
            st.markdown(f"**{safe_text(m['name'])} {safe_text(m['strength'])}** · {safe_text(m['dose'])}")
            slots = " · ".join(tr(s) for s in json.loads(m["slots"]))
            food = tr(m["food"])
            st.write(f"{slots}{' · ' + food if food else ''}")
            ends = datetime.fromisoformat(m["last_dose"]).strftime("%d %b") if m["last_dose"] else "-"
            st.caption(f"{m['remaining']} dose(s) remaining · course ends {ends}")


def patient_adherence():
    show_header("ADHERENCE", "How the last week <span class='hero-glow'>went.</span>",
                "Your doctor sees this summary. Taking medicine as prescribed is what matters.")
    adherence_panel(user["id"])
    dose_history_table(user["id"])


def patient_link():
    show_header("LINK DOCTOR", "Connect to <span class='hero-glow'>your doctor.</span>",
                "Enter the code your doctor gave you. This lets them see your prescriptions and adherence summary.")
    with st.form("link_form", clear_on_submit=True):
        code = st.text_input("Doctor join code")
        go = st.form_submit_button("Link doctor", type="primary")
    if go:
        doc = core.link_patient_to_doctor(user["id"], code)
        if doc:
            flash("success", f"Linked to Dr {doc['full_name']}.")
            st.rerun()
        else:
            st.error("That code was not found.")
    for d in core.linked_doctors(user["id"]):
        st.markdown(f"• Dr {safe_text(d['full_name'])} (@{safe_text(d['username'])})")


# =========================================================
# SHARED PAGES
# =========================================================
def agent_activity():
    show_header("AGENT ACTIVITY", "Everything the agent did, <span class='hero-glow'>on the record.</span>",
                "Reading, flagging, waiting for approval, scheduling, missed-dose checks and alerts.")
    if is_doctor:
        people = core.linked_patients(user["id"])
    else:
        people = [{"id": user["id"], "full_name": user["full_name"]}]
    ids = [p["id"] for p in people]
    if is_doctor and people:
        opts = {"All patients": ids, **{p["full_name"]: [p["id"]] for p in people}}
        ids = opts[st.selectbox("Patient", list(opts))]
    rows = core.agent_log_for(ids)
    if not rows:
        render_empty_state("No activity yet", "Agent steps appear here as prescriptions are processed.", "✦")
        return
    st.dataframe(pd.DataFrame([{"When": fmt_dt(r["created_at"]), "Patient": r["patient_name"],
                                "Step": r["step"], "Detail": r["detail"]} for r in rows]), hide_index=True)


def about():
    show_header("ABOUT", "AI reads. Doctor decides. <span class='hero-glow'>Code schedules.</span>",
                "How the Prescription Reader Agent works and what it will not do.")
    st.markdown("""
**The agent loop**
1. Photo or PDF in. Gemini reads it and returns `null` for anything unclear (no guessing).
2. Plain code validates the AI output and flags missing fields.
3. The doctor corrects and approves. The approval gate is enforced in code, not only in the UI.
4. Dose times are generated by plain rules. There is no AI in scheduling.
5. The patient taps Take / Skip / Later (English or தமிழ்).
6. The daily check marks missed doses and alerts the doctor after 2 doses in a row not taken. It also warns when a course is ending.

**What it will not do**
- Recommend, start, stop or change any medicine, or suggest a replacement dose.
- Monitor health conditions. It tracks adherence only.
- Act as an emergency service or medical device.

**Honest limits of this prototype**
- Reminders appear in the app. Push / SMS needs a separate provider.
- The agent check runs when the app opens (or on the button). Production would use a scheduler.
- Data is stored in a local SQLite file. Use fake data only.
- Production would need Indian data-protection compliance (DPDP Act), real hosting security and audit.
""")


PAGE_FUNCS = {
    "Dashboard": doctor_dashboard, "Prescriptions": doctor_prescriptions, "Patients": doctor_patients,
    "Today": patient_today, "Upload Prescription": patient_upload, "My Medicines": patient_medicines,
    "My Adherence": patient_adherence, "Link Doctor": patient_link,
    "Agent Activity": agent_activity, "About": about,
}
PAGE_FUNCS[page]()

st.markdown('<div class="footer">NEXUSAGENT · PRESCRIPTION READER AGENT · PROTOTYPE · FAKE DATA ONLY</div>',
            unsafe_allow_html=True)
