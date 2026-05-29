import streamlit as st
from modules.db import run_query

st.title("Database Test")

df = run_query("SELECT now()")
st.write(df)


import streamlit as st
from modules.db import reset_user_password

st.title("🔐 Admin Password Reset (Temporary)")

email = st.text_input("User email").strip().lower()
new_pw = st.text_input("New password", type="password")

if st.button("Reset password"):
    if not email or not new_pw:
        st.error("Both fields required.")
    else:
        reset_user_password(email, new_pw)
        st.success(f"Password reset for {email}")
