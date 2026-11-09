from filters import (software_required, abroad, dealbreakers, html_to_text, location_ok, years_required, pay, skills_ok, student_only,
                     title_maybe, title_ok)

F = {
    "title_include": ["data", "analytics", "bi", "business intelligence", "supply chain", "gis", "risk", "trading",
                      "energy", "commodities", "settlements", "fundamentals", "planning", "demand", "procurement", "marketing", "investment", "product", "business", "operations", "audit"],
    "title_exclude": ["senior", "sr", "lead", "manager", "data center", "data entry", "helpdesk", "pqa", "scientist",
                      "cybersecurity", "benefits", "fp&a", "financial planning", "accounting", "accountant", "actuarial", "actuary"],
    "dealbreakers": ["unable to sponsor", "no sponsorship", "security clearance"],
    "locations_allowed": ["United States", "USA", "US", "Texas", "TX", "CA"],
    "locations_blocked": ["Canada", "India", "(DE)", "(CA)"],
}


def test_consultant_titles():
    assert title_ok("Data Consultant", F) and title_ok("Sr. BI Consultant", {**F, "title_exclude": []})
    assert not title_ok("Management Consultant", F) and not title_ok("IT Consultant", F)


def test_titles():
    good = ["Data Analyst", "Associate Data Engineer", "Supply Chain Analyst - Leadership Program", "Analytics Engineer",
            "Analyst, Supply Chain Planning", "Financial Data Analyst", "Finance Data Analyst II", "Business Intelligence Analyst - Marketing",
            "Data Engineer with PostgreSQL", "Procurement Planner", "Marketing Analyst", "Investment Analyst",
            "BI Developer", "Data Analytics Intern",
            "Product Associate, Data & Analytics-Payments", "Engineer, Data Platform",
            "Strategic Analytics [Multiple Positions Available]", "Buyer - Procurement Planning",
            "Clinical Data / Reporting Analyst", "Product Support Analyst",
            "Analyst, Client Audit and Performance",
            # ai engineer roles paused for now
            # "AI/ML Engineer", "AI Engineer", "Generative AI Developer",
            "Data Steward", "Data Governance Analyst", "GIS Analyst I", "GIS Data Entry Analyst", "GIS Technician",
            "Energy Trading Analyst", "Commodities Risk Analyst", "Power Settlements Analyst", "Natural Gas Fundamentals Analyst"]
    bad = ["Senior Data Analyst", "Sr. Analyst", "Analyst Manager", "Leadership Coordinator",
           "Data Center Critical Infrastructure Engineer", "Modem System Test Engineer -  6G/5G Data and Networking",
           "Administrative Support Representative/Data Entry Operator", "PQA Analyst", "Helpdesk Analyst", "Data Scientist",
           "Cybersecurity Analyst I", "Benefits Support Analyst, Missed Enrollments (US)",
           "Laboratory Informatics Master Data Assistant", "Modem Machine Learning Engineer", "Managing SAP Consultant Basis",
           "Software Engineer", "Data Center Asset Management, Commercial Associate",
           "Corp FP&A Financial Analyst II - (B2)", "Financial Planning and Analysis", "Accounting Analyst", "Financial Analyst",
           "Export & Agency Finance (EAF US) - LatAm Focus - Analyst", "FP&A Analyst", "Data Entry Clerk", "Pharmacy Technician",
           "Actuarial Associate - IR Pricing & Product Development"]
    for t in good:
        assert title_ok(t, F), t
    for t in bad:
        assert not title_ok(t, F), t


def test_unknown_analyst_titles_need_skills():
    assert title_maybe("Transcript Analyst I", F)
    assert title_maybe("Labor & Productivity Analyst", F)
    assert not title_maybe("Data Analyst", F)
    assert not title_maybe("PQA Analyst", F)
    assert not title_maybe("Software Engineer", F)
    assert skills_ok("Strong SQL and Excel skills, build dashboards")
    # excel, sap and oracle roles count, from the sysco, invesco and henry schein postings
    assert skills_ok("Advanced Excel skills required") and skills_ok("Experience with SAP and Oracle")
    assert skills_ok("Proficient in Microsoft Access") and not skills_ok("Gain access to our tools")
    # excel can't stand in for a software language
    assert software_required("Required: experience with Java or Excel.")
    assert not software_required("Required: Advanced Excel and SAP.")
    assert skills_ok("Pull reports with SQL or Python")
    assert not skills_ok("Review transcripts for accuracy and answer calls")
    assert not skills_ok("Builds par level systems. Processes supply and implant requisitions. Basic communication skills.")


def test_locations():
    assert location_ok("Houston, TX", F)
    assert location_ok("United States - TX - The Woodlands", F)
    assert location_ok("Remote - US", F)
    assert location_ok("Houston Corporate", F)
    assert location_ok("2 Locations", F)
    assert location_ok("", F)
    # a foreign place next to a us one means the role can be filled abroad
    assert not location_ok("Calgary, AB, Canada; Houston, TX, United States", F)
    assert not location_ok("Austin, TX; Bangalore, India", F)
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
    assert not location_ok("IN - Bengaluru, India", {**F, "locations_allowed": F["locations_allowed"] + ["IN"]})
    assert not location_ok("MYS - Selangor - Petaling Jaya (Ascent Paradigm)", F)
    assert location_ok("USA - Texas - Houston", F)
    # a foreign city beats a code shared by a state and a country, a plain state code still wins
    g = {**F, "locations_allowed": F["locations_allowed"] + ["IN", "OH"], "locations_blocked": F["locations_blocked"] + ["Bangalore", "Dublin"]}
    assert not location_ok("Bangalore, IN", g)
    assert location_ok("Indianapolis, IN", g)
    assert location_ok("Dublin, OH", g)
    assert not location_ok("Kulim, 02 (MY)", F)
    assert not location_ok("King Abdullah Economic City, 02", F)
    assert location_ok("Houston, TX 77056", F)
    assert location_ok("Houston (US)", F)
    assert not location_ok("Barceloneta, Puerto Rico", F)
    assert not location_ok("San Juan, PR, United States", F)
    assert not location_ok("Hagatna, Guam, USA", F)
    tn = {**F, "locations_allowed": F["locations_allowed"] + ["Tennessee", "TN"]}
    assert not location_ok("Tennessee, USA; Bengaluru, Karnataka, India; Chennai, Tamil Nadu, India", tn)
    assert not location_ok("Nashville, TN; Bengaluru, Karnataka, India", tn)
    assert location_ok("Tennessee, USA", tn)
    assert location_ok("Austin, tx area", F) is True  # names match any case, unclear passes


def test_dealbreakers():
    blocked = [
        "We are UNABLE TO SPONSOR visas",
        "U.S. work authorization sponsorship (H-1B, TN, J, etc.) is offered exclusively for Principal-level roles and above.",
        "Roles below the Principal level require candidates to possess unrestricted U.S. work authorization at the time of hire.",
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
        "If you prefer that your profile not be used in this process, you can opt out at any time.",
        "Where roles have hard requirements (eg days in office, unable to provide visas, etc), tell us.",
        "- Employer sponsored health, dental and vision plan with no monthly premium",
        "Benefits are an integral part of total rewards and First Citizens Bank is committed to meet the needs of our associates.",
        "Citizens Bank needs analysts who are eligible for promotion.",
        "While relocation, immigration, and/or tax compliance support are not guaranteed, we may offer assistance.",
    ]
    for s in allowed:
        assert dealbreakers(s, F) == [], s


def test_abroad():
    gratkorn = "Location: Gratkorn, Austria | Part-time. More information about NXP in Austria."
    assert abroad("Gratkorn", gratkorn, {**F, "locations_blocked": ["Austria"]})
    assert not abroad("Austin (Oakhill, Office)", "More information about NXP in the United States.",
                      {**F, "locations_blocked": ["Austria"]})
    assert abroad("Houston, TX", gratkorn, {**F, "locations_blocked": ["Austria"]})
    assert abroad("Dela Rosa - Street office", ", Philippines\nSupports US and local reporting.",
                  {**F, "locations_blocked": ["Philippines"]})
    assert not abroad("Remote","Work from anywhere in the US. Teams in India too.", F)
    # no location and nothing foreign is fine, remote roles often say nothing
    assert not abroad("", "Join our well services team in Aberdeen.", F)
    assert abroad("Houston, TX", "This role can be based in Houston or Bengaluru, India.", F)
    assert not abroad("", "Based at our office in Houston, TX.", F)
    assert not abroad("", "This role sits in Texas.", F)
    caps = {**F, "locations_blocked": ["CAN", "IND"]}
    assert not abroad("MN, United States", "Located in a bustling town, you can drive to lunch.", caps)
    assert abroad("", "Work location: Toronto, CAN.", caps)


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
    assert years_required("THREE (3) or more years of experience in anti-money laundering") == 3
    assert years_required("5 or more years of relevant experience") == 5
    assert years_required("8+ years in management consulting at a strategy consulting firm or similar, synthesizing "
                          "analysis and advising senior executives. A degree or equivalent experience") == 8
    assert years_required("5 years working in supply chain planning") == 5
    assert years_required("Five years running as industry award winner. Requires 1 year of data analysis experience.") == 1
    uhg = ("Required Qualifications:\n- 2+ years of experience with data engineering, SQL and ETL tools\n"
           "- 2+ years of experience with big data processing\n- 1+ years of experience with cloud tools\n"
           "- Proven ability to collaborate across teamsPreferred Qualifications:\n- 4+ years of experience in software engineering")
    assert years_required(uhg) == 2
    assert years_required("- 5+ years of healthcare domain experience\n- 3+ years of relevant experience") == 3
    assert years_required("Bachelor's degree and 4 years of experience, or Master's degree and 2 years of experience") == 2
    assert years_required("Bachelor's Degree with 5+ years (or Master's with 3+ years, or equivalent 8+ years) of "
                          "professional experience in data analysis.") == 3
    assert years_required("2-4+ years of experience in business analytics, finance/accounting, or related field(s)") == 2
    assert years_required("- 2+ years of experience with SQL\n- 1+ years of experience analyzing data using cloud tools") == 2
    assert years_required("Requirements:\n- 2 years of experience\nNice to have:\n- 6+ years of experience in banking") == 2
    assert years_required("3 years or more in a similar procurement, sourcing or supply chain role") == 3
    assert years_required("2 years in Revenue Cycle Operations in a hospital setting, multi-hospital setting preferred") == 2
    assert years_required("Minimum Qualifications:\n- High school diploma\nPreferred Qualifications:\n- 2-4 years of accounting experience") is None
    assert years_required("no experience needed") is None
    assert years_required("We have been in business 10 years") is None
    assert years_required("With over 30 years of experience serving customers") is None
    assert years_required("Offer includes 401(k) and 2 weeks PTO") is None


def test_pay():
    assert pay("Salary: $70,000 - $85,000 per year") == "$70,000 - $85,000"
    assert pay("Pay $25.50 to $31 hourly") == "$25.50 to $31"
    assert pay("Competitive pay") is None
    assert pay("JR210610 Product Operations Analyst Employee referral: $250 CareBridge Health") is None
    assert pay("Sign-on bonus $5,000. Salary range $68,000 to $90,000") == "$68,000 to $90,000"
    assert pay("Corebridge matches donations to tax-exempt organizations 1:1, up to $5,000.") is None
    assert pay("The anticipated salary range is $115, 000 to $120, 000 at the start.") == "$115, 000 to $120, 000"


def test_html_to_text():
    out = html_to_text("<p>Hi&amp;bye</p><ul><li>SQL</li><li>Python</li></ul><script>x()</script>")
    assert out == "Hi&bye\n\n- SQL\n- Python"


def test_software_languages_only_when_required():
    assert software_required("Requirements:\n- SQL, Python, and Java")
    assert software_required("Must have strong C++ skills.")
    assert not software_required("Programming languages (eg, Python, C#, Java, or SQL).")
    assert not software_required("Requirements:\n- SQL and Python\nPreferred Qualifications:\n- Java and C++")
    assert not software_required("Java experience is a plus.")
    assert not software_required("Grade C or better in statistics. Go-to partner for reporting.")


def test_new_tools_and_weak_ones():
    assert skills_ok("Build Spotfire dashboards") and skills_ok("Python/R") and skills_ok("Alteryx workflows")
    assert not skills_ok("AWS and Azure") and not skills_ok("Our R&D team")


def test_offshore_firms_never_followed():
    from filters import offshore
    for n in ("Accenture", "Capgemini", "Cognizant", "Tata Consultancy Services", "TCS", "HCLTech", "EXL", "Genpact", "NTT DATA"):
        assert offshore(n), n
    for n in ("Chubb", "Excel Energy", "Charles Schwab", "Texas Children's", "Duke Energy", "Wells Fargo", "Trust Bank"):
        assert not offshore(n), n


def test_google_senior_levels_skipped():
    from filters import google_senior
    assert google_senior("Google", "Senior Financial Analyst, Technical Infrastructure, Supply Chain")
    assert google_senior("Google", "Technical Program Manager III, AI Product Growth, Google Ads")
    assert google_senior("Google", "Partner Incentives Senior Analyst, Google Cloud")
    assert not google_senior("Google", "Financial Analyst, Cloud Product Finance")
    assert not google_senior("Google", "Data Analytics and Systems Analyst, Tax Technology")
    assert not google_senior("Google", "Business Analyst II, Payments")
    assert not google_senior("Chubb", "Senior Data Analyst")
