import os

from fetchers import http


def _headers(prefer=None):
    key = os.environ["SUPABASE_KEY"]
    # supabase rejects secret keys sent with a browser user agent
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "lookout"}
    if prefer:
        h["Prefer"] = prefer
    return h


def _url(table):
    return os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/" + table


def companies():
    return http("GET", _url("companies"), headers=_headers(), params={"active": "eq.true", "order": "id"}).json()


def filters():
    return http("GET", _url("filters"), headers=_headers(), params={"id": "eq.1"}).json()[0]


def _quote(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def seen_ids(company_id, ids):
    seen, chunks, cur = set(), [], []
    # look up only these ids, postgrest caps replies at 1000 rows; keep urls short
    for x in ids:
        cur.append(_quote(x))
        if len(cur) >= 500 or sum(len(c) for c in cur) > 4000:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    for chunk in chunks:
        rows = http("GET", _url("seen_jobs"), headers=_headers(), params={
            "select": "external_job_id", "company_id": f"eq.{company_id}",
            "external_job_id": f"in.({','.join(chunk)})"}).json()
        seen |= {r["external_job_id"] for r in rows}
    return seen


def is_repost(company_id, title, location):
    rows = http("GET", _url("seen_jobs"), headers=_headers(), params={
        "select": "id", "company_id": f"eq.{company_id}", "title": f"eq.{title}",
        "location": f"eq.{location}", "limit": "1"}).json()
    return bool(rows)


def save_jobs(rows):
    for i in range(0, len(rows), 500):
        http("POST", _url("seen_jobs"), headers=_headers("resolution=ignore-duplicates,return=minimal"),
             params={"on_conflict": "company_id,external_job_id"}, json=rows[i:i + 500])


def mark_first_run(company_id):
    http("PATCH", _url("companies"), headers=_headers("return=minimal"), params={"id": f"eq.{company_id}"},
         json={"first_run_done": True})


def count(table, **params):
    r = http("GET", _url(table), headers=_headers("count=exact"), params={"select": "*", "limit": "1", **params})
    return int(r.headers.get("Content-Range", "*/0").split("/")[-1])


def failing():
    rows = http("GET", _url("company_health"), headers=_headers(),
                params={"select": "last_error,companies(name)", "last_error": "not.is.null"}).json()
    return [f"{r['companies']['name']}: {r['last_error'][:150]}" for r in rows]


def health(company_id):
    rows = http("GET", _url("company_health"), headers=_headers(), params={"company_id": f"eq.{company_id}"}).json()
    return rows[0] if rows else None


def set_health(company_id, **fields):
    http("POST", _url("company_health"), headers=_headers("resolution=merge-duplicates,return=minimal"),
         json={"company_id": company_id, **fields})
