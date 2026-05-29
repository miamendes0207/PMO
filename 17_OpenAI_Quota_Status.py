# ============================================================
# 17_🔋_OpenAI_Quota_Status.py — ScopeSight v1.3
# Leni Diagnostics Dashboard (NO Admin / Usage API required)
#
# Works with existing OPENAI_API_KEY (sk-pro…)
# Shows:
# - ✅ Connectivity check (OpenAI reachable?)
# - ✅ Model access sanity check
# - ✅ Lightweight “can Leni respond?” test
# - ✅ Error classifier (rate limit / quota / auth / network)
# - ✅ Session counters (calls, failures, last error)
#
# NOTES:
# - This does NOT read org billing/credits (requires api.usage.read / admin key)
# ============================================================

import os
import json
import time
import datetime as dt

import requests
import streamlit as st
import humanize

from auth.login import require_login
from modules.ui_branding import set_pmo_theme, pmo_footer
from modules.ui_sidebar import render_sidebar
from modules.ui_hide_nav import hide_streamlit_nav



# -----------------------------------------------------------
# PAGE CONFIG (must be FIRST Streamlit command)
# -----------------------------------------------------------
st.set_page_config(
    page_title="🔋 Leni Diagnostics",
    page_icon="🔋",
    layout="wide",
)


# -----------------------------------------------------------
# BOOTSTRAP
# -----------------------------------------------------------
require_login()
hide_streamlit_nav()
set_pmo_theme(page_title="🔋 Leni Diagnostics")
render_sidebar()


# -----------------------------------------------------------
# STYLES
# -----------------------------------------------------------
st.markdown(
    """
<style>
header[data-testid="stHeader"] { height: 0px !important; visibility: hidden !important; }

.section-header {
    background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
    padding: 1rem 1.5rem;
    border-radius: 8px;
    margin: 1.75rem 0 1rem 0;
}
.section-header h3 { color: white; margin: 0; font-size: 1.2rem; font-weight: 700; }

.step-header {
    background: #f0f9ff;
    border-left: 4px solid #4facfe;
    padding: 0.75rem 1rem;
    border-radius: 6px;
    margin: 1.25rem 0 0.75rem 0;
}
.step-header h4 { color: #0077be; margin: 0; font-size: 1.05rem; font-weight: 700; }

.info-box {
    background: #f0fff4;
    border-left: 4px solid #48bb78;
    padding: 1rem;
    border-radius: 6px;
    margin: 1rem 0 1.25rem 0;
}

.warning-box {
    background: #fffbeb;
    border-left: 4px solid #f59e0b;
    padding: 1rem;
    border-radius: 6px;
    margin: 1rem 0 1.25rem 0;
}

.danger-box {
    background: #fef2f2;
    border-left: 4px solid #ef4444;
    padding: 1rem;
    border-radius: 6px;
    margin: 1rem 0 1.25rem 0;
}

.metric-card {
    background: #f0f9ff;
    border: 2px solid #bae6fd;
    border-radius: 10px;
    padding: 1.1rem;
    text-align: center;
    margin: 0.35rem 0;
}
.metric-value { font-size: 1.8rem; font-weight: 800; color: #0077be; margin: 0.35rem 0; }
.metric-label { color: #0369a1; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px; }

.small-note { color: #64748b; font-size: 0.9rem; font-style: italic; margin: 0.4rem 0; }

code { font-size: 0.9rem; }
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------------------------------------
# CONFIG
# -----------------------------------------------------------
BASE_URL = "https://api.openai.com/v1"

def get_key_with_source():
    # Prefer Streamlit secrets
    k = None
    src = None
    try:
        k = st.secrets.get("openai_api_key")
        if k:
            return k, "st.secrets['openai_api_key']"
    except Exception:
        pass

    k = os.environ.get("OPENAI_API_KEY")
    if k:
        return k, "os.environ['OPENAI_API_KEY']"

    try:
        k = st.secrets.get("OPENAI_API_KEY")
        if k:
            return k, "st.secrets['OPENAI_API_KEY']"
    except Exception:
        pass

    return None, "(not found)"


def mask_key(k: str | None) -> str:
    if not k:
        return "(none)"
    k = str(k).strip()
    if len(k) < 10:
        return k[:3] + "…"
    return f"{k[:6]}…{k[-4:]}"


OPENAI_API_KEY, KEY_SRC = get_key_with_source()


# -----------------------------------------------------------
# SESSION METRICS (in-memory)
# -----------------------------------------------------------
def _init_session_metrics():
    st.session_state.setdefault("leni_diag_calls", 0)
    st.session_state.setdefault("leni_diag_success", 0)
    st.session_state.setdefault("leni_diag_fail", 0)
    st.session_state.setdefault("leni_diag_last_error", "")
    st.session_state.setdefault("leni_diag_last_error_type", "")
    st.session_state.setdefault("leni_diag_last_status", None)
    st.session_state.setdefault("leni_diag_last_ok_ts", None)

_init_session_metrics()


# -----------------------------------------------------------
# OPTIONAL: Persistent logging hook (DB)
# -----------------------------------------------------------
# def log_event(event_type: str, payload: dict):
#     """
#     Optional persistent logging. Create a table e.g. leni_diag_events
#     and store diagnostics over time.
#     """
#     run_execute(
#         """
#         INSERT INTO public.leni_diag_events (event_type, payload, created_at)
#         VALUES (:t, :p::jsonb, NOW())
#         """,
#         {"t": event_type, "p": json.dumps(payload)}
#     )


# -----------------------------------------------------------
# HTTP + ERROR CLASSIFICATION
# -----------------------------------------------------------
def classify_error(status_code: int | None, body: dict | None, exc: Exception | None) -> tuple[str, str]:
    """
    Returns (error_type, user_hint)
    """
    if exc is not None:
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            return "network_timeout", "Network timeout. Check internet / firewall / proxy."
        if "connection" in msg or "dns" in msg:
            return "network_error", "Network connectivity issue. Check DNS / firewall."
        return "unknown_exception", "Unexpected client error."

    if status_code is None:
        return "unknown", "Unknown error."

    if status_code in (401, 403):
        # 403 can be permission/scope; 401 is invalid/expired key
        if body and isinstance(body, dict) and "error" in body:
            emsg = str(body.get("error")).lower()
            if "incorrect api key" in emsg or "invalid" in emsg:
                return "auth_invalid_key", "API key invalid/expired. Replace OPENAI_API_KEY."
        return "auth_or_permission", "Auth/permission issue. Check key + project permissions."

    if status_code == 429:
        # Could be rate limit or quota
        txt = json.dumps(body or {}).lower()
        if "insufficient_quota" in txt or "quota" in txt:
            return "insufficient_quota", "Quota/credits issue. Billing/limits may be exhausted."
        return "rate_limited", "Rate limited. Reduce requests, add backoff, or raise limits."

    if status_code >= 500:
        return "openai_server_error", "OpenAI server issue. Try again later."

    # 400/404 etc
    return "request_error", "Request rejected. Check endpoint/model name."


def openai_get(path: str, params: dict | None = None, timeout: int = 20):
    if not OPENAI_API_KEY:
        raise RuntimeError("Missing OPENAI_API_KEY. Add it to env or Streamlit secrets.")
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    r = requests.get(f"{BASE_URL}{path}", headers=headers, params=params, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = {"raw_text": r.text}
    return r.status_code, data


def openai_post(path: str, payload: dict, timeout: int = 30):
    if not OPENAI_API_KEY:
        raise RuntimeError("Missing OPENAI_API_KEY. Add it to env or Streamlit secrets.")
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    r = requests.post(f"{BASE_URL}{path}", headers=headers, json=payload, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = {"raw_text": r.text}
    return r.status_code, data


def run_check(label: str, fn):
    """
    Wrap a check and update session counters + last error info.
    """
    st.session_state["leni_diag_calls"] += 1
    start = time.time()
    status_code = None
    data = None
    exc = None

    try:
        status_code, data = fn()
        ok = (200 <= int(status_code) < 300)
        elapsed = time.time() - start

        st.session_state["leni_diag_last_status"] = status_code

        if ok:
            st.session_state["leni_diag_success"] += 1
            st.session_state["leni_diag_last_error"] = ""
            st.session_state["leni_diag_last_error_type"] = ""
            st.session_state["leni_diag_last_ok_ts"] = dt.datetime.utcnow().isoformat()
            return True, status_code, data, elapsed
        else:
            etype, hint = classify_error(status_code, data, None)
            st.session_state["leni_diag_fail"] += 1
            st.session_state["leni_diag_last_error_type"] = etype
            st.session_state["leni_diag_last_error"] = hint
            return False, status_code, data, elapsed

    except Exception as e:
        elapsed = time.time() - start
        exc = e
        etype, hint = classify_error(None, None, exc)
        st.session_state["leni_diag_fail"] += 1
        st.session_state["leni_diag_last_error_type"] = etype
        st.session_state["leni_diag_last_error"] = hint
        return False, status_code, {"exception": str(e)}, elapsed


# -----------------------------------------------------------
# HEADER
# -----------------------------------------------------------
st.markdown(
    """
<div class='info-box'>
    <strong style='color:#2f855a;'>✅ This version requires NO Admin key.</strong><br/>
    It uses your normal <code>OPENAI_API_KEY</code> and focuses on operational health, not billing telemetry.
</div>
""",
    unsafe_allow_html=True,
)


# -----------------------------------------------------------
# DIAGNOSTICS SUMMARY
# -----------------------------------------------------------
st.markdown(
    """
    <div class='section-header'>
        <h3>🔑 Key & Runtime Summary</h3>
    </div>
    """,
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Key Loaded</div><div class='metric-value'>{'YES' if OPENAI_API_KEY else 'NO'}</div></div>",
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Key Source</div><div class='metric-value' style='font-size:1.0rem;'>{KEY_SRC}</div></div>",
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Key Masked</div><div class='metric-value' style='font-size:1.0rem;'>{mask_key(OPENAI_API_KEY)}</div></div>",
        unsafe_allow_html=True,
    )
with c4:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Last OK</div><div class='metric-value' style='font-size:1.0rem;'>{('—' if not st.session_state['leni_diag_last_ok_ts'] else humanize.naturaltime(dt.datetime.utcnow() - dt.datetime.fromisoformat(st.session_state['leni_diag_last_ok_ts'])) )}</div></div>",
        unsafe_allow_html=True,
    )

if not OPENAI_API_KEY:
    st.markdown(
        """
<div class='danger-box'>
    <strong>❌ OPENAI_API_KEY not found.</strong><br/>
    Add it as an environment variable or in <code>.streamlit/secrets.toml</code> as <code>openai_api_key</code>.
</div>
""",
        unsafe_allow_html=True,
    )
    pmo_footer()
    st.stop()


# -----------------------------------------------------------
# RUN CHECKS
# -----------------------------------------------------------
st.markdown(
    """
    <div class='section-header'>
        <h3>🩺 Health Checks</h3>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class='small-note'>
Tip: Start with “Ping OpenAI”. If that passes but “Leni test call” fails, it’s usually model access or rate limits.
</div>
""",
    unsafe_allow_html=True,
)

btn1, btn2, btn3 = st.columns(3)

with btn1:
    do_ping = st.button("✅ Ping OpenAI (/models)", use_container_width=True)
with btn2:
    do_list = st.button("✅ List 10 models", use_container_width=True)
with btn3:
    do_test = st.button("✅ Leni test call (tiny response)", use_container_width=True)

# Area to show outputs
out = st.container()

if do_ping:
    ok, status, data, elapsed = run_check("models_ping", lambda: openai_get("/models"))
    with out:
        if ok:
            st.success(f"✅ OpenAI reachable. HTTP {status} in {elapsed:.2f}s")
        else:
            et = st.session_state["leni_diag_last_error_type"]
            hint = st.session_state["leni_diag_last_error"]
            st.error(f"❌ Ping failed. HTTP {status} in {elapsed:.2f}s — {et}")
            st.write(hint)
            st.json(data)

if do_list:
    ok, status, data, elapsed = run_check("models_list", lambda: openai_get("/models"))
    with out:
        if ok:
            models = (data.get("data") or [])[:10]
            st.success(f"✅ Models fetched. HTTP {status} in {elapsed:.2f}s")
            st.json({"sample_models": models})
        else:
            et = st.session_state["leni_diag_last_error_type"]
            hint = st.session_state["leni_diag_last_error"]
            st.error(f"❌ Model list failed. HTTP {status} in {elapsed:.2f}s — {et}")
            st.write(hint)
            st.json(data)

if do_test:
    # Use Responses API (recommended), tiny output
    payload = {
        "model": "gpt-4o-mini",
        "input": "Reply with the single word: OK",
        "max_output_tokens": 5,
    }
    ok, status, data, elapsed = run_check(
        "leni_test_response",
        lambda: openai_post("/responses", payload),
    )
    with out:
        if ok:
            # Try to extract a small preview safely
            preview = ""
            try:
                # responses output can vary; show raw if unknown
                preview = data.get("output_text") or ""
            except Exception:
                preview = ""
            st.success(f"✅ Leni test call succeeded. HTTP {status} in {elapsed:.2f}s")
            if preview:
                st.write(f"**Output:** {preview}")
            else:
                st.json(data)
        else:
            et = st.session_state["leni_diag_last_error_type"]
            hint = st.session_state["leni_diag_last_error"]
            st.error(f"❌ Leni test call failed. HTTP {status} in {elapsed:.2f}s — {et}")
            st.write(hint)
            st.json(data)


# -----------------------------------------------------------
# SESSION HEALTH SNAPSHOT
# -----------------------------------------------------------
st.markdown(
    """
    <div class='section-header'>
        <h3>📌 Session Snapshot</h3>
    </div>
    """,
    unsafe_allow_html=True,
)

calls = int(st.session_state["leni_diag_calls"])
succ = int(st.session_state["leni_diag_success"])
fail = int(st.session_state["leni_diag_fail"])
last_type = st.session_state["leni_diag_last_error_type"] or "—"
last_hint = st.session_state["leni_diag_last_error"] or "—"
last_status = st.session_state["leni_diag_last_status"]

s1, s2, s3, s4 = st.columns(4)
with s1:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Calls</div><div class='metric-value'>{calls}</div></div>",
        unsafe_allow_html=True,
    )
with s2:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Success</div><div class='metric-value'>{succ}</div></div>",
        unsafe_allow_html=True,
    )
with s3:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Failures</div><div class='metric-value' style='color:#dc2626;'>{fail}</div></div>",
        unsafe_allow_html=True,
    )
with s4:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>Last HTTP</div><div class='metric-value'>{last_status if last_status is not None else '—'}</div></div>",
        unsafe_allow_html=True,
    )

st.markdown(
    f"""
<div class='warning-box'>
    <strong>Last error type:</strong> <code>{last_type}</code><br/>
    <strong>Suggested action:</strong> {last_hint}
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class='info-box'>
    <strong style='color:#2f855a;'>Want real “usage over time” without admin access?</strong><br/>
    Log Leni calls in your own database (per request: timestamp, model, tokens, error_type).<br/>
    Then this page can show accurate trends for <i>your app</i> even if org telemetry is locked down.
</div>
""",
    unsafe_allow_html=True,
)

# -----------------------------------------------------------
# FOOTER
# -----------------------------------------------------------
pmo_footer()
