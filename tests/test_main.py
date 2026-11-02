import pytest

import main
from fetchers import Job

F = {"title_include": ["analyst"], "title_exclude": ["senior"], "dealbreakers": ["no sponsorship"],
     "locations_allowed": ["TX"], "locations_blocked": ["India"]}


@pytest.fixture
def world(monkeypatch):
    w = {"jobs": [], "jd": {}, "saved": [], "sent": [], "health": {}, "marked": [], "fail": set(), "send_fails": False}

    def fetch_list(c, newest=None):
        if c["id"] in w["fail"]:
            raise RuntimeError("boom https://secret.example/jobs")
        return w["jobs"]

    def send(msg):
        if w["send_fails"]:
            raise OSError("smtp down")
        w["sent"].append(msg["Subject"])

    monkeypatch.setattr(main.fetchers, "fetch_list", fetch_list)
    monkeypatch.setattr(main.fetchers, "fetch_detail", lambda c, j: w["jd"].get(j.id, "<p>Great job</p>"))
    monkeypatch.setattr(main.db, "save_jobs", lambda rows: w["saved"].extend(rows))
    monkeypatch.setattr(main.db, "seen_ids", lambda cid, ids: {r["external_job_id"] for r in w["saved"]} & set(ids))
    monkeypatch.setattr(main.db, "mark_first_run", lambda cid: w["marked"].append(cid))
    monkeypatch.setattr(main.db, "is_repost", lambda cid, t, loc: any(
        r["title"] == t and r["location"] == loc for r in w["saved"]))
    monkeypatch.setattr(main.db, "health", lambda cid: w["health"].get(cid))
    monkeypatch.setattr(main.db, "set_health", lambda cid, **kw: w["health"].setdefault(cid, {}).update(kw))
    monkeypatch.setattr(main.db, "filters", lambda: F)
    monkeypatch.setattr(main.mail, "send", send)
    monkeypatch.setenv("GMAIL_USER", "me@example.com")
    monkeypatch.setenv("ALERT_TO", "me@example.com")
    return w


def company(cid=1, first_run_done=True):
    return {"id": cid, "name": "Acme", "platform": "greenhouse", "first_run_done": first_run_done, "overrides": {}}


def job(i, title="Data Analyst", loc="Houston, TX"):
    return Job(str(i), title, loc, f"https://x/{i}")


def test_first_run_saves_all_and_sends_nothing(world):
    world["jobs"] = [job(1), job(2, "Welder")]
    assert main.check(company(first_run_done=False), F) == (0, 2)
    assert len(world["saved"]) == 2 and world["sent"] == [] and world["marked"] == [1]


def test_new_matching_job_is_emailed_once(world):
    world["jobs"] = [job(1)]
    assert main.check(company(), F)[0] == 1
    assert world["sent"] == ["New role at Acme: Data Analyst, Houston, TX"]
    assert main.check(company(), F)[0] == 0


def test_rejected_jobs_are_saved_not_emailed(world):
    world["jobs"] = [job(1), job(2), job(3, "Welder"), job(4, loc="Pune, India")]
    world["jd"] = {"1": "<p>4+ years of experience</p>", "2": "<p>No sponsorship available</p>"}
    assert main.check(company(), F) == (0, 4)
    assert {r["external_job_id"] for r in world["saved"]} == {"1", "2", "3", "4"}
    assert not any(r["emailed"] for r in world["saved"])


def test_experience_cutoff(world):
    world["jobs"] = [job(1), job(2), job(3)]
    world["jd"] = {"1": "<p>3-6 years of experience</p>", "2": "<p>1-3 years of experience with SQL</p>",
                   "3": "<p>2+ years of experience</p>"}
    assert main.check(company(), F)[0] == 2


def test_failed_send_is_retried_next_run(world):
    world["jobs"] = [job(1)]
    world["send_fails"] = True
    with pytest.raises(OSError):
        main.check(company(), F)
    assert world["saved"] == []
    world["send_fails"] = False
    assert main.check(company(), F)[0] == 1


def test_repost_flagged(world):
    world["saved"].append({"company_id": 1, "external_job_id": "old", "title": "Data Analyst",
                           "location": "Houston, TX", "emailed": True})
    world["jobs"] = [job(9)]
    main.check(company(), F)
    assert world["saved"][-1]["possible_repost"] is True


def test_one_failing_company_does_not_stop_others(world, monkeypatch, capsys):
    monkeypatch.setattr(main.db, "companies", lambda: [company(1), company(2)])
    world["fail"] = {1}
    world["jobs"] = [job(1)]
    assert main.run() == (2, 1)
    assert sorted(world["sent"]) == ["Acme fetch failed", "New role at Acme: Data Analyst, Houston, TX"]
    out = capsys.readouterr().out
    assert out.strip() == "checked 2 companies, 1 new jobs, 1 failed"


def test_failure_alert_only_once_and_recovery_clears(world, monkeypatch):
    monkeypatch.setattr(main.db, "companies", lambda: [company(1)])
    world["fail"] = {1}
    main.run()
    main.run()
    assert world["sent"].count("Acme fetch failed") == 1
    world["fail"] = set()
    main.run()
    assert world["health"][1]["last_error"] is None


def test_short_blip_sends_no_email(world, monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(main.db, "companies", lambda: [company(1)])
    world["health"][1] = {"last_success_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()}
    world["fail"] = {1}
    main.run()
    assert world["sent"] == []
    world["health"][1]["last_success_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    main.run()
    main.run()
    assert world["sent"] == ["Acme fetch failed"]


def test_zero_jobs_warns_once(world, monkeypatch):
    monkeypatch.setattr(main.db, "companies", lambda: [company(1)])
    world["health"][1] = {"last_job_count": 10}
    main.run()
    main.run()
    assert world["sent"] == ["Acme returned zero jobs, check it"]


def test_crash_prints_no_details(world, monkeypatch, capsys):
    monkeypatch.setattr(main.db, "filters", lambda: (_ for _ in ()).throw(RuntimeError("https://secret.example")))
    monkeypatch.setattr(main, "load_env", lambda: None)
    import runpy
    with pytest.raises(SystemExit):
        runpy.run_module("main", run_name="__main__")
    out = capsys.readouterr().out
    assert "secret" not in out


def test_portfolio_email_names_startup(world):
    world["jobs"] = [Job("1", "Data Analyst", "Austin, TX", "https://x/1", {}, "Startup Co")]
    world["jd"] = {"1": ""}
    c = {**company(), "name": "Accel portfolio"}
    assert main.check(c, F)[0] == 1
    assert world["sent"] == ["New role at Startup Co (via Accel portfolio): Data Analyst, Austin, TX"]
