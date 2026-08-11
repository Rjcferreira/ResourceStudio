"""Integrity guard for the official PayPal and Discord support cards."""

from hashlib import sha256
from pathlib import Path

from app.config import WEB

_PAYPAL_MARKER = "if(!grid.querySelector('[href=\"https://www.paypal.com/paypalme/rjota\"]')"
_END_MARKER = ")},70));"
_EXPECTED_SUPPORT_SHA256 = "20372db5967b611d14650badb8a8eed7f184f4551122dd9cb25b9667f0a2e8b9"


def support_cards_valid() -> bool:
    """Return false when either official support card was removed or changed."""
    try:
        source = (WEB / "home-extra.js").read_text(encoding="utf-8")
        start = source.index(_PAYPAL_MARKER)
        end = source.index(_END_MARKER, start)
        fragment = source[start:end]
        return sha256(fragment.encode("utf-8")).hexdigest() == _EXPECTED_SUPPORT_SHA256
    except (OSError, ValueError, UnicodeError):
        return False
