import hashlib
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import db
import fetchers
import filters as flt
import mail

NEWEST = 200
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


def _row(company, job, emailed=False, repost=False):
    return {"company_id": company["id"], "external_job_id": job.id, "title": job.title,
            "location": job.location, "url": job.url, "emailed": emailed, "possible_repost": repost}


def check(company, f, before=None):
    """Returns (emails sent, jobs listed, fingerprint of the job list)."""
    f = {**f, **{k: v for k, v in (company.get("overrides") or {}).items() if k in f}}
    # after the first check only the newest jobs matter
    newest = NEWEST if company["first_run_done"] else FIRST_CHECK
    jobs = list({j.id: j for j in fetchers.fetch_list(company, newest)}.values())
    fingerprint = hashlib.sha1("\n".join(sorted(j.id for j in jobs)).encode()).hexdigest()[:16]

    if not company["first_run_done"]:
        db.save_jobs([_row(company, j) for j in jobs])
        db.mark_first_run(company["id"])
        return 0, len(jobs), fingerprint
    # same list as last time means nothing new, no need to ask the database
    if fingerprint == (before or {}).get("ids_hash"):
        return 0, len(jobs), fingerprint

    seen = db.seen_ids(company["id"], [j.id for j in jobs])
    new = [j for j in jobs if j.id not in seen]
    skipped = [j for j in new if not ((flt.title_ok(j.title, f) or flt.title_maybe(j.title, f))
                                      and flt.location_ok(j.location, f))]
    if skipped:
        db.save_jobs([_row(company, j) for j in skipped])

    sent = 0
    for job in (j for j in new if j not in skipped):
        jd = fetchers.fetch_detail(company, job)
        text = flt.html_to_text(jd)
        years = flt.years_required(text)
        # an analyst title we don't know needs one of the resume skills in the description
        unsure = not flt.title_ok(job.title, f) and not flt.skills_ok(text)
        if (unsure or flt.dealbreakers(text, f) or flt.student_only(job.title, text) or flt.abroad(job.location, text, f)
                or (years is not None and years > 3)):
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
        # send before saving so a failed send is retried next run
        mail.send(mail.job_email(name, job, jd, flags, first_seen))
        db.save_jobs([_row(company, job, emailed=True, repost=repost)])
        sent += 1
    return sent, len(jobs), fingerprint


def _quietly(fn, *args, **kw):
    try:
        fn(*args, **kw)
    except Exception:
        pass


def _one(c, f, before):
    """Returns (emails sent, failed, health row)."""
    row = {"company_id": c["id"], "last_success_at": before.get("last_success_at"),
           "last_job_count": before.get("last_job_count"), "last_error": before.get("last_error"),
           "ids_hash": before.get("ids_hash")}
    try:
        n, count, fingerprint = check(c, f, before)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"[:1000]
        last_ok = before.get("last_success_at")
        # short blips like rate limits are normal, only report boards down for over an hour
        down_long = not last_ok or datetime.fromisoformat(last_ok) < datetime.now(timezone.utc) - timedelta(hours=1)
        notified = (before.get("last_error") or "").startswith("notified: ")
        if down_long and not notified:
            _quietly(mail.send, mail.notice(f"{c['name']} fetch failed", f"Not working for over an hour.\n\n{error}"))
            error = "notified: " + error
        elif notified:
            error = "notified: " + error
        return 0, 1, {**row, "last_error": error}
    if count == 0 and (before.get("last_job_count") or 0) > 0:
        _quietly(mail.send, mail.notice(f"{c['name']} returned zero jobs, check it",
                                        "The job board returned no jobs. It may have moved to a new address."))
    return n, 0, {**row, "last_success_at": datetime.now(timezone.utc).isoformat(), "last_job_count": count,
                  "last_error": None, "ids_hash": fingerprint}


def run():
    f = db.filters()
    companies = db.companies()
    health = db.all_health()
    # companies sit on different job boards, so a few at once is still polite
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda c: _one(c, f, health.get(c["id"]) or {}), companies))
    _quietly(db.save_health, [r[2] for r in results])
    sent, failed = sum(r[0] for r in results), sum(r[1] for r in results)
    print(f"checked {len(companies)} companies, {sent} new jobs, {failed} failed")
    return len(companies), sent


def heartbeat():
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    companies = len(db.companies())
    seen = db.count("seen_jobs", first_seen_at=f"gte.{since}")
    emailed = db.count("seen_jobs", first_seen_at=f"gte.{since}", emailed="eq.true")
    bad = db.failing()
    body = (f"Watching {companies} companies.\nLast 24 hours: {seen} new postings seen, {emailed} emailed to you.\n"
            + ("\nFailing boards:\n" + "\n".join(bad) if bad else "\nAll job boards working."))
    mail.send(mail.notice(f"Lookout daily: {emailed} sent, {len(bad)} failing", body))
    f = db.filters()
    db.prune(lambda title: flt.title_ok(title, f) or flt.title_maybe(title, f))


if __name__ == "__main__":
    load_env()
    try:
        heartbeat() if "--heartbeat" in sys.argv else run()
    except Exception as e:
        # never print details, the logs are public
        print(f"run failed: {type(e).__name__}")
        _quietly(mail.send, mail.notice("tracker failed", traceback.format_exc()))
        sys.exit(1)
