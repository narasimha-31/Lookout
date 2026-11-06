import sys
from concurrent.futures import ThreadPoolExecutor

import db
import fetchers
import filters as flt
import mail
from main import FIRST_CHECK, load_env

# below this share of h-1b filings in engineering and data roles a company mostly sponsors other work
LOW_MIX = 15


def data_roles(c, f):
    jobs = fetchers.fetch_list(c, FIRST_CHECK)
    return [j for j in jobs if flt.title_ok(j.title, f) and flt.location_ok(j.location, f)]


def review():
    f = db.filters()
    low = [c for c in db.companies() if c.get("sponsor_mix") is not None and c["sponsor_mix"] < LOW_MIX]

    def safe(c):
        try:
            return len(data_roles(c, f))
        except Exception:
            # a board that is down is not proof of no data roles
            return None
    with ThreadPoolExecutor(8) as pool:
        counts = list(pool.map(safe, low))
    empty, kept = [], []
    for c, n in zip(low, counts):
        # report only, companies stay checked every run in case a data role opens
        if n == 0:
            empty.append(f"{c['name']}: {c['sponsor_mix']}% engineering and data")
        else:
            kept.append(f"{c['name']}: {'board down, checked next time' if n is None else f'{n} data roles open'}")
    body = (f"Checked {len(low)} companies that put under {LOW_MIX}% of their H-1Bs into engineering and data roles.\n\n"
            + ("No data roles posted right now:\n" + "\n".join(empty) if empty else "All have data roles open.")
            + ("\n\nWith data roles:\n" + "\n".join(kept) if kept else ""))
    mail.send(mail.notice(f"Lookout review: {len(empty)} with no data roles", body))
    print(f"checked {len(low)}, {len(empty)} with no data roles")


def paused_check():
    # paused companies stay off, this only says which ones opened data roles so they can be turned back on by hand
    f = db.filters()
    companies = db.paused("paused: no data roles")

    def safe(c):
        try:
            return data_roles(c, f)
        except Exception:
            return []
    with ThreadPoolExecutor(8) as pool:
        found = [(c, jobs) for c, jobs in zip(companies, pool.map(safe, companies)) if jobs]
    lines = lambda jobs: "\n".join(f"  {j.title} | {j.location or 'location not listed'}\n  {j.url}" for j in jobs[:10])
    body = "\n\n".join(f"{c['name']} ({len(jobs)}):\n{lines(jobs)}" for c, jobs in found)
    mail.send(mail.notice(f"Lookout paused check: {len(found)} of {len(companies)} have data roles",
                          body or "None of the paused companies have data roles open."))
    print(f"checked {len(companies)} paused, {len(found)} with data roles")


if __name__ == "__main__":
    load_env()
    paused_check() if sys.argv[1:] == ["paused"] else review()
