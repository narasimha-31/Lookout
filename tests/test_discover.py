import discover
from fetchers import Job


class R:
    def __init__(self, text):
        self.text = text


def test_names_from_funding_news_and_launches(monkeypatch):
    tc = ("<rss><item><title>Viral AI startup Instinct has raised $350M at a $2.5B valuation</title></item>"
          "<item><title>Airbnb-backed WeRoad raises $58M</title></item><item><title>Convective Capital closes $100M fund</title></item>"
          "<item><title>Sequoia hits rewind</title></item></rss>")
    ph = "<feed><entry><title>Floot Payments</title></entry></feed>"
    monkeypatch.setattr(discover.fetchers, "http", lambda m, url, **kw: R(ph if "producthunt" in url else tc))
    assert discover.names() == ["Instinct", "WeRoad", "Floot Payments"]


def test_adds_only_new_companies_with_data_roles(monkeypatch):
    added, sent = [], []
    monkeypatch.setenv("GMAIL_USER", "a@b.c")
    monkeypatch.setenv("ALERT_TO", "a@b.c")
    monkeypatch.setattr(discover, "names", lambda: ["Wispr", "Oura", "Known Co"])
    monkeypatch.setattr(discover.db, "known", lambda: {"known co"})
    monkeypatch.setattr(discover.db, "filters", lambda: {"title_include": ["data"], "title_exclude": [], "dealbreakers": [],
                                                         "locations_allowed": ["CA"], "locations_blocked": []})
    boards = {("ashby", "wispr"): [Job("1", "Data Analyst", "San Francisco, CA", "u")],
              ("greenhouse", "oura"): [Job("2", "Nurse", "San Francisco, CA", "u")]}

    def fetch(c, n):
        if (c["platform"], c["board"]) not in boards:
            raise OSError("no board")
        return boards[(c["platform"], c["board"])]
    monkeypatch.setattr(discover.fetchers, "fetch_list", fetch)
    monkeypatch.setattr(discover, "_audit_one", lambda c, f: (1, []))
    monkeypatch.setattr(discover.db, "add_company", lambda row: added.append(row) or True)
    monkeypatch.setattr(discover.mail, "send", lambda m: sent.append(m["Subject"]))
    discover.discover()
    assert [(r["name"], r["platform"], r["active"]) for r in added] == [("Wispr", "ashby", True)]
    assert sent == ["Lookout found 1 new companies"]
