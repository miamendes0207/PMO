# modules/notifications_overlay.py

from __future__ import annotations

import html
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from modules.db import get_inapp_notifications, dismiss_all_notifications


def _severity(sev: str) -> tuple[str, str]:
    s = (sev or "info").lower()
    if s == "critical":
        return "\U0001f534", "Critical"
    if s == "warning":
        return "\U0001f7e1", "Warning"
    return "\U0001f535", "Info"


@st.fragment(run_every=30)
def render_notifications_overlay(user_email: str, limit: int = 20):
    email_norm = (user_email or "").strip().lower()
    if not email_norm:
        return

    # Handle dismiss triggered from JS via query param
    if st.query_params.get("notif_dismiss") == "1":
        dismiss_all_notifications(email_norm)
        st.query_params.pop("notif_dismiss", None)
        st.rerun(scope="fragment")

    # ---------------------------
    # Load notifications
    # FIX: removed the spurious _tick kwarg — get_inapp_notifications
    # does not accept it, causing a TypeError that swallowed all results.
    # Cache-busting is handled naturally by the fragment's run_every=30 cycle.
    # ---------------------------
    df = get_inapp_notifications(email_norm, limit=limit)

    has_notifs = isinstance(df, pd.DataFrame) and not df.empty
    count = int(len(df)) if has_notifs else 0
    count_label = f"{count} unread" if count > 0 else "All caught up"
    badge = f'<span id="ss-badge">{count}</span>' if count > 0 else ""

    # ---------------------------
    # Build cards
    # ---------------------------
    cards_html = ""
    if has_notifs:
        for _, r in df.iterrows():
            title = html.escape(str(r.get("title") or "Notification"))
            body  = html.escape(str(r.get("body") or "").strip())
            icon, _ = _severity(str(r.get("severity") or "info"))

            meta_parts = []
            if r.get("event_type"):
                meta_parts.append(html.escape(str(r["event_type"])))
            if r.get("created_at"):
                meta_parts.append(str(r["created_at"])[:19].replace("T", " "))

            meta      = " &middot; ".join(meta_parts)
            body_html = f'<p class="notif-body">{body}</p>' if body else ""
            meta_html = f'<p class="notif-meta">{meta}</p>' if meta else ""

            cards_html += f"""
<div class="notif-card">
  <span class="notif-icon">{icon}</span>
  <div class="notif-text">
    <strong>{title}</strong>
    {body_html}
    {meta_html}
  </div>
</div>"""

    panel_body = cards_html if has_notifs else "<p class='notif-empty'>You're all caught up &mdash; no new notifications. &#x2705;</p>"
    dismiss_btn = "<div class='dismiss-footer'><button class='dismiss-link' onclick='dismissAll()'>&#x1f5d1; Dismiss All</button></div>" if has_notifs else ""

    # ---------------------------
    # Render via components.html so the iframe is real and JS can reach parent
    # ---------------------------
    components.html(f"""
<!DOCTYPE html>
<html>
<head>
<style>
  body {{ margin: 0; padding: 0; background: transparent; overflow: hidden; }}

  #ss-notif-wrap {{
    position: fixed;
    top: 16px;
    right: 20px;
    z-index: 99999;
    font-family: sans-serif;
  }}

  #ss-bell {{
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    border-radius: 999px;
    background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    box-shadow: 0 4px 14px rgba(79,172,254,0.45);
    font-size: 1.25rem;
    color: white;
    cursor: pointer;
    border: none;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }}
  #ss-bell:hover {{
    transform: translateY(-2px) scale(1.06);
    box-shadow: 0 8px 22px rgba(79,172,254,0.55);
  }}

  #ss-badge {{
    position: absolute;
    top: -6px; right: -6px;
    background: #ef4444;
    color: white;
    font-size: 0.6rem;
    font-weight: 900;
    min-width: 18px;
    height: 18px;
    border-radius: 999px;
    padding: 0 4px;
    border: 2px solid white;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    line-height: 1;
  }}

  #ss-notif-panel {{
    display: none;
    position: fixed;
    top: 68px;
    right: 20px;
    width: 340px;
    max-height: 480px;
    overflow-y: auto;
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    box-shadow: 0 12px 40px rgba(0,0,0,0.15);
    padding: 16px;
    color: #1e293b;
    z-index: 99999;
  }}
  #ss-notif-panel.open {{ display: block; }}

  .notif-header {{ font-size: 1rem; font-weight: 700; margin: 0 0 2px; color: #0f172a; }}
  .notif-subhead {{ font-size: 0.75rem; color: #64748b; margin: 0 0 12px; padding-bottom: 10px; border-bottom: 1px solid #e2e8f0; }}
  .notif-card {{ display: flex; gap: 10px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; }}
  .notif-icon {{ font-size: 1.1rem; flex-shrink: 0; padding-top: 2px; }}
  .notif-text {{ flex: 1; min-width: 0; }}
  .notif-text strong {{ display: block; font-size: 0.85rem; color: #0f172a; margin-bottom: 3px; }}
  .notif-body {{ font-size: 0.8rem; color: #475569; margin: 0 0 3px; word-break: break-word; }}
  .notif-meta {{ font-size: 0.7rem; color: #94a3b8; margin: 0; }}
  .notif-empty {{ font-size: 0.85rem; color: #64748b; text-align: center; padding: 20px 0; margin: 0; }}
  .dismiss-footer {{ margin-top: 4px; padding-top: 10px; border-top: 1px solid #e2e8f0; display: flex; justify-content: flex-end; }}
  .dismiss-link {{ font-size: 0.78rem; color: #ef4444; background: transparent; border: 1px solid #ef4444; border-radius: 6px; padding: 4px 14px; font-weight: 600; cursor: pointer; }}
</style>
</head>
<body>

<div id="ss-notif-wrap">
  <button id="ss-bell" onclick="togglePanel(event)" title="Notifications">
    &#x1f514;{badge}
  </button>
</div>

<div id="ss-notif-panel">
  <p class="notif-header">&#x1f514; Notifications</p>
  <p class="notif-subhead">{count_label}</p>
  {panel_body}
  {dismiss_btn}
</div>

<script>
  // Move the widget and panel into the parent document so they
  // sit on top of the real Streamlit page, not inside the iframe.
  (function() {{
    var parentDoc = window.parent.document;

    // ── Styles ──────────────────────────────────────────────────
    if (!parentDoc.getElementById('ss-notif-style')) {{
      var link = parentDoc.createElement('style');
      link.id = 'ss-notif-style';
      link.textContent = document.querySelector('style').textContent;
      parentDoc.head.appendChild(link);
    }}

    // ── Move bell wrap ───────────────────────────────────────────
    var existingWrap = parentDoc.getElementById('ss-notif-wrap');
    if (existingWrap) existingWrap.remove();
    var wrap = document.getElementById('ss-notif-wrap');
    parentDoc.body.appendChild(wrap);

    // ── Move panel ───────────────────────────────────────────────
    var existingPanel = parentDoc.getElementById('ss-notif-panel');
    var wasOpen = existingPanel && existingPanel.classList.contains('open');
    if (existingPanel) existingPanel.remove();
    var panel = document.getElementById('ss-notif-panel');
    parentDoc.body.appendChild(panel);
    if (wasOpen) panel.classList.add('open');

    // ── Functions ────────────────────────────────────────────────
    window.parent.togglePanel = function(e) {{
      e.stopPropagation();
      parentDoc.getElementById('ss-notif-panel').classList.toggle('open');
    }};

    // Wire up the bell button that's now in the parent doc
    parentDoc.getElementById('ss-bell').onclick = function(e) {{
      e.stopPropagation();
      parentDoc.getElementById('ss-notif-panel').classList.toggle('open');
    }};

    // Close on outside click
    if (!window.parent._ssNotifOutside) {{
      window.parent._ssNotifOutside = true;
      parentDoc.addEventListener('click', function(e) {{
        var w = parentDoc.getElementById('ss-notif-wrap');
        var p = parentDoc.getElementById('ss-notif-panel');
        if (p && w && !w.contains(e.target) && !p.contains(e.target)) {{
          p.classList.remove('open');
        }}
      }});
    }}

    window.parent.dismissAll = function() {{
      var p = parentDoc.getElementById('ss-notif-panel');
      if (!p) return;
      p.querySelectorAll('.notif-card').forEach(function(c) {{ c.remove(); }});
      var f = p.querySelector('.dismiss-footer');
      if (f) f.remove();
      var b = parentDoc.getElementById('ss-badge');
      if (b) b.remove();
      var sub = p.querySelector('.notif-subhead');
      if (sub) sub.textContent = 'All caught up';
      var empty = parentDoc.createElement('p');
      empty.className = 'notif-empty';
      empty.textContent = "You're all caught up \u2014 no new notifications. \u2705";
      p.appendChild(empty);
      // Signal Streamlit to dismiss server-side
      var url = new URL(window.parent.location.href);
      url.searchParams.set('notif_dismiss', '1');
      window.parent.history.replaceState(null, '', url.toString());
    }};
  }})();
</script>
</body>
</html>
""", height=0, scrolling=False)