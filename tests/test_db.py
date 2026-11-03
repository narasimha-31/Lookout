import db


class Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def test_prune_keeps_matching_titles(monkeypatch):
    deleted, pages = [], [[{"id": 1, "title": "Welder"}, {"id": 2, "title": "Data Analyst"}], []]

    def http(method, url, **kw):
        if method == "DELETE":
            deleted.append(kw["params"]["id"])
            return Resp(None)
        return Resp(pages.pop(0))

    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "k")
    monkeypatch.setattr(db, "http", http)
    assert db.prune(lambda t: "Analyst" in t) == 1
    assert deleted == ["in.(1)"]


def test_seen_ids_chunks_and_quotes(monkeypatch):
    calls = []

    def http(method, url, **kw):
        calls.append(kw["params"]["external_job_id"])
        return Resp([{"external_job_id": "a,1"}])

    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "k")
    monkeypatch.setattr(db, "http", http)
    assert db.seen_ids(1, ["a,1"] + [str(i) for i in range(1100)]) == {"a,1"}
    assert len(calls) == 3
    assert calls[0].startswith('in.("a,1",')
    long_ids = ["/job/Austin-TX/" + "x" * 80 + str(i) for i in range(100)]
    calls.clear()
    db.seen_ids(1, long_ids)
    assert len(calls) > 1 and all(len(c) < 5000 for c in calls)


def test_quiet_lists_boards_without_new_jobs(monkeypatch):
    calls = []

    def http(method, url, **kw):
        calls.append((url, kw["params"]))
        return Resp([{"name": "Acme", "last_new": "2026-10-01T05:00:00+00:00"}, {"name": "Blank", "last_new": None}])

    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "k")
    monkeypatch.setattr(db, "http", http)
    assert db.quiet() == ["Acme: last new job 2026-10-01", "Blank: last new job never"]
    assert calls[0][0].endswith("/company_activity")
    assert "last_new.is.null" in calls[0][1]["or"]
