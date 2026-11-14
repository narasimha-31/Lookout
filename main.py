import hashlib
import os
import re
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import db
import fetchers
import filters as flt
import fit
import mail

NEWEST = 200
# these two serve 10 or 20 a page; dejobs is read one company at a time, so its pages set the run length
PAGED_NEWEST = {"workday": 100, "dejobs": 50}
# vc boards list tens of thousands of jobs worldwide
FIRST_CHECK = 2000


def load_env(path=".env"):
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _row(company, job, emailed=False, repost=False, description=None, score=None):
    return {"company_id": company["id"], "external_job_id": job.id, "title": job.title, "location": job.location,
            "url": job.url, "emailed": emailed, "possible_repost": repost, "description": description, "fit": score}


def check(company, f, before=None, model=None):
    """Returns (emails sent, jobs listed, fingerprint of the job list)."""
    f = {**f, **{k: v for k, v in (company.get("overrides") or {}).items() if k in f}}
    # after the first check only the newest jobs matter
    newest = PAGED_NEWEST.get(company["platform"], NEWEST) if company["first_run_done"] else FIRST_CHECK
    jobs = list({j.id: j for j in fetchers.fetch_list(company, newest)}.values())
    fingerprint = hashlib.sha1("\n".join(sorted(j.id for j in jobs)).encode()).hexdigest()[:16]

    if not company["first_run_done"]:
        db.save_jobs([_row(company, j) for j in jobs])
        # an empty first read is a board hiccup; marking it done would mail every open job next time
        if jobs:
            db.mark_first_run(company["id"])
        return 0, len(jobs), fingerprint
    # same list as last time means nothing new
    if fingerprint == (before or {}).get("ids_hash"):
        return 0, len(jobs), fingerprint

    # only matching titles are looked up by id, supabase logs every request url and long id lists fill the log quota
    jobs_ok = [j for j in jobs if flt.title_ok(j.title, f) or flt.title_maybe(j.title, f)]
    seen = db.seen_ids(company["id"], [j.id for j in jobs_ok]) if jobs_ok else set()
    new = [j for j in jobs_ok if j.id not in seen]
    skipped = [j for j in new if not flt.location_ok(j.location, f)]
    # the rest still gets stored, duplicates are ignored by the database
    ok_ids = {j.id for j in jobs_ok}
    others = [j for j in jobs if j.id not in ok_ids]
    if skipped or others:
        db.save_jobs([_row(company, j) for j in skipped + others])

    sent = 0
    skipped_ids = {j.id for j in skipped}
    for job in (j for j in new if j.id not in skipped_ids):
        jd = _detail(company, job)
        text = flt.html_to_text(jd)
        years = flt.years_required(text)
        # every description has to name a real data tool; with no description the matching title is enough, you check the posting
        unsure = (not flt.skills_ok(text, office=False) if flt.title_wide(job.title, f)
                  else bool(text) and not flt.skills_ok(text))
        # the posting page can name a place the job list left out
        if (unsure or flt.software_required(text) or flt.dealbreakers(text, f) or flt.student_only(job.title, text)
                or flt.google_senior(job.company or company["name"], job.title)
                # with no location listed the title can name the place, "Frankfurt, Germany Working Student"
                or not flt.location_ok(job.location, f)
                or flt.abroad(job.location, text if job.location else f"{job.title}\n{text}", f)
                or (years is not None and years > flt.max_years(job.title))):
            db.save_jobs([_row(company, job)])
            continue
        repost = db.is_repost(company["id"], job.title, job.location)
        flags = [f"asks for {years} years" if years is not None else "no experience mentioned"]
        if repost:
            flags.append("possible repost")
        if not text:
            flags.append("no description on this board, check sponsorship on the posting")
        name = f"{job.company} (via {company['name']})" if job.company else company["name"]
        first_seen = datetime.now(ZoneInfo("America/Chicago")).strftime("%b %d, %I:%M %p CT")
        score = fit.score(model, job.title, text)
        # send before saving so a failed send is retried next run
        mail.send(mail.job_email(name, job, jd, flags, first_seen, fit=fit.label(model, job.title, text),
                                 key=f"{company['id']}:{job.id}"))
        db.save_jobs([_row(company, job, emailed=True, repost=repost, description=text[:fit.TEXT_CHARS], score=score)])
        sent += 1
    return sent, len(jobs), fingerprint


def _detail(company, job):
    # a posting that can't be read is sent with its link instead of dropped
    for _ in range(2):
        try:
            return fetchers.fetch_detail(company, job)
        except Exception:
            pass
    return ""


def _quietly(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except Exception:
        return None


def _one(c, f, before, model=None):
    """Returns (emails sent, failed, health row, down alert)."""
    row = {"company_id": c["id"], "last_success_at": before.get("last_success_at"),
           "last_job_count": before.get("last_job_count"), "last_error": before.get("last_error"),
           "ids_hash": before.get("ids_hash")}
    try:
        n, count, fingerprint = check(c, f, before, model)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"[:1000]
        last_ok = before.get("last_success_at")
        # short blips like rate limits are normal, only report boards down for over an hour
        down_long = not last_ok or datetime.fromisoformat(last_ok) < datetime.now(timezone.utc) - timedelta(hours=1)
        notified = (before.get("last_error") or "").startswith("notified: ")
        alert = (f"{c['name']} fetch failed", f"Not working for over an hour.\n\n{error}", c["platform"]) if down_long and not notified else None
        if down_long or notified:
            error = "notified: " + error
        return 0, 1, {**row, "last_error": error}, alert
    alert = None
    if count == 0 and (before.get("last_job_count") or 0) > 0:
        alert = (f"{c['name']} returned zero jobs", "The job board returned no jobs. It may be under maintenance, "
                 "have nothing posted right now, or have moved to a new address.", c["platform"])
    return n, 0, {**row, "last_success_at": datetime.now(timezone.utc).isoformat(), "last_job_count": count,
                  "last_error": None, "ids_hash": fingerprint}, alert


def workday_down(now=None):
    # workday's weekly update takes its sites down friday 11 pm to saturday 3 am pacific
    t = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/Los_Angeles"))
    return (t.weekday() == 4 and t.hour >= 23) or (t.weekday() == 5 and t.hour < 3)


def run():
    f = db.filters()
    companies = [c for c in db.companies() if not flt.offshore(c["name"])]
    if workday_down():
        companies = [c for c in companies if c["platform"] != "workday"]
    health = db.all_health()
    model = db.fit_model()
    # companies sit on different job boards, so a few at once is still polite
    took = {}

    def timed(c):
        start = time.monotonic()
        try:
            return _one(c, f, health.get(c["id"]) or {}, model)
        finally:
            took[c["id"]] = (time.monotonic() - start, c["platform"])

    start = time.monotonic()
    with ThreadPoolExecutor(12) as pool:
        results = list(pool.map(timed, companies))
    slowest = ", ".join(f"{p} {s:.0f}s" for s, p in sorted(took.values(), reverse=True)[:10])
    print(f"work {sum(s for s, _ in took.values()):.0f}s over 12 workers, took {time.monotonic() - start:.0f}s, slowest {slowest}")
    _quietly(db.save_health, [r[2] for r in results])
    # an outage spreads, later boards on a site already reported are the same news
    known = Counter(c["platform"] for c in companies
                    if ((health.get(c["id"]) or {}).get("last_error") or "").startswith("notified: "))
    down = [r[3][:2] for r in results if r[3] and known[r[3][2]] <= 3]
    # a whole job site going down is one piece of news, not a hundred
    if len(down) > 3:
        _quietly(mail.send, mail.notice(f"{len(down)} job boards are not responding",
                                        "Down for over an hour or returning no jobs. Often maintenance.\n\n"
                                        + "\n".join(subject for subject, _ in down)))
    else:
        for subject, body in down:
            _quietly(mail.send, mail.notice(subject, body))
    if db.calls:
        print("database requests " + ", ".join(f"{k} {v}" for k, v in db.calls.most_common()))
    sent, failed = sum(r[0] for r in results), sum(r[1] for r in results)
    print(f"checked {len(companies)} companies, {sent} new jobs, {failed} failed")
    return len(companies), sent


def _agreed(rows):
    rows = [r for r in rows if r.get("fit") is not None]
    return sum((r["fit"] >= 0.5) == (r["label"] > 0) for r in rows), len(rows)


def learn():
    """Saves today's stars and deletes as lessons, retrains on every lesson, and says how often the score agreed."""
    reacted = mail.reactions()
    jobs = db.emailed(list(reacted))
    before = {f"{r['company_id']}:{r['external_job_id']}": r["label"] for r in db.lessons()}
    new = [{"company_id": row["company_id"], "external_job_id": row["external_job_id"], "title": row["title"],
            "description": row["description"], "label": label, "source": "star" if label > 0 else "trash", "fit": row["fit"]}
           for key, label in reacted.items() if (row := jobs.get(key)) and before.get(key) != label]
    db.save_lessons(new)
    every = db.lessons()
    model = fit.train([(r["title"] or "", r["description"] or "", r["label"]) for r in every])
    a, n = _agreed(new)
    a50, n50 = _agreed([r for r in every if r.get("fit") is not None][-50:])
    line = (f"Fit agreed with you on {a} of {n} reactions today, {a50} of {n50} over the last 50."
            + ("" if model else f" Still learning: needs {fit.MIN_EACH} starred and {fit.MIN_EACH} deleted jobs."))
    db.save_model(model, line)
    return line


def heartbeat():
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    companies = len(db.companies())
    seen = db.count("seen_jobs", first_seen_at=f"gte.{since}")
    emailed = db.count("seen_jobs", first_seen_at=f"gte.{since}", emailed="eq.true")
    bad = db.failing()
    try:
        fit_line = learn()
    except Exception as e:
        # gmail or training trouble must not stop the daily summary
        fit_line = f"Fit model not updated today ({type(e).__name__})."
    f = db.filters()
    old = _quietly(db.prune, lambda title: flt.title_ok(title, f) or flt.title_maybe(title, f)) or 0
    gone = _quietly(db.prune_blocked) or 0
    body = (f"Watching {companies} companies.\nLast 24 hours: {seen} new postings seen, {emailed} emailed to you.\n"
            + ("\nFailing boards:\n" + "\n".join(bad) if bad else "\nAll job boards working.") + f"\n\n{fit_line}"
            + f"\nCleanup: {old} unrelated postings over 14 days old and {gone} from blocked companies deleted.")
    mail.send(mail.notice(f"Lookout daily: {emailed} sent, {len(bad)} failing", body))


AUDIT_JDS = 10
AUDIT_BLOCK = 4


def _audit_one(c, f):
    """Returns (descriptions read, the dealbreaker lines found) for the company's newest matching jobs."""
    # student programs carry their own sponsorship line, it says nothing about full-time roles
    jobs = [j for j in fetchers.fetch_list(c, NEWEST)
            if (flt.title_ok(j.title, f) or flt.title_maybe(j.title, f)) and flt.location_ok(j.location, f)
            and not re.search(r"\bintern(s|ship)?\b|co-?op\b|summer analyst", j.title, re.I)]
    # one job posted in five cities is still one job
    titles = set()
    jobs = [j for j in jobs if not (j.title.strip().lower() in titles or titles.add(j.title.strip().lower()))]
    read, hits = 0, []
    for job in jobs:
        if read == AUDIT_JDS:
            break
        text = flt.html_to_text(fetchers.fetch_detail(c, job))
        # only us jobs count, some boards list no location so the description has to say
        # the posting page can fill in a place the list left as "2 Locations"
        if (not (flt.title_ok(job.title, f) or flt.skills_ok(text)) or not flt.location_ok(job.location, f)
                or flt.abroad(job.location, text, f)):
            continue
        read += 1
        hits += flt.dealbreakers(text, f)[:1]
    return read, hits


def audit():
    # companies change their wording, so recheck every company's newest descriptions each week
    f = db.filters()
    # vc boards mix many startups, each job is already checked on its own
    companies = [c for c in db.companies() if c["platform"] not in ("consider", "getro")]

    def safe(c):
        try:
            return _audit_one(c, f)
        except Exception:
            return 0, []
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(safe, companies))
    paused, close = [], []
    day = datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")
    for c, (read, hits) in zip(companies, results):
        # 4 of 10 can be one internship program's wording, so most of them have to say it
        if len(hits) >= AUDIT_BLOCK and len(hits) * 2 > read:
            db.pause(c["id"], f"blocked: no sponsorship {len(hits)}/{read} (weekly check {day})")
            paused.append(f"{c['name']}: {len(hits)} of {read}, e.g. {hits[0][:110]}")
        elif hits:
            close.append(f"{c['name']}: {len(hits)} of {read}")
    body = (f"Checked the newest descriptions at {len(companies)} companies.\n\n"
            + ("Paused, 4 or more say no sponsorship or citizenship:\n" + "\n".join(paused) if paused else "Nothing paused.")
            + ("\n\nClose, still tracked:\n" + "\n".join(close) if close else ""))
    mail.send(mail.notice(f"Lookout weekly: {len(paused)} paused", body))


if __name__ == "__main__":
    load_env()
    try:
        audit() if "--audit" in sys.argv else heartbeat() if "--heartbeat" in sys.argv else run()
    except Exception as e:
        # never print details, the logs are public
        print(f"run failed: {type(e).__name__}")
        _quietly(mail.send, mail.notice("tracker failed", traceback.format_exc()))
        sys.exit(1)
