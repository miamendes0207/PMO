# nbrown_attendee_resolver.py

"""
Attendee Resolver for N Brown
-----------------------------
This module identifies, resolves, and classifies attendee names found
in transcript text for the N Brown ScopeSight 1.0 NFR generator.

It performs:
1. Name extraction
2. Fuzzy matching to known attendees
3. Internal/external categorisation
"""

from difflib import SequenceMatcher
import re
from nbrown_profile import NBROWN_PROFILE


# ------------------------------------------------------------
# Utility: Fuzzy matching
# ------------------------------------------------------------

def fuzzy_match(name, known_names, threshold=0.75):
    """
    Return the best fuzzy match from known_names.
    If no match meets threshold, return None.
    """
    best_match = None
    best_score = 0

    for known in known_names:
        score = SequenceMatcher(None, name.lower(), known.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = known

    return best_match if best_score >= threshold else None


# ------------------------------------------------------------
# Extract raw name-like words from transcript
# ------------------------------------------------------------

def extract_candidate_names(text):
    """
    Attempts to extract names from transcript text.
    Handles Teams AI formats, e.g.:
    - "Orel:"
    - "Heather Thomson - "
    - "DM:"
    - "CH:"

    Returns a *set* of string candidates.
    """

    candidates = set()

    # Pattern for lines like "Name:" or "Name -"
    speaker_pattern = re.compile(r"^([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s*[:\-]", re.MULTILINE)

    for match in speaker_pattern.findall(text):
        candidates.add(match.strip())

    # Also capture single names (e.g. "Orel said...", "Chris mentioned...")
    name_pattern = re.compile(r"\b([A-Z][a-z]{2,})\b")
    short_names = name_pattern.findall(text)
    for name in short_names:
        candidates.add(name)

    return candidates


# ------------------------------------------------------------
# Resolve raw extracted names → real attendee names
# ------------------------------------------------------------

def resolve_attendees(raw_names):
    """
    Takes a list/set of raw names extracted from transcript text,
    uses fuzzy matching to resolve them to the known attendee list.
    Returns unique internal/external attendees.
    """

    internal_known = NBROWN_PROFILE["attendees_internal"]
    external_known = NBROWN_PROFILE["attendees_external"]
    all_known = internal_known + external_known

    resolved = set()

    for raw in raw_names:
        match = fuzzy_match(raw, all_known)
        if match:
            resolved.add(match)

    return resolved


# ------------------------------------------------------------
# Classify into internal / external
# ------------------------------------------------------------

def classify_attendees(resolved_names):
    """
    Splits attendees into internal and external lists.
    Returns: (internal_list, external_list)
    """

    internal_known = set(NBROWN_PROFILE["attendees_internal"])
    external_known = set(NBROWN_PROFILE["attendees_external"])

    internal = []
    external = []

    for name in resolved_names:
        if name in internal_known:
            internal.append(name)
        elif name in external_known:
            external.append(name)
        else:
            # Unknown → treat as external for safety
            external.append(name)

    return internal, external


# ------------------------------------------------------------
# Full pipeline
# ------------------------------------------------------------

def detect_attendees_from_transcript(text):
    """
    Complete attendee extraction pipeline:
    1. Extract raw candidate names
    2. Fuzzy match to known attendees
    3. Classify into internal/external
    """

    raw_names = extract_candidate_names(text)
    resolved = resolve_attendees(raw_names)
    internal, external = classify_attendees(resolved)

    return {
        "raw_candidates": list(raw_names),
        "resolved_attendees": list(resolved),
        "internal": internal,
        "external": external
    }
