import email
import html
import imaplib
import os
import re
import smtplib
from email.message import EmailMessage

from filters import html_to_text, pay


def _one_line(s):
    return " ".join(str(s).split())


def _message(subject, text, html_body=None):
    m = EmailMessage()
    m["Subject"] = _one_line(subject)
    m["From"] = os.environ["GMAIL_USER"]
    m["To"] = os.environ["ALERT_TO"]
    m.set_content(text)
    if html_body:
        m.add_alternative(html_body, subtype="html")
    return m


def job_email(company, job, jd_html, flags, first_seen, fit=None, key=None):
    # some boards send line breaks as escaped "&#xa;" text
    jd_html = re.sub(r"&(?:amp;)?#x[aA];", "<br>", jd_html or "")
    text = html_to_text(jd_html)
    salary = pay(text)
    subject = f"New role at {company}: {job.title}, {job.location or 'location not listed'}"
    rows = [("Company", company), ("Title", job.title), ("Location", job.location or "not listed"),
            ("Pay", salary), ("Fit", fit), ("First seen", first_seen)]
    head = "\n".join(f"{k}: {v}" for k, v in rows if v)
    plain = f"{head}\nApply: {job.url}\nFlags: {', '.join(flags)}\n\n{text}"

    e = html.escape
    table = "".join(f"<tr><td style='color:#666;padding-right:12px'>{k}</td><td><b>{e(str(v))}</b></td></tr>"
                    for k, v in rows if v)
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", jd_html or "")
    rich = (f"<div style='font-family:Arial,sans-serif;max-width:680px'>"
            f"<table>{table}</table>"
            f"<p><a href='{e(job.url)}' style='display:inline-block;background:#1a73e8;color:#fff;padding:12px 28px;"
            f"border-radius:6px;text-decoration:none;font-size:18px'>Apply now</a></p>"
            f"<p style='color:#444'>{e(', '.join(flags))}</p><hr>{body}</div>")
    m = _message(subject, plain, rich)
    if key:
        # lets a star or delete in gmail be matched back to this job
        m["X-Lookout-Job"] = key
    return m


def notice(subject, body):
    return _message(subject, body)


def send(msg):
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
        s.send_message(msg)


def alerts(query, days=14):
    """Html bodies of recent emails matching a Gmail search, e.g. from:tesla.com."""
    import email
    import imaplib
    with imaplib.IMAP4_SSL("imap.gmail.com") as box:
        box.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
        # all mail, so a filter can keep the alerts out of the inbox
        box.select('"[Gmail]/All Mail"', readonly=True)
        _, ids = box.search(None, "X-GM-RAW", f'"{query} newer_than:{days}d"')
        bodies = []
        for i in ids[0].split():
            _, data = box.fetch(i, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    bodies.append(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "ignore"))
        return bodies


def reactions(days=30):
    """Job key to +1 for a starred job email, -1 for one in trash. Read-only."""
    found = {}
    with imaplib.IMAP4_SSL("imap.gmail.com") as box:
        box.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
        # trash goes last so a starred email that was then deleted counts as bad
        for folder, query, label in (('"[Gmail]/All Mail"', f'"is:starred newer_than:{days}d"', 1),
                                     ('"[Gmail]/Trash"', f'"newer_than:{days}d"', -1)):
            box.select(folder, readonly=True)
            _, ids = box.search(None, "X-GM-RAW", query)
            for i in ids[0].split():
                _, data = box.fetch(i, "(BODY.PEEK[HEADER.FIELDS (X-LOOKOUT-JOB)])")
                key = email.message_from_bytes(data[0][1]).get("X-Lookout-Job")
                if key:
                    found[key.strip()] = label
    return found
