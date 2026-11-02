from filters import abroad, dealbreakers, html_to_text, location_ok, years_required, pay, student_only, title_ok

F = {
    "title_include": ["analyst", "data engineer", "sql"],
    "title_exclude": ["senior", "sr", "lead", "manager"],
    "dealbreakers": ["unable to sponsor", "no sponsorship", "security clearance"],
    "locations_allowed": ["United States", "USA", "US", "Texas", "TX", "CA"],
    "locations_blocked": ["Canada", "India", "(DE)", "(CA)"],
}


def test_titles():
    assert title_ok("Data Analyst", F)
    assert title_ok("Associate Data Engineer", F)
    assert not title_ok("Senior Data Analyst", F)
    assert not title_ok("Sr. Analyst", F)
    assert not title_ok("Analyst Manager", F)
    assert not title_ok("Leadership Coordinator", F)
    assert title_ok("Supply Chain Analyst - Leadership Program", F)


def test_locations():
    assert location_ok("Houston, TX", F)
    assert location_ok("United States - TX - The Woodlands", F)
    assert location_ok("Remote - US", F)
    assert location_ok("Houston Corporate", F)
    assert location_ok("2 Locations", F)
    assert location_ok("", F)
    assert location_ok("Calgary, AB, Canada; Houston, TX, United States", F)
    assert not location_ok("Toronto, ON, Canada", F)
    assert not location_ok("Remote - India", F)
    assert not location_ok("Leduc, AB, Canada", F)
    assert not location_ok("Munich (DE)", F)
    assert not location_ok("Toronto (CA)", F)
    assert location_ok("San Diego, CA", F)
    assert not location_ok("IN-Pune", F)
    assert not location_ok("CA-Ontario-Toronto", F)
    assert not location_ok("IL-Israel-Remote", F)
    assert location_ok("US-CA-Menlo Park", F)
    assert location_ok("US-TX-Remote", F)
    assert location_ok("TX - San Angelo", F)
    assert not location_ok("Kulim, 02 (MY)", F)
    assert location_ok("Houston (US)", F)
    tn = {**F, "locations_allowed": F["locations_allowed"] + ["Tennessee", "TN"]}
    assert not location_ok("Tennessee, USA; Bengaluru, Karnataka, India; Chennai, Tamil Nadu, India", tn)
    assert location_ok("Nashville, TN; Bengaluru, Karnataka, India", tn)
    assert location_ok("Tennessee, USA", tn)
    assert location_ok("Austin, tx area", F) is True  # names match any case, unclear passes


def test_dealbreakers():
    blocked = [
        "We are UNABLE TO SPONSOR visas",
        "Candidates must be eligible to work in the United States without sponsorship.",
        "Sponsorship for this role is not being offered at this time.",
        "We cannot sponsor visas for this position.",
        "This role is ineligible for visa sponsorship.",
        "Visa sponsorship is unavailable.",
        "The company won’t sponsor work visas.",
        "Candidates must be a U.S. Citizen or Permanent Resident.",
        "This position requires US citizenship.",
        "Open to green card holders only.",
        "Must be a U.S. person as defined by ITAR.",
        "Requires an active Secret clearance.",
        "This position is open only to individuals who would not require visa support including H-1B or CPT/OPT/STEM, etc., now or in the future.",
        "We are unable to support OPT or H1B candidates for this role.",
        "Applicants requiring a work permit will not be considered.",
        "Ability to obtain a security clearance.",
    ]
    for s in blocked:
        assert dealbreakers(s, F), s
    allowed = [
        "Review organizations considered for company sponsorship or employee participation.",
        "Any sponsorship considerations are subject to company policy.",
        "We offer visa sponsorship for qualified candidates.",
        "Must be authorized to work in the US.",
        "We consider all applicants without regard to race, national origin or citizenship status.",
        "We participate in E-Verify and must confirm the identity of U.S. citizens and noncitizens.",
        "No security clearance required.",
        "Coordinate customs clearance for imports.",
        "We do not discriminate on the basis of immigration status.",
        "Visa sponsorship is available for this role.",
        "Candidates who need H-1B transfer are welcome to apply.",
        "Where roles have hard requirements (eg days in office, unable to provide visas, etc), tell us.",
    ]
    for s in allowed:
        assert dealbreakers(s, F) == [], s


def test_abroad():
    gratkorn = "Location: Gratkorn, Austria | Part-time. More information about NXP in Austria."
    assert abroad("Gratkorn", gratkorn, {**F, "locations_blocked": ["Austria"]})
    assert not abroad("Austin (Oakhill, Office)", "More information about NXP in the United States.",
                      {**F, "locations_blocked": ["Austria"]})
    assert not abroad("Houston, TX", gratkorn, {**F, "locations_blocked": ["Austria"]})
    assert not abroad("Remote", "Work from anywhere in the US. Teams in India too.", F)


def test_student_only():
    assert student_only("Internship: Software Engineer", "Ongoing studies in Computer Science.")
    assert student_only("Data Analyst Intern", "Must be currently enrolled in a degree program.")
    assert student_only("Summer Internship - Data", "Rising senior pursuing a bachelor's degree.")
    assert not student_only("Data Analyst Intern", "Bachelor's degree in a related field.")
    assert not student_only("Data Analyst", "Must be currently enrolled in a degree program.")


def test_min_years():
    assert years_required("2+ years of SQL experience") == 2
    assert years_required("3+ years of experience") == 3
    assert years_required("4+ years experience required") == 4
    assert years_required("2-4 years of relevant experience") == 2
    assert years_required("Experience: 5 years preferred, 1 year required") == 1
    assert years_required("three (3) years of experience") == 3
    assert years_required("a minimum of 5+ years of field sales experience and at least 2 years of experience selling") == 5
    assert years_required("3+ years of SQL experience, 2+ years of Python experience") == 3
    assert years_required("1-3 years of experience in analytics") == 1
    assert years_required("no experience needed") is None
    assert years_required("We have been in business 10 years") is None
    assert years_required("With over 30 years of experience serving customers") is None
    assert years_required("Offer includes 401(k) and 2 weeks PTO") is None


def test_pay():
    assert pay("Salary: $70,000 - $85,000 per year") == "$70,000 - $85,000"
    assert pay("Pay $25.50 to $31 hourly") == "$25.50 to $31"
    assert pay("Competitive pay") is None


def test_html_to_text():
    out = html_to_text("<p>Hi&amp;bye</p><ul><li>SQL</li><li>Python</li></ul><script>x()</script>")
    assert out == "Hi&bye\n\n- SQL\n- Python"
