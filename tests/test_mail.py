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


class FakeBox:
    folders = {'"[Gmail]/All Mail"': {b"1": "1:a", b"2": "1:b", b"3": None}, '"[Gmail]/Trash"': {b"9": "1:a"}}

    def __init__(self, host):
        self.folder = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, password):
        pass

    def select(self, folder, readonly=False):
        assert readonly
        self.folder = folder

    def search(self, charset, *query):
        return "OK", [b" ".join(self.folders[self.folder])]

    def fetch(self, i, spec):
        key = self.folders[self.folder][i]
        return "OK", [(b"x", (f"X-Lookout-Job: {key}\r\n\r\n" if key else "\r\n").encode())]


def test_reactions_trash_wins_and_ignores_unkeyed(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "a@b.c")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "x")
    monkeypatch.setattr(mail.imaplib, "IMAP4_SSL", FakeBox)
    assert mail.reactions() == {"1:a": -1, "1:b": 1}


def test_email_highlights_experience_and_tools(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "a@b.c")
    monkeypatch.setenv("ALERT_TO", "a@b.c")
    job = Job("1", "Analyst - Cost", "Houston, TX", "https://x/1")
    jd = "<p class='sql'>2-5 years of relevant job-related experience</p><li>Strong SQL and Power BI skills, Excel</li>"
    rich = mail.job_email("Acme", job, jd, [], "Nov 06").get_body(("html",)).get_content()
    mark = "<mark style='background:#fff3a3'>"
    assert f"{mark}2-5 years</mark>" in rich
    assert f"{mark}SQL</mark>" in rich and f"{mark}Power BI</mark>" in rich and f"{mark}Excel</mark>" in rich
    # tag attributes are left alone
    assert "<p class='sql'>" in rich
    assert "Tools</td><td><b>SQL, Power BI, Excel</b>" in rich


def test_email_without_description_has_no_tools_row(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "a@b.c")
    monkeypatch.setenv("ALERT_TO", "a@b.c")
    job = Job("1", "Data Analyst", "Houston, TX", "https://x/1")
    rich = mail.job_email("Acme", job, "", [], "Nov 06").get_body(("html",)).get_content()
    assert "Tools" not in rich and "<mark" not in rich


def test_plain_text_description_keeps_its_paragraphs(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "a@b.c")
    monkeypatch.setenv("ALERT_TO", "a@b.c")
    job = Job("1", "Ops Analyst", "Pennington, NJ", "https://x/1")
    jd = ("**To proceed, you must be at least 18 years of age.**\n  \n\n  \n**Job Description:**\nHandles tax reporting & more.\n\n"
          "+ Proficient in Excel\n+ 3+ years of experience in reporting\n§ Link (https://x/job\_1)")
    rich = mail.job_email("Acme", job, jd, [], "Nov 06").get_body(("html",)).get_content()
    mark = "<mark style='background:#fff3a3'>"
    assert "<p><b>To proceed, you must be at least 18 years of age.</b></p>" in rich
    assert "<p><b>Job Description:</b><br>Handles tax reporting &amp; more.</p>" in rich
    assert f"• Proficient in {mark}Excel</mark><br>• {mark}3+ years</mark> of experience" in rich
    assert "job_1" in rich


def test_only_experience_years_are_highlighted(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "a@b.c")
    monkeypatch.setenv("ALERT_TO", "a@b.c")
    job = Job("1", "Ops Analyst", "Pennington, NJ", "https://x/1")
    jd = "<p>Must be 18 years of age. We have led the field for 30 years.</p><p>Minimum 2 years experience with SQL.</p>"
    rich = mail.job_email("Acme", job, jd, [], "Nov 06").get_body(("html",)).get_content()
    assert rich.count("<mark") == 2 and ">2 years</mark>" in rich and ">SQL</mark>" in rich
