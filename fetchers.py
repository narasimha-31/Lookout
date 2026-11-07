import html
import json
import re
import time
from dataclasses import dataclass, field
from urllib.parse import unquote

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


@dataclass
class Job:
    id: str
    title: str
    location: str
    url: str
    raw: dict = field(default_factory=dict, repr=False)
    # set on vc portfolio boards, where one board lists many startups
    company: str = ""


def http(method, url, **kw):
    headers = {"User-Agent": UA, "Accept": "application/json", **kw.pop("headers", {})}
    for attempt in (1, 2):
        try:
            r = (kw.get("session") or requests).request(method, url, headers=headers, timeout=20,
                                                       **{k: v for k, v in kw.items() if k != "session"})
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


def _cap(c):
    return c.get("newest") or float("inf")


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
    # wd12.myworkdaysite.com boards put the tenant in the job page path
    page = f"recruiting/{c['board'].split('/', 1)[1]}/" if "myworkdaysite" in host else ""
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
                                                  f"https://{host}/{page}{c['site']}{p['externalPath']}", p)
            offset += 20
            if not posts or offset >= total or len(jobs) >= _cap(c):
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
            if not ops or skip >= data.get("totalCount", 0) or len(jobs) >= _cap(c):
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
            if not reqs or offset >= (item.get("TotalJobsCount") or 0) or len(jobs) >= _cap(c):
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
        if not posts or offset >= data.get("totalFound", 0) or len(jobs) >= _cap(c):
            return jobs


def _smartrecruiters_detail(c, job):
    data = http("GET", f"https://api.smartrecruiters.com/v1/companies/{c['board']}/postings/{job.id}").json()
    sections = (data.get("jobAd") or {}).get("sections") or {}
    return "".join((sections.get(k) or {}).get("text") or ""
                   for k in ("jobDescription", "qualifications", "additionalInformation"))


def _from_linkedin(job):
    # vc boards copy some jobs from linkedin, often weeks old and with no real posting behind them
    return "linkedin.com" in (job.url or "")


def _consider_list(c):
    host, board = c["board"].split("/", 1)
    s = requests.Session()
    page = http("GET", f"https://{host}/jobs", session=s, headers={"Accept": "text/html"}).text
    token = re.search(r'csrf[^"]*"\s*:\s*"([^"]+)"', page) or re.search(r'name="csrf-token" content="([^"]+)"', page)
    headers = {"x-csrf-token": token.group(1) if token else "", "Referer": f"https://{host}/jobs"}
    jobs, meta = [], {"size": 100}
    while True:
        data = http("POST", f"https://{host}/api-boards/search-jobs", session=s, headers=headers, json={
            "meta": meta, "board": {"id": board, "isParent": True}, "query": {"locations": ["United States"]},
            "grouped": False}).json()
        posts = data.get("jobs") or []
        jobs += [Job(f"{p.get('companySlug')}:{p['jobId']}", p["title"], "; ".join(x.strip() for x in p.get("locations") or []),
                     p.get("applyUrl") or p.get("url"), p, p.get("companyName", "")) for p in posts]
        seq = (data.get("meta") or {}).get("sequence")
        if not posts or not seq or len(jobs) >= min(_cap(c), data.get("total", 0)):
            return [j for j in jobs if not _from_linkedin(j)]
        meta = {"size": 100, "sequence": seq}


def from_apply_link(url):
    # vc boards link to the startup's own board; read the description there when we can
    try:
        m = re.match(r"https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/]+)(/job/[^?#]+)", url)
        if m:
            c = {"board": f"{m[1]}.{m[2]}.myworkdayjobs.com/{m[1]}", "site": m[3]}
            return _workday_detail(c, Job(m[4], "", "", url))
        m = re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)/jobs/(\d+)", url)
        if m:
            return _greenhouse_detail({"board": m[1]}, Job(m[2], "", "", url))
        m = re.search(r"jobs\.lever\.co/([\w-]+)/([0-9a-f-]{36})", url)
        if m:
            p = http("GET", f"https://api.lever.co/v0/postings/{m[1]}/{m[2]}").json()
            return _lever_detail({}, Job(m[2], "", "", url, p))
        m = re.search(r"jobs\.ashbyhq\.com/([\w.-]+)/([0-9a-f-]{36})", url)
        if m:
            jobs = http("GET", f"https://api.ashbyhq.com/posting-api/job-board/{m[1]}").json().get("jobs") or []
            return next((j.get("descriptionHtml") or "" for j in jobs if j.get("id") == m[2]), "")
    except Exception:
        pass
    return ""


def _consider_detail(c, job):
    # consider has no description; follow the apply link when it is a board we can read
    years = job.raw.get("minYearsExp")
    found = from_apply_link(job.url)
    return found or (f"<p>Minimum {years} years of experience</p>" if years else "")


def _getro_parts(c):
    # board is "jobs.accel.com/8672": the vc's board host and getro's collection id
    host, _, coll = c["board"].rpartition("/")
    return host, coll


def _getro_list(c):
    _, coll = _getro_parts(c)
    jobs, page = [], 0
    while True:
        data = http("POST", f"https://api.getro.com/api/v2/collections/{coll}/search/jobs",
                    json={"hitsPerPage": 100, "page": page, "filters": "", "query": ""}).json()
        res = data.get("results") or {}
        posts = res.get("jobs") or []
        jobs += [Job(str(p["id"]), p["title"], "; ".join(p.get("locations") or []), p["url"], p,
                     (p.get("organization") or {}).get("name", "")) for p in posts]
        page += 1
        if not posts or len(jobs) >= min(_cap(c), res.get("count", 0)):
            # getro tags each job with countries, keep only the ones it places in the US
            return [j for j in jobs if "United States" in (j.raw.get("searchable_locations") or [])
                    and not _from_linkedin(j)]


def _getro_detail(c, job):
    host, _ = _getro_parts(c)
    org = (job.raw.get("organization") or {}).get("slug")
    if not host or not org:
        return ""
    page = http("GET", f"https://{host}/companies/{org}/jobs/{job.raw.get('slug')}", headers={"Accept": "text/html"}).text
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page, re.S)
    if not m:
        return ""
    state = json.loads(m.group(1)).get("props", {}).get("pageProps", {}).get("initialState", {})
    return ((state.get("jobs") or {}).get("currentJob") or {}).get("description") or ""


def _rss_list(c):
    # successfactors career sites publish their newest jobs as rss
    # some sites block /services/ in robots but serve the same feed as sitemap.xml
    url = f"https://{c['board']}" if c["board"].endswith(".xml") else f"https://{c['board']}/services/rss/job/?locale=en_US&keywords="
    feed = http("GET", url, headers={"Accept": "application/rss+xml"}).text
    jobs = []
    for item in re.findall(r"<item>(.*?)</item>", feed, re.S):
        get = lambda tag: (re.search(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", item, re.S) or [None, ""])[1].strip()
        link, heading = html.unescape(get("link")).split("?")[0], html.unescape(get("title"))
        m = re.match(r"(.*?)\s*\(([^()]*)\)\s*$", heading)
        title, where = (m.group(1), m.group(2)) if m else (heading, "")
        # "Toronto, ON, CA" ends in a country code, and CA here is Canada; some add a zip after it
        where = re.sub(r",\s*([A-Z]{2})(,\s*\d[\w -]*)?$", lambda x: "" if x.group(1) == "US" else f" ({x.group(1)})", where)
        jid = (re.search(r"/(\d+)/?$", link) or [None, link])[1]
        jobs.append(Job(jid, title, where, link, {"description": get("description")}))
    return jobs


def _rss_detail(c, job):
    text = job.raw.get("description") or ""
    # some feeds send the html escaped instead of in cdata
    return html.unescape(text) if "&lt;" in text else text


def _jibe_list(c):
    jobs, page = [], 1
    # one portal can hold several companies, each a brand
    brand = (c.get("overrides") or {}).get("jibe_brand")
    while True:
        data = http("GET", f"https://{c['board']}/api/jobs?page={page}&limit=100&sortBy=posted_date"
                           "&descending=true&internal=false", params={"brand": brand} if brand else None).json()
        posts = [p["data"] for p in data.get("jobs") or []]
        jobs += [Job(str(p.get("req_id") or p["slug"]), p["title"], p.get("full_location") or "",
                     f"https://{c['board']}/careers-home/jobs/{p['slug']}", p) for p in posts]
        page += 1
        if not posts or len(jobs) >= min(_cap(c), data.get("totalCount", 0)):
            return jobs


def _jibe_detail(c, job):
    return job.raw.get("description") or ""


def _eightfold_parts(c):
    host, domain = c["board"].split("/", 1)
    return host, domain


def _eightfold_list(c):
    host, domain = _eightfold_parts(c)
    jobs, start = [], 0
    while True:
        data = http("GET", f"https://{host}/api/pcsx/search", params={
            "domain": domain, "query": "", "location": "United States", "start": start, "sort_by": "timestamp"}).json()
        d = data.get("data") or {}
        posts = d.get("positions") or []
        jobs += [Job(str(p["id"]), p["name"], "; ".join(p.get("locations") or []),
                     f"https://{host}{p.get('positionUrl') or '/careers/job/' + str(p['id'])}", p) for p in posts]
        start += len(posts)
        if not posts or len(jobs) >= min(_cap(c), d.get("count", 0)):
            return jobs


def _eightfold_detail(c, job):
    host, domain = _eightfold_parts(c)
    data = http("GET", f"https://{host}/api/pcsx/position_details",
                params={"position_id": job.id, "domain": domain, "hl": "en"}).json()
    return (data.get("data") or {}).get("jobDescription") or ""


def _amazon_list(c):
    jobs, offset = [], 0
    while True:
        data = http("GET", "https://www.amazon.jobs/en/search.json", params={
            "country": "USA", "result_limit": 100, "offset": offset, "sort": "recent"}).json()
        posts = data.get("jobs") or []
        jobs += [Job(str(p.get("id_icims") or p["id"]), p["title"], p.get("normalized_location") or p.get("location") or "",
                     "https://www.amazon.jobs" + p["job_path"], p) for p in posts]
        offset += len(posts)
        if not posts or len(jobs) >= min(_cap(c), data.get("hits", 0)):
            return jobs


def _amazon_detail(c, job):
    return "".join(f"<p>{job.raw.get(k) or ''}</p>" for k in ("description", "basic_qualifications", "preferred_qualifications"))


def _phenom_ddo(url, **kw):
    page = http("GET", url, **kw).text
    return json.loads(re.search(r"phApp\.ddo\s*=\s*(\{.*?\});\s*phApp\.", page, re.S).group(1))


def _phenom_list(c):
    # phenom sites embed the search results in the page, 100 at a time
    jobs = []
    while True:
        # unsorted results put new jobs anywhere, past the newest-200 window
        data = _phenom_ddo(f"https://{c['board']}/search-results",
                           params={"size": 100, "from": len(jobs), "sortBy": "Most recent"})
        found = data.get("eagerLoadRefineSearch") or {}
        posts = (found.get("data") or {}).get("jobs") or []
        jobs += [Job(p["jobSeqNo"], p["title"], "; ".join(p.get("multi_location") or []) or p.get("location") or "",
                     f"https://{c['board']}/job/{p['jobId']}", p) for p in posts]
        if not posts or len(jobs) >= min(_cap(c), found.get("totalHits", 0)):
            return jobs


def _phenom_detail(c, job):
    data = _phenom_ddo(job.url)
    return (((data.get("jobDetail") or {}).get("data") or {}).get("job") or {}).get("description") or ""


def _sfxml_list(c):
    # older successfactors sites list every job as xml, without locations
    host, company = c["board"].split("/", 1)
    feed = http("GET", f"https://{host}/career", params={
        "company": company, "career_ns": "job_listing_summary", "resultType": "XML"}).text
    jobs = []
    for item in re.findall(r"<Job>(.*?)</Job>", feed, re.S):
        get = lambda tag: (re.search(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", item, re.S) or [None, ""])[1].strip()
        rid = get("ReqId")
        jobs.append(Job(rid, html.unescape(get("JobTitle")), "",
                        f"https://{host}/career?company={company}&career_job_req_id={rid}&career_ns=job_listing",
                        {"description": get("Job-Description")}))
    return jobs


def _bamboohr_list(c):
    posts = http("GET", f"https://{c['board']}.bamboohr.com/careers/list").json().get("result") or []
    where = lambda p: ", ".join(x for x in ((p.get("location") or {}).get("city"), (p.get("location") or {}).get("state"),
                                            (p.get("atsLocation") or {}).get("country")) if x)
    return [Job(str(p["id"]), p["jobOpeningName"], where(p), f"https://{c['board']}.bamboohr.com/careers/{p['id']}", p)
            for p in posts]


def _bamboohr_detail(c, job):
    data = http("GET", f"https://{c['board']}.bamboohr.com/careers/{job.id}/detail").json()
    return ((data.get("result") or {}).get("jobOpening") or {}).get("description") or ""


STATE_END = re.compile(r"-(al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|mi|mn|ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|wv|wi|wy|dc)$", re.I)


GUID = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.I)


def _sitemap_list(c):
    # some staffing sites only publish their jobs in a sitemap; the url slug stands in for the title
    index = http("GET", f"https://{c['board']}").text
    maps = [u for u in re.findall(r"<sitemap>\s*<loc>(.*?)</loc>", index) if "job" in u] or [f"https://{c['board']}"]
    urls = []
    for m in maps:
        page = index if m == f"https://{c['board']}" else http("GET", m).text
        urls += re.findall(r"<url>\s*<loc>(.*?)</loc>(?:(?:(?!</url>).)*?<lastmod>(.*?)</lastmod>)?", page, re.S)
    # a group-wide sitemap keeps each company under its own path
    path = (c.get("overrides") or {}).get("sitemap_path", "")
    urls = sorted({u: d for u, d in urls if ("/job/" in u or "/jobdetails/" in u) and path in u}.items(), key=lambda x: x[1], reverse=True)
    jobs = []
    for url, _ in urls[:int(min(_cap(c), len(urls)))]:
        # the title is the last part with letters, ".../job/plymouth/data-analyst/34088/1027..." included,
        # skipping a trailing place like ".../job/pharmacy-tech/sarasota-fl/2528697/"
        parts = [p for p in reversed(url.rstrip("/").split("/")[3:]) if re.search(r"[a-z]", p, re.I) and p.lower() not in ("job", "jobs")]
        parts = [p for p in parts if not GUID.fullmatch(p)] or parts
        slug = next((p for p in parts if not STATE_END.search(p)), parts[0] if parts else "")
        title = html.unescape(unquote(re.sub(r"^\d+-", "", slug)))
        # successfactors slugs end in the state, often with a zip, "HOUSTON-Trading-Analyst-TX-77056"
        place = re.search(r"-([A-Z]{2})(?:-\d{5})?$", title)
        state = place and STATE_END.search("-" + place[1])
        if state:
            title = title[:place.start()]
        elif (c.get("overrides") or {}).get("us_only"):
            continue
        jobs.append(Job(url, title.replace("-", " ").replace("_", " ").strip(), f"{place[1].upper()}, United States" if state else "", url))
    return jobs


def _sitemap_detail(c, job, headers=None, params=None):
    page = http("GET", job.url, headers=headers or {"Accept": "text/html"}, params=params).text
    for block in re.findall(r"<script[^>]*application/ld(?:\+|&#x2B;|&#43;)json[^>]*>(.*?)</script>", page, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in data.get("@graph", [data]) if isinstance(data, dict) else data:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                place = ((item.get("jobLocation") or {}).get("address") or {}) if isinstance(item.get("jobLocation"), dict) else {}
                job.title = html.unescape(html.unescape(item.get("title") or job.title))
                job.location = ", ".join(x for x in (place.get("addressLocality"), place.get("addressRegion")) if x) or job.location
                return html.unescape(item.get("description") or "")
    # successfactors career sites only have it in the page
    found = re.search(r'class="jobdescription"[^>]*>|itemprop="description"[^>]*>', page)
    column = page.find('class="jobColumnOne"')
    if not found and column > 0:
        # newer layouts put the whole posting in the first column
        start = page.find(">", column) + 1
        end = page.find('class="jobColumnTwo"', start)
        return page[start:page.rfind("<", start, end if end > 0 else len(page))]
    if not found:
        return ""
    start = found.end()
    end = min(k for k in (page.find("applylink", start), page.find("<script", start), page.find("<style", start), len(page)) if k > 0)
    return page[start:page.rfind("<", start, end)]


def _icims_detail(c, job):
    # icims turns away browser-looking clients that are not browsers
    return _sitemap_detail(c, job, {"Accept": "text/html", "User-Agent": "lookout"}, {"in_iframe": 1})


def _icims_list(c):
    # classic icims portals render plain html, about 20 jobs a page
    jobs, page = [], 0
    while True:
        text = http("GET", f"https://{c['board']}/jobs/search", params={"ss": 1, "in_iframe": 1, "pr": page},
                    headers={"Accept": "text/html", "User-Agent": "lookout"}).text
        cards = re.findall(r'<li class="iCIMS_JobCardItem">(.*?)</li>', text, re.S)
        for card in cards:
            link = re.search(r'href="(https://[^"]+/jobs/(\d+)/[^"]+/job)', card)
            title = re.search(r"<h3[^>]*>(.*?)</h3>", card, re.S)
            where = re.search(r'Job Locations</span>\s*<span[^>]*>(.*?)</span>', card, re.S)
            if link and title:
                jobs.append(Job(link.group(2), html.unescape(title.group(1).strip()),
                                html.unescape(where.group(1).strip()) if where else "", link.group(1)))
        page += 1
        if not cards or len(jobs) >= _cap(c) or f"pr={page}" not in text:
            return jobs


def _selectminds_detail(c, job):
    page = http("GET", job.url, headers={"Accept": "text/html"}).text
    start = page.find('class="job_description"')
    return page[start:page.find("jBlockRegion", start)] if start >= 0 else ""


def _sfxml_detail(c, job):
    text = job.raw.get("description") or ""
    if "[[" not in text:
        return text
    # the feed keeps template fields like [[salaryMin]], the posting page has them filled in
    page = http("GET", job.url, headers={"Accept": "text/html"}).text
    start = page.find('class="joqReqDescription"')
    if start < 0:
        return text
    start = page.find(">", start) + 1
    end = page.find("navBarLevel", start)
    return page[start:page.rfind("<", start, end if end > 0 else len(page))]


def _paylocity_list(c):
    # board is the guid/name part of recruiting.paylocity.com/recruiting/jobs/All/<guid>/<name>
    page = http("GET", f"https://recruiting.paylocity.com/recruiting/jobs/All/{c['board']}", headers={"Accept": "text/html"}).text
    data = json.loads(re.search(r"window\.pageData\s*=\s*(\{.*?\});\s*\n", page, re.S).group(1))
    where = lambda p: ", ".join(x for x in (p.get("City"), p.get("State"), p.get("Country")) if x)
    posts = sorted(data.get("Jobs") or [], key=lambda p: p.get("PublishedDate") or "", reverse=True)
    return [Job(str(p["JobId"]), p["JobTitle"], where(p.get("JobLocation") or {}) or p.get("LocationName") or "",
                f"https://recruiting.paylocity.com/Recruiting/Jobs/Details/{p['JobId']}", p) for p in posts]


def _taleo_list(c):
    # board is host/career section/portal, e.g. hdr.taleo.net/ex/101430233
    host, section, portal = c["board"].split("/")
    jobs, page = [], 1
    while len(jobs) < _cap(c):
        body = {"multilineEnabled": False, "sortingSelection": {"sortBySelectionParam": "3", "ascendingSortingOrder": "false"},
                "fieldData": {"fields": {"KEYWORD": "", "LOCATION": ""}, "valid": True},
                "filterSelectionParam": {"searchFilterSelections": []},
                "advancedSearchFiltersSelectionParam": {"searchFilterSelections": []}, "pageNo": page}
        data = http("POST", f"https://{host}/careersection/rest/jobboard/searchjobs", params={"lang": "en", "portal": portal},
                    json=body, headers={"tz": "GMT-06:00"}).json()
        posts = data.get("requisitionList") or []
        for p in posts:
            cols = p.get("column") or []
            try:
                where = "; ".join(json.loads(cols[1])) if len(cols) > 1 else ""
            except ValueError:
                where = cols[1]
            jobs.append(Job(p["contestNo"], cols[0] if cols else "", where.replace("-", ", "),
                            f"https://{host}/careersection/{section}/jobdetail.ftl?job={p['contestNo']}&lang=en"))
        if not posts or len(jobs) >= (data.get("pagingData") or {}).get("totalCount", 0):
            return jobs
        page += 1
    return jobs


def _taleo_detail(c, job):
    page = http("GET", job.url, headers={"Accept": "text/html"}).text
    found = re.search(r'id="initialHistory"[^>]*value="([^"]*)"', page)
    if not found:
        return ""
    # the page state is one escaped string of fields, the description is the long html one
    fields = unquote(html.unescape(found[1])).split("!|!")
    return max(fields, key=len).replace("!*!", "").replace("\\:", ":")


NOT_JOBS = re.compile(r"view all|see all|more jobs|unsubscribe|manage|preferences|privacy|apply now|sign in|log in|search jobs|edit alert", re.I)


def _email_list(c):
    # board is a gmail search for the company's job alert emails, e.g. from:tesla.com
    import mail
    jobs = {}
    for body in mail.alerts(c["board"]):
        for href, inner in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, re.S):
            title = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", inner)).split())
            if not 3 <= len(title) <= 120 or NOT_JOBS.search(title) or not re.search(r"job|career|posting|req", href, re.I):
                continue
            # tracking links change per email, the requisition number does not
            num = re.findall(r"\d{5,}", unquote(html.unescape(href)))
            jid = num[-1] if num else title.lower()
            jobs.setdefault(jid, Job(jid, title, "", html.unescape(href)))
    return list(jobs.values())


def _inbox_list(c):
    # tesla blocks automated visits, so a button in the user's own browser sends the list
    import db
    slug = lambda t: re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
    return [Job(str(j["id"]), j["t"], j.get("w") or "", f"https://www.tesla.com/careers/search/job/{slug(j['t'])}-{j['id']}")
            for j in db.inbox(c["id"]) if j.get("id") and j.get("t")]


AVATURE_LINK = re.compile(r'href="([^"]+/(?:Job|Folder)Detail(?:/(?:[^"?]*/)?|\?jobId=)(\d+)(?:[?&][^"]*)?)"[^>]*>\s*(.*?)\s*</a>', re.S)
AVATURE_WHERE = re.compile(r'(?:list-item-location">|subtitle--location">|Location:\s*</div>\s*<div[^>]*>|Location:"[^>]*>\s*<p>)\s*([^<]*)')


def _avature_list(c):
    # board is host plus locale, e.g. insperity.avature.net/en_US, or a full listing path like jobs.enel.com/en_US/careers/JobOpeningsUSA
    url = f"https://{c['board']}" + ("" if c["board"].count("/") > 1 else "/careers/SearchJobs")
    jobs, seen = [], set()
    while len(jobs) < _cap(c):
        page = http("GET", url, params={"jobOffset": len(seen)}, headers={"Accept": "text/html"}).text
        # cards are article or div blocks on newer sites, list items on older ones
        new = 0
        for card in re.split(r'class="article article--result|class="jobResultItem', page)[1:]:
            link = AVATURE_LINK.search(card)
            if not link or link[2] in seen:
                continue
            seen.add(link[2])
            new += 1
            where = AVATURE_WHERE.search(card)
            jobs.append(Job(link[2], html.unescape(link[3]), " ".join(html.unescape(where[1]).split()) if where else "", link[1]))
        if not new:
            return jobs
    return jobs


def _avature_detail(c, job):
    page = http("GET", job.url, headers={"Accept": "text/html"}).text
    start = max(page.find("tf_replaceFieldVideoTokens"), page.find('class="jobDetail'))
    if start < 0:
        # newer sites split the posting into detail sections
        return "".join(re.findall(r'<article class="article article--details.*?</article>', page, re.S))
    start = page.find(">", start) + 1
    ends = [k for k in (page.find('class="article__content"', start), page.find("ApplyFlowCheck", start)) if k > 0]
    return page[start:page.rfind("<", start, min(ends) if ends else len(page))]


def _jazzhr_list(c):
    page = http("GET", f"https://{c['board']}.applytojob.com/apply", headers={"Accept": "text/html"}).text
    jobs = []
    for item in re.findall(r"list-group-item-heading.*?</ul>", page, re.S):
        link = re.search(r'href="([^"]+/apply/(\w+)/[^"]*)">\s*(.*?)\s*</a>', item, re.S)
        where = re.search(r"fa-map-marker'></i>\s*([^<]*)", item)
        if link:
            jobs.append(Job(link[2], html.unescape(link[3]), (where[1].strip() if where else ""), link[1]))
    return jobs


def _recruitee_list(c):
    posts = http("GET", f"https://{c['board']}.recruitee.com/api/offers/").json().get("offers") or []
    posts = sorted(posts, key=lambda p: p.get("published_at") or "", reverse=True)
    return [Job(str(p["id"]), p["title"], p.get("location") or "", p["careers_url"],
                {"description": (p.get("description") or "") + (p.get("requirements") or "")}) for p in posts]



def _wpgh_list(c):
    # board is a wordpress careers page mirroring greenhouse jobs, e.g. arevonenergy.com/careers
    page = http("GET", f"https://{c['board']}/", headers={"Accept": "text/html"}).text
    found = re.findall(r'data-gid="(\d+)">\s*<a href="([^"]+)">\s*<strong class="title">(.*?)</strong>\s*'
                       r'<span class="subtitle">(.*?)</span>', page, re.S)
    return [Job(jid, html.unescape(title.strip()), html.unescape(where.strip()), url) for jid, url, title, where in found]


def _wpgh_detail(c, job):
    page = http("GET", job.url, headers={"Accept": "text/html"}).text
    start = page.find("__content-col__content")
    if start < 0:
        return ""
    start = page.find(">", start) + 1
    end = page.find("__sidebar-col", start)
    return page[start:page.rfind("<", start, end if end > 0 else len(page))]


JOBVITE_ROW = re.compile(r'<td class="jv-job-list-name">\s*<a href="(/[^"]+/job/(\w+))">(.*?)</a>\s*</td>\s*<td class="jv-job-list-location">(.*?)</td>', re.S)


def _jobvite_list(c):
    # one html page lists every job, grouped by department
    page = http("GET", f"https://jobs.jobvite.com/{c['board']}/jobs", headers={"Accept": "text/html"}).text
    clean = lambda s: " ".join(html.unescape(re.sub(r"<[^>]+>", "", s)).split()).replace(" ,", ",")
    return [Job(jid, clean(title), clean(where), f"https://jobs.jobvite.com{path}") for path, jid, title, where in JOBVITE_ROW.findall(page)]


def _rippling_list(c):
    if "." in c["board"]:
        page = http("GET", f"https://{c['board']}/", headers={"Accept": "text/html"}).text
        found = re.findall(r'href="(/job/(\d+)/[^"]+)" aria-label="Link to job discription for ([^"]+)"', page)
        return [Job(jid, html.unescape(title), "", f"https://{c['board']}{path}") for path, jid, title in found]
    posts = http("GET", f"https://api.rippling.com/platform/api/ats/v1/board/{c['board']}/jobs").json()
    return [Job(p["uuid"], p["name"].strip(), (p.get("workLocation") or {}).get("label") or "", p["url"]) for p in posts]


def _rippling_detail(c, job):
    if "." in c["board"]:
        return _sitemap_detail(c, job)
    data = http("GET", f"https://api.rippling.com/platform/api/ats/v1/board/{c['board']}/jobs/{job.id}").json()
    text = data.get("description") or {}
    return (text.get("role") or "") + (text.get("company") or "")


def _pinpoint_list(c):
    posts = http("GET", f"https://{c['board']}/postings.json").json().get("data") or []
    # some cities are just the state code, "CA, California"
    where = lambda p: ", ".join(x for x in (p.get("city"), p.get("province")) if x and len(x) > 2)
    return [Job(p["id"], p["title"], where(p.get("location") or {}), p["url"],
                {"description": "".join(p.get(k) or "" for k in ("description", "key_responsibilities", "skills_knowledge_expertise", "benefits"))
                 + (f"<p>{p['compensation']}</p>" if p.get("compensation_visible") and p.get("compensation") else "")}) for p in posts]

SELECTMINDS_JOB = re.compile(r'href="(https://[^"]+/jobs/[\w-]+-(\d+))" class="job_link[^"]*">(.*?)</a>(?:(?!job_link).)*?class="location">\s*(.*?)\s*</span>', re.S)


def _selectminds_list(c):
    # taleo referral sites list every job in a search, ten a page
    page = http("GET", f"https://{c['board']}/jobs/search", headers={"Accept": "text/html"}).text
    search = re.search(r'data-jsid="(\d+)"', page)
    pages = int(float((re.search(r'id="jPaginateNumPages"[^>]*>([\d.]+)', page) or [0, 1])[1]))
    jobs = {}
    for n in range(1, pages + 1):
        if n > 1:
            page = http("GET", f"https://{c['board']}/jobs/search/{search[1]}/page{n}", headers={"Accept": "text/html"}).text
        for url, jid, title, where in SELECTMINDS_JOB.findall(page):
            jobs[jid] = Job(jid, html.unescape(title.strip()), html.unescape(where.strip()), url)
    # results are not by date, a higher id is a newer post
    return sorted(jobs.values(), key=lambda j: int(j.id), reverse=True)


def _dejobs_list(c):
    # directemployers ".jobs" sites, e.g. aecom.jobs; the search api serves 10 a page, newest first
    jobs, page = [], 1
    while len(jobs) < _cap(c):
        data = http("GET", "https://prod-search-api.jobsyn.org/api/v1/solr/search", headers={"X-Origin": c["board"]},
                    params={"page": page, "num_items": 10, "location": "United States"}).json()
        posts = data.get("jobs") or []
        jobs += [Job(p["guid"], p.get("title_exact") or "", p.get("location_exact") or "",
                     f"https://{c['board']}/{p['guid']}/job/", {"description": p.get("description") or ""}) for p in posts]
        if not posts or not (data.get("pagination") or {}).get("has_more_pages"):
            return jobs
        page += 1
    return jobs


def _csod_list(c):
    # board is host/career site id, e.g. linde.csod.com/23; the page hands out a public search token
    host, site = c["board"].split("/")
    corp = host.split(".")[0]
    page = http("GET", f"https://{host}/ux/ats/careersite/{site}/home", params={"c": corp}, headers={"Accept": "text/html"}).text
    token, cloud = re.search(r'"token":"([^"]+)"', page)[1], re.search(r'"cloud":"([^"]+)"', page)[1]
    jobs, num = [], 1
    while len(jobs) < _cap(c):
        body = {"careerSiteId": int(site), "careerSitePageId": int(site), "pageNumber": num, "pageSize": 100, "cultureId": 1,
                "searchText": "", "cultureName": "en-US", "states": [], "countryCodes": [], "cities": [], "placeID": "",
                "radius": None, "postingsWithinDays": None, "customFieldCheckboxKeys": [], "customFieldDropdowns": [],
                "customFieldRadios": []}
        data = http("POST", f"{cloud}rec-job-search/external/jobs", json=body,
                    headers={"Authorization": f"Bearer {token}"}).json().get("data") or {}
        posts = data.get("requisitions") or []
        for p in posts:
            where = "; ".join(", ".join(x for x in (l.get("city"), l.get("state"), l.get("country")) if x) for l in p.get("locations") or [])
            jobs.append(Job(str(p["requisitionId"]), p.get("displayJobTitle") or "", where,
                            f"https://{host}/ux/ats/careersite/{site}/home/requisition/{p['requisitionId']}?c={corp}",
                            {"description": p.get("externalDescription") or ""}))
        if not posts or len(jobs) >= data.get("totalCount", 0):
            return jobs
        num += 1
    return jobs


def _tbe_list(c):
    # taleo business edition, board is host/instance/org/cws, e.g. phh.tbe.taleo.net/phh03/SIERRANEVADABREWINGCO/39
    host, inst, org, cws = c["board"].split("/")
    base = f"https://{host}/{inst}/ats/careers/v2/searchResults"
    jobs, seen = [], set()
    while len(jobs) < _cap(c):
        params = {"org": org, "cws": cws, **({"act": "next", "rowFrom": len(seen)} if seen else {})}
        page = http("GET", base, params=params, headers={"Accept": "text/html"}).text
        found = re.findall(r'<a href="([^"]+rid=(\d+))" class="viewJobLink">(.*?)</a></h4>(.*?)<!--/.accordion-head-info', page, re.S)
        new = [f for f in found if f[1] not in seen]
        for url, rid, title, info in new:
            seen.add(rid)
            # each org picks its own fields here (place, department, job type), so keep them all
            where = ", ".join(html.unescape(x.strip()) for x in re.findall(r"<div[^>]*>(.*?)</div>", info) if x.strip())
            jobs.append(Job(rid, html.unescape(title.strip()), where, html.unescape(url)))
        if not new:
            return jobs
    return jobs


def _tbe_detail(c, job):
    page = http("GET", job.url, headers={"Accept": "text/html"}).text
    start = page.find('name="cwsJobDescription"')
    if start < 0:
        return ""
    start = page.find(">", start) + 1
    return page[start:page.find("<link", start)]


LIST = {"greenhouse": _greenhouse_list, "lever": _lever_list, "ashby": _ashby_list, "workday": _workday_list,
        "ukg": _ukg_list, "workable": _workable_list, "oracle": _oracle_list, "smartrecruiters": _smartrecruiters_list,
        "consider": _consider_list, "getro": _getro_list, "jibe": _jibe_list, "eightfold": _eightfold_list,
        "rss": _rss_list, "amazon": _amazon_list, "phenom": _phenom_list, "sfxml": _sfxml_list, "bamboohr": _bamboohr_list, "sitemap": _sitemap_list, "icims": _icims_list, "rippling": _rippling_list, "selectminds": _selectminds_list,
        "paylocity": _paylocity_list, "recruitee": _recruitee_list, "jazzhr": _jazzhr_list, "avature": _avature_list, "taleo": _taleo_list, "email": _email_list, "inbox": _inbox_list, "wpgh": _wpgh_list, "jobvite": _jobvite_list, "pinpoint": _pinpoint_list, "dejobs": _dejobs_list, "csod": _csod_list, "tbe": _tbe_list}
DETAIL = {"greenhouse": _greenhouse_detail, "lever": _lever_detail, "ashby": _ashby_detail, "workday": _workday_detail,
          "ukg": _ukg_detail, "workable": _workable_detail, "oracle": _oracle_detail,
          "smartrecruiters": _smartrecruiters_detail, "consider": _consider_detail, "getro": _getro_detail,
          "jibe": _jibe_detail, "eightfold": _eightfold_detail, "rss": _rss_detail,
          "amazon": _amazon_detail, "phenom": _phenom_detail, "sfxml": _sfxml_detail, "bamboohr": _bamboohr_detail, "sitemap": _sitemap_detail, "icims": _icims_detail, "rippling": _rippling_detail, "selectminds": _selectminds_detail,
          "paylocity": _sitemap_detail, "recruitee": _rss_detail, "jazzhr": _sitemap_detail, "avature": _avature_detail, "taleo": _taleo_detail, "email": lambda c, job: "", "inbox": lambda c, job: "", "wpgh": _wpgh_detail, "jobvite": _sitemap_detail, "pinpoint": _rss_detail, "dejobs": _rss_detail, "csod": _rss_detail, "tbe": _tbe_detail}


def fetch_list(company, newest=None):
    # newest: stop paging after this many, boards list newest first
    return LIST[company["platform"]]({**company, "newest": newest})


def fetch_detail(company, job):
    return DETAIL[company["platform"]](company, job)
