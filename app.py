import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, time as dtime
from html import escape

import pandas as pd
import streamlit as st

import agent_core as core
import nexcare  # NexCare add-on: report explainer, languages, dark mode, motivation

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

GEMINI_MODEL_DEFAULT = "gemini-3.5-flash"


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


def ai_cfg():
    return get_secret("GEMINI_API_KEY"), get_secret("GEMINI_MODEL", GEMINI_MODEL_DEFAULT) or GEMINI_MODEL_DEFAULT


@st.cache_resource
def _init_db_once():
    core.init_db()
    nexcare.init_tables(core)
    return True


_init_db_once()

st.session_state.setdefault("user_id", None)
st.session_state.setdefault("lang", "English")

# --------------------- FRESH TEAL HEALTH UI ----------------------

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');
    :root{--teal:#40E0D0;--teal-d:#1FB8A8;--teal-l:#E3FAF7;--bg:#F5F9FF;--ink:#0F3D3E;--muted:#9DB0BE;
          --coral:#FF6F61;--blue:#2F80ED;--yellow:#F2B64B;--line:#E6EEF5;--shadow:0 14px 40px rgba(64,224,208,.14);}
    html,body,[class*="css"]{font-family:'Poppins',sans-serif;}
    .stApp{background:var(--bg);color:var(--ink);}
    [data-testid="stHeader"]{background:transparent;}
    #MainMenu,footer{visibility:hidden;}
    h1,h2,h3,.brand,.section-title,.panel-title,.metric-value,.dose-time{font-family:'Poppins',sans-serif!important;color:var(--ink);letter-spacing:-.2px;}
    .stMarkdown p,label,li{color:#3F5F66;}

    /* sidebar */
    [data-testid="stSidebar"]{background:#fff;border-right:none;box-shadow:8px 0 40px rgba(64,224,208,.08);}
    .brand{font-size:1.35rem;font-weight:700;}
    .brand span{color:var(--teal-d);}
    .brand-mark{display:inline-flex;align-items:center;justify-content:center;width:42px;height:42px;border-radius:50%;
        margin-right:10px;color:#fff;font-size:1.2rem;background:var(--teal);box-shadow:0 8px 18px rgba(64,224,208,.4);vertical-align:middle;}
    .eyebrow{color:var(--teal-d);text-transform:uppercase;letter-spacing:2px;font-size:.7rem;font-weight:600;margin-bottom:8px;}
    .st-key-nav_radio label{padding:10px 14px;border-radius:14px;width:100%;margin-bottom:4px;transition:all .18s ease;}
    .st-key-nav_radio label > div:first-child{display:none;}
    .st-key-nav_radio label:hover{background:var(--teal-l);}
    .st-key-nav_radio label:has(input:checked){background:var(--teal);box-shadow:0 8px 20px rgba(64,224,208,.35);}
    .st-key-nav_radio label:has(input:checked) *{color:#fff!important;font-weight:600;}

    /* teal hero banner (like the dashboard card) */
    .hero{position:relative;overflow:hidden;padding:30px 34px;border-radius:30px;margin-bottom:24px;
        background:linear-gradient(135deg,#40E0D0,#3CD3C3);box-shadow:var(--shadow);}
    .hero::before{content:"";position:absolute;width:270px;height:270px;border-radius:50%;background:rgba(255,255,255,.16);right:-70px;top:-100px;}
    .hero::after{content:"";position:absolute;width:190px;height:190px;border-radius:50%;border:34px solid rgba(255,255,255,.14);right:100px;bottom:-115px;}
    .hero > *{position:relative;z-index:1;}
    .hero .eyebrow{color:rgba(255,255,255,.85);}
    .hero h1{color:#fff!important;font-size:clamp(1.55rem,2.6vw,2.2rem);line-height:1.25;margin:4px 0 10px;font-weight:700;padding:0;}
    .hero p{color:rgba(255,255,255,.93)!important;max-width:620px;font-size:.94rem;line-height:1.7;}
    .hero-glow{color:#0B4F4A;}

    /* cards */
    .metric-card,.panel,[data-testid="stVerticalBlockBorderWrapper"],[data-testid="stForm"],[data-testid="stExpander"],[data-testid="stMetric"]{
        background:#fff;border:none!important;border-radius:24px!important;box-shadow:var(--shadow);}
    .metric-card,.panel{padding:20px 22px;margin-bottom:14px;}
    [data-testid="stExpander"] details{border:none!important;}
    [data-testid="stMetric"]{padding:16px 20px;}
    [data-testid="stMetricValue"]{color:var(--ink);font-weight:700;}
    [data-testid="stMetricLabel"] p{color:var(--muted)!important;}
    .metric-card{min-height:140px;transition:transform .2s ease;}
    .metric-card:hover{transform:translateY(-3px);}
    .metric-top{display:flex;align-items:center;justify-content:space-between;gap:10px;}
    .metric-label{color:var(--muted);font-size:.82rem;font-weight:500;}
    .metric-icon{width:38px;height:38px;display:flex;align-items:center;justify-content:center;border-radius:50%;font-weight:700;
        background:color-mix(in srgb,currentColor 14%,#fff);}
    .metric-value{font-weight:700;font-size:2rem;margin-top:12px;line-height:1;}
    .metric-note{color:var(--muted);font-size:.76rem;margin-top:10px;}
    .section-title{font-size:1.15rem;font-weight:600;margin:20px 0 8px;}
    .panel-title{font-weight:600;font-size:1rem;margin-bottom:6px;}
    .panel-caption{color:var(--muted);font-size:.84rem;line-height:1.6;}
    .status-pill{display:inline-block;border-radius:999px;padding:5px 12px;font-size:.73rem;font-weight:600;background:var(--teal-l);color:var(--teal-d);}
    .divider{border:0;border-top:1px solid var(--line);margin:20px 0;}
    .empty-state{text-align:center;padding:34px 20px;border:1.5px dashed #BFEFE9;border-radius:22px;background:#fff;}
    .empty-icon{font-size:2rem;margin-bottom:8px;color:var(--teal-d);}
    .empty-title{color:var(--ink);font-weight:600;}
    .empty-text{color:var(--muted);font-size:.85rem;margin-top:6px;}
    .footer{color:var(--muted);font-size:.74rem;text-align:center;padding:20px 0 8px;}

    /* pill buttons */
    .stButton>button,.stFormSubmitButton>button,.stDownloadButton>button{width:100%;min-height:44px;border-radius:999px;
        border:1.5px solid var(--teal);background:#fff;color:var(--teal-d);font-weight:600;transition:all .18s ease;}
    .stButton>button:hover,.stFormSubmitButton>button:hover,.stDownloadButton>button:hover{background:var(--teal-l);color:var(--teal-d);border-color:var(--teal);transform:translateY(-1px);}
    .stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{background:var(--teal);color:#fff;border-color:transparent;box-shadow:0 8px 20px rgba(64,224,208,.38);}
    .stButton>button[kind="primary"]:hover,.stFormSubmitButton>button[kind="primary"]:hover{background:var(--teal);color:#fff;filter:brightness(1.05);}
    .stButton>button p,.stFormSubmitButton>button p,.stDownloadButton>button p{color:inherit!important;}

    /* inputs */
    .stTextInput input,.stTextArea textarea,.stDateInput input,.stNumberInput input,.stSelectbox div[data-baseweb="select"]>div,[data-testid="stFileUploader"] section{
        background:#fff!important;color:var(--ink)!important;border:1.5px solid var(--line)!important;border-radius:14px!important;}
    .stTextInput input:focus,.stTextArea textarea:focus{border-color:var(--teal)!important;box-shadow:0 0 0 3px rgba(64,224,208,.2)!important;}
    [data-testid="stAlert"]{border-radius:16px;}

    /* pill tabs */
    .stTabs [data-baseweb="tab-list"]{gap:6px;background:#fff;border-radius:999px;padding:5px;box-shadow:var(--shadow);width:fit-content;}
    .stTabs [data-baseweb="tab"]{border-radius:999px;padding:8px 22px;height:auto;color:var(--muted);font-weight:600;}
    .stTabs [data-baseweb="tab"] p{color:inherit!important;}
    .stTabs [aria-selected="true"]{background:var(--teal);color:#fff!important;}
    .stTabs [data-baseweb="tab-highlight"],.stTabs [data-baseweb="tab-border"]{display:none;}

    /* dose chips */
    .chip{display:inline-block;border-radius:999px;padding:5px 12px;font-size:.74rem;font-weight:600;}
    .chip-Taken{color:#0E9F8E;background:#DDF8F4;}
    .chip-Missed{color:#E5483A;background:#FFE7E4;}
    .chip-Skipped{color:#B8841C;background:#FFF2D6;}
    .chip-Pending{color:var(--blue);background:#E4EEFF;}
    .dose-time{font-weight:700;font-size:1.2rem;}
    .dose-name{font-weight:600;font-size:1.03rem;color:var(--ink);}
    .dose-meta{color:var(--muted);font-size:.88rem;}

    /* week strip (coral selected day) */
    .week{display:flex;justify-content:space-between;gap:8px;margin-top:14px;}
    .day{flex:1;text-align:center;padding:10px 0;border-radius:16px;color:var(--muted);font-size:.75rem;}
    .day b{display:block;font-size:1rem;margin-top:4px;}
    .day.on{background:var(--coral);color:#fff;box-shadow:0 8px 18px rgba(255,111,97,.35);}
    /* ring gauge */
    .ring{width:150px;height:150px;border-radius:50%;margin:6px auto;display:flex;align-items:center;justify-content:center;
        background:conic-gradient(var(--teal) calc(var(--p)*1%),#E3FAF7 0);}
    .ring-in{width:114px;height:114px;border-radius:50%;background:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;}
    .ring-in b{font-size:1.7rem;color:var(--ink);line-height:1;}
    .ring-in span{font-size:.72rem;color:var(--muted);margin-top:4px;}
    /* thin progress bars */
    .bar-row{display:flex;align-items:center;gap:12px;margin:14px 0;}
    .bar-label{width:70px;color:var(--muted);font-size:.8rem;}
    .bar-track{flex:1;height:6px;border-radius:99px;background:#EEF3F7;overflow:hidden;}
    .bar-fill{height:100%;border-radius:99px;}
    .bar-val{width:34px;text-align:right;font-weight:600;color:var(--ink);font-size:.85rem;}

    @media (max-width:700px){.hero{padding:22px;}.metric-value{font-size:1.7rem;}}
    @media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important;}}
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
    lang = st.session_state.get("lang", "English")
    base = TA if lang == "தமிழ்" else EN
    return nexcare.UI.get(lang, {}).get(key) or base.get(key, key)


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


def ring_html(pct, caption):
    p = 0 if pct is None else max(0, min(100, int(pct)))
    txt = "–" if pct is None else f"{p}%"
    return (f'<div class="panel" style="text-align:center"><div class="ring" style="--p:{p}">'
            f'<div class="ring-in"><b>{txt}</b><span>{safe_text(caption)}</span></div></div></div>')


def bar_row(label, count, total, color):
    w = round(100 * count / total) if total else 0
    return (f'<div class="bar-row"><div class="bar-label">{safe_text(label)}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{w}%;background:{color}"></div></div>'
            f'<div class="bar-val">{count}</div></div>')


def week_strip():
    base = core.now()
    cells = ""
    for off in range(-2, 3):
        d = base + timedelta(days=off)
        cls = "day on" if off == 0 else "day"
        cells += f'<div class="{cls}">{d.strftime("%a")}<b>{d.day:02d}</b></div>'
    st.markdown(f'<div class="panel"><div class="panel-title" style="text-align:center">{base.strftime("%B %Y")}</div>'
                f'<div class="week">{cells}</div></div>', unsafe_allow_html=True)


def adherence_panel(patient_id, days=7):
    s = core.adherence_stats(patient_id, days)
    total = s["Taken"] + s["Skipped"] + s["Missed"]
    c1, c2 = st.columns([1, 2], gap="medium")
    c1.markdown(ring_html(s["pct"], "adherence"), unsafe_allow_html=True)
    bars = (bar_row("Taken", s["Taken"], total, "#40E0D0") + bar_row("Skipped", s["Skipped"], total, "#F2B64B")
            + bar_row("Missed", s["Missed"], total, "#FF6F61"))
    c2.markdown(f'<div class="panel"><div class="panel-title">Dose summary · last {days} days</div>{bars}</div>',
                unsafe_allow_html=True)
    breakdown = core.daily_breakdown(patient_id, days)
    if any(r["Taken"] or r["Skipped"] or r["Missed"] for r in breakdown):
        df = pd.DataFrame(breakdown).set_index("Day")
        st.bar_chart(df, color=["#40E0D0", "#F2B64B", "#FF6F61"])
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
PATIENT_PAGES = ["Today", "Upload Prescription", "Report Explainer", "My Medicines", "My Adherence", "Link Doctor", "Agent Activity", "About"]
pages = DOCTOR_PAGES if is_doctor else PATIENT_PAGES

with st.sidebar:
    st.markdown(
        """
        <div style="padding: 0 0 24px;">
            <div><span class="brand-mark">✦</span><span class="brand">Nexus<span>Agent</span></span></div>
            <div style="color:#8AA0B2;font-size:.75rem;margin:10px 0 0 4px;letter-spacing:1.6px;text-transform:uppercase;">
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
        st.selectbox("Language / மொழி", nexcare.LANGS, key="lang")
    st.toggle("🌙 Dark mode", key="dark_mode")

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
        <div style="font-size:.76rem;color:#6B8294;line-height:1.7;"><b style="color:#0F3D3E;">Emergency?</b><br>
        This app is not an emergency service. Call <b>112</b> for urgent help.</div>""",
        unsafe_allow_html=True,
    )

page = selected_page
nexcare.inject_theme(st.session_state.get("dark_mode", False))
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
    with c1: render_metric("Linked patients", ov["patients"], "☺", "#1FB8A8", "Patients who shared their code")
    with c2: render_metric("Awaiting approval", ov["pending"], "◷", "#FF6F61", "Nothing runs until you approve")
    with c3: render_metric("Medicines tracked", ov["active_meds"], "✚", "#2F80ED", "With upcoming doses")
    with c4: render_metric("Open alerts", ov["alerts"], "!", "#F2B64B", "Missed / skipped doses, course ends")

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
    nexcare.today_extras(user, core, tr, st.session_state.get("lang", "English"), *ai_cfg())
    week_strip()
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
                            if action == "take":
                                st.session_state["_celebrate"] = True
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


def patient_reports():
    nexcare.report_page(user, core, show_header, st.session_state.get("lang", "English"), *ai_cfg())


PAGE_FUNCS = {
    "Dashboard": doctor_dashboard, "Prescriptions": doctor_prescriptions, "Patients": doctor_patients,
    "Today": patient_today, "Upload Prescription": patient_upload, "Report Explainer": patient_reports, "My Medicines": patient_medicines,
    "My Adherence": patient_adherence, "Link Doctor": patient_link,
    "Agent Activity": agent_activity, "About": about,
}
PAGE_FUNCS[page]()

st.markdown('<div class="footer">NEXUSAGENT · PRESCRIPTION READER AGENT · PROTOTYPE · FAKE DATA ONLY</div>',
            unsafe_allow_html=True)
