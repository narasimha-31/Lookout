import review
from fetchers import Job

F = {"title_include": ["data"], "title_exclude": [], "dealbreakers": [], "locations_allowed": ["TX"], "locations_blocked": []}


def test_paused_check_lists_companies_with_data_roles(monkeypatch):
    companies = [{"id": 1, "name": "Quiet"}, {"id": 2, "name": "Hiring"}, {"id": 3, "name": "Down"}]
    boards = {1: [Job("1", "Welder", "Houston, TX", "u1")], 2: [Job("2", "Data Analyst", "Houston, TX", "u2")]}

    def fetch(c, n):
        if c["id"] == 3:
            raise OSError("down")
        return boards[c["id"]]
    sent = []
    monkeypatch.setenv("GMAIL_USER", "a@b.c")
    monkeypatch.setenv("ALERT_TO", "a@b.c")
    monkeypatch.setattr(review.db, "filters", lambda: F)
    monkeypatch.setattr(review.db, "paused", lambda start: companies)
    monkeypatch.setattr(review.fetchers, "fetch_list", fetch)
    monkeypatch.setattr(review.mail, "send", lambda m: sent.append((m["Subject"], m.get_payload())))
    review.paused_check()
    assert sent[0][0] == "Lookout paused check: 1 of 3 have data roles"
    assert "Hiring (1)" in str(sent[0][1]) and "Quiet" not in str(sent[0][1])
