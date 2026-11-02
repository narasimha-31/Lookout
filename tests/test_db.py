import db


class Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


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
