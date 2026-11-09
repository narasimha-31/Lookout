import html
import re

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10}
YEARS = re.compile(r"(?<![\d.])(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")\s*\+?\s*(?:\(\d{1,2}\)\s*)?"
                   r"(?:(?:-|–|to)\s*(?:\d{1,2}|" + "|".join(NUMBER_WORDS) + r")\s*\+?\s*)?"
                   r"(?:(?:or more|or greater|plus)\s+)?(?:years?|yrs?)\b", re.I)
# "$115, 000" shows up with a stray space after the comma
NUM = r"(?:\d{1,3}(?:,\s?\d{3})+|\d+)(?:\.\d+)?"
PAY = re.compile(rf"\$\s?{NUM}\s*[kK]?(?:\s*(?:-|–|to)\s*\$?\s?{NUM}\s*[kK]?)?")


def _matches(terms, text, flags=re.I):
    # codes like CAN and IND only count in capitals, not "can" or "ind"
    return [t for t in terms if re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", text, 0 if t.isupper() else flags)]


ROLES = ["analyst", "engineer", "developer", "specialist", "associate", "planner", "coordinator", "buyer", "steward", "intern",
         "internship", "co-op", "technician", "consultant"]
# gis data entry and gis technician jobs are real entry gis work
GIS_OK = ["data entry", "technician"]
# engineers and developers only count for data work, not "Data Center Engineer" style titles
BUILDERS = ["engineer", "developer"]
DATA_DOMAINS = ["data", "analytics", "bi", "business intelligence", "etl", "sql", "reporting", "power bi", "tableau",
                "database", "data warehouse", "visualization", "gis"]
# applied ai work like llm apps, rag and agents, not machine learning research
AI_DOMAINS = ["ai", "genai", "gen ai", "generative ai", "llm", "llms", "rag", "agentic", "artificial intelligence"]
CLOUD = ["cloud", "aws", "azure", "gcp"]
# associates, specialists and interns are too broad for words like operations or product
CORE_DOMAINS = DATA_DOMAINS + ["supply chain", "demand", "procurement", "sourcing",
                               "pricing", "information systems", "s&op", "insights"]
WORK = ["business intelligence", "analytics",
        "data analysis", "data engineering"]
# data tools from the resume
SKILLS = ["sql", "python", "power bi", "power query", "dax", "tableau", "looker", "snowflake", "etl", "pandas", "postgresql",
          "sql server", "bigquery", "airflow", "dbt", "kafka", "gis", "esri", "qgis", "postgis", "arcgis", "databricks",
          "sas", "alteryx", "spark", "pyspark", "redshift", "azure data factory", "synapse", "mysql", "qlik", "ssrs", "ssis",
          "spotfire", "aws", "azure", "gcp", "google cloud"]
# a bare "R" is too common a letter, only clear uses count
R_TOOL = re.compile(r"\bRStudio\b|\bR (programming|language|studio)\b|(?<![\w&-])R\s*/|/\s*R(?![\w&'-])")
# core software languages; C and Go only count next to another language or the word programming
LANGS = re.compile(r"C\+\+|C#|\bJava\b(?!\s*[Ss]cript)|\bJavaScript\b|\bTypeScript\b|\bGolang\b|\bRust\b|\bKotlin\b"
                   r"|(?<![\w-])C(?![\w+#-])|(?<![\w-])Go(?![\w-])")
SOFT = re.compile(r"prefer|nice to have|a plus|bonus|desired|ideally|familiarity|exposure", re.I)
# outsourcing firms that staff us roles from abroad; never followed, whatever their board says
OFFSHORE = re.compile(r"accenture|capgemini|cognizant|infosys|wipro|tata consultancy|\btcs\b|hcl|tech mahindra|ltimindtree|mindtree"
                      r"|larsen|\blti\b|mphasis|hexaware|virtusa|ntt data|persistent systems|zensar|birlasoft|coforge|genpact"
                      r"|\bexl\b|exlservice|\bwns\b|mu sigma|tiger analytics|latentview|fractal|igate|syntel|mastech|\bust\b|ust global"
                      r"|sutherland|firstsource|concentrix|teleperformance|dxc|kyndryl|\bcgi\b|epam|sonata software|cyient|tredence"
                      r"|sigmoid|course5|quess|happiest minds|kpit|nagarro|globallogic|itc infotech|sasken|mindtree", re.I)


def offshore(name):
    return bool(OFFSHORE.search(name or ""))


TERRITORIES = re.compile(r"puerto rico|guam|virgin islands|american samoa|mariana islands|\bPR\b(?=,? (US|USA|United States)\b|$)", re.I)
PARTS = re.compile(r"\s[-–—|/]\s|[,()|:–—]")
LEVEL = re.compile(r"\b([ivx]+|\d+|jr\.?|junior|entry[- ]level|level \w+)\b", re.I)


def _excluded(title, f):
    hits = _matches(f["title_exclude"], title)
    if _matches(["gis"], title):
        hits = [h for h in hits if h not in GIS_OK]
    return hits


def _roles(title, f):
    """Yields (role, matched) for each role word, matched when a domain word sits with it."""
    if _excluded(title, f):
        return
    parts = [p.strip() for p in PARTS.split(title) if p.strip()]
    for part in parts:
        roles = [r.lower() for r in _matches(ROLES, part)]
        # "Analyst, Supply Chain Planning": a role on its own takes its domain from the other parts
        alone = LEVEL.sub("", part).strip(" .").lower() in roles
        for role in roles:
            if role in BUILDERS:
                # ai engineer roles paused for now, put AI_DOMAINS back to resume
                # yield role, any(_matches(DATA_DOMAINS + AI_DOMAINS, p) for p in (parts if alone else [part]))
                yield role, any(_matches(DATA_DOMAINS + CLOUD, p) for p in (parts if alone else [part]))
            else:
                yield role, bool(_matches(f["title_include"] if role in ("analyst", "planner") else CORE_DOMAINS, title))


def max_years(title):
    # data engineers stay at 2 years or less, other roles take "3+"
    return 2 if re.search(r"\bengineer", title, re.I) else 3


def title_ok(title, f):
    # some titles name only the work, like "Financial Planning and Analysis"
    work = not _excluded(title, f) and _matches(WORK, title)
    return bool(work) or any(ok for _, ok in _roles(title, f))


WIDE = ["associate", "specialist", "consultant", "coordinator", "intern", "internship", "co-op"]


def title_wide(title, f):
    # "Associate, Tax-Driven Investments" never says analyst, its posting has to name a real data tool
    return (not title_ok(title, f) and bool(_matches(f["title_include"], title))
            and any(r in WIDE for r, _ in _roles(title, f)))


def title_maybe(title, f):
    # an analyst title without a known domain, worth reading the description for
    return not title_ok(title, f) and (any(r == "analyst" for r, _ in _roles(title, f)) or title_wide(title, f))


# excel-only roles are wanted too, a bare "access" is too common a word
OFFICE = ["excel", "sap", "oracle", "microsoft access", "ms access"]


def skills_ok(text, office=True):
    return bool(R_TOOL.search(text)) or (office and any(re.search(rf"(?<!\w){s}(?!\w)", text, re.I) for s in OFFICE)) or any(re.search(rf"(?<!\w){s}(?!\w)", text, re.I) for s in SKILLS)


def software_required(text):
    """The first required line asking for a core software language like Java or C++, or None."""
    for s in (s for line in _required_lines(text) for s in _sentences(line)):
        hits = LANGS.findall(s)
        if not hits or SOFT.search(s):
            continue
        if set(hits) <= {"C", "Go"} and not re.search(r"programming|languages?|coding", s, re.I):
            continue
        # "Python, Java, or SQL" can be met with python or sql
        if re.search(r"\bor\b|/|\be\.?g\b|such as|like", s, re.I) and skills_ok(s, office=False):
            continue
        return s
    return None


def _us_marked(place, f):
    allowed = f["locations_allowed"]
    # two-letter state codes only count in capitals
    codes = [t for t in allowed if len(t) == 2 and t.isupper()]
    names = [t for t in allowed if t not in codes]
    # "(DE)" style country codes are not states
    return bool(_matches(names, place) or _matches(codes, re.sub(r"\([A-Z]{2}\)", "", place), 0))


# state codes that are also country codes
TWIN_CODES = {"IN", "CA", "DE", "AR", "CO", "MA", "PA", "ID", "IL", "GA", "SC", "AL", "MD", "ME", "MN", "MT", "NE", "SD", "VA"}


def _place_ok(place, f):
    # territories often say "United States" too
    if TERRITORIES.search(place):
        return False
    # "IN-Pune", "CA-Ontario-Toronto": a leading code is a country, only US- is ours
    m = re.match(r"\s*([A-Z]{3})( - |-)\S", place)
    if m:
        return m.group(1) == "USA"
    m = re.match(r"\s*([A-Z]{2})( - |-)\S", place)
    if m:
        # "TX - San Angelo" is a state, "IN - Bengaluru, India" is not Indiana
        state = m.group(2) == " - " and m.group(1) in f["locations_allowed"] and not _matches(f["locations_blocked"], place)
        return m.group(1) == "US" or state
    # "King Abdullah Economic City, 02": us states are letters, never numbered regions
    if re.search(r",\s*\d{1,3}\s*$", place):
        return False
    # "Kulim, 02 (MY)", "London (GB)": a bracketed code is a country too
    m = re.search(r"\(([A-Z]{2})\)", place)
    if m:
        return m.group(1) == "US"
    if not _matches(f["locations_blocked"], place):
        return True
    # "Dublin, OH" is ours, but in "Bangalore, IN" or "Toronto, CA" the code is a country, not a state
    return _us_marked(place, {**f, "locations_allowed": [t for t in f["locations_allowed"] if t not in TWIN_CODES]})


def _places(location):
    return [p for p in re.split(r"[;|]", location) if p.strip()]


def location_ok(location, f):
    places = _places(location)
    if not places:
        return True
    # any foreign place means the role can be filled abroad, so "Austin, TX; Bangalore, India" is out
    return all(_place_ok(p, f) for p in places)


WHERE = re.compile(r"based in|located in|work location|job location|location:|onsite in|on-site in|hybrid in|remote in|this (role|position) (is|will be|can be)", re.I)


def abroad(location, text, f):
    foreign = [t for t in f["locations_blocked"] if not t.startswith("(")]
    # "based in Houston or Bengaluru, India" can be filled abroad even with a us city listed
    for s in re.split(r"(?<=[.!?;])\s+|\n", text):
        if WHERE.search(s) and _matches(foreign, s):
            return True
    # a bare town like "Gratkorn" says nothing, so ask the description
    if any(_us_marked(p, f) or re.match(r"\s*US-", p) for p in _places(location)):
        return False
    names = [t for t in f["locations_allowed"] if not (len(t) == 2 and t.isupper())]
    us = _matches(names, text) or re.search(r"\bU\.?S\.?A?\b", text)
    # workday puts the full location on the first line, ", Philippines", while the body may still mention US work
    head = text.strip().split("\n", 1)[0][:200]
    if _matches(foreign, head) and not _us_marked(head, f):
        return True
    return bool(_matches(foreign, text)) and not us


def _clean(text):
    return " ".join(text.replace("’", "'").replace("‑", "-").split())


NEGATIVE = re.compile(r"\b(without|not|no|unable|cannot|can't|won't|never|ineligible|unavailable)\b", re.I)
VISA = re.compile(r"sponsor|\bvisas?\b|\bh-?1-?b\b|\bopt\b(?![- ]?(out|in)\b)|\bcpt\b|stem opt|immigration|work permit", re.I)
# bank names like First Citizens and Citizens Bank are not citizenship
CITIZEN = re.compile(r"(?<!first )citizen(?!s (bank|financial))|green ?card|permanent resident|\bu\.?s\.? persons?\b|\bitar\b", re.I)
REQUIRED = re.compile(r"\b(must|required?|requires|requirement|only|need|needs|eligible|obtain)\b", re.I)
CLEARANCE = re.compile(r"security clearance|secret clearance|\bts/sci\b|public trust", re.I)
# equal opportunity and e-verify text mentions citizenship without restricting it
BOILERPLATE = re.compile(r"regard|discriminat|equal (employment )?opportunity|e-verify|\bi-9\b|protected"
                         # "employer sponsored health plan" is a benefit, not a visa
                         r"|sponsored (health|medical|dental|vision|benefit|insurance|plan|401|retirement|events?)"
                         # "support is not guaranteed, we may offer assistance" leaves it open
                         r"|not guaranteed", re.I)
STUDENT = re.compile(r"currently enrolled|current(ly)? (a )?(student|pursuing)|pursuing an? (bachelor|master|undergrad|graduate|degree)"
                     r"|rising (junior|senior)|returning to school|enrolled in an? (accredited )?(university|college|degree)"
                     r"|expected graduation|graduation date|ongoing studies|fit your studies|student position", re.I)


def _sentences(text):
    text = re.sub(r"\bU\.\s?S\.(\s?A\.)?|\be\.g\.|\bi\.e\.", lambda m: m.group(0).replace(".", ""), text.replace("’", "'"))
    return [" ".join(s.split()) for s in re.split(r"(?<=[.!?;])\s+|\n", text) if s.strip()]


def dealbreakers(text, f):
    phrases = [p.lower() for p in f["dealbreakers"]]
    for s in _sentences(text):
        if BOILERPLATE.search(s):
            continue
        low = s.lower()
        no_clearance = re.search(r"not required|no (security )?clearance", s, re.I)
        hit = next((p for p in phrases if p in low and not (no_clearance and "clearance" in p)), None)
        # "e.g. unable to provide visas" in a note about screening is an example, not this role
        example = not re.search(r"sponsor", s, re.I) and re.search(r"\be\.?g\b|for example", s, re.I)
        if not hit and VISA.search(s) and NEGATIVE.search(s) and not example:
            hit = "no sponsorship"
        # "sponsorship is offered exclusively for principal roles", "require unrestricted work authorization"
        if not hit and re.search(r"unrestricted (u\.?s\.? |us )?work authori|sponsor\w* .*\b(exclusively|only) (for|to) (principal|director|senior)", s, re.I):
            hit = "no sponsorship"
        if not hit and CITIZEN.search(s) and REQUIRED.search(s):
            hit = "citizenship or green card required"
        if not hit and CLEARANCE.search(s) and not no_clearance:
            hit = "clearance"
        if hit:
            return [f"{hit}: {s[:120]}"]
    return []


def google_senior(company, title):
    # google's pages are closed to robots, so its level words stand in for the years
    return company.lower() == "google" and bool(re.search(r"\b(senior|sr|staff|lead|principal|manager|director|head)\b", title, re.I)
                                                or re.search(r"\b(III|IV|V|VI)\b", title))


def student_only(title, text):
    return bool(re.search(r"\bintern(ship)?\b|co-op", title, re.I) and STUDENT.search(text))


PREFERRED = re.compile(r"(preferred|desired|additional) (qualifications?|skills|experience|requirements)|nice[- ]to[- ]haves?"
                       r"|bonus points|preferred:", re.I)
HEADING = re.compile(r"(required|basic|minimum|must[- ]haves?|qualifications|requirements|what you|who you|about you"
                     r"|your experience|experience|skills|education|responsibilities)\b", re.I)
HISTORY = re.compile(r"award|winn|history|founded|\bserv(e|es|ed|ing)\b|been in business|in business for|leader|anniversar|legacy|celebrat"
                     r"|\bour \d|\bwe('ve| have)\b|company has", re.I)
GENERAL = re.compile(r"\s*(of\s+)?((professional|relevant|related|work|working|industry|progressive|full[- ]time|total"
                     r"|overall|prior|previous|practical|hands[- ]on|post[- ]graduate)\s+)*(experience|exp)\b"
                     # plain means nothing narrows it, "experience analyzing data" or "experience with SQL" is a skill
                     r"(?=\s*($|[.,;:)]|(is )?required|needed|minimum|or\b|and\b|in an? (similar|related|relevant|comparable)"
                     r"|in (the|this|a) (field|industry|role)))", re.I)
DEGREES = re.compile(r"bachelor|master|degree|\bBS\b|\bMS\b|equivalent", re.I)


def _required_lines(text):
    # headings glued to the line before, like "teamsPreferred Qualifications:"
    text = PREFERRED.sub(lambda m: "\n" + m.group(0), text.replace("’", "'"))
    keep, preferred = [], False
    for line in text.splitlines():
        s = line.strip(" -*•\t")
        if PREFERRED.match(s):
            preferred = True
        else:
            if len(s) < 60 and HEADING.match(s):
                preferred = False
            if not preferred:
                keep.append(s)
    return keep


def years_required(text):
    general, skill = [], []
    for s in (s for line in _required_lines(text) for s in _sentences(line)):
        if HISTORY.search(s):
            continue
        plain, narrow = [], []
        for m in YEARS.finditer(s):
            # "8+ years in consulting" or "5 years working" count without the word experience
            work = "+" in m.group(0) or re.match(r"\s+(or more\s+)?(working|in|as)\b", s[m.end():], re.I)
            if "experience" not in s.lower() and not work:
                continue
            # "5 years preferred" is a wish, not a bar
            if re.search(r"prefer|nice to have|a plus|bonus", s[m.end():m.end() + 30], re.I):
                continue
            nums = [NUMBER_WORDS.get(x.lower()) or int(x) for x in re.findall(r"\d{1,2}|" + "|".join(NUMBER_WORDS), m.group(0), re.I)]
            # "3-5 years" is a five year job, while "1-4" still takes juniors
            n = nums[-1] if nums[0] >= 3 else nums[0]
            # bigger numbers are company history, like "over 30 years of experience"
            if n <= 15:
                (plain if GENERAL.match(s[m.end():]) else narrow).append(n)
        # "5+ years with a bachelor's (or 3+ with a master's)" is one requirement, the easier path counts
        if DEGREES.search(s) and len(plain + narrow) > 1:
            plain, narrow = [min(plain + narrow)], []
        general += plain
        skill += narrow
    # skill lines only matter when there is no plain requirement, then the first one is the main one
    if general:
        return min(general)
    return skill[0] if skill else None


def pay(text):
    text = _clean(text)
    for m in PAY.finditer(text):
        before = re.split(r"[.\n]\s", text[max(0, m.start() - 150):m.start()])[-1]
        after = text[m.end():m.end() + 20]
        # "employee referral: $250" or a signing bonus is not the salary
        if re.search(r"referral|bonus|stipend|reimburs|allowance|gift|credit|donat|charit|match|contribut|tuition|relocat", before, re.I):
            continue
        hourly = re.search(r"^\s*(/\s*h(ou)?r|per hour|an hour|hourly)", after, re.I)
        amount = float(re.sub(r"[^\d.]", "", m.group(0).split("-")[0].split("–")[0].split("to")[0]) or 0)
        if hourly or amount >= 1000 or re.search(r"\d\s*[kK]", m.group(0)):
            return m.group(0).strip()
    return None


def html_to_text(raw):
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", raw or "")
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|h\d|tr)>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "\n- ", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in s.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
