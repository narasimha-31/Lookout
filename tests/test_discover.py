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


def test_board_from_search_link():
    b = discover.board_from_url
    assert b("https://jobs.ashbyhq.com/ramp/9f1c-2a/application") == ("ashby", "ramp", None)
    assert b("https://job-boards.greenhouse.io/figma/jobs/55") == ("greenhouse", "figma", None)
    assert b("https://boards.greenhouse.io/embed/job_app?for=x") is None
    assert b("https://jobs.lever.co/plaid/abc") == ("lever", "plaid", None)
    assert b("https://acme.wd5.myworkdayjobs.com/en-US/Acme_Careers/job/Houston-TX/Data-Analyst_R1") == (
        "workday", "acme.wd5.myworkdayjobs.com/acme", "Acme_Careers")
    assert b("https://www.linkedin.com/jobs/view/1") is None


def test_role_search_adds_new_boards(monkeypatch):
    added, asked = [], []
    monkeypatch.setenv("BRAVE_KEY", "k")
    monkeypatch.setenv("GMAIL_USER", "a@b.c")
    monkeypatch.setenv("ALERT_TO", "a@b.c")
    links = ["https://jobs.ashbyhq.com/ramp/1", "https://jobs.ashbyhq.com/ramp/2", "https://jobs.lever.co/known/3"]

    class B:
        def json(self):
            return {"web": {"results": [{"url": u} for u in links]}}
    monkeypatch.setattr(discover.fetchers, "http", lambda m, url, **kw: asked.append(kw["params"]["q"]) or B())
    monkeypatch.setattr(discover.time, "sleep", lambda s: None)
    monkeypatch.setattr(discover.db, "known", lambda: {"known"})
    monkeypatch.setattr(discover.db, "filters", lambda: {})
    monkeypatch.setattr(discover, "judge", lambda c, f: (True, "1 data roles"))
    monkeypatch.setattr(discover.db, "add_company", lambda row: added.append(row) or True)
    monkeypatch.setattr(discover.mail, "send", lambda m: None)
    discover.role_search(run=0)
    assert len(asked) == discover.PER_RUN
    assert [(r["name"], r["platform"], r["board"], r["first_run_done"]) for r in added] == [("Ramp", "ashby", "ramp", False)]
