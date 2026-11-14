from datetime import datetime, timezone
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
    monkeypatch.setattr(main.fetchers, "fetch_detail", lambda c, j: w["jd"].get(j.id, "<p>Great job using SQL</p>"))
    monkeypatch.setattr(main.db, "save_jobs", lambda rows: w["saved"].extend(rows))
    monkeypatch.setattr(main.db, "seen_ids", lambda cid, ids: {r["external_job_id"] for r in w["saved"]} & set(ids))
    monkeypatch.setattr(main.db, "mark_first_run", lambda cid: w["marked"].append(cid))
    monkeypatch.setattr(main.db, "is_repost", lambda cid, t, loc: any(
        r["title"] == t and r["location"] == loc for r in w["saved"]))
    monkeypatch.setattr(main.db, "all_health", lambda: {k: dict(v) for k, v in w["health"].items()})
    monkeypatch.setattr(main.db, "save_health", lambda rows: [w["health"].__setitem__(r["company_id"], r) for r in rows])
    monkeypatch.setattr(main.db, "filters", lambda: w.get("filters", F))
    monkeypatch.setattr(main.db, "fit_model", lambda: None)
    monkeypatch.setattr(main.mail, "send", send)
    monkeypatch.setenv("GMAIL_USER", "me@example.com")
    monkeypatch.setenv("ALERT_TO", "me@example.com")
    return w


def company(cid=1, first_run_done=True):
    return {"id": cid, "name": "Acme", "platform": "greenhouse", "first_run_done": first_run_done, "overrides": {}}


def job(i, title="Data Analyst", loc="Houston, TX"):
    return Job(str(i), title, loc, f"https://x/{i}")


def test_emailed_job_saves_description_and_fit(world, monkeypatch):
    monkeypatch.setattr(main.fit, "score", lambda model, title, text: 0.9)
    world["jobs"] = [job(1)]
    assert main.check(company(), F, model={"w": {}, "b": 0, "good": 30, "bad": 30})[0] == 1
    row = [r for r in world["saved"] if r["emailed"]][0]
    assert row["fit"] == 0.9 and "SQL" in row["description"]


def test_broken_model_still_emails(world, monkeypatch):
    monkeypatch.setattr(main.db, "companies", lambda: [company()])
    monkeypatch.setattr(main.db, "fit_model", lambda: None)
    world["jobs"] = [job(1)]
    main.run()
    assert world["sent"] == ["New role at Acme: Data Analyst, Houston, TX"]


def test_first_run_saves_all_and_sends_nothing(world):
    world["jobs"] = [job(1), job(2, "Welder")]
    assert main.check(company(first_run_done=False), F)[:2] == (0, 2)
    assert len(world["saved"]) == 2 and world["sent"] == [] and world["marked"] == [1]


def test_new_matching_job_is_emailed_once(world):
    world["jobs"] = [job(1)]
    assert main.check(company(), F)[0] == 1
    assert world["sent"] == ["New role at Acme: Data Analyst, Houston, TX"]
    assert main.check(company(), F)[0] == 0


def test_rejected_jobs_are_saved_not_emailed(world):
    world["jobs"] = [job(1), job(2), job(3, "Welder"), job(4, loc="Pune, India")]
    world["jd"] = {"1": "<p>4+ years of experience</p>", "2": "<p>No sponsorship available</p>"}
    assert main.check(company(), F)[:2] == (0, 4)
    assert {r["external_job_id"] for r in world["saved"]} == {"1", "2", "3", "4"}
    assert not any(r["emailed"] for r in world["saved"])


def test_experience_cutoff(world):
    world["jobs"] = [job(1), job(2), job(3)]
    world["jd"] = {"1": "<p>4-6 years of experience</p>", "2": "<p>1-3 years of experience with SQL</p>",
                   "3": "<p>2+ years of experience with Tableau</p>"}
    assert main.check(company(), F)[0] == 2


def test_every_role_caps_at_three_years(world):
    world["jobs"] = [job(1, "Data Engineer"), job(2, "Data Engineer II"), job(3, "Data Analyst")]
    world["jd"] = {"1": "<p>3 years of experience with SQL</p>", "2": "<p>2 years of experience with SQL</p>",
                   "3": "<p>3+ years of experience with SQL</p>"}
    assert main.check(company(), F)[0] == 2


def test_senior_titles_cap_at_three_years(world):
    world["jobs"] = [job(1, "Senior Data Analyst"), job(2, "Sr. Analytics Analyst"), job(3, "Senior Data Engineer")]
    world["jd"] = {"1": "<p>4+ years of experience with SQL</p>", "2": "<p>3 years of experience with SQL</p>",
                   "3": "<p>Great team, SQL daily</p>"}
    # no years stated still goes out, the reader may have missed them
    assert main.check(company(), {**F, "title_exclude": []})[0] == 2


def test_data_title_without_data_tools_is_skipped(world):
    world["jobs"] = [job(1), job(2)]
    world["jd"] = {"1": "<p>Track orders and answer calls</p>", "2": ""}
    assert main.check(company(), F)[0] == 1


def test_no_description_sends_any_matching_title(world):
    world["jobs"] = [job(1, "Supply Chain Analyst"), job(2, "Welder")]
    world["jd"] = {"1": "", "2": ""}
    assert main.check(company(), F)[0] == 1


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


def test_unchanged_board_skips_database(world, monkeypatch):
    monkeypatch.setattr(main.db, "companies", lambda: [company(1)])
    world["jobs"] = [job(1)]
    main.run()
    lookups = []
    monkeypatch.setattr(main.db, "seen_ids", lambda cid, ids: lookups.append(cid) or set())
    main.run()
    assert lookups == [] and world["sent"] == ["New role at Acme: Data Analyst, Houston, TX"]
    world["jobs"] = [job(1), job(2, "BI Analyst")]
    main.run()
    assert lookups == [1]


def test_weekly_audit_pauses_companies_that_stopped_sponsoring(world, monkeypatch):
    paused = []
    monkeypatch.setattr(main.db, "pause", lambda cid, note: paused.append((cid, note)))
    vc = {**company(3), "platform": "getro"}
    monkeypatch.setattr(main.db, "companies", lambda: [company(1), company(2), vc])
    world["jobs"] = [job(i, f"Data Analyst {i}") for i in range(1, 7)]
    world["jd"] = {str(i): "<p>No sponsorship for this role.</p>" for i in range(1, 5)}
    main.audit()
    assert [cid for cid, _ in paused] == [1, 2] and "4/6" in paused[0][1]
    assert world["sent"] == ["Lookout weekly: 2 paused"]


def test_weekly_audit_keeps_companies_with_few_hits(world, monkeypatch):
    paused = []
    monkeypatch.setattr(main.db, "pause", lambda cid, note: paused.append(cid))
    monkeypatch.setattr(main.db, "companies", lambda: [company(1)])
    world["jobs"] = [job(i, f"Data Analyst {i}") for i in range(1, 12)]
    world["jd"] = {str(i): "<p>No sponsorship for this role.</p>" for i in range(1, 4)}
    main.audit()
    assert paused == [] and world["sent"] == ["Lookout weekly: 0 paused"]


def test_unreadable_posting_is_sent_with_its_link(world, monkeypatch):
    world["jobs"] = [job(1), job(2)]
    real = main.fetchers.fetch_detail
    tries = []
    def flaky(c, j):
        if j.id == "1":
            tries.append(1)
            raise OSError("404")
        return real(c, j)
    monkeypatch.setattr(main.fetchers, "fetch_detail", flaky)
    assert main.check(company(), F)[0] == 2 and len(tries) == 2


def test_senior_titles_need_a_low_years_ask(world):
    world["jobs"] = [job(1, "Senior Data Analyst"), job(2, "Sr. Data Analyst"), job(3, "Senior Data Analyst II")]
    world["jd"] = {"1": "<p>2-3 years of experience in SQL</p>", "2": "<p>5+ years of experience</p>", "3": "<p>Great team, Python daily</p>"}
    f = {**F, "title_exclude": []}
    assert main.check(company(), f)[0] == 2
    assert world["sent"] == ["New role at Acme: Senior Data Analyst, Houston, TX",
                             "New role at Acme: Senior Data Analyst II, Houston, TX"]


def test_weekly_audit_ignores_jobs_outside_the_us(world, monkeypatch):
    paused = []
    monkeypatch.setattr(main.db, "pause", lambda cid, note: paused.append(cid))
    monkeypatch.setattr(main.db, "companies", lambda: [company(1)])
    world["jobs"] = [job(i, f"Data Analyst {i}", "") for i in range(1, 6)]
    world["jd"] = {str(i): "<p>Based in Bengaluru, India. No sponsorship for this role.</p>" for i in range(1, 6)}
    main.audit()
    assert paused == []


def test_weekly_audit_needs_most_postings_to_say_no(world, monkeypatch):
    paused = []
    monkeypatch.setattr(main.db, "pause", lambda cid, note: paused.append(cid))
    monkeypatch.setattr(main.db, "companies", lambda: [company(1)])
    world["jobs"] = [job(i, f"Data Analyst {i}") for i in range(1, 11)]
    world["jd"] = {str(i): "<p>No sponsorship for this role. SQL daily.</p>" for i in range(1, 6)}
    main.audit()
    assert paused == []


def test_weekly_audit_counts_a_title_once(world, monkeypatch):
    paused = []
    monkeypatch.setattr(main.db, "pause", lambda cid, note: paused.append(cid))
    monkeypatch.setattr(main.db, "companies", lambda: [company(1)])
    world["jobs"] = [job(i, "Risk Analyst") for i in range(1, 5)] + [job(5, "Data Analyst"), job(6, "BI Analyst")]
    world["jd"] = {str(i): "<p>No sponsorship for this role. SQL daily.</p>" for i in range(1, 5)}
    main.audit()
    assert paused == []


def test_weekly_audit_ignores_internships(world, monkeypatch):
    paused = []
    monkeypatch.setattr(main.db, "pause", lambda cid, note: paused.append(cid))
    monkeypatch.setattr(main.db, "companies", lambda: [company(1)])
    titles = ["Data Analyst Intern", "Analyst Internship", "Analyst Co-op", "Summer Analyst Program", "Data Analyst"]
    world["jobs"] = [job(i, t) for i, t in enumerate(titles, 1)]
    world["jd"] = {str(i): "<p>No sponsorship for this role. SQL daily.</p>" for i in range(1, 5)}
    main.audit()
    assert paused == []


def test_weekly_audit_skips_places_the_posting_page_fills_in(world, monkeypatch):
    paused = []
    monkeypatch.setattr(main.db, "pause", lambda cid, note: paused.append(cid))
    monkeypatch.setattr(main.db, "companies", lambda: [company(1)])
    world["jobs"] = [job(i, f"Data Analyst {i}", "2 Locations") for i in range(1, 9)]

    def detail(c, j):
        if int(j.id) > 4:
            j.location = "Taguig, India"
            return "<p>SQL daily.</p>"
        return "<p>No sponsorship for this role.</p>"
    monkeypatch.setattr(main.fetchers, "fetch_detail", detail)
    main.audit()
    assert paused == [1]


def test_learn_saves_lessons_and_reports_agreement(monkeypatch):
    old = ([{"company_id": 2, "external_job_id": str(i), "title": "Data Analyst", "description": "power bi sql dashboards",
             "label": 1, "fit": None} for i in range(25)]
           + [{"company_id": 2, "external_job_id": f"b{i}", "title": "Research Engineer", "description": "phd physics",
               "label": -1, "fit": None} for i in range(25)])
    saved, models = [], []
    monkeypatch.setattr(main.mail, "reactions", lambda: {"1:a": 1, "1:b": -1})
    monkeypatch.setattr(main.db, "emailed", lambda keys: {
        "1:a": {"company_id": 1, "external_job_id": "a", "title": "BI Analyst", "description": "power bi", "fit": 0.9},
        "1:b": {"company_id": 1, "external_job_id": "b", "title": "Consultant", "description": "client lead", "fit": 0.8}})
    monkeypatch.setattr(main.db, "lessons", lambda: old + saved)
    monkeypatch.setattr(main.db, "save_lessons", lambda rows: saved.extend(rows))
    monkeypatch.setattr(main.db, "save_model", lambda model, line: models.append(model))
    line = main.learn()
    assert sorted(r["label"] for r in saved) == [-1, 1] and models[0] is not None
    assert line.startswith("Fit agreed with you on 1 of 2 reactions today")


def test_heartbeat_survives_learn_failure(world, monkeypatch):
    monkeypatch.setattr(main.db, "companies", lambda: [])
    monkeypatch.setattr(main.db, "count", lambda *a, **k: 0)
    monkeypatch.setattr(main.db, "failing", lambda: [])
    monkeypatch.setattr(main.db, "prune", lambda keep: 0)
    bodies = []
    monkeypatch.setattr(main.mail, "send", lambda m: bodies.append(m.get_content()))
    monkeypatch.setattr(main, "learn", lambda: 1 / 0)
    main.heartbeat()
    assert "Fit model not updated today (ZeroDivisionError)." in bodies[0]
    monkeypatch.setattr(main, "learn", lambda: "Fit agreed with you on 3 of 4 reactions today")
    main.heartbeat()
    assert "Fit agreed with you on 3 of 4" in bodies[1]


def test_workday_down_in_its_weekly_window():
    utc = lambda *a: datetime(*a, tzinfo=timezone.utc)
    assert main.workday_down(utc(2026, 11, 7, 7, 10))
    assert main.workday_down(utc(2026, 11, 7, 10, 59))
    assert not main.workday_down(utc(2026, 11, 7, 11, 0))
    assert not main.workday_down(utc(2026, 11, 6, 6, 50))


def test_title_place_counts_when_location_missing(world):
    # suntory lists no location and names germany only in the title
    world["jobs"] = [job(1, "Frankfurt, Germany Working Student Insights & Analytics Frankfurt HE", loc=""),
                     job(2, "Data Analyst - Remote", loc="")]
    world["jd"] = {"1": "<p>Werkstudent Insights & Analytics, Power BI und Excel</p>"}
    assert main.check(company(), {**F, "title_include": ["analy"], "locations_blocked": ["Germany"]})[0] == 1
    assert world["sent"] == ["New role at Acme: Data Analyst - Remote, location not listed"]


def test_wide_titles_need_a_real_data_tool(world):
    world["jobs"] = [job(1, "Inventory Associate"), job(2, "Inventory Associate II"), job(3, "Inventory Associate I")]
    world["jd"] = {"1": "<p>Build reports in SQL and Tableau</p>", "2": "<p>Advanced Excel</p>", "3": ""}
    assert main.check(company(), F)[0] == 1


def test_empty_first_read_is_not_marked_done(world):
    world["jobs"] = []
    assert main.check(company(first_run_done=False), F)[:2] == (0, 0)
    assert world["marked"] == []


def test_paged_boards_read_fewer_jobs(world, monkeypatch):
    asked = []
    monkeypatch.setattr(main.fetchers, "fetch_list", lambda c, newest=None: asked.append((c["platform"], newest)) or [])
    main.check({**company(), "platform": "workday"}, F)
    main.check({**company(), "platform": "greenhouse"}, F)
    main.check({**company(first_run_done=False), "platform": "workday"}, F)
    assert asked == [("workday", 100), ("greenhouse", 200), ("workday", 2000)]


def test_many_boards_down_send_one_email(world, monkeypatch):
    monkeypatch.setattr(main.db, "companies", lambda: [company(i) for i in range(1, 6)])
    world["fail"] = {1, 2, 3, 4, 5}
    main.run()
    main.run()
    assert world["sent"] == ["5 job boards are not responding"]
