import streamlit as st

def logout():
    """Clear session state and return user to login page."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]

    st.session_state["auth"] = False
    st.session_state["email"] = None

    st.rerun()
