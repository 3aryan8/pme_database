from __future__ import annotations

import re
import unicodedata


_DESIGNATION_TOKENS = {
    "ADMO",
    "BRC",
    "DMO",
    "DRH",
    "EXAMINER",
    "IRHS",
    "MEDICAL",
    "RAILWAY",
    "SR",
    "SR.",
    "UROLOGIST",
}


def normalize_doctor_name(raw_name: str | None) -> str:
    """Normalize the doctor name while keeping the designation separate."""
    if raw_name is None:
        return ""

    text = unicodedata.normalize("NFKC", str(raw_name)).strip()
    if not text:
        return ""

    text = text.replace("\u200c", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    text = text.replace("DR", "DR.") if text.upper().startswith("DR ") else text
    text = re.sub(r"(?i)^\s*doctor\s*", "DR. ", text)
    text = re.sub(r"(?i)^\s*dr\.\s*", "DR. ", text)
    text = re.sub(r"(?i)^\s*dr\s+", "DR. ", text)

    text = re.sub(r"(?i)\b(?:sr|admo|dmo|brc|drh|irhs|medical|examiner|railway|urologist)\b\.?", " ", text)
    text = re.sub(r"[\/|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return ""

    if text.upper().startswith("DR."):
        remainder = text[3:].strip()
        if remainder:
            return "DR. " + re.sub(r"\s+", " ", remainder).upper()
        return "DR."

    return re.sub(r"\s+", " ", text).upper()


def doctor_lookup_key(raw_name: str | None) -> str:
    """Return a compact, case-insensitive key for duplicate prevention."""
    return re.sub(r"[^a-z0-9]+", "", normalize_doctor_name(raw_name).lower())
