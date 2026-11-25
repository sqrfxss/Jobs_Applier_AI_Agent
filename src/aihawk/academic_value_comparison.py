"""Conservative matching of existing portal values without overwriting them.

Only address *lines*, not names, test scores, identifiers, dates or email,
may tolerate case and punctuation formatting changes. Word/digit tokens
must remain identical and in the same order.
"""

from __future__ import annotations

import re
import unicodedata

_ADDRESS_LINE = re.compile(r"^#IPR_[HC]AD[1-4]$")


def formatting_equivalent(selector: str, expected: str, stored: str) -> bool:
    """Return True only for verified presentation differences in address lines."""
    if not (isinstance(selector, str) and _ADDRESS_LINE.fullmatch(selector)):
        return False
    if not (isinstance(expected, str) and isinstance(stored, str)):
        return False
    if not expected.strip() or not stored.strip():
        return False

    def tokens(value: str) -> tuple[str, ...]:
        value = unicodedata.normalize("NFKC", value).casefold()
        # Maintain token boundaries and all letters/digits. A changed house
        # number or word cannot become an accepted "formatting" difference.
        return tuple(re.findall(r"[^\W_]+", value, re.UNICODE))

    lhs, rhs = tokens(expected), tokens(stored)
    return bool(lhs) and lhs == rhs
