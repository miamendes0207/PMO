# ============================================================
# auth/login.py — ScopeSight 1.0
# Email-based login (public.users) + branding + helpers
# ============================================================

import streamlit as st
from pathlib import Path
import base64
import re

from modules.db import validate_user
from modules.ui_sidebar import render_login_sidebar

# ============================================================
# OPENAI BOOTSTRAP (runs once per session)
# ============================================================

import os

if not st.session_state.get("_openai_bootstrapped"):
    # Prefer Streamlit secrets, fall back to env
    api_key = None

    if "OPENAI_API_KEY" in st.secrets:
        api_key = st.secrets["OPENAI_API_KEY"]
    elif os.getenv("OPENAI_API_KEY"):
        api_key = os.getenv("OPENAI_API_KEY")

    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
        st.session_state["_openai_bootstrapped"] = True
    else:
        # Don’t crash the app, but make it obvious in logs
        st.session_state["_openai_bootstrapped"] = False

# ============================================================
# PASSWORD VALIDATION HELPERS
# ============================================================

def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validate strong password rules."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must include an uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must include a lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must include a number."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must include a special character."
    return True, ""


# ============================================================
# LOGIN GUARD
# ============================================================

def require_login():
    """Page guard. Call at the top of any protected page."""
    if not st.session_state.get("auth"):
        login_page()
        st.stop()


# ============================================================
# LOGIN PAGE (BRANDED)
# ============================================================

def login_page():
    # ---------------------------------------------------------
    # DEV MODE QUERY PARAM
    # ---------------------------------------------------------
    try:
        query = st.query_params
    except AttributeError:
        query = st.experimental_get_query_params()

    if query.get("dev") == "1":
        st.session_state["force_dev_mode"] = True

    # ---------------------------------------------------------
    # SAFE HEADER / LAYOUT CLEANUP
    # ---------------------------------------------------------
    st.markdown(
        """
        <style>
            [data-testid="stDecoration"] {
                background-color: #A3C73E !important;
                height: 6px !important;
            }
            header[data-testid="stHeader"] {
                display: none !important;
            }
            .block-container {
                padding-top: 1rem !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Use the proper formatted sidebar (brand-only, no auth required)
    render_login_sidebar()

    # ---------------------------------------------------------
    # BRANDING THEME
    # ---------------------------------------------------------
    st.markdown(
        """
        <style>
        body { background-color: #FFFFFF !important; }

        .login-container {
            max-width: 420px;
            margin: 60px auto;
            padding: 40px;
            background-color: #F8F9FC;
            border-radius: 16px;
            border: 1px solid #192B56;
            box-shadow: 0 4px 10px rgba(0,0,0,0.05);
            text-align: center;
        }

        .login-title {
            font-size: 1.6rem;
            font-weight: 800;
            color: #142D53;
            margin-bottom: 6px;
        }

        .login-subtitle {
            font-size: 0.95rem;
            color: #1E74BB;
            margin-bottom: 25px;
        }

        .stTextInput > label {
            font-weight: 600 !important;
            color: #142D53 !important;
        }

        .stTextInput > div > input {
            border-radius: 8px !important;
            border: 1px solid #C7D2E1 !important;
            background-color: white !important;
        }

        .stButton>button {
            background-color: #142D53 !important;
            color: white !important;
            border-radius: 8px !important;
            padding: 0.55rem 1rem !important;
            font-weight: 700 !important;
            width: 100% !important;
            transition: all 0.2s ease-in-out !important;
        }

        .stButton>button:hover {
            background-color: #1E74BB !important;
            transform: scale(1.03);
        }

        .forgot-text {
            font-size: 0.85rem;
            color: #555;
            margin-top: 12px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---------------------------------------------------------
    # LOGO (MAIN BODY)
    # ---------------------------------------------------------
    logo_path = Path("assets/plenitude_logo.png")
    if logo_path.exists():
        encoded = base64.b64encode(logo_path.read_bytes()).decode()
        st.markdown(
            f"""
            <div style="text-align:center; margin-top:20px;">
                <img src="data:image/png;base64,{encoded}" width="180"/>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ---------------------------------------------------------
    # LOGIN CARD
    # ---------------------------------------------------------
    st.markdown("<div class='login-container'>", unsafe_allow_html=True)

    st.markdown(
        "<div class='login-title'>Login to ScopeSight</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='login-subtitle'>Plenitude Consulting • PMO Automation Platform</div>",
        unsafe_allow_html=True,
    )

    # =========================================================
    # LOGIN FORM ✅ FIXES STREAMLIT RERUN PASSWORD BUG
    # =========================================================
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email address")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    email = (email or "").strip().lower()
    password = (password or "").strip()

    # ---------------------------------------------------------
    # SECRET DEVELOPER LOGIN
    # ---------------------------------------------------------
    if email == "developer@scopesight.local":
        st.session_state.update(
            {
                "auth": True,
                "email": email,
                "username": "Developer Mode",
                "clients": ["*"],
                "role": "admin",
                "force_dev_mode": True,
            }
        )
        st.success("Developer mode activated.")
        st.rerun()

    # ---------------------------------------------------------
    # NORMAL LOGIN
    # ---------------------------------------------------------
    if submitted:
        if not email or not password:
            st.error("Please enter both email and password.")
        else:
            user = validate_user(email, password)

            if user:
                # Make this robust to whatever validate_user returns
                uid = user.get("user_id") or user.get("id")
                email_val = (user.get("email") or user.get("user_email") or email).strip().lower()
                full_name = user.get("full_name") or user.get("name") or user.get("username") or ""

                st.session_state.update(
                    {
                        "auth": True,
                        "user_id": user.get("user_id"),
                        "email": email_val,
                        "username": full_name or email_val,
                        "full_name": full_name,
                        "role": user.get("role", "user"),
                        "clients": ["*"],
                    }
                )
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid email or password.")

    st.markdown(
        "<div class='forgot-text'>Forgot your password? Contact your PMO admin.</div>",
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)
