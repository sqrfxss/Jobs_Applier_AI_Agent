from aihawk.academic_field_mapper import build_plan


def control(label, kind="text", **kw):
    return dict(label_untrusted=label, selector_candidate="#test", selector_unique=True, kind=kind, **kw)


def test_reuse_verified():
    p = build_plan({"controls": [control("First name")]}, {"fields": {"first_name": {"value": "Example", "verified": True}}})
    assert p["field_values"] == {"first_name": "Example"} and not p["approved_for_draft"]


def test_dropdown_exact():
    p = build_plan(
        {"controls": [control("Nationality", "select", options_untrusted=[{"label": "Iran", "value": "IR"}, {"label": "Iraq", "value": "IQ"}])]},
        {"fields": {"nationality": {"value": "Iran", "verified": True}}},
    )
    assert p["field_values"] == {"nationality": "IR"}


def test_ambiguous_option():
    p = build_plan(
        {"controls": [control("Nationality", "select", options_untrusted=[{"label": "Iran", "value": "IR"}, {"label": "Iran", "value": "2"}])]},
        {"fields": {"nationality": {"value": "Iran", "verified": True}}},
    )
    assert not p["bindings"] and p["unresolved"]


def test_no_guess():
    p = build_plan(
        {"controls": [control("First name"), control("Country"), control("Password")]}, {"fields": {"first_name": {"value": "Example", "verified": False}}}
    )
    assert not p["bindings"] and len(p["unresolved"]) == 3


def test_upload_role():
    p = build_plan(
        {"controls": [control("Master transcript", "upload")]}, {"documents": {"msc_transcript": {"verified": True, "path": "example.pdf", "sha256": "test"}}}
    )
    assert p["upload_proposals"][0]["requires_reviewed_receipt_and_endpoint"] and not p["bindings"]


def test_conflict():
    p = build_plan({"controls": [control("First name", name="last name")]}, {"fields": {"first_name": {"value": "Example", "verified": True}}})
    assert not p["bindings"]
