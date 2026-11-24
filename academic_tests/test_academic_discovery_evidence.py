from aihawk.academic_discovery_evidence import window,signals,admission_links
from bs4 import BeautifulSoup
def test_exact_window():
 r=window("The next application period is from 7 to 28 January 2027.")
 assert r["opening_date"]=="2027-01-07" and r["deadline"]=="2027-01-28"
def test_month_does_not_invent_day():
 r=window("The next application period is in January 2027.")
 assert r["application_month"]=="January 2027" and "deadline" not in r
def test_invalid_range():
 assert window("Application period from 30 to 10 January 2027")=={}
def test_english_and_fee():
 r=signals("The programme is delivered fully in English. Tuition fee €12,000 per year.")
 assert r["english_evidence"] and r["tuition_evidence"]
def test_home_edition_not_guessed():
 r=signals("TOEFL iBT 90. No Home Edition accepted.")
 assert r["requirement_evidence"]["home_edition"] and "No Home Edition accepted" in r["requirement_evidence"]["home_edition"][0]
def test_links():
 s=BeautifulSoup('<a href="https://opintopolku.fi/x">Admission criteria</a><a href="https://other.org/x">Apply online</a>',"html.parser")
 links=admission_links(s,"https://example.edu/x","example.edu")
 assert links[0]["fetch_allowed"] and not links[1]["fetch_allowed"]
