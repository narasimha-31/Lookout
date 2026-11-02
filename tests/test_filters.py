from filters import dealbreakers, html_to_text, location_ok, min_years, pay, title_ok

F = {
    "title_include": ["analyst", "data engineer", "sql"],
    "title_exclude": ["senior", "sr", "lead", "manager"],
    "dealbreakers": ["unable to sponsor", "no sponsorship", "security clearance"],
    "locations_allowed": ["United States", "USA", "US", "Texas", "TX", "CA"],
    "locations_blocked": ["Canada", "India"],
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
    assert location_ok("Austin, tx area", F) is True  # names match any case, unclear passes


def test_dealbreakers():
    assert dealbreakers("We are UNABLE TO SPONSOR visas", F) == ["unable to sponsor"]
    assert dealbreakers("Must be authorized to work in the US", F) == []
    assert dealbreakers("requires an active\nsecurity   clearance", F) == ["security clearance"]


def test_min_years():
    assert min_years("2+ years of SQL experience") == 2
    assert min_years("3+ years of experience") == 3
    assert min_years("4+ years experience required") == 4
    assert min_years("2-4 years of relevant experience") == 2
    assert min_years("Experience: 5 years preferred, 1 year required") == 1
    assert min_years("three (3) years of experience") == 3
    assert min_years("no experience needed") is None
    assert min_years("We have been in business 10 years") is None
    assert min_years("With over 30 years of experience serving customers") is None
    assert min_years("Offer includes 401(k) and 2 weeks PTO") is None


def test_pay():
    assert pay("Salary: $70,000 - $85,000 per year") == "$70,000 - $85,000"
    assert pay("Pay $25.50 to $31 hourly") == "$25.50 to $31"
    assert pay("Competitive pay") is None


def test_html_to_text():
    out = html_to_text("<p>Hi&amp;bye</p><ul><li>SQL</li><li>Python</li></ul><script>x()</script>")
    assert out == "Hi&bye\n\n- SQL\n- Python"
