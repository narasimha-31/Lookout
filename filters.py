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


NO_SPONSOR = re.compile(r"\b(without|not|no|unable|cannot|can't|won't|never|ineligible|unavailable)\b", re.I)


def dealbreakers(text, f):
    low = _clean(text).lower()
    found = [p for p in f["dealbreakers"] if p.lower() in low]
    # catches wordings like "sponsorship for this role is not being offered"
    for sentence in [] if found else re.split(r"(?<=[.!?;])\s+|\n", text.replace("’", "'")):
        if re.search(r"sponsor", sentence, re.I) and NO_SPONSOR.search(sentence):
            found.append("no sponsorship: " + " ".join(sentence.split())[:120])
            break
    return found


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
