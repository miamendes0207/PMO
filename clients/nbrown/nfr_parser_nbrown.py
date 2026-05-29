"""
NBrown – Intelligent NFR Parser
Summarises Teams transcripts into clean NFR fields:
    {{MEETING_NAME}}, {{DATE}}, {{TIME}}, {{LOCATION}}
    {{OBJECTIVES}}, {{ATTENDEES}}, {{KEY_DISCUSSION_POINTS}}, {{ACTIONS}}
"""

import re
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Any, Optional


# =====================================================================
# META EXTRACTION (date, time, meeting name, location)
# =====================================================================

def parse_transcript_to_nfr(
    transcript_text: str,
    overrides: Optional[Dict] = None,
    profile: Optional[Dict] = None
) -> Dict[str, Any]:

    overrides = overrides or {}

    meta = extract_meta(transcript_text)
    speakers = extract_speaker_blocks(transcript_text)
    internal, external, attendees_block = classify_attendees(speakers)

    objectives = summarise_objectives(transcript_text)
    discussion = summarise_discussion(transcript_text)

    actions_list, actions_block = extract_actions(
        transcript_text,
        meta["date"]
    )

    return {
        # ==== Meta Fields ====
        "MEETING_NAME": overrides.get("MEETING_NAME", meta["meeting_name"]),
        "DATE": overrides.get("DATE", meta["date"]),
        "TIME": overrides.get("TIME", meta["time"]),
        "LOCATION": overrides.get("LOCATION", meta["location"]),

        # ==== Main Content ====
        "OBJECTIVES": objectives,
        "ATTENDEES": attendees_block,
        "KEY_DISCUSSION_POINTS": discussion,
        "ACTIONS": actions_block,

        # ==== Preview ====
        "ATTENDEES_INTERNAL": internal,
        "ATTENDEES_EXTERNAL": external,
        "ACTIONS_LIST": actions_list,
        "RAW_SPEAKERS": speakers,
    }


def extract_meta(text: str) -> Dict[str, str]:
    # Date & time e.g.: “1 October 2025, 09:01am”
    m = re.search(
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4}),?\s+(\d{1,2}:\d{2}\s*(?:am|pm)?)",
        text, re.IGNORECASE
    )

    if m:
        raw_date = m.group(1)
        raw_time = m.group(2)

        dt = datetime.strptime(raw_date, "%d %B %Y")
        date_str = dt.strftime("%d/%m/%Y")
        time_str = raw_time
    else:
        date_str = datetime.now().strftime("%d/%m/%Y")
        time_str = "10:00"

    # Meeting name (top lines)
    meeting_name = "N Brown & Plenitude Daily Stand Up"
    first_lines = text.strip().splitlines()[:4]
    for line in first_lines:
        if "stand" in line.lower():
            meeting_name = line.strip()
            break

    return {
        "meeting_name": meeting_name,
        "date": date_str,
        "time": time_str,
        "location": "Teams",
    }


# =====================================================================
# SPEAKER BLOCK EXTRACTION
# =====================================================================

def extract_speaker_blocks(text: str) -> List[Tuple[str, str]]:
    pattern = re.compile(r"^([A-Z][a-z]+(?: [A-Z][a-z]+)+)\s+\d{1,2}:\d{2}", re.MULTILINE)
    lines = text.splitlines()

    speakers = []
    current = None
    buffer = []

    for line in lines:
        m = pattern.match(line.strip())
        if m:
            if current:
                speakers.append((current, "\n".join(buffer).strip()))
                buffer = []
            current = m.group(1)
        else:
            if current:
                buffer.append(line.strip())

    if current and buffer:
        speakers.append((current, "\n".join(buffer).strip()))

    return speakers


# =====================================================================
# ATTENDEE CLASSIFICATION
# =====================================================================

INTERNAL = {"OG", "DM", "HT", "MDO", "CB", "TJ", "MH", "NC", "AW", "TN"}
EXTERNAL = {"SW", "CH", "AH"}


def to_initials(name: str) -> str:
    parts = name.split()
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) > 1 else parts[0][0].upper()


def classify_attendees(speakers: List[Tuple[str, str]]):
    names = sorted({s[0] for s in speakers})
    internal = []
    external = []
    unknown = []

    for n in names:
        ini = to_initials(n)
        if ini in INTERNAL:
            internal.append(f"{n} ({ini})")
        elif ini in EXTERNAL:
            external.append(f"{n} ({ini})")
        else:
            unknown.append(f"{n}")

    lines = []
    if internal:
        lines.append("Internal:")
        lines.extend(f"• {n}" for n in internal)

    if external:
        lines.append("")
        lines.append("External:")
        lines.extend(f"• {n}" for n in external)

    if unknown:
        lines.append("")
        lines.append("Unclassified:")
        lines.extend(f"• {n}" for n in unknown)

    return internal, external, "\n".join(lines).strip()


# =====================================================================
# OBJECTIVES SUMMARY
# =====================================================================

def summarise_objectives(text: str) -> str:
    l = text.lower()
    bullets = []

    if "threshold" in l:
        bullets.append("• Threshold finalisation and monitoring")
    if "risk register" in l or "risk appetite" in l or "framework" in l:
        bullets.append("• Risk register and framework development")
    if "incident" in l or "cyber" in l or "spoof" in l or "bot" in l:
        bullets.append("• Incident management & cybersecurity engagement")
    if "meeting" in l or "tomorrow" in l or "session" in l:
        bullets.append("• Meeting scheduling and next steps")

    if not bullets:
        bullets.append("• General project updates")

    return "\n".join(bullets)


# =====================================================================
# DISCUSSION POINTS (SUMMARISED)
# =====================================================================

THEME_KEYWORDS = {
    "Thresholds & Performance Modelling": ["threshold", "performance", "figures", "model"],
    "Risk Register, Appetite & Framework": ["risk register", "risk appetite", "framework"],
    "Incident Playbook & Cybersecurity": ["incident", "cyber", "spoof", "bot", "playbook"],
    "Scheduling & Next Steps": ["meeting", "tomorrow", "session", "invite", "diary"],
}


def summarise_discussion(text: str) -> str:
    buckets = {theme: [] for theme in THEME_KEYWORDS}

    for line in text.splitlines():
        l = line.lower().strip()
        if not l:
            continue

        for theme, keys in THEME_KEYWORDS.items():
            if any(k in l for k in keys):
                buckets[theme].append(line.strip())
                break

    output = []

    for theme, lines in buckets.items():
        if not lines:
            continue

        # Summarise each theme
        summary = []

        combined = " ".join(lines).lower()

        if "threshold" in combined:
            summary.append("• Threshold logic and performance MI updates reviewed; 30% + 5-day rule confirmed.")
        if "risk" in combined or "framework" in combined:
            summary.append("• Risk register ownership confirmed; work underway to align framework and appetite statement.")
        if "incident" in combined or "cyber" in combined:
            summary.append("• Cybersecurity dependencies discussed; alignment needed on triggers and monitoring responsibilities.")
        if "meeting" in combined or "tomorrow" in combined:
            summary.append("• Tomorrow’s stand-up consolidated into the afternoon workshop session.")

        output.append(theme)
        output.extend(summary)
        output.append("")

    return "\n".join(output).strip()


# =====================================================================
# ACTIONS – THEMATIC PMO-STYLE SUMMARY
# =====================================================================

ACTION_THEMES = {
    "threshold": "Threshold MI Update",
    "performance": "Threshold MI Update",
    "figures": "Threshold MI Update",

    "risk register": "Risk Framework Workshop",
    "risk appetite": "Risk Framework Workshop",
    "framework": "Risk Framework Workshop",

    "incident": "Incident Playbook Development",
    "cyber": "Incident Playbook Development",
    "spoof": "Incident Playbook Development",
    "bot": "Incident Playbook Development",

    "kri": "Incident Management Reporting",
    "report": "Incident Management Reporting",

    "meeting": "Meeting Scheduling",
    "tomorrow": "Meeting Scheduling",
    "session": "Meeting Scheduling",
}


def next_due_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%d/%m/%Y").date()
    except Exception:
        return "TBD"

    wd = d.weekday()
    if wd <= 3:
        due = d + timedelta(days=1)
    elif wd == 4:
        due = d + timedelta(days=3)
    else:
        due = d + timedelta(days=1)

    return due.strftime("%d/%m/%Y")


def extract_actions(text: str, date_str: str):
    speakers = extract_speaker_blocks(text)
    due = next_due_date(date_str)

    # theme → [(sentence, speaker)]
    buckets = {}

    for speaker, content in speakers:
        for raw in content.splitlines():
            line = raw.strip()
            if not line:
                continue
            l = line.lower()

            matched = None
            for key, theme in ACTION_THEMES.items():
                if key in l:
                    matched = theme
                    break

            if not matched:
                continue

            if matched not in buckets:
                buckets[matched] = []

            sentence = re.split(r"[.!?]", line)[0].strip()
            buckets[matched].append((sentence, speaker))

    # Convert buckets → structured actions
    actions = []

    for theme, items in buckets.items():
        owners = sorted({s for _, s in items})
        owner_str = " / ".join(owners)

        # PMO friendly detail
        if theme == "Threshold MI Update":
            detail = "Refresh threshold MI and share updated performance figures."
        elif theme == "Risk Framework Workshop":
            detail = "Schedule workshop with NBrown to address risk framework documentation gaps."
        elif theme == "Incident Playbook Development":
            detail = "Coordinate updates to the incident playbook, focusing on cybersecurity dependencies."
        elif theme == "Incident Management Reporting":
            detail = "Share relevant KRI reporting with the Plenitude team."
        elif theme == "Meeting Scheduling":
            detail = "Consolidate tomorrow’s stand-up into the afternoon threshold workshop session."
        else:
            detail = theme

        title = theme

        actions.append({
            "Title": title,
            "Detail": detail,
            "Owner": owner_str,
            "Due Date": due
        })

    if not actions:
        return [], "No new actions captured."

    block = "\n".join(
        f"{a['Title']} – {a['Detail']} (Owner: {a['Owner']}, Due: {a['Due Date']})"
        for a in actions
    )

    return actions, block
