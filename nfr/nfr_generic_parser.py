"""
Generic NFR Parser
Used when a client does not have a bespoke parser module.
"""

def parse_transcript_to_nfr(text, overrides, profile):
    """
    Generic parser that returns EXACTLY the fields required by:
      - your DOCX template
      - your docx_utils.create_nfr_docx()
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    objectives = []
    discussion = []
    actions = []

    for line in lines:
        low = line.lower()
        if "action" in low:
            actions.append(line)
        elif "objective" in low:
            objectives.append(line)
        else:
            discussion.append(line)

    # --------------------------
    # Attendees (generic)
    # --------------------------
    attendees_internal = []
    attendees_external = []

    # If attendees come in overrides (future support)
    if "ATTENDEES_INTERNAL" in overrides:
        attendees_internal = overrides["ATTENDEES_INTERNAL"]
    if "ATTENDEES_EXTERNAL" in overrides:
        attendees_external = overrides["ATTENDEES_EXTERNAL"]

    # --------------------------
    # Actions for table format
    # --------------------------
    # Convert raw action lines into the expected object format
    actions_list = []
    for a in actions:
        actions_list.append({
            "Title": a,
            "Detail": "",
            "Owner": "",
            "Due Date": ""
        })

    return {
        # ====== MEETING DETAILS ======
        "MEETING_NAME": overrides.get("MEETING_NAME"),
        "DATE": overrides.get("DATE"),
        "LOCATION": overrides.get("LOCATION"),
        "TIME": overrides.get("TIME"),

        # ====== SIMPLE TEXT FIELDS ======
        "OBJECTIVES": "\n".join(objectives) if objectives else "",
        "KEY_DISCUSSION_POINTS": "\n".join(discussion) if discussion else "",

        # ====== ATTENDEE TABLE ======
        "ATTENDEES_INTERNAL": attendees_internal,
        "ATTENDEES_EXTERNAL": attendees_external,

        # ====== ACTION TABLE ======
        "ACTIONS_LIST": actions_list

    }


