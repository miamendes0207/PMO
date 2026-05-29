import streamlit as st
from typing import Optional, Tuple, Dict
from modules.client_loader import (
    list_available_clients,
    load_client_config,
    ClientLoaderError,
    ClientNotFoundError,
    ClientConfigError
)


@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_available_clients() -> list:
    """
    Cached wrapper for listing available clients.
    TTL prevents stale data if clients are added/removed.
    """
    return list_available_clients()


@st.cache_data(ttl=300)
def get_client_config(client_name: str) -> Optional[Dict]:
    """
    Cached wrapper for loading client config.
    Returns None if config cannot be loaded.
    """
    try:
        return load_client_config(client_name)
    except ClientLoaderError as e:
        st.error(f"Failed to load config for {client_name}: {e}")
        return None


def client_selector() -> Tuple[Optional[str], Optional[Dict]]:
    """
    Display a client dropdown and manage the selected client in session state.

    Returns:
        Tuple of (selected_client_name, client_config) or (None, None) if no clients.
    """
    # Get available clients (cached)
    clients = get_available_clients()

    # Handle no clients case
    if not clients:
        st.warning("⚠️ No clients configured yet.")
        st.info("Add client folders to `modules/clients/` to get started.")
        return None, None

    # Initialize session state
    if "client" not in st.session_state or st.session_state["client"] not in clients:
        st.session_state["client"] = clients[0]

    # Calculate safe index
    try:
        current_index = clients.index(st.session_state["client"])
    except ValueError:
        current_index = 0
        st.session_state["client"] = clients[0]

    # Client selector
    selected = st.selectbox(
        "Select Client",
        options=clients,
        index=current_index,
        key="client_selector_dropdown",
        help="Choose which client configuration to use"
    )

    # Update session state if changed
    if selected != st.session_state["client"]:
        st.session_state["client"] = selected
        # Clear config cache for the new client to force reload
        get_client_config.clear()

    # Load and display config
    config = get_client_config(selected)

    if config:
        client_display_name = config.get('client_name', selected)

        # Display client info
        with st.container():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.success(f"✓ Using templates and tone for **{client_display_name}**")
            with col2:
                if st.button("🔄 Reload", help="Refresh client configuration"):
                    get_client_config.clear()
                    get_available_clients.clear()
                    st.rerun()

        # Optional: Show config details in expander
        with st.expander("📋 View Configuration Details"):
            st.json(config)

        return selected, config
    else:
        st.error(f"❌ Failed to load configuration for **{selected}**")
        st.info("Check the client folder structure and config files.")
        return selected, None


def client_selector_sidebar() -> Tuple[Optional[str], Optional[Dict]]:
    """
    Sidebar variant of client selector for cleaner layouts.

    Returns:
        Tuple of (selected_client_name, client_config) or (None, None) if no clients.
    """
    with st.sidebar:
        st.header("🏢 Client Configuration")
        return client_selector()


def get_current_client() -> Tuple[Optional[str], Optional[Dict]]:
    """
    Get the currently selected client without rendering UI.
    Useful for accessing client info in other parts of the app.

    Returns:
        Tuple of (selected_client_name, client_config) or (None, None)
    """
    if "client" not in st.session_state:
        return None, None

    client_name = st.session_state["client"]
    config = get_client_config(client_name)

    return client_name, config


def ensure_client_selected() -> Tuple[str, Dict]:
    """
    Ensures a client is selected, raises error if not.
    Use this in pages that require a client to be selected.

    Returns:
        Tuple of (selected_client_name, client_config)

    Raises:
        RuntimeError: If no client is selected or config is invalid
    """
    client_name, config = get_current_client()

    if not client_name or not config:
        st.error("⚠️ No client selected or invalid configuration")
        st.stop()

    return client_name, config


# ------------------------------------------------------------
# Advanced: Multi-client selector
# ------------------------------------------------------------
def multi_client_selector(key: str = "multi_client") -> Tuple[list, Dict[str, Dict]]:
    """
    Allow selection of multiple clients at once.
    Useful for comparison or batch operations.

    Args:
        key: Unique key for this multi-selector widget

    Returns:
        Tuple of (selected_client_names, dict of configs by client name)
    """
    clients = get_available_clients()

    if not clients:
        st.warning("⚠️ No clients configured yet.")
        return [], {}

    selected_clients = st.multiselect(
        "Select Clients",
        options=clients,
        default=st.session_state.get(key, [clients[0]]),
        key=f"{key}_multiselect",
        help="Choose one or more client configurations"
    )

    st.session_state[key] = selected_clients

    # Load configs for all selected clients
    configs = {}
    for client in selected_clients:
        config = get_client_config(client)
        if config:
            configs[client] = config
        else:
            st.warning(f"⚠️ Failed to load config for {client}")

    if configs:
        st.success(f"✓ Loaded {len(configs)} client configuration(s)")

    return selected_clients, configs


# ------------------------------------------------------------
# Example usage
# ------------------------------------------------------------
if __name__ == "__main__":
    st.set_page_config(page_title="Client Selector Demo", layout="wide")

    st.title("Client Selector Components")

    # Tab 1: Standard selector
    tab1, tab2, tab3 = st.tabs(["Standard", "Sidebar", "Multi-Select"])

    with tab1:
        st.header("Standard Client Selector")
        client, config = client_selector()

        if client and config:
            st.write("**Selected Client:**", client)
            st.write("**Config Keys:**", list(config.keys()))

    with tab2:
        st.header("Sidebar Client Selector")
        st.write("Check the sidebar →")
        client, config = client_selector_sidebar()

        if client and config:
            st.write("**Selected Client:**", client)

    with tab3:
        st.header("Multi-Client Selector")
        clients, configs = multi_client_selector()

        if configs:
            for client_name, client_config in configs.items():
                with st.expander(f"📁 {client_name}"):
                    st.json(client_config)