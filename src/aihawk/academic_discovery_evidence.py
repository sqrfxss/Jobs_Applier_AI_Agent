"""Conservative extraction: signals are not admission or funding decisions."""

import re
from datetime import date
from urllib.parse import urljoin, urlsplit

MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
WINDOW = re.compile(
    r"(?:next application period|application period|applications? (?:are open|open)|application window)\s*(?:is|will be|runs|from|:|in|are)?\s*(?:(?:from|in)\s+)?(?:(\d{1,2})\s*(?:to|[–—-])\s*(\d{1,2})\s+("
    + MONTH
    + r")\s+(20\d{2})|("
    + MONTH
    + r")\s+(20\d{2}))",
    re.I,
)
ENGLISH = re.compile(
    r"(?:taught in English|language of instruction\s*:?\s*English|English.taught|delivered (?:fully |entirely )?in English|instruction in English)", re.I
)
TUITION = re.compile(r"tuition fees?\s*:?\s*(?:EUR\s*|€\s*)[\d,. ]+(?:\s*(?:per year|/year|first year|second year|annually))?", re.I)
PATTERNS = {
    "language_test": r"TOEFL(?:\s+iBT)?(?:\s+Home Edition)?|IELTS(?: Academic)?",
    "home_edition": r"TOEFL(?:\s+iBT)?\s+Home Edition|Home Edition",
    "legalization": r"legali[sz](?:ation|ed|e)|apostille",
    "certification": r"certified (?:copies|translations)|officially certified|country.specific requirements",
    "prerequisites": r"(?:eligible|eligibility|prerequisite|educational background|bachelor.s degree|master.s degree|required credits)",
    "funding": r"fully funded|salaried employment contract|doctoral salary|monthly salary|employment contract",
    "application_link": r"apply online|apply now|admission criteria|how to apply|application portal",
    "excluded_track": r"no intake in 20\d{2}|not offered in 20\d{2}",
}


def excerpts(text, pattern, limit=5):
    return [text[max(0, m.start() - 55) : min(len(text), m.end() + 100)].strip() for m in list(re.finditer(pattern, text, re.I))[:limit]]


def window(text):
    m = WINDOW.search(text)
    if not m:
        return {}
    if m.group(1):
        try:
            month = list(__import__("calendar").month_name).index(m.group(3).capitalize())
            a = date(int(m.group(4)), month, int(m.group(1)))
            b = date(int(m.group(4)), month, int(m.group(2)))
            if a > b:
                return {}
            return {"opening_date": a.isoformat(), "deadline": b.isoformat(), "window_evidence": m.group(0), "window_precision": "day"}
        except ValueError:
            return {}
    return {"application_month": m.group(5) + " " + m.group(6), "window_evidence": m.group(0), "window_precision": "month"}


def signals(text):
    return {
        **window(text),
        "english_evidence": bool(ENGLISH.search(text)),
        "english_excerpt": excerpts(text, ENGLISH.pattern, 2),
        "tuition_evidence": [m.group(0).strip() for m in TUITION.finditer(text)][:4],
        "requirement_evidence": {k: excerpts(text, v) for k, v in PATTERNS.items()},
    }


def admission_links(soup, base, host):
    out = []
    for a in soup.select("a[href]"):
        title = a.get_text(" ", strip=True)
        url = urljoin(base, a["href"])
        p = urlsplit(url)
        if p.scheme != "https" or p.username or p.password:
            continue
        if not re.search(PATTERNS["application_link"], title, re.I):
            continue
        h = p.hostname or ""
        # Studyinfo is the official Finnish education portal; other cross-domain links are evidence only.
        allowed = h == host or h.endswith("." + host) or h == "opintopolku.fi" or h == "studyinfo.fi"
        if url not in [x["url"] for x in out]:
            out.append({"title": title, "url": url, "fetch_allowed": allowed})
    return out[:10]
