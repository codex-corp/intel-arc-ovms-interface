from __future__ import annotations

import re

# Unicode ranges for Arabic and RTL scripts
_ARABIC_RTL_REGEX = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")


def is_arabic_or_rtl(text: str) -> bool:
    """Returns True if the text contains Arabic or RTL characters.

    NOTE: Textual / Rich do not natively support Arabic contextual shaping
    or RTL text layout. This utility is used only for CSS class tagging
    (e.g. right-aligning user message cards).
    """
    if not text:
        return False
    return bool(_ARABIC_RTL_REGEX.search(text))
