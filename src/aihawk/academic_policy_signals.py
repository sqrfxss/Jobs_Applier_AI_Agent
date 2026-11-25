"""Evidence signals for hard admissions constraints; no automatic equivalence."""

import re


def extract_policy(text):
    text = " ".join(text.split())
    rules = {
        "same_field_masters_exclusion": r"If you already hold a master.s degree.{0,130}in this field, you cannot be admitted",
        "acres_only": r"(?:can prove your English skills only by participating in ACRES|only by participating in ACRES)",
        "acres_not_accepted": r"ACRES does not serve as proof of English skills",
        "home_edition_listed": r"TOEFL iBT, TOEFL iBT Home Edition, and TOEFL iBT Paper Edition",
        "home_edition_excluded": r"(?:TOEFL iBT )?Home Edition (?:is |are )?not accepted|(?:do not accept|does not accept) (?:TOEFL iBT )?Home Edition",
        "legacy_toefl_threshold": r"total score of (\d{2,3}) \(if taken before 21 Jan 2026\)",
        "new_toefl_threshold": r"total score of (\d(?:\.\d)?) with no section below (\d(?:\.\d)?) \(if taken on or after 21 Jan 2026\)",
        "toefl_validity": r"TOEFL results are valid for two years from the test date",
    }
    out = {}
    for key, pattern in rules.items():
        m = re.search(pattern, text, re.I)
        if m:
            out[key] = {"evidence": m.group(0), "values": list(m.groups())}
    return out


def review_policy(policies):
    keys = {k for p in policies for k in p}
    checks = []
    if "same_field_masters_exclusion" in keys:
        checks.append("Potential exclusion: prior master's in same field. Institutional determination required.")
    if "acres_only" in keys:
        checks.append("ACRES internal assessment required; TOEFL alone is insufficient.")
    if "home_edition_excluded" in keys:
        checks.append("Home Edition exclusion signal; verify scope and current intake.")
    if "home_edition_listed" in keys and "home_edition_excluded" not in keys and "acres_only" not in keys:
        checks.append("Home Edition listed; verify score scale, test date, validity and section requirements.")
    if not checks:
        checks.append("Language and degree rules need review.")
    return checks
