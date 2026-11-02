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


def _us_marked(place, f):
    allowed = f["locations_allowed"]
    # two-letter state codes only count in capitals
    codes = [t for t in allowed if len(t) == 2 and t.isupper()]
    names = [t for t in allowed if t not in codes]
    # "(DE)" style country codes are not states
    return bool(_matches(names, place) or _matches(codes, re.sub(r"\([A-Z]{2}\)", "", place), 0))


def _place_ok(place, f):
    # "IN-Pune", "CA-Ontario-Toronto": a leading code is a country, only US- is ours
    m = re.match(r"\s*([A-Z]{2})-\S", place)
    if m:
        return m.group(1) == "US"
    # "Kulim, 02 (MY)", "London (GB)": a bracketed code is a country too
    m = re.search(r"\(([A-Z]{2})\)", place)
    if m:
        return m.group(1) == "US"
    return _us_marked(place, f) or not _matches(f["locations_blocked"], place)


def _places(location):
    return [p for p in re.split(r"[;|]", location) if p.strip()]


def _bare_state(place, f):
    name = re.sub(r",?\s*(USA|US|United States( of America)?)\s*$", "", place.strip(), flags=re.I).strip()
    return name.lower() in {t.lower() for t in f["locations_allowed"] if len(t) > 3}


def location_ok(location, f):
    places = _places(location)
    if not places:
        return True
    ours = [p for p in places if _place_ok(p, f)]
    # "Tennessee, USA; Chennai, India": a bare state next to foreign cities is usually a misread "TN" (Tamil Nadu)
    if ours and len(ours) < len(places) and all(_bare_state(p, f) for p in ours):
        return False
    return bool(ours)


def abroad(location, text, f):
    # a bare town like "Gratkorn" says nothing, so ask the description
    if any(_us_marked(p, f) or re.match(r"\s*US-", p) for p in _places(location)):
        return False
    names = [t for t in f["locations_allowed"] if not (len(t) == 2 and t.isupper())]
    us = _matches(names, text) or re.search(r"\bU\.?S\.?A?\b", text)
    foreign = [t for t in f["locations_blocked"] if not t.startswith("(")]
    return bool(_matches(foreign, text)) and not us


def _clean(text):
    return " ".join(text.replace("’", "'").replace("‑", "-").split())


NEGATIVE = re.compile(r"\b(without|not|no|unable|cannot|can't|won't|never|ineligible|unavailable)\b", re.I)
VISA = re.compile(r"sponsor|\bvisas?\b|\bh-?1-?b\b|\bopt\b|\bcpt\b|stem opt|immigration|work permit", re.I)
CITIZEN = re.compile(r"citizen|green ?card|permanent resident|\bu\.?s\.? persons?\b|\bitar\b", re.I)
REQUIRED = re.compile(r"\b(must|required?|requires|requirement|only|need|needs|eligible|obtain)\b", re.I)
CLEARANCE = re.compile(r"security clearance|secret clearance|\bts/sci\b|public trust", re.I)
# equal opportunity and e-verify text mentions citizenship without restricting it
BOILERPLATE = re.compile(r"regard|discriminat|equal (employment )?opportunity|e-verify|\bi-9\b|protected", re.I)
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
        example = not re.search(r"sponsor", s, re.I) and re.search(r"e\.?g|for example", s, re.I)
        if not hit and VISA.search(s) and NEGATIVE.search(s) and not example:
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


def years_required(text):
    text = _clean(text)
    found = []
    for m in YEARS.finditer(text):
        # only count years near the word experience
        if "experience" not in text[max(0, m.start() - 100):m.end() + 100].lower():
            continue
        # "5 years preferred" is a wish, not a bar
        if re.search(r"prefer|nice to have|a plus|bonus", text[m.end():m.end() + 60], re.I):
            continue
        first = m.group(1).lower()
        n = NUMBER_WORDS.get(first) or int(first)
        # bigger numbers are company history, like "over 30 years of experience"
        if n <= 15:
            found.append(n)
    # ranges count by their low end, but the strictest requirement is the real bar
    return max(found) if found else None


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
