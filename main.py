import os
import sys
import time
import traceback
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import db
import fetchers
import filters as flt
import mail


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


def check(company, f):
    """Returns (emails sent, jobs listed)."""
    f = {**f, **{k: v for k, v in (company.get("overrides") or {}).items() if k in f}}
    jobs = list({j.id: j for j in fetchers.fetch_list(company)}.values())

    if not company["first_run_done"]:
        db.save_jobs([_row(company, j) for j in jobs])
        db.mark_first_run(company["id"])
        return 0, len(jobs)

    seen = db.seen_ids(company["id"], [j.id for j in jobs])
    new = [j for j in jobs if j.id not in seen]
    skipped = [j for j in new if not (flt.title_ok(j.title, f) and flt.location_ok(j.location, f))]
    if skipped:
        db.save_jobs([_row(company, j) for j in skipped])

    sent = 0
    for job in (j for j in new if j not in skipped):
        jd = fetchers.fetch_detail(company, job)
        text = flt.html_to_text(jd)
        years = flt.min_years(text)
        if flt.dealbreakers(text, f) or flt.student_only(job.title, text) or (years is not None and years > 3):
            db.save_jobs([_row(company, job)])
            continue
        repost = db.is_repost(company["id"], job.title, job.location)
        flags = [f"asks for {years} years" if years is not None else "no experience mentioned"]
        if repost:
            flags.append("possible repost")
        first_seen = datetime.now(ZoneInfo("America/Chicago")).strftime("%b %d, %I:%M %p CT")
        # send before saving so a failed send is retried next run
        mail.send(mail.job_email(company["name"], job, jd, flags, first_seen))
        db.save_jobs([_row(company, job, emailed=True, repost=repost)])
        sent += 1
    return sent, len(jobs)


def _quietly(fn, *args, **kw):
    try:
        fn(*args, **kw)
    except Exception:
        pass


def run():
    f = db.filters()
    companies = db.companies()
    sent = failed = 0
    for i, c in enumerate(companies):
        if i:
            time.sleep(2)
        before = _health(c["id"])
        try:
            n, count = check(c, f)
        except Exception as e:
            failed += 1
            error = f"{type(e).__name__}: {e}"[:1000]
            if not before.get("last_error"):
                _quietly(mail.send, mail.notice(f"{c['name']} fetch failed", error))
            _quietly(db.set_health, c["id"], last_error=error)
            continue
        sent += n
        if count == 0 and (before.get("last_job_count") or 0) > 0:
            _quietly(mail.send, mail.notice(f"{c['name']} returned zero jobs, check it",
                                            "The job board returned no jobs. It may have moved to a new address."))
        _quietly(db.set_health, c["id"], last_success_at=datetime.now(timezone.utc).isoformat(),
                 last_job_count=count, last_error=None)
    print(f"checked {len(companies)} companies, {sent} new jobs, {failed} failed")
    return len(companies), sent


def _health(company_id):
    try:
        return db.health(company_id) or {}
    except Exception:
        return {}


if __name__ == "__main__":
    load_env()
    try:
        run()
    except Exception as e:
        # never print details, the logs are public
        print(f"run failed: {type(e).__name__}")
        _quietly(mail.send, mail.notice("tracker failed", traceback.format_exc()))
        sys.exit(1)
