import mail
from fetchers import Job


def test_job_email(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "me@example.com")
    monkeypatch.setenv("ALERT_TO", "me@example.com")
    job = Job("1", "Data Analyst", "Houston, TX", "https://x/1")
    msg = mail.job_email("Acme", job, "<p>Pay $70,000 - $85,000</p>Line one&amp;#xa;&#xa;Line two",
                         ["possible repost"], "Nov 02, 08:25 AM CT")
    assert msg["Subject"] == "New role at Acme: Data Analyst, Houston, TX"
    plain = msg.get_body(("plain",)).get_content()
    rich = msg.get_body(("html",)).get_content()
    assert "#xa" not in plain and "#xa" not in rich
    assert "Line one" in plain and "Line two" in plain
    assert "$70,000 - $85,000" in plain
    assert "href='https://x/1'" in rich and "possible repost" in rich


def test_email_has_fit_row_and_job_header(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "a@b.c")
    monkeypatch.setenv("ALERT_TO", "a@b.c")
    job = Job("1", "Data Analyst", "Houston, TX", "https://x/1")
    msg = mail.job_email("Acme", job, "<p>SQL</p>", [], "Nov 06", fit="82% (learned from 60 reactions)", key="7:abc")
    assert msg["X-Lookout-Job"] == "7:abc"
    page = msg.get_body(("html",)).get_content()
    assert "Fit" in page and "82%" in page
