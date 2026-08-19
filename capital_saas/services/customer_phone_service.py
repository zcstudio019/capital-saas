"""Customer phone identity helpers used by registration, login and backfill."""
import re


def normalize_phone(value: str | None) -> str | None:
    """Return an 11-digit mainland-mobile identity, or a conservative fallback.

    Spaces, hyphens and common country-code prefixes are not meaningful account
    identity differences. Empty values deliberately remain ``None`` rather
    than becoming an empty-string identity.
    """
    if value is None:
        return None
    digits = re.sub(r"[^0-9]", "", str(value))
    if not digits:
        return None
    if digits.startswith("0086"):
        digits = digits[4:]
    elif digits.startswith("86") and len(digits) == 13 and digits[2] == "1":
        digits = digits[2:]
    return digits
