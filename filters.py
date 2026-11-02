import html
import re

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10}
YEARS = re.compile(r"(?<![\d.])(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")\s*\+?\s*(?:\(\d{1,2}\)\s*)?"
                   r"(?:(?:-|–|to)\s*(?:\d{1,2}|" + "|".join(NUMBER_WORDS) + r")\s*\+?\s*)?(?:years?|yrs?)\b", re.I)
PAY = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s*[kK]?(?:\s*(?:-|–|to)\s*\$?\s?\d[\d,]*(?:\.\d+)?\s*[kK]?)?")


def _matches(terms, text, flags=re.I):
    return [t for t in terms if re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", text, flags)]


def title_ok(title, f):
    return not _matches(f["title_exclude"], title) and bool(_matches(f["title_include"], title))


def _place_ok(place, f):
    # "IN-Pune", "CA-Ontario-Toronto": a leading code is a country, only US- is ours
    m = re.match(r"\s*([A-Z]{2})-\S", place)
    if m:
        return m.group(1) == "US"
    allowed = f["locations_allowed"]
    # two-letter state codes only count in capitals
    codes = [t for t in allowed if len(t) == 2 and t.isupper()]
    names = [t for t in allowed if t not in codes]
    # "(DE)" style country codes are not states
    if _matches(names, place) or _matches(codes, re.sub(r"\([A-Z]{2}\)", "", place), 0):
        return True
    return not _matches(f["locations_blocked"], place)


def location_ok(location, f):
    places = [p for p in re.split(r"[;|]", location) if p.strip()]
    return not places or any(_place_ok(p, f) for p in places)


def _clean(text):
    return " ".join(text.replace("’", "'").replace("‑", "-").split())


NEGATIVE = re.compile(r"\b(without|not|no|unable|cannot|can't|won't|never|ineligible|unavailable)\b", re.I)
CITIZEN = re.compile(r"citizen|green ?card|permanent resident|\bu\.?s\.? persons?\b|\bitar\b", re.I)
REQUIRED = re.compile(r"\b(must|required?|requires|requirement|only|need|needs|eligible|obtain)\b", re.I)
CLEARANCE = re.compile(r"security clearance|secret clearance|\bts/sci\b|public trust", re.I)
# equal opportunity and e-verify text mentions citizenship without restricting it
BOILERPLATE = re.compile(r"regard|discriminat|equal (employment )?opportunity|e-verify|\bi-9\b|protected", re.I)
STUDENT = re.compile(r"currently enrolled|current(ly)? (a )?(student|pursuing)|pursuing an? (bachelor|master|undergrad|graduate|degree)"
                     r"|rising (junior|senior)|returning to school|enrolled in an? (accredited )?(university|college|degree)"
                     r"|expected graduation|graduation date", re.I)


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
        if not hit and re.search(r"sponsor", s, re.I) and NEGATIVE.search(s):
            hit = "no sponsorship"
        if not hit and CITIZEN.search(s) and REQUIRED.search(s):
            hit = "citizenship or green card required"
        if not hit and CLEARANCE.search(s) and not no_clearance:
            hit = "clearance"
        if hit:
            return [f"{hit}: {s[:120]}"]
    return []


def student_only(title, text):
    return bool(re.search(r"\bintern(ship)?\b|co-op", title, re.I) and STUDENT.search(text))


def min_years(text):
    text = _clean(text)
    found = []
    for m in YEARS.finditer(text):
        # only count years near the word experience
        if "experience" not in text[max(0, m.start() - 100):m.end() + 100].lower():
            continue
        first = m.group(1).lower()
        n = NUMBER_WORDS.get(first) or int(first)
        # bigger numbers are company history, like "over 30 years of experience"
        if n <= 15:
            found.append(n)
    return min(found) if found else None


def pay(text):
    m = PAY.search(_clean(text))
    return m.group(0).strip() if m else None


def html_to_text(raw):
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", raw or "")
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|h\d|tr)>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "\n- ", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in s.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
