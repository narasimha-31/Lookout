import fetchers
from fetchers import Job


class Resp:
    def __init__(self, data=None, text=""):
        self._data, self.text = data, text

    def json(self):
        return self._data


def fake_http(routes, calls):
    def http(method, url, **kw):
        calls.append((method, url, kw))
        for key, value in routes.items():
            if key in url:
                return value(kw) if callable(value) else value
        raise AssertionError(url)
    return http


def test_greenhouse(monkeypatch):
    calls = []
    monkeypatch.setattr(fetchers, "http", fake_http({
        "/jobs/7": Resp({"content": "&lt;p&gt;Hello&lt;/p&gt;"}),
        "/jobs": Resp({"jobs": [{"id": 7, "title": "Data Analyst", "location": {"name": "Houston, TX"},
                                 "absolute_url": "https://x/7"}]}),
    }, calls))
    c = {"platform": "greenhouse", "board": "acme"}
    jobs = fetchers.fetch_list(c)
    assert jobs[0].id == "7" and jobs[0].location == "Houston, TX"
    assert fetchers.fetch_detail(c, jobs[0]) == "<p>Hello</p>"


def test_workday_pages_and_facets(monkeypatch):
    calls = []

    def page(kw):
        off = kw["json"]["offset"]
        posts = [{"externalPath": f"/job/{i}", "title": "Analyst", "locationsText": "Houston, TX"}
                 for i in range(off, min(off + 20, 25))] + [{"bulletFields": ["21018"]}]
        return Resp({"total": 25 if off == 0 else 0, "jobPostings": posts})

    monkeypatch.setattr(fetchers, "http", fake_http({"/jobs": page}, calls))
    c = {"platform": "workday", "board": "acme.wd5.myworkdayjobs.com/acme", "site": "Careers",
         "overrides": {"workday_facets": {"locations": ["abc"]}}}
    jobs = fetchers.fetch_list(c)
    assert len(jobs) == 25
    assert calls[0][1] == "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Careers/jobs"
    assert calls[0][2]["json"]["appliedFacets"] == {"locations": ["abc"]}
    assert jobs[0].url == "https://acme.wd5.myworkdayjobs.com/Careers/job/0"


def test_workday_search_terms_merge(monkeypatch):
    calls = []

    def page(kw):
        term = kw["json"]["searchText"]
        ids = {"analyst": [1, 2], "data": [2, 3]}[term]
        return Resp({"total": len(ids), "jobPostings": [{"externalPath": f"/job/{i}", "title": term} for i in ids]})

    monkeypatch.setattr(fetchers, "http", fake_http({"/jobs": page}, calls))
    c = {"platform": "workday", "board": "acme.wd5.myworkdayjobs.com/acme", "site": "Careers",
         "overrides": {"search_texts": ["analyst", "data"]}}
    assert sorted(j.id for j in fetchers.fetch_list(c)) == ["/job/1", "/job/2", "/job/3"]


def test_workday_newest_cap(monkeypatch):
    calls = []

    def page(kw):
        off = kw["json"]["offset"]
        return Resp({"total": 100, "jobPostings": [{"externalPath": f"/job/{i}"} for i in range(off, off + 20)]})

    monkeypatch.setattr(fetchers, "http", fake_http({"/jobs": page}, calls))
    c = {"platform": "workday", "board": "acme.wd5.myworkdayjobs.com/acme", "site": "Careers"}
    assert len(fetchers.fetch_list(c, newest=40)) == 40 and len(calls) == 2
    calls.clear()
    assert len(fetchers.fetch_list(c)) == 100 and len(calls) == 5


def test_ukg(monkeypatch):
    calls = []
    op = {"Id": "abc", "Title": "Data Analyst",
          "Locations": [{"Address": {"City": "Houston", "State": {"Code": "TX"}, "Country": {"Name": "United States"}}}]}
    page = 'x CandidateOpportunityDetail({"Title":"Data Analyst","Description":"<p>Hi \\"there\\"</p>"}); y'
    monkeypatch.setattr(fetchers, "http", fake_http({
        "LoadSearchResults": Resp({"opportunities": [op], "totalCount": 1}),
        "OpportunityDetail": Resp(text=page),
    }, calls))
    c = {"platform": "ukg", "board": "recruiting.ultipro.com/ABC/JobBoard/guid/"}
    jobs = fetchers.fetch_list(c)
    assert jobs[0].location == "Houston, TX, United States"
    assert jobs[0].url == "https://recruiting.ultipro.com/ABC/JobBoard/guid/OpportunityDetail?opportunityId=abc"
    assert fetchers.fetch_detail(c, jobs[0]) == '<p>Hi "there"</p>'


def test_oracle_pages(monkeypatch):
    calls = []

    def page(kw):
        off = int(calls[-1][1].split("offset=")[1].split(",")[0])
        reqs = [{"Id": i, "Title": "Analyst", "PrimaryLocation": "Houston, TX, United States",
                 "secondaryLocations": [{"Name": "Midland, TX"}]} for i in range(off, min(off + 25, 30))]
        return Resp({"items": [{"TotalJobsCount": 30, "requisitionList": reqs}]})

    monkeypatch.setattr(fetchers, "http", fake_http({
        "Details": Resp({"items": [{"ExternalDescriptionStr": "<p>A</p>", "ExternalQualificationsStr": "<p>B</p>"}]}),
        "recruitingCEJobRequisitions": page}, calls))
    c = {"platform": "oracle", "board": "abcd.fa.us2.oraclecloud.com/CX_1"}
    jobs = fetchers.fetch_list(c)
    assert len(jobs) == 30
    assert jobs[0].location == "Houston, TX, United States; Midland, TX"
    assert jobs[0].url == "https://abcd.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/0"
    assert fetchers.fetch_detail(c, jobs[0]) == "<p>A</p><p>B</p>"


def test_smartrecruiters(monkeypatch):
    calls = []
    post = {"id": "7", "name": "Data Analyst", "location": {"fullLocation": "Austin, TX, United States"}}
    monkeypatch.setattr(fetchers, "http", fake_http({
        "postings/7": Resp({"jobAd": {"sections": {"jobDescription": {"text": "<p>A</p>"},
                                                   "qualifications": {"text": "<p>B</p>"}}}}),
        "postings?": Resp({"content": [post], "totalFound": 1})}, calls))
    c = {"platform": "smartrecruiters", "board": "acme"}
    jobs = fetchers.fetch_list(c)
    assert jobs[0].location == "Austin, TX, United States"
    assert jobs[0].url == "https://jobs.smartrecruiters.com/acme/7"
    assert fetchers.fetch_detail(c, jobs[0]) == "<p>A</p><p>B</p>"


def test_lever_detail_joins_sections():
    j = Job("1", "Analyst", "Houston", "u", {"description": "<p>A</p>",
                                            "lists": [{"text": "Needs", "content": "<li>SQL</li>"}],
                                            "additional": "<p>B</p>"})
    assert fetchers.fetch_detail({"platform": "lever"}, j) == "<p>A</p><h3>Needs</h3><ul><li>SQL</li></ul><p>B</p>"


def test_getro_keeps_startup_name(monkeypatch):
    calls = []
    post = {"id": 5, "title": "Data Analyst", "locations": ["Austin, TX, USA"], "url": "https://x/5",
            "organization": {"name": "Startup Co"}, "searchable_locations": ["Austin, TX, USA", "United States"]}
    riga = {"id": 6, "title": "Consulting Analyst", "locations": ["Riga, Latvia"], "url": "https://x/6",
            "organization": {"name": "Pismo"}, "searchable_locations": ["Riga, Latvia", "Latvia"]}
    monkeypatch.setattr(fetchers, "http", fake_http({"search/jobs": Resp({"results": {"jobs": [post, riga], "count": 2}})}, calls))
    jobs = fetchers.fetch_list({"platform": "getro", "board": "8672"})
    assert (jobs[0].id, jobs[0].company, jobs[0].location) == ("5", "Startup Co", "Austin, TX, USA")


def test_consider_years_from_field():
    j = Job("a:1", "Data Analyst", "Austin, TX", "u", {"minYearsExp": 2}, "Startup Co")
    assert fetchers.fetch_detail({"platform": "consider"}, j) == "<p>Minimum 2 years of experience</p>"


def test_eightfold_asks_for_us_and_pages(monkeypatch):
    calls = []

    def page(kw):
        start = kw["params"]["start"]
        assert kw["params"]["location"] == "United States"
        pos = [{"id": i, "name": "Data Analyst", "locations": ["Boise, Idaho, United States of America"],
                "positionUrl": f"/careers/job/{i}"} for i in range(start, min(start + 10, 25))]
        return Resp({"data": {"count": 25, "positions": pos}})

    monkeypatch.setattr(fetchers, "http", fake_http({"pcsx/search": page}, calls))
    jobs = fetchers.fetch_list({"platform": "eightfold", "board": "careers.acme.com/acme.com"})
    assert len(jobs) == 25 and jobs[0].url == "https://careers.acme.com/careers/job/0"


def test_jibe_uses_slug_page(monkeypatch):
    calls = []
    post = {"data": {"req_id": "86587", "slug": "86587", "title": "Data Analyst", "full_location": "Austin, Texas",
                     "description": "<p>Hi</p>"}}
    monkeypatch.setattr(fetchers, "http", fake_http({"/api/jobs": Resp({"jobs": [post], "totalCount": 1})}, calls))
    c = {"platform": "jibe", "board": "careers.acme.com"}
    jobs = fetchers.fetch_list(c)
    assert jobs[0].url == "https://careers.acme.com/careers-home/jobs/86587"
    assert fetchers.fetch_detail(c, jobs[0]) == "<p>Hi</p>"


def test_rss_feed(monkeypatch):
    calls = []
    feed = ("<rss><item><title><![CDATA[Logistics Analyst (Fort Worth, TX, US)]]></title>"
            "<link>https://careers.acme.com/job/Fort-Worth-Logistics-Analyst/1453497833/?feedId=null&amp;utm=x</link>"
            "<description><![CDATA[<p>2 years of experience</p>]]></description></item>"
            "<item><title><![CDATA[Buyer (Toronto, ON, CA)]]></title><link>https://careers.acme.com/job/x/77/</link>"
            "<description>d</description></item></rss>")
    monkeypatch.setattr(fetchers, "http", fake_http({"services/rss": Resp(text=feed)}, calls))
    c = {"platform": "rss", "board": "careers.acme.com"}
    a, b = fetchers.fetch_list(c)
    assert (a.id, a.title, a.location) == ("1453497833", "Logistics Analyst", "Fort Worth, TX")
    assert a.url == "https://careers.acme.com/job/Fort-Worth-Logistics-Analyst/1453497833/"
    assert b.location == "Toronto, ON (CA)"
    assert fetchers.fetch_detail(c, a) == "<p>2 years of experience</p>"
