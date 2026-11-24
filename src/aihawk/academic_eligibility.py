"""Evaluate explicit reviewed admission criteria; never infer foreign equivalence."""

from datetime import date


def result(status, reason, source=None):
    return {"status": status, "reason": reason, "source": source}


def evaluate_language(rule, certificate, *, on):
    source = rule.get("source")
    if not source or not rule.get("reviewed"):
        return result("unknown", "Official language rule not reviewed", source)
    if rule.get("not_required") is True:
        return result("verified_not_required", "Explicit exemption", source)
    if not certificate.get("verified"):
        return result("unknown", "Test evidence not verified", source)
    if rule.get("accepted_delivery_modes") is None:
        return result("unknown", "Delivery-mode rule unspecified", source)
    if certificate.get("delivery_mode") not in rule["accepted_delivery_modes"]:
        return result("ineligible" if certificate.get("delivery_mode") else "unknown", "Test delivery mode not accepted or unverified", source)
    if certificate.get("test") != rule.get("test") or certificate.get("scale") != rule.get("scale"):
        return result("unknown", "Different test or score scale; no implicit conversion", source)
    try:
        taken = date.fromisoformat(certificate["test_date"])
        months = int(rule["valid_months"])
        if months <= 0:
            raise ValueError()
        from calendar import monthrange

        y, m = divmod(taken.year * 12 + taken.month - 1 + months, 12)
        expiry = date(y, m + 1, min(taken.day, monthrange(y, m + 1)[1]))
        if on > expiry:
            return result("ineligible", "Test expired on required assessment date", source)
        if float(certificate["total"]) < float(rule["minimum_total"]):
            return result("ineligible", "Total below requirement", source)
        for name, minimum in rule.get("minimum_sections", {}).items():
            if name not in certificate.get("sections", {}):
                return result("unknown", "Section result missing", source)
            if float(certificate["sections"][name]) < float(minimum):
                return result("ineligible", "Section below requirement: " + name, source)
    except (KeyError, ValueError, TypeError, OverflowError):
        return result("unknown", "Required score or validity evidence missing", source)
    return result("verified_eligible", "Reviewed language criteria satisfied", source)


def evaluate_credits(requirements, courses):
    """Courses must be transcribed and independently reviewed, with official credit units.
    No generic conversion of local units to ECTS and no double counting.
    """
    rows = []
    used = set()
    for r in requirements:
        source = r.get("source")
        if not r.get("reviewed") or not source:
            rows.append(result("unknown", "Requirement not verified", source))
            continue
        found = [
            c
            for c in courses
            if c.get("verified") is True
            and c.get("id") not in used
            and r.get("category") in c.get("reviewed_categories", [])
            and c.get("credit_unit") == r.get("credit_unit")
        ]
        if not found:
            rows.append(result("unknown", "No reviewed course matches in required credit units", source))
            continue
        credits = sum(float(c["credits"]) for c in found)
        minimum = float(r["minimum"])
        used.update(c["id"] for c in found)
        rows.append(
            {
                **result(
                    "verified_eligible" if credits >= minimum else "unknown",
                    "Documented credit match; incomplete transcript cannot establish rejection",
                    source,
                ),
                "category": r["category"],
                "matched_credits": credits,
                "required_credits": minimum,
                "course_ids": [c["id"] for c in found],
            }
        )
    return rows


def evaluate_degree(rule, degree):
    source = rule.get("source")
    if not rule.get("reviewed") or not source or not degree.get("verified"):
        return result("unknown", "Reviewed degree evidence required", source)
    if rule.get("foreign_equivalence_individual") and not degree.get("institutional_equivalence_confirmed"):
        return result("pending_institutional_assessment", "Individual equivalence decision outstanding", source)
    if degree.get("level") not in rule.get("accepted_levels", []):
        return result("ineligible", "Degree level not accepted", source)
    if rule.get("accepted_fields") and degree.get("field") not in rule["accepted_fields"]:
        return result("unknown", "Related-field determination needed", source)
    return result("verified_eligible", "Explicit reviewed degree requirements satisfied", source)


def evaluate_credentials(rule, documents):
    source = rule.get("source")
    if not source or not rule.get("reviewed"):
        return result("unknown", "Official credential policy not reviewed", source)
    for requirement in rule.get("required_at_application", []):
        if documents.get(requirement, {}).get("verified") is not True:
            return result("missing_document", "Required at application: " + requirement, source)
    if rule.get("legalization_timing") not in ("application", "enrolment", "not_required"):
        return result("unknown", "Legalization timing not established", source)
    if rule["legalization_timing"] == "application" and documents.get("legalization", {}).get("verified") is not True:
        return result("missing_document", "Legalization required at application", source)
    return result("verified_eligible", "Reviewed application-stage credential rules satisfied", source)
