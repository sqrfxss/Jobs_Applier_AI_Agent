from aihawk.academic_policy_signals import extract_policy,review_policy
from aihawk.academic_public_render import allowed_url

def test_same_field():
 p=extract_policy("If you already hold a master's degree (or some other equivalent or higher degree) in this field, you cannot be admitted.")
 assert "same_field_masters_exclusion" in p and "Potential exclusion" in review_policy([p])[0]
def test_acres_only():
 p=extract_policy("When applying for this programme, you can prove your English skills only by participating in ACRES.")
 assert "acres_only" in p
def test_toefl_scales():
 p=extract_policy("TOEFL iBT, TOEFL iBT Home Edition, and TOEFL iBT Paper Edition. total score of 92 (if taken before 21 Jan 2026) total score of 4.5 with no section below 4 (if taken on or after 21 Jan 2026)")
 assert p["legacy_toefl_threshold"]["values"]==["92"] and p["new_toefl_threshold"]["values"]==["4.5","4"]
def test_no_positive_from_absence():
 assert not extract_policy("English required")
def test_excluded():
 assert "home_edition_excluded" in extract_policy("TOEFL iBT Home Edition is not accepted")
def test_render_allowlist():
 assert allowed_url("https://opintopolku.fi/konfo/en")
 assert not allowed_url("https://opintopolku.fi.evil.test/")
 assert not allowed_url("https://user@opintopolku.fi/")
 assert not allowed_url("http://opintopolku.fi/")
