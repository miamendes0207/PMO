# modules/nfr_engine.py
from typing import List, Tuple, Dict, Any
import re

def extract_attendees(transcript: str) -> List[str]:
    """
    Extract attendee candidates from transcript/notes.
    Keep it simple: return a flat list of raw strings.
    """
    t = transcript or ""
    out: List[str] = []

    # attendee blocks: "Attendees: A, B, C"
    for m in re.finditer(r"(?im)^\s*(attendees|participants|present|in attendance)\s*[:\-]\s*(.+)$", t):
        chunk = m.group(2)
        for part in re.split(r"[;,]|(?:\s{2,})|\n", chunk):
            p = re.sub(r"\s+", " ", (part or "").strip())
            if p and p.lower() not in {"all", "tbc", "n/a"}:
                out.append(p)

    # speaker labels: "Mia:" / "OG:"
    for m in re.finditer(r"(?m)^\s*([A-Za-z][A-Za-z .'-]{0,40}?)\s*:\s+", t):
        label = re.sub(r"\s+", " ", m.group(1).strip())
        if label and label.lower() not in {"meeting", "notes", "actions", "agenda"}:
            out.append(label)

    # emails
    for m in re.finditer(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", t):
        out.append(m.group(0).lower())

    # dedupe, preserve order
    seen = set()
    deduped = []
    for x in out:
        k = x.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        deduped.append(x.strip())

    return deduped


def split_attendees(
    attendees: List[str],
    *,
    client_config: Dict[str, Any],
    flags: List[str] | None = None,
) -> Tuple[List[str], List[str]]:
    """
    Split attendees into internal/external using the SAME logic as T1/T2.
    If initials are ambiguous (e.g., internal AH and external AH), we flag and
    route to unknown_participant_bucket.
    """
    # If you already implemented the duplicate-initials directory approach in T1/T2,
    # ideally import and reuse it here to avoid drift.
    # For now, do a minimal domain-based split + optional participant_directory.
    internal_domains = client_config.get("internal_domains") or ["plenitudeconsulting.com"]
    if not isinstance(internal_domains, list):
        internal_domains = ["plenitudeconsulting.com"]

    unknown_bucket = str(client_config.get("unknown_participant_bucket", "internal")).strip().lower()
    if unknown_bucket not in {"internal", "external"}:
        unknown_bucket = "internal"

    # optional directory (simple form)
    # recommended: client_config["participant_directory"]["people"] = [{name, initials, type, email}]
    directory = (client_config.get("participant_directory") or {})
    people = directory.get("people") if isinstance(directory, dict) else None
    by_email = {}
    by_name = {}
    by_initials = {}
    if isinstance(people, list):
        for p in people:
            if not isinstance(p, dict):
                continue
            email = str(p.get("email", "")).strip().lower()
            name = str(p.get("name", "")).strip().lower()
            ini = str(p.get("initials", "")).strip().upper()
            if email:
                by_email[email] = p
            if name:
                by_name[name] = p
            if ini:
                by_initials.setdefault(ini, []).append(p)

    def format_attendee(name: str, ini: str) -> str:
        name = re.sub(r"\s+", " ", (name or "").strip()) or "Unknown"
        ini = re.sub(r"\s+", " ", (ini or "").strip()).upper() or "TBC"
        return f"{name} - ({ini})"

    def initials_from_raw(s: str) -> str:
        compact = re.sub(r"[^A-Za-z]", "", s or "")
        if re.fullmatch(r"[A-Za-z]{2,4}", compact):
            return compact.upper()
        parts = [p for p in re.split(r"\s+", (s or "").strip()) if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        if len(parts) == 1:
            return parts[0][:2].upper()
        return "TBC"

    internal_out: List[str] = []
    external_out: List[str] = []

    for raw in attendees or []:
        r = (raw or "").strip()
        if not r:
            continue

        # email-driven
        if "@" in r:
            email = r.lower()
            if email in by_email:
                p = by_email[email]
                bucket = "external" if str(p.get("type", "")).lower() == "external" else "internal"
                ini = str(p.get("initials", "")).strip().upper() or initials_from_raw(p.get("name", "") or email)
                name = p.get("name") or email
                item = format_attendee(name, ini)
                (external_out if bucket == "external" else internal_out).append(item)
                continue

            domain = email.split("@")[-1]
            bucket = "internal" if any(domain.endswith(d.lower()) for d in internal_domains) else "external"
            item = format_attendee(email, initials_from_raw(email.split("@")[0]))
            (external_out if bucket == "external" else internal_out).append(item)
            continue

        # "Full Name - (XX)"
        m = re.match(r"^(.*?)\s*-\s*\(([^)]+)\)\s*$", r)
        if m:
            name = m.group(1).strip()
            ini = initials_from_raw(m.group(2))
        else:
            name = r
            ini = initials_from_raw(r)

        # directory by full name
        p = by_name.get(name.lower())
        if p:
            bucket = "external" if str(p.get("type", "")).lower() == "external" else "internal"
            ini = str(p.get("initials", "")).strip().upper() or ini
            item = format_attendee(p.get("name") or name, ini)
            (external_out if bucket == "external" else internal_out).append(item)
            continue

        # directory by initials (ambiguous-safe)
        candidates = by_initials.get(ini, [])
        if len(candidates) == 1:
            p = candidates[0]
            bucket = "external" if str(p.get("type", "")).lower() == "external" else "internal"
            item = format_attendee(p.get("name") or name, ini)
            (external_out if bucket == "external" else internal_out).append(item)
            continue
        if len(candidates) > 1:
            if flags is not None:
                flags.append(f"NFR Engine: Ambiguous initials '{ini}' for attendee '{name}'. Using unknown bucket '{unknown_bucket}'.")
            item = format_attendee(name, ini)
            (external_out if unknown_bucket == "external" else internal_out).append(item)
            continue

        # fallback unknown
        item = format_attendee(name, ini)
        (external_out if unknown_bucket == "external" else internal_out).append(item)

    # dedupe preserve order
    def dedupe(lst: List[str]) -> List[str]:
        seen = set()
        out = []
        for x in lst:
            k = x.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(x)
        return out

    return dedupe(internal_out), dedupe(external_out)


def process_transcript(transcript: str, *, client_config: Dict[str, Any] | None = None) -> dict:
    """
    Shared extraction engine used by BOTH daily and weekly NFRs.
    Takes raw transcript → returns structured sections.
    """
    client_config = client_config or {}
    flags: List[str] = []

    all_attendees = extract_attendees(transcript)
    attendees_internal, attendees_external = split_attendees(all_attendees, client_config=client_config, flags=flags)

    data = {
        "objectives": extract_objectives(transcript),
        "discussion_sections": extract_sections(transcript),
        "attendees_internal": attendees_internal,
        "attendees_external": attendees_external,
        "actions": extract_actions(transcript),
        "issues": extract_issues(transcript),
        "risks": extract_risks(transcript),
        "raw_transcript": transcript,
        "flags": flags,  # optional but very useful
    }

    return data

