"""Open-source license classification (spec §12).

Maps a license identifier to a category and a flag. It never declares a project
"legally safe": permissive licenses are "ok", copyleft and proprietary licenses
are flagged for review (they carry obligations), and anything it can't recognise —
including a missing license — is "unknown" and must be reviewed, not assumed fine.
"""
from __future__ import annotations

PERMISSIVE = "permissive"
WEAK_COPYLEFT = "weak_copyleft"
STRONG_COPYLEFT = "strong_copyleft"
PROPRIETARY = "proprietary"
UNKNOWN = "unknown"

# Flags: ok (no special obligation), review (obligations to check), unknown.
_CATEGORY_FLAG = {
    PERMISSIVE: "ok",
    WEAK_COPYLEFT: "review",
    STRONG_COPYLEFT: "review",
    PROPRIETARY: "review",
    UNKNOWN: "unknown",
}

# Substring markers (checked against the upper-cased license string).
_MARKERS = [
    (STRONG_COPYLEFT, ("AGPL", "GPLV3", "GPLV2", "GPL-3", "GPL-2", "GPL ")),
    (STRONG_COPYLEFT, ("GPL",)),
    (WEAK_COPYLEFT, ("LGPL", "MPL", "MOZILLA", "EPL", "ECLIPSE", "CDDL")),
    (PERMISSIVE, ("MIT", "BSD", "APACHE", "ISC", "ZLIB", "UNLICENSE", "PSF",
                  "PYTHON SOFTWARE", "0BSD", "WTFPL", "BOOST")),
    (PROPRIETARY, ("PROPRIETARY", "COMMERCIAL", "ALL RIGHTS RESERVED")),
]


def classify(license_str: str) -> dict:
    name = (license_str or "").strip()
    if not name:
        return {"category": UNKNOWN, "flag": "unknown"}
    upper = name.upper()
    # LGPL must be matched before GPL; handle weak-copyleft explicitly first.
    if "LGPL" in upper:
        return {"category": WEAK_COPYLEFT, "flag": "review"}
    for category, markers in _MARKERS:
        if any(m in upper for m in markers):
            return {"category": category, "flag": _CATEGORY_FLAG[category]}
    return {"category": UNKNOWN, "flag": "unknown"}
