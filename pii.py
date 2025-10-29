
# pii.py – simple regex PII (PoC). For production, use Microsoft Purview / DLP.
import re

PII_PATTERNS = {
    "Email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "Korean SSN-like": r"\b\d{6}-\d{7}\b",
    "Card Number-like": r"\b(?:\d[ -]*?){13,16}\b",
    "API Key-like": r"\b[A-Za-z0-9_\-]{24,}\b",
}

def scan_pii(text: str):
    out = {}
    for name, pat in PII_PATTERNS.items():
        hits = re.findall(pat, text)
        if hits:
            out[name] = list(set(hits))[:20]
    return out
