import html
import os
import re
import time
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
    if len(hits) >= AUDIT_BLOCK and len(hits) * 2 > read:
        return False, f"blocked: no sponsorship {len(hits)}/{read}"
    return True, f"{len(data)} data roles, {len(hits)}/{read} say no sponsorship"


def discover():
    f = db.filters()
    seen = db.known()
    fresh = [n for n in names() if n.lower() not in seen and not flt.offshore(n)]
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
        # the first read only saves what is open; just later postings get mailed
        row = {"name": c["name"], "platform": c["platform"], "board": c["board"], "active": active,
               "first_run_done": False, "note": None if active else f"{why} (found in the news)"}
        if db.add_company(row):
            (added if active else blocked).append(f"{c['name']} ({c['platform']}): {why}")
    if added or blocked:
        body = ("Added from TechCrunch and Product Hunt:\n" + "\n".join(added or ["none"])
                + ("\n\nFound but blocked:\n" + "\n".join(blocked) if blocked else ""))
        mail.send(mail.notice(f"Lookout found {len(added)} new companies", body))
    print(f"{len(fresh)} new names, {len(found)} with boards, {len(added)} added, {len(blocked)} blocked")


# role phrases across the tracked areas; each run takes the next few with each site
ROLE_QUERIES = ["data analyst", "business intelligence analyst", "data engineer", "analytics engineer", "business analyst",
                "reporting analyst", "financial analyst", "fp&a analyst", "supply chain analyst", "demand planner",
                "procurement analyst", "inventory analyst", "pricing analyst", "revenue analyst", "risk analyst",
                "credit analyst", "investment analyst", "operations analyst", "marketing analyst", "sales operations analyst",
                "product analyst", "energy analyst", "commodity analyst", "gis analyst", "sap analyst", "data governance analyst"]
SITES = ["jobs.ashbyhq.com", "job-boards.greenhouse.io", "jobs.lever.co", "myworkdayjobs.com"]
# brave's free plan is 2000 a month, 8 runs a day of 6 stays under it
PER_RUN = 6
MAX_ADDS = 10


def board_from_url(url):
    m = re.match(r"https://jobs\.ashbyhq\.com/([\w.-]+)", url)
    if m:
        return "ashby", m[1].lower(), None
    m = re.match(r"https://(?:job-boards|boards)\.greenhouse\.io/(\w[\w-]*)/jobs/", url)
    if m:
        return "greenhouse", m[1].lower(), None
    m = re.match(r"https://jobs\.lever\.co/([\w.-]+)/", url)
    if m:
        return "lever", m[1].lower(), None
    m = re.match(r"https://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)/job/", url)
    if m:
        return "workday", f"{m[1]}.{m[2]}.myworkdayjobs.com/{m[1]}", m[3]
    return None


def _search(q):
    data = fetchers.http("GET", "https://api.search.brave.com/res/v1/web/search", params={"q": q, "count": 20, "freshness": "pw"},
                         headers={"X-Subscription-Token": os.environ["BRAVE_KEY"], "Accept": "application/json"}).json()
    return [r["url"] for r in (data.get("web") or {}).get("results") or []]


def role_search(run=None):
    if not os.environ.get("BRAVE_KEY"):
        return
    run = int(time.time() // 10800) if run is None else run
    pairs = [(site, role) for role in ROLE_QUERIES for site in SITES]
    found = {}
    for i in range(PER_RUN):
        site, role = pairs[(run * PER_RUN + i) % len(pairs)]
        try:
            urls = _search(f'site:{site} "{role}"')
        except Exception:
            urls = []
        for u in urls:
            b = board_from_url(u)
            if b:
                found.setdefault(b[1], b)
        # free plan allows one search a second
        time.sleep(1.1)
    f, seen = db.filters(), db.known()
    added = []
    for platform, board, site in found.values():
        if len(added) >= MAX_ADDS:
            break
        slug = board.split("/")[-1]
        name = re.sub(r"[-_.]+", " ", slug).title()
        if board in seen or name.lower() in seen or flt.offshore(name):
            continue
        c = {"name": name, "platform": platform, "board": board, "site": site, "overrides": {}}
        try:
            active, why = judge(c, f)
        except Exception:
            continue
        if not active:
            continue
        # the first read only saves what is open; just later postings get mailed
        if db.add_company({**c, "active": True, "first_run_done": False, "note": None}):
            added.append(f"{name} ({platform}): {why}")
    if added:
        mail.send(mail.notice(f"Lookout found {len(added)} new companies by role", "Added from job search:\n" + "\n".join(added)))
    print(f"{len(found)} boards in search, {len(added)} added")


if __name__ == "__main__":
    load_env()
    import sys
    role_search() if "--roles" in sys.argv else discover()
