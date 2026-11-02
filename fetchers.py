import html
import json
import re
import time
from dataclasses import dataclass, field

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


@dataclass
class Job:
    id: str
    title: str
    location: str
    url: str
    raw: dict = field(default_factory=dict, repr=False)


def http(method, url, **kw):
    headers = {"User-Agent": UA, "Accept": "application/json", **kw.pop("headers", {})}
    for attempt in (1, 2):
        try:
            r = requests.request(method, url, headers=headers, timeout=20, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if attempt == 2:
                raise
            wait = 3
            if getattr(e.response, "status_code", None) == 429:
                # rate limited, wait as long as the site asks, within reason
                retry_after = e.response.headers.get("Retry-After", "")
                wait = min(int(retry_after), 20) if retry_after.isdigit() else 15
            time.sleep(wait)


def _greenhouse_list(c):
    data = http("GET", f"https://boards-api.greenhouse.io/v1/boards/{c['board']}/jobs").json()
    return [Job(str(j["id"]), j["title"], (j.get("location") or {}).get("name", ""), j["absolute_url"], j)
            for j in data["jobs"]]


def _greenhouse_detail(c, job):
    data = http("GET", f"https://boards-api.greenhouse.io/v1/boards/{c['board']}/jobs/{job.id}").json()
    return html.unescape(data.get("content") or "")


def _lever_list(c):
    data = http("GET", f"https://api.lever.co/v0/postings/{c['board']}?mode=json").json()
    return [Job(j["id"], j["text"], (j.get("categories") or {}).get("location") or "", j["hostedUrl"], j)
            for j in data]


def _lever_detail(c, job):
    j = job.raw
    parts = [j.get("description") or ""]
    for section in j.get("lists") or []:
        parts.append(f"<h3>{section.get('text', '')}</h3><ul>{section.get('content', '')}</ul>")
    parts.append(j.get("additional") or "")
    return "".join(parts)


def _ashby_list(c):
    data = http("GET", f"https://api.ashbyhq.com/posting-api/job-board/{c['board']}?includeCompensation=true").json()
    return [Job(j["id"], j["title"], j.get("location") or "", j["jobUrl"], j) for j in data["jobs"]]


def _ashby_detail(c, job):
    return job.raw.get("descriptionHtml") or ""


def _terms(c):
    o = c.get("overrides") or {}
    return o.get("search_texts") or [o.get("search_text", "")]


def _workday_base(c):
    host, tenant = c["board"].split("/", 1)
    return host, f"https://{host}/wday/cxs/{tenant}/{c['site']}"


def _workday_list(c):
    host, base = _workday_base(c)
    o = c.get("overrides") or {}
    jobs = {}
    # huge boards get searched on workday's side, one term at a time
    for term in _terms(c):
        offset, total = 0, 0
        while True:
            data = http("POST", f"{base}/jobs", json={
                "appliedFacets": o.get("workday_facets", {}), "limit": 20, "offset": offset,
                "searchText": term}).json()
            posts = data.get("jobPostings") or []
            # workday only reports total on the first page
            total = data.get("total") or total
            # workday sometimes sends blank placeholder postings
            for p in posts:
                if p.get("externalPath"):
                    jobs[p["externalPath"]] = Job(p["externalPath"], p.get("title", ""), p.get("locationsText", ""),
                                                  f"https://{host}/{c['site']}{p['externalPath']}", p)
            offset += 20
            if not posts or offset >= total:
                break
    return list(jobs.values())


def _workday_detail(c, job):
    _, base = _workday_base(c)
    data = http("GET", f"{base}{job.id}").json()
    return (data.get("jobPostingInfo") or {}).get("jobDescription") or ""


UKG_SEARCH = {
    "opportunitySearch": {
        "Top": 50, "Skip": 0, "QueryString": "",
        "OrderBy": [{"Value": "postedDateDesc", "PropertyName": "PostedDate", "Ascending": False}],
        "Filters": [{"t": "TermsSearchFilterDto", "fieldName": n, "extra": None, "values": []} for n in (4, 5, 6)],
    },
    "matchCriteria": {"PreferredJobs": [], "Educations": [], "LicenseAndCertifications": [], "Skills": [],
                      "hasNoLicenses": False, "SkippedSkills": []},
}


def _ukg_location(o):
    places = []
    for loc in o.get("Locations") or []:
        a = loc.get("Address") or {}
        country = a.get("Country") or {}
        parts = [a.get("City"), (a.get("State") or {}).get("Code"),
                 country.get("Name") if isinstance(country, dict) else country]
        places.append(", ".join(p for p in parts if p) or loc.get("LocalizedDescription") or "")
    return "; ".join(places)


def _ukg_list(c):
    base = "https://" + c["board"].strip("/")
    jobs = {}
    for term in _terms(c):
        skip = 0
        while True:
            body = {**UKG_SEARCH, "opportunitySearch": {**UKG_SEARCH["opportunitySearch"], "Skip": skip,
                                                        "QueryString": term}}
            data = http("POST", f"{base}/JobBoardView/LoadSearchResults", json=body).json()
            ops = data.get("opportunities") or []
            for o in ops:
                jobs[o["Id"]] = Job(o["Id"], o["Title"], _ukg_location(o),
                                    f"{base}/OpportunityDetail?opportunityId={o['Id']}", o)
            skip += 50
            if not ops or skip >= data.get("totalCount", 0):
                break
    return list(jobs.values())


def _ukg_detail(c, job):
    page = http("GET", job.url, headers={"Accept": "text/html"}).text
    m = re.search(r'"Description":("(?:[^"\\]|\\.)*")', page)
    return json.loads(m.group(1)) if m else ""


def _workable_list(c):
    url = f"https://apply.workable.com/api/v3/accounts/{c['board']}/jobs"
    body = {"query": "", "location": [], "department": [], "worktype": [], "remote": []}
    jobs = []
    for _ in range(50):
        data = http("POST", url, json=body).json()
        for j in data.get("results") or []:
            loc = j.get("location") or {}
            where = ", ".join(p for p in (loc.get("city"), loc.get("region"), loc.get("country")) if p)
            jobs.append(Job(j["shortcode"], j["title"], where,
                            f"https://apply.workable.com/{c['board']}/j/{j['shortcode']}/", j))
        if not data.get("nextPage"):
            break
        body = {**body, "token": data["nextPage"]}
    return jobs


def _workable_detail(c, job):
    data = http("GET", f"https://apply.workable.com/api/v2/accounts/{c['board']}/jobs/{job.id}").json()
    return "".join(data.get(k) or "" for k in ("description", "requirements", "benefits"))


def _oracle_base(c):
    host, site = c["board"].split("/", 1)
    return host, site, f"https://{host}/hcmRestApi/resources/latest"


def _oracle_list(c):
    host, site, api = _oracle_base(c)
    jobs = {}
    for term in _terms(c):
        keyword = f',keyword="{term}"' if term else ""
        offset = 0
        while True:
            data = http("GET", f"{api}/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations"
                               f"&finder=findReqs;siteNumber={site}{keyword},limit=25,offset={offset},"
                               f"sortBy=POSTING_DATES_DESC").json()
            item = (data.get("items") or [{}])[0]
            reqs = item.get("requisitionList") or []
            for r in reqs:
                places = [r.get("PrimaryLocation")] + [s.get("Name") for s in r.get("secondaryLocations") or []]
                jobs[str(r["Id"])] = Job(str(r["Id"]), r["Title"], "; ".join(p for p in places if p),
                                         f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{r['Id']}", r)
            offset += 25
            if not reqs or offset >= (item.get("TotalJobsCount") or 0):
                break
    return list(jobs.values())


def _oracle_detail(c, job):
    _, site, api = _oracle_base(c)
    data = http("GET", f'{api}/recruitingCEJobRequisitionDetails?expand=all&onlyData=true'
                       f'&finder=ById;Id="{job.id}",siteNumber={site}').json()
    d = (data.get("items") or [{}])[0]
    return "".join(d.get(k) or "" for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr",
                                            "ExternalQualificationsStr"))


def _smartrecruiters_list(c):
    api = f"https://api.smartrecruiters.com/v1/companies/{c['board']}/postings"
    jobs, offset = [], 0
    while True:
        data = http("GET", f"{api}?limit=100&offset={offset}").json()
        posts = data.get("content") or []
        jobs += [Job(p["id"], p["name"], (p.get("location") or {}).get("fullLocation", ""),
                     f"https://jobs.smartrecruiters.com/{c['board']}/{p['id']}", p) for p in posts]
        offset += 100
        if not posts or offset >= data.get("totalFound", 0):
            return jobs


def _smartrecruiters_detail(c, job):
    data = http("GET", f"https://api.smartrecruiters.com/v1/companies/{c['board']}/postings/{job.id}").json()
    sections = (data.get("jobAd") or {}).get("sections") or {}
    return "".join((sections.get(k) or {}).get("text") or ""
                   for k in ("jobDescription", "qualifications", "additionalInformation"))


LIST = {"greenhouse": _greenhouse_list, "lever": _lever_list, "ashby": _ashby_list, "workday": _workday_list,
        "ukg": _ukg_list, "workable": _workable_list, "oracle": _oracle_list, "smartrecruiters": _smartrecruiters_list}
DETAIL = {"greenhouse": _greenhouse_detail, "lever": _lever_detail, "ashby": _ashby_detail, "workday": _workday_detail,
          "ukg": _ukg_detail, "workable": _workable_detail, "oracle": _oracle_detail,
          "smartrecruiters": _smartrecruiters_detail}


def fetch_list(company):
    return LIST[company["platform"]](company)


def fetch_detail(company, job):
    return DETAIL[company["platform"]](company, job)
