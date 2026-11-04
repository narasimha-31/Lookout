import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

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
    day = datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")
    paused, kept = [], []
    for c, n in zip(low, counts):
        if n == 0:
            db.pause(c["id"], f"paused: sponsors other roles ({c['sponsor_mix']}% engineering and data), no data roles posted ({day})")
            paused.append(f"{c['name']}: {c['sponsor_mix']}% engineering and data")
        else:
            kept.append(f"{c['name']}: {'board down, checked next time' if n is None else f'{n} data roles open'}")
    body = (f"Checked {len(low)} companies that put under {LOW_MIX}% of their H-1Bs into engineering and data roles.\n\n"
            + ("Paused, no data roles posted:\n" + "\n".join(paused) if paused else "Nothing paused.")
            + ("\n\nKept:\n" + "\n".join(kept) if kept else ""))
    mail.send(mail.notice(f"Lookout review: {len(paused)} paused", body))
    print(f"checked {len(low)}, paused {len(paused)}")


if __name__ == "__main__":
    load_env()
    review()
