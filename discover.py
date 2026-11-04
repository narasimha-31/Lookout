import html
import re
from concurrent.futures import ThreadPoolExecutor

import db
import fetchers
import filters as flt
import mail
from main import AUDIT_BLOCK, _audit_one, load_env

FEEDS = ["https://techcrunch.com/tag/funding/feed/", "https://techcrunch.com/category/venture/feed/",
         "https://techcrunch.com/category/startups/feed/", "https://www.producthunt.com/feed"]
PAGES = 3
# "Viral AI startup Instinct has raised $350M" -> Instinct
FUNDED = re.compile(r"([A-Z][\w.&'-]*(?: [A-Z][\w.&'-]*){0,2}) (?:raises|raised|has raised|lands|secures|closes|bags|nabs|snags|picks up|doubles)\b")
BOARDS = ["greenhouse", "lever", "ashby"]
INVESTOR = re.compile(r"\b(capital|ventures|partners|fund|catalyst|vc|investors)$", re.I)


def names():
    found = []
    for feed in FEEDS:
        for page in range(1, PAGES + 1):
            try:
                xml = fetchers.http("GET", feed, params={"paged": page} if page > 1 else None, headers={"Accept": "application/rss+xml"}).text
            except Exception:
                break
            titles = [html.unescape(t) for t in re.findall(r"<(?:item|entry)>.*?<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", xml, re.S)]
            if "producthunt" in feed:
                found += [t.split(" - ")[0].strip() for t in titles]
            else:
                found += [m[1] for m in (FUNDED.search(t) for t in titles) if m]
            if "producthunt" in feed:
                break
    # "Airbnb-backed WeRoad" -> WeRoad
    found = [re.sub(r"^\S+-backed ", "", n) for n in found]
    return list(dict.fromkeys(n for n in found if 2 < len(n) < 40 and not INVESTOR.search(n)))


def slugs(name):
    base = re.sub(r"[^a-z0-9 ]", "", name.lower()).split()
    return list(dict.fromkeys(["".join(base), "-".join(base)]))


def board(name):
    for slug in slugs(name):
        for platform in BOARDS:
            c = {"name": name, "platform": platform, "board": slug}
            try:
                if fetchers.fetch_list(c, 50):
                    return c
            except Exception:
                continue
    return None


def judge(c, f):
    jobs = fetchers.fetch_list(c, 500)
    data = [j for j in jobs if flt.title_ok(j.title, f) and flt.location_ok(j.location, f)]
    if not data:
        return None, "no data roles"
    read, hits = _audit_one(c, f)
    if len(hits) >= AUDIT_BLOCK:
        return False, f"blocked: no sponsorship {len(hits)}/{read}"
    return True, f"{len(data)} data roles, {len(hits)}/{read} say no sponsorship"


def discover():
    f = db.filters()
    seen = db.known()
    fresh = [n for n in names() if n.lower() not in seen]
    with ThreadPoolExecutor(8) as pool:
        found = [c for c in pool.map(board, fresh) if c and c["board"].lower() not in seen]
    added, blocked = [], []
    for c in found:
        try:
            active, why = judge(c, f)
        except Exception:
            continue
        if active is None:
            continue
        # first_run_done so the roles open today reach you too
        row = {"name": c["name"], "platform": c["platform"], "board": c["board"], "active": active,
               "first_run_done": active, "note": None if active else f"{why} (found in the news)"}
        if db.add_company(row):
            (added if active else blocked).append(f"{c['name']} ({c['platform']}): {why}")
    if added or blocked:
        body = ("Added from TechCrunch and Product Hunt:\n" + "\n".join(added or ["none"])
                + ("\n\nFound but blocked:\n" + "\n".join(blocked) if blocked else ""))
        mail.send(mail.notice(f"Lookout found {len(added)} new companies", body))
    print(f"{len(fresh)} new names, {len(found)} with boards, {len(added)} added, {len(blocked)} blocked")


if __name__ == "__main__":
    load_env()
    discover()
