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
                 for i in range(off, min(off + 20, 25))]
        return Resp({"total": 25 if off == 0 else 0, "jobPostings": posts})

    monkeypatch.setattr(fetchers, "http", fake_http({"/jobs": page}, calls))
    c = {"platform": "workday", "board": "acme.wd5.myworkdayjobs.com/acme", "site": "Careers",
         "overrides": {"workday_facets": {"locations": ["abc"]}}}
    jobs = fetchers.fetch_list(c)
    assert len(jobs) == 25
    assert calls[0][1] == "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Careers/jobs"
    assert calls[0][2]["json"]["appliedFacets"] == {"locations": ["abc"]}
    assert jobs[0].url == "https://acme.wd5.myworkdayjobs.com/Careers/job/0"


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


def test_lever_detail_joins_sections():
    j = Job("1", "Analyst", "Houston", "u", {"description": "<p>A</p>",
                                            "lists": [{"text": "Needs", "content": "<li>SQL</li>"}],
                                            "additional": "<p>B</p>"})
    assert fetchers.fetch_detail({"platform": "lever"}, j) == "<p>A</p><h3>Needs</h3><ul><li>SQL</li></ul><p>B</p>"
