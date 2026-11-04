import review
from fetchers import Job

F = {"title_include": ["data"], "title_exclude": [], "dealbreakers": [], "locations_allowed": ["TX"], "locations_blocked": []}


def test_pauses_only_low_mix_companies_with_no_data_roles(monkeypatch):
    companies = [{"id": 1, "name": "Hospital", "sponsor_mix": 3}, {"id": 2, "name": "Clinic", "sponsor_mix": 5},
                 {"id": 3, "name": "Tech", "sponsor_mix": 80}, {"id": 4, "name": "Down", "sponsor_mix": 0}]
    boards = {1: [Job("1", "Registered Nurse", "Houston, TX", "u")], 2: [Job("2", "Data Analyst", "Houston, TX", "u")]}

    def fetch(c, n):
        if c["id"] == 4:
            raise OSError("down")
        return boards[c["id"]]
    paused, sent = [], []
    monkeypatch.setenv("GMAIL_USER", "a@b.c")
    monkeypatch.setenv("ALERT_TO", "a@b.c")
    monkeypatch.setattr(review.db, "filters", lambda: F)
    monkeypatch.setattr(review.db, "companies", lambda: companies)
    monkeypatch.setattr(review.db, "pause", lambda cid, note: paused.append(cid))
    monkeypatch.setattr(review.fetchers, "fetch_list", fetch)
    monkeypatch.setattr(review.mail, "send", lambda m: sent.append(m["Subject"]))
    review.review()
    assert paused == [1] and sent == ["Lookout review: 1 paused"]
