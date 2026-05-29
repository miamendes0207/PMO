# modules/nfr/nfr_generator.py

import os
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Optional, Any
from dataclasses import dataclass

from modules.client_loader import (
    load_client_module,
    load_client_config,
    ClientLoaderError,
    ClientNotFoundError,
)
from modules.nfr.docx_utils import create_nfr_docx
from modules.log_utils import log_document
from modules.db import run_query

logger = logging.getLogger("nfr_engine")


# ----------------------------------------------------
# Generic Fallback Settings
# ----------------------------------------------------
GENERIC_NFR_TEMPLATE = os.getenv("NFR_GENERIC_TEMPLATE", "templates/nfr_generic.docx")
GENERIC_NFR_PARSER = "modules.nfr.nfr_generic_parser"
GENERIC_DOCUMENT_PREFIX = os.getenv("NFR_DOCUMENT_PREFIX", "")


# ----------------------------------------------------
# Exceptions
# ----------------------------------------------------
class NFRGenerationError(Exception):
    """Base exception for NFR generation errors."""
    pass


class ParserError(NFRGenerationError):
    """Raised when parsing fails."""
    pass


class TemplateError(NFRGenerationError):
    """Raised when template is missing or invalid."""
    pass


class ValidationError(NFRGenerationError):
    """Raised when structured data validation fails."""
    pass


# ----------------------------------------------------
# Data Classes
# ----------------------------------------------------
@dataclass
class NFRGenerationResult:
    """Result of NFR generation."""
    doc_path: str
    structured_data: Dict[str, Any]
    filename: str
    client_name: str
    timestamp: str


# ----------------------------------------------------
# Helper — Sanitise client name (fallback only)
# ----------------------------------------------------
def sanitize_client_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", (name or "")).strip("_")
    return safe or "Client"


# ----------------------------------------------------
# Validation Functions
# ----------------------------------------------------
def validate_profile(profile: Dict, client_name: str) -> None:
    required_fields = ["document_prefix", "templates", "parsers"]
    missing = [f for f in required_fields if f not in profile]

    if missing:
        raise ValidationError(
            f"Client '{client_name}' profile missing required fields: {missing}"
        )

    if "nfr" not in profile.get("parsers", {}):
        raise ValidationError(
            f"Client '{client_name}' has no NFR parser defined in profile['parsers']"
        )

    if "nfr_template" not in profile.get("templates", {}):
        raise ValidationError(
            f"Client '{client_name}' has no NFR template defined in profile['templates']"
        )


def validate_template_path(template_path: str, client_name: str) -> None:
    if not template_path:
        raise TemplateError(f"Template path is empty for client '{client_name}'")

    template_file = Path(template_path)

    if not template_file.exists():
        raise TemplateError(
            f"Template not found: {template_path}\n"
            f"Expected file at: {template_file.absolute()}"
        )

    if not template_file.is_file():
        raise TemplateError(f"Template path is not a file: {template_path}")


def validate_structured_data(structured: Dict, client_name: str) -> None:
    if not isinstance(structured, dict):
        raise ValidationError(
            f"Parser returned invalid type: {type(structured)}. Expected dict."
        )

    if not structured:
        raise ValidationError(
            f"Parser returned empty data for client '{client_name}'"
        )


# ----------------------------------------------------
# Core Functions
# ----------------------------------------------------
def load_nfr_parser(client_code: str, parser_name: str):
    """
    Load the NFR parser module for a given client code.
    parser_name can be:
      - per-client parser from profile["parsers"]["nfr"]
      - or the generic fallback parser (GENERIC_NFR_PARSER)
    """
    try:
        parser = load_client_module(client_code, parser_name)
        logger.info(
            "Loaded NFR parser '%s' for client '%s' via client folder.",
            parser_name,
            client_code,
        )
    except ClientLoaderError:
        try:
            import importlib

            parser = importlib.import_module(parser_name)
            logger.info(
                "Loaded NFR parser '%s' as global module for client '%s'.",
                parser_name,
                client_code,
            )
        except Exception as e:
            raise ParserError(
                f"Failed to load NFR parser '{parser_name}' for client '{client_code}': {e}"
            ) from e

    if not hasattr(parser, "parse_transcript_to_nfr"):
        raise ParserError(
            f"Parser '{parser_name}' must define "
            f"parse_transcript_to_nfr(text, overrides, profile)"
        )

    return parser


def parse_transcript(parser, transcript_text: str, overrides: Optional[Dict],
                     profile: Dict, client_name: str) -> Dict:
    if not transcript_text or not transcript_text.strip():
        raise ParserError("Transcript text is empty")

    try:
        structured = parser.parse_transcript_to_nfr(
            transcript_text, overrides, profile
        )
    except Exception as e:
        raise ParserError(
            f"Parser failed for client '{client_name}': {e}"
        ) from e

    validate_structured_data(structured, client_name)
    return structured


def create_output_path(profile: Dict, client_code: str) -> Tuple[str, str, str]:
    """
    Create an NFR output path under:
        clients/<client_code>/nfr/outputs/<prefix>NFR_<timestamp>.docx
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    document_prefix = profile.get("document_prefix") or GENERIC_DOCUMENT_PREFIX
    filename = f"{document_prefix}NFR_{timestamp}.docx"

    output_dir = Path("clients") / client_code / "nfr" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = str(output_dir / filename)
    return output_path, filename, timestamp


def log_generation(client_name: str, filename: str,
                   overrides: Optional[Dict],
                   success: bool = True,
                   error: Optional[str] = None):
    generated_by = "System"
    if overrides:
        # support both legacy "Generated By" and newer "GENERATED_BY"
        generated_by = overrides.get("Generated By") or overrides.get("GENERATED_BY") or generated_by

    try:
        if success:
            log_document(
                client_name=client_name,
                doc_type="NFR",
                file_name=filename,
                generated_by=generated_by,
                source="Teams Transcript",
            )
        else:
            log_document(
                client_name=client_name,
                doc_type="NFR",
                file_name=filename,
                generated_by=generated_by,
                source="Teams Transcript",
                status="FAILED",
                error_message=error,
            )
    except Exception as e:
        logger.warning("Failed to log document generation: %s", e)


def _split_profile_for_nfr(raw_profile: Dict, client_code: str) -> Dict:
    """
    Ensure we have a usable NFR profile.

    Cases:
      1) Full per-client profile (document_prefix/templates/parsers) → use + validate.
      2) DB-style config (nfr_config/settings only) → fallback to generic.
    """
    has_nfr_keys = all(
        key in raw_profile for key in ("document_prefix", "templates", "parsers")
    )

    if has_nfr_keys:
        validate_profile(raw_profile, client_code)
        logger.info("Using bespoke NFR profile for client '%s'.", client_code)
        return raw_profile

    logger.warning(
        "Client '%s' has no bespoke NFR profile keys; using generic NFR settings.",
        client_code,
    )

    return {
        "_base_profile": raw_profile,
        "document_prefix": raw_profile.get("document_prefix", GENERIC_DOCUMENT_PREFIX),
        "templates": {
            "nfr_template": raw_profile.get("templates", {}).get("nfr_template", GENERIC_NFR_TEMPLATE)
            if isinstance(raw_profile.get("templates"), dict)
            else GENERIC_NFR_TEMPLATE
        },
        "parsers": {
            "nfr": raw_profile.get("parsers", {}).get("nfr", GENERIC_NFR_PARSER)
            if isinstance(raw_profile.get("parsers"), dict)
            else GENERIC_NFR_PARSER
        },
    }


# ----------------------------------------------------
# Main Generation Functions
# ----------------------------------------------------
def generate_nfr(
    client_code: str,
    transcript_text: str,
    overrides: Optional[Dict] = None,
) -> NFRGenerationResult:
    """
    Low-level NFR generator.

    - Loads profile + parser + template
    - Parses transcript using client parser
    - Renders DOCX using create_nfr_docx(...)
    """
    filename = None

    client_code = (client_code or "").strip()
    if not client_code:
        raise ValidationError("Client code is required for NFR generation.")

    try:
        # 1) Load raw profile
        raw_profile = load_client_config(client_code)

        # 2) Normalise into NFR profile
        profile = _split_profile_for_nfr(raw_profile, client_code)

        # 3) Load parser
        parser_name = profile["parsers"]["nfr"]
        parser = load_nfr_parser(client_code, parser_name)

        # 4) Validate template
        template_path = profile["templates"]["nfr_template"]
        validate_template_path(template_path, client_code)

        # 5) Parse transcript -> structured
        structured = parse_transcript(
            parser, transcript_text, overrides, profile, client_code
        )

        # 6) Create output path
        output_path, filename, timestamp = create_output_path(profile, client_code)

        # 7) Create docx (PASS OVERRIDES so placeholders are replaced)
        try:
            doc_path = create_nfr_docx(
                structured=structured,
                template_path=template_path,
                output_path=output_path,
                overrides=overrides or {},
            )
        except Exception as e:
            raise NFRGenerationError(f"Failed to create DOCX document: {e}") from e

        if not Path(doc_path).exists():
            raise NFRGenerationError(f"Document not created at expected path: {doc_path}")

        # 8) Log + return
        log_generation(client_code, filename, overrides, success=True)

        return NFRGenerationResult(
            doc_path=doc_path,
            structured_data=structured,
            filename=filename,
            client_name=client_code,
            timestamp=timestamp,
        )

    except Exception as e:
        if filename:
            log_generation(client_code, filename, overrides, success=False, error=str(e))
        logger.exception("NFR generation failed for client '%s': %s", client_code, e)
        raise


def generate_nfr_from_structured(
    client_code: str,
    structured: Dict[str, Any],
    overrides: Optional[Dict] = None,
) -> NFRGenerationResult:
    """
    Structured-first NFR generator.

    - Skips parsing entirely
    - Renders DOCX directly from already structured JSON (e.g. OpenAI agent output)
    """
    filename = None

    client_code = (client_code or "").strip()
    if not client_code:
        raise ValidationError("Client code is required for NFR generation.")

    if not isinstance(structured, dict) or not structured:
        raise ValidationError("Structured NFR data must be a non-empty dict.")

    try:
        # 1) Load raw profile
        raw_profile = load_client_config(client_code)

        # 2) Normalise into NFR profile
        profile = _split_profile_for_nfr(raw_profile, client_code)

        # 3) Validate template
        template_path = profile["templates"]["nfr_template"]
        validate_template_path(template_path, client_code)

        # 4) Create output path
        output_path, filename, timestamp = create_output_path(profile, client_code)

        # 5) Create docx directly from structured JSON (PASS OVERRIDES)
        try:
            doc_path = create_nfr_docx(
                structured=structured,
                template_path=template_path,
                output_path=output_path,
                overrides=overrides or {},
            )
        except Exception as e:
            raise NFRGenerationError(f"Failed to create DOCX document: {e}") from e

        if not Path(doc_path).exists():
            raise NFRGenerationError(f"Document not created at expected path: {doc_path}")

        # 6) Log + return
        log_generation(client_code, filename, overrides, success=True)

        return NFRGenerationResult(
            doc_path=doc_path,
            structured_data=structured,
            filename=filename,
            client_name=client_code,
            timestamp=timestamp,
        )

    except Exception as e:
        if filename:
            log_generation(client_code, filename, overrides, success=False, error=str(e))
        logger.exception("Structured NFR generation failed for client '%s': %s", client_code, e)
        raise


# ----------------------------------------------------
# Convenience Wrappers
# ----------------------------------------------------
def normalize_name(x: str) -> str:
    """Lowercase, remove spaces/dashes/underscores for fuzzy matching."""
    return "".join(c for c in (x or "").lower() if c.isalnum())


def resolve_client_code(input_name: str) -> str:
    """
    Accepts:
      - client_code (demo_client)
      - client_name (Demo Client)
      - project_name (Phase 1 - Rule Transformation)

    Returns:
      - canonical client_code from client_scaffold
    """
    norm_input = normalize_name(input_name or "")

    rows = run_query("""
        SELECT client_code, client_name
        FROM client_scaffold
        WHERE status = 'approved'
    """)

    if rows is None or rows.empty:
        raise ClientNotFoundError("No approved clients available in database.")

    # Direct client_code match
    for _, row in rows.iterrows():
        code = (row.get("client_code") or "").strip()
        if code.lower() == (input_name or "").lower():
            return code

    # Exact client_name match
    for _, row in rows.iterrows():
        name = (row.get("client_name") or "").strip()
        if name.lower() == (input_name or "").lower():
            return row["client_code"]

    # Fuzzy client_name match
    for _, row in rows.iterrows():
        name = (row.get("client_name") or "").strip()
        if normalize_name(name) == norm_input:
            return row["client_code"]

    # PROJECT NAME → client_code (keep your existing join logic)
    project_rows = run_query("""
        SELECT 
            p.project_name,
            cs.client_code,
            cs.client_name
        FROM projects p
        JOIN clients c 
              ON p.client_id = c.client_id
        JOIN client_scaffold cs 
              ON cs.client_name = c.client_name
        WHERE cs.status = 'approved'
    """)

    if project_rows is not None and not project_rows.empty:
        # Exact project_name match
        for _, row in project_rows.iterrows():
            pname = (row.get("project_name") or "").strip()
            if pname.lower() == (input_name or "").lower():
                return row["client_code"]

        # Fuzzy project_name match
        for _, row in project_rows.iterrows():
            pname = (row.get("project_name") or "").strip()
            if normalize_name(pname) == norm_input:
                return row["client_code"]

    raise ClientNotFoundError(
        f"Client '{input_name}' could not be resolved to a valid client_code."
    )


def generate_nfr_safe(
    input_identifier: str,
    text_or_structured,
    overrides: Optional[Dict] = None,
):
    """
    Wrapper used by Streamlit:
    - resolves client_code from input_identifier
    - supports either raw transcript text OR already-structured dict
    - returns (result, error)
    """
    try:
        client_code = resolve_client_code(input_identifier)

        if isinstance(text_or_structured, dict):
            result = generate_nfr_from_structured(
                client_code=client_code,
                structured=text_or_structured,
                overrides=overrides or {},
            )
        else:
            result = generate_nfr(
                client_code=client_code,
                transcript_text=str(text_or_structured or ""),
                overrides=overrides or {},
            )

        return result, None

    except Exception as e:
        return None, str(e)


def batch_generate_nfr(
    client_name: str,
    transcripts: Dict[str, str],
    overrides: Optional[Dict] = None,
):
    results = {}
    for identifier, transcript_text in transcripts.items():
        result, error = generate_nfr_safe(client_name, transcript_text, overrides)
        results[identifier] = (result, error)
    return results
