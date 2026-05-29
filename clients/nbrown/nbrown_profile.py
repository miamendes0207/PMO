"""
N Brown Client Configuration Profile
Defines all rules, defaults, formatting, and attendee lists
required to generate NFRs for the N Brown project.
"""

CLIENT_PROFILE = {

    # ------------------------------------------------------------
    # BASIC CLIENT METADATA
    # ------------------------------------------------------------
    "client_name": "N Brown",
    "document_prefix": "NBrown_",

    "default_meeting_name": "N Brown and Plenitude Daily Stand Up",
    "default_location": "Teams",
    "default_time": "10:00",

    # ------------------------------------------------------------
    # TEMPLATE PATHS
    # Must match structure expected by nfr_generator.py
    # ------------------------------------------------------------
    "templates": {
        "nfr_template": "templates/n_brown_template.docx"
    },

    # ------------------------------------------------------------
    # PARSER MODULES
    # Must match the filename in modules/clients/nbrown/
    # ------------------------------------------------------------
    "parsers": {
        "nfr": "nfr_parser_nbrown"
    },

    # ------------------------------------------------------------
    # KNOWN ATTENDEES
    # ------------------------------------------------------------
    "attendees_internal": [
        "Tymon Jaworski",
        "Orel Garcia",
        "Dovile Morkunaite",
        "Heather Thomson",
        "Matt Hawes",
        "Nina Craig",
        "Anais Westergaard",
        "Mia De Oliveira",
        "Chris Bone",
        "Tom Nickelson",
    ],

    "attendees_external": [
        "Simon Wilson",
        "Chris Harnick",
        "Alex Humphries",
    ],

    # ------------------------------------------------------------
    # TERMINOLOGY (optional)
    # ------------------------------------------------------------
    "terminology": {},

    # ------------------------------------------------------------
    # FORMATTING RULES
    # ------------------------------------------------------------
    "formatting": {
        "title_font_size": 14,
        "heading_font_size": 12,
        "body_font_size": 11,
        "line_spacing": 1.15,
        "use_bullets": False,
        "table_style": "Table Grid",
    },

    # ------------------------------------------------------------
    # ACTION DUE DATE RULES
    # ------------------------------------------------------------
    "due_date_logic": {
        "mon_thu": 1,
        "fri": 3,
    },
}
