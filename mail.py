import html
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


def job_email(company, job, jd_html, flags, first_seen):
    text = html_to_text(jd_html)
    salary = pay(text)
    subject = f"New role at {company}: {job.title}, {job.location or 'location not listed'}"
    rows = [("Company", company), ("Title", job.title), ("Location", job.location or "not listed"),
            ("Pay", salary), ("First seen", first_seen)]
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
    return _message(subject, plain, rich)


def notice(subject, body):
    return _message(subject, body)


def send(msg):
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
        s.send_message(msg)
