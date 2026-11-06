import json

import fetchers
import mail
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
            "<description>d</description></item>"
            "<item><title>Data Analyst (Bangalore, KA, IN, 560066)</title><link>https://careers.acme.com/job/y/78/</link>"
            "<description>d</description></item>"
            "<item><title>Data Analyst (Houston, TX, US, 77002)</title><link>https://careers.acme.com/job/z/79/</link>"
            "<description>d</description></item></rss>")
    monkeypatch.setattr(fetchers, "http", fake_http({"services/rss": Resp(text=feed)}, calls))
    c = {"platform": "rss", "board": "careers.acme.com"}
    a, b, india, houston = fetchers.fetch_list(c)
    assert (a.id, a.title, a.location) == ("1453497833", "Logistics Analyst", "Fort Worth, TX")
    assert a.url == "https://careers.acme.com/job/Fort-Worth-Logistics-Analyst/1453497833/"
    assert b.location == "Toronto, ON (CA)"
    assert india.location == "Bangalore, KA (IN)"
    assert houston.location == "Houston, TX"
    assert fetchers.fetch_detail(c, a) == "<p>2 years of experience</p>"


def test_consider_reads_description_from_workday_apply_link(monkeypatch):
    calls = []
    monkeypatch.setattr(fetchers, "http", fake_http({
        "/wday/cxs/guidehouse/External/job/": Resp({"jobPostingInfo": {"jobDescription": "<p>Public Trust</p>"}})}, calls))
    url = "https://guidehouse.wd1.myworkdayjobs.com/External/job/US---Remote/Cyber-Analyst_45309"
    j = Job("bain:1", "Cyber Analyst", "United States", url, {"minYearsExp": None}, "Guidehouse")
    assert fetchers.fetch_detail({"platform": "consider"}, j) == "<p>Public Trust</p>"
    assert calls[0][1] == "https://guidehouse.wd1.myworkdayjobs.com/wday/cxs/guidehouse/External/job/US---Remote/Cyber-Analyst_45309"


def test_vc_boards_skip_linkedin_copies(monkeypatch):
    calls = []
    us = ["New York, NY, USA", "United States"]
    posts = [{"id": 1, "title": "ML Intern", "locations": us[:1], "url": "https://www.linkedin.com/jobs/view/1",
              "organization": {"name": "Scale AI"}, "searchable_locations": us},
             {"id": 2, "title": "Data Analyst", "locations": us[:1], "url": "https://job-boards.greenhouse.io/x/jobs/2",
              "organization": {"name": "X"}, "searchable_locations": us}]
    monkeypatch.setattr(fetchers, "http", fake_http({"search/jobs": Resp({"results": {"jobs": posts, "count": 2}})}, calls))
    assert [j.id for j in fetchers.fetch_list({"platform": "getro", "board": "jobs.accel.com/8672"})] == ["2"]


def test_amazon(monkeypatch):
    calls = []
    post = {"id": "x1", "id_icims": "10594811", "title": "Data Analyst", "normalized_location": "Austin, Texas, USA",
            "job_path": "/en/jobs/10594811/data-analyst", "description": "<p>A</p>", "basic_qualifications": "2+ years"}
    monkeypatch.setattr(fetchers, "http", fake_http({"search.json": Resp({"jobs": [post], "hits": 1})}, calls))
    c = {"platform": "amazon", "board": "amazon.jobs"}
    j = fetchers.fetch_list(c)[0]
    assert (j.id, j.url) == ("10594811", "https://www.amazon.jobs/en/jobs/10594811/data-analyst")
    assert "2+ years" in fetchers.fetch_detail(c, j)
    assert calls[0][2]["params"]["country"] == "USA"


def test_phenom(monkeypatch):
    calls = []
    post = {"jobSeqNo": "UFSUFAUS123EXTERNALENUS", "jobId": "123", "title": "Pricing Analyst",
            "multi_location": ["Rosemont, Illinois, United States", "Houston, Texas, United States"], "location": "x"}
    listing = 'x phApp.ddo = {"eagerLoadRefineSearch": {"totalHits": 1, "data": {"jobs": [%s]}}}; phApp.sessionParams = {};' % json.dumps(post)
    detail = 'phApp.ddo = {"jobDetail": {"data": {"job": {"description": "<p>2 years</p>"}}}}; phApp.x = 1;'
    monkeypatch.setattr(fetchers, "http", fake_http({"search-results": Resp(text=listing), "/job/123": Resp(text=detail)}, calls))
    c = {"platform": "phenom", "board": "careers.usfoods.com/us/en"}
    j = fetchers.fetch_list(c)[0]
    assert (j.id, j.url) == ("UFSUFAUS123EXTERNALENUS", "https://careers.usfoods.com/us/en/job/123")
    assert j.location == "Rosemont, Illinois, United States; Houston, Texas, United States"
    assert calls[0][2]["params"] == {"size": 100, "from": 0, "sortBy": "Most recent"}
    assert fetchers.fetch_detail(c, j) == "<p>2 years</p>"


def test_sfxml(monkeypatch):
    calls = []
    feed = ("<Job-Listing><Job><JobTitle><![CDATA[Data Analyst &amp; BI]]></JobTitle>"
            "<Job-Description><![CDATA[<p>Irvine, CA</p>]]></Job-Description><ReqId>1456</ReqId></Job></Job-Listing>")
    monkeypatch.setattr(fetchers, "http", fake_http({"/career": Resp(text=feed)}, calls))
    c = {"platform": "sfxml", "board": "career8.successfactors.com/kia1"}
    j = fetchers.fetch_list(c)[0]
    assert (j.id, j.title) == ("1456", "Data Analyst & BI")
    assert j.url == "https://career8.successfactors.com/career?company=kia1&career_job_req_id=1456&career_ns=job_listing"
    assert calls[0][2]["params"]["company"] == "kia1"
    assert fetchers.fetch_detail(c, j) == "<p>Irvine, CA</p>"


def test_bamboohr(monkeypatch):
    calls = []
    post = {"id": "156", "jobOpeningName": "AI Engineer", "location": {"city": "Austin", "state": "Texas"},
            "atsLocation": {"country": "United States"}}
    monkeypatch.setattr(fetchers, "http", fake_http({
        "/careers/list": Resp({"result": [post]}),
        "/careers/156/detail": Resp({"result": {"jobOpening": {"description": "<p>JD</p>"}}})}, calls))
    c = {"platform": "bamboohr", "board": "energyx"}
    j = fetchers.fetch_list(c)[0]
    assert (j.id, j.location, j.url) == ("156", "Austin, Texas, United States", "https://energyx.bamboohr.com/careers/156")
    assert fetchers.fetch_detail(c, j) == "<p>JD</p>"


def test_sitemap_state_zip(monkeypatch):
    urls = ("<urlset><url><loc>https://jobs.engie.com/job/HOUSTON-Trading-Support-Analyst-II-TX-77056/1375953355/</loc></url>"
            "<url><loc>https://jobs.engie.com/job/Madrid-TPI-Settlement-Analyst-28042/1375109055/</loc></url></urlset>")
    monkeypatch.setattr(fetchers, "http", fake_http({"sitemap.xml": Resp(text=urls)}, []))
    c = {"platform": "sitemap", "board": "jobs.engie.com/sitemap.xml"}
    jobs = fetchers.fetch_list(c)
    assert ("HOUSTON Trading Support Analyst II", "TX, United States") in [(j.title, j.location) for j in jobs]
    c["overrides"] = {"us_only": True}
    assert [j.location for j in fetchers.fetch_list(c)] == ["TX, United States"]


def test_sitemap(monkeypatch):
    calls = []
    index = "<sitemapindex><sitemap><loc>https://x.com/page-sitemap.xml</loc></sitemap><sitemap><loc>https://x.com/job_listing-sitemap.xml</loc></sitemap></sitemapindex>"
    urls = ("<urlset><url><loc>https://x.com/job/1-old-data-analyst-austin-tx/</loc><lastmod>2026-10-01</lastmod></url>"
            "<url><loc>https://x.com/job/2-data-analyst-austin-tx/</loc><lastmod>2026-11-01</lastmod></url>"
            "<url><loc>https://x.com/about/</loc></url></urlset>")
    ld = {"@type": "JobPosting", "title": "Data Analyst", "description": "&lt;p&gt;2 years&lt;/p&gt;",
          "jobLocation": {"address": {"addressLocality": "Austin", "addressRegion": "Texas"}}}
    page = '<script type="application/ld+json">%s</script>' % json.dumps(ld)
    monkeypatch.setattr(fetchers, "http", fake_http({"sitemap_index": Resp(text=index), "job_listing-sitemap": Resp(text=urls),
                                                     "/job/2-": Resp(text=page)}, calls))
    c = {"platform": "sitemap", "board": "x.com/sitemap_index.xml"}
    jobs = fetchers.fetch_list(c)
    assert [j.title for j in jobs] == ["data analyst austin tx", "old data analyst austin tx"]
    assert len(fetchers.fetch_list(c, 1)) == 1
    j = jobs[0]
    assert fetchers.fetch_detail(c, j) == "<p>2 years</p>"
    assert (j.title, j.location) == ("Data Analyst", "Austin, Texas")
    uhg = "<urlset><url><loc>https://y.com/job/plymouth/data-analyst/34088/1027</loc><lastmod>2026-11-01</lastmod></url></urlset>"
    monkeypatch.setattr(fetchers, "http", fake_http({"y.com": Resp(text=uhg)}, calls))
    assert fetchers.fetch_list({"platform": "sitemap", "board": "y.com/sitemap.xml"})[0].title == "data analyst"
    eh = "<urlset><url><loc>https://e.com/job/data-analyst/birmingham-al/2532189/</loc></url></urlset>"
    monkeypatch.setattr(fetchers, "http", fake_http({"e.com": Resp(text=eh)}, calls))
    assert fetchers.fetch_list({"platform": "sitemap", "board": "e.com/sitemap.xml"})[0].title == "data analyst"
    md = ("<urlset><url><loc>https://m.org/search/jobdetails/data-engineer/4828d718-26b3-48d8-83e6-17d08a15e580</loc>"
          "<changefreq>daily</changefreq><lastmod>2026-11-04</lastmod></url>"
          "<url><loc>https://m.org/search/jobdetails/old-analyst/5828d718-26b3-48d8-83e6-17d08a15e580</loc><lastmod>2026-10-01</lastmod></url></urlset>")
    mpage = '<script type="application/ld&#x2B;json">{"@type": "JobPosting", "title": "Data Engineer", "description": "SQL"}</script>'
    monkeypatch.setattr(fetchers, "http", fake_http({"sitemap.xml": Resp(text=md), "jobdetails/data-engineer": Resp(text=mpage)}, calls))
    mj = fetchers.fetch_list({"platform": "sitemap", "board": "m.org/sitemap.xml"})
    assert [j.title for j in mj] == ["data engineer", "old analyst"]
    assert fetchers.fetch_detail({"platform": "sitemap"}, mj[0]) == "SQL"
    sf = "<urlset><url><loc>https://z.com/acme/job/Planner%2C-Supply-Chain/14/</loc></url></urlset>"
    sf_page = '<span class="jobdescription"><p>SQL</p><div>2 years</div></span></span><a class="applylink">Apply</a>'
    monkeypatch.setattr(fetchers, "http", fake_http({"sitemap.xml": Resp(text=sf), "/job/": Resp(text=sf_page)}, calls))
    j = fetchers.fetch_list({"platform": "sitemap", "board": "z.com/sitemap.xml"})[0]
    assert j.title == "Planner, Supply Chain"
    assert fetchers.fetch_detail({"platform": "sitemap"}, j) == "<p>SQL</p><div>2 years</div></span></span>"
    te = '<span itemprop="description" class="x"><p>Excel</p></span><span itemprop="description"><p>1 year</p></span><style>a{}</style>'
    monkeypatch.setattr(fetchers, "http", fake_http({"/job/": Resp(text=te)}, calls))
    assert fetchers.fetch_detail({"platform": "sitemap"}, j) == '<p>Excel</p></span><span itemprop="description"><p>1 year</p>'


def test_icims(monkeypatch):
    calls = []
    card = ('<li class="iCIMS_JobCardItem"><span class="sr-only field-label">Job Locations</span> <span > US-TX-Houston</span>'
            '<a href="https://careers-x.icims.com/jobs/3483/energy-risk-analyst/job?in_iframe=1"><h3 > Energy Risk &amp; Analyst</h3></a></li>')
    pages = {0: f"{card} <a href='?pr=1'>2</a>", 1: ""}
    monkeypatch.setattr(fetchers, "http", fake_http({"/jobs/search": lambda kw: Resp(text=pages[kw["params"]["pr"]])}, calls))
    j = fetchers.fetch_list({"platform": "icims", "board": "careers-x.icims.com"})[0]
    assert (j.id, j.title, j.location) == ("3483", "Energy Risk & Analyst", "US-TX-Houston")
    assert j.url == "https://careers-x.icims.com/jobs/3483/energy-risk-analyst/job"
    assert len(calls) == 2


def test_rippling(monkeypatch):
    calls = []
    page = '<a href="/job/1063983/project-finance-analyst" aria-label="Link to job discription for Project Finance &amp; Analyst">'
    monkeypatch.setattr(fetchers, "http", fake_http({"rippling-ats.com/": Resp(text=page)}, calls))
    j = fetchers.fetch_list({"platform": "rippling", "board": "net-power-llc.rippling-ats.com"})[0]
    assert (j.id, j.title) == ("1063983", "Project Finance & Analyst")
    assert j.url == "https://net-power-llc.rippling-ats.com/job/1063983/project-finance-analyst"


def test_selectminds(monkeypatch):
    calls = []
    listing = ('<p><a href="https://x.referrals.selectminds.com/ETP/jobs/data-analyst-20041" class="job_link font_bold">Data &amp; Analyst</a></p>'
               ' <p class="jlr_location"> <a href="#" class="location"><span class="loc_icon entypo">&#128269;</span>BEAUMONT, Texas, United States</a> </p>')
    page = '<div class="job_description"><p>2 years</p></div><div class="jBlockRegion">x'
    monkeypatch.setattr(fetchers, "http", fake_http({"latest-jobs": Resp(text=listing), "/jobs/data-analyst-20041": Resp(text=page)}, calls))
    c = {"platform": "selectminds", "board": "x.referrals.selectminds.com/ETP"}
    j = fetchers.fetch_list(c)[0]
    assert (j.id, j.title, j.location) == ("20041", "Data & Analyst", "BEAUMONT, Texas, United States")
    assert "2 years" in fetchers.fetch_detail(c, j)


def test_paylocity_newest_first(monkeypatch):
    jobs = [{"JobId": 1, "JobTitle": "Merchandiser", "PublishedDate": "2026-10-01", "LocationName": "Humble",
             "JobLocation": {"City": "Pasadena", "State": "TX", "Country": "USA"}},
            {"JobId": 2, "JobTitle": "Data Analyst", "PublishedDate": "2026-11-01", "LocationName": "Houston", "JobLocation": None}]
    page = "<script>window.pageData = %s;\n</script>" % json.dumps({"Jobs": jobs})
    monkeypatch.setattr(fetchers, "http", fake_http({"jobs/All/abc/Acme": Resp(text=page)}, []))
    got = fetchers.fetch_list({"platform": "paylocity", "board": "abc/Acme"})
    assert [(j.id, j.location) for j in got] == [("2", "Houston"), ("1", "Pasadena, TX, USA")]
    assert got[0].url == "https://recruiting.paylocity.com/Recruiting/Jobs/Details/2"


def test_recruitee(monkeypatch):
    offers = {"offers": [{"id": 7, "title": "Business Operations Analyst", "location": "Austin, Texas, United States",
                          "careers_url": "https://acme.recruitee.com/o/boa", "published_at": "2026-11-04",
                          "description": "<p>SQL</p>", "requirements": "<p>2 years</p>"}]}
    monkeypatch.setattr(fetchers, "http", fake_http({"acme.recruitee.com/api/offers": Resp(offers)}, []))
    c = {"platform": "recruitee", "board": "acme"}
    j = fetchers.fetch_list(c)[0]
    assert (j.title, j.location) == ("Business Operations Analyst", "Austin, Texas, United States")
    assert fetchers.fetch_detail(c, j) == "<p>SQL</p><p>2 years</p>"


def test_jazzhr(monkeypatch):
    page = ("<li class=\"list-group-item\"><h3 class='list-group-item-heading'><a href=\"https://acme.applytojob.com/apply/aB1/Data-Analyst\">"
            "\n Data Analyst &amp; BI </a></h3><ul class='list-inline'><li><i class='fa fa-map-marker'></i>Houston, TX</li></ul></li>")
    monkeypatch.setattr(fetchers, "http", fake_http({"acme.applytojob.com/apply": Resp(text=page)}, []))
    j = fetchers.fetch_list({"platform": "jazzhr", "board": "acme"})[0]
    assert (j.id, j.title, j.location, j.url) == ("aB1", "Data Analyst & BI", "Houston, TX", "https://acme.applytojob.com/apply/aB1/Data-Analyst")


def test_avature_pages_until_nothing_new(monkeypatch):
    card = ('<article class="article article--result"><a href="https://a.avature.net/en_US/careers/JobDetail/Houston-Data-Analyst/%s">'
            "\n Data Analyst \n</a><span class=\"list-item-location\">Houston, Texas, United States</span></article>")
    pages = {0: card % 1 + card % 2, 2: card % 3, 3: card % 3}
    monkeypatch.setattr(fetchers, "http", lambda m, u, params=None, **kw: Resp(text=pages[params["jobOffset"]]))
    jobs = fetchers.fetch_list({"platform": "avature", "board": "a.avature.net/en_US"})
    assert [(j.id, j.title, j.location) for j in jobs] == [("1", "Data Analyst", "Houston, Texas, United States"),
                                                           ("2", "Data Analyst", "Houston, Texas, United States"),
                                                           ("3", "Data Analyst", "Houston, Texas, United States")]
    detail = '<div class="x tf_replaceFieldVideoTokens"><p>SQL, 2 years</p></div><div class="article__content"><a>Apply</a>'
    monkeypatch.setattr(fetchers, "http", lambda *a, **kw: Resp(text=detail))
    assert fetchers.fetch_detail({"platform": "avature"}, jobs[0]) == "<p>SQL, 2 years</p></div>"


def test_taleo(monkeypatch):
    calls = []
    page = {"requisitionList": [{"contestNo": "197703", "column": ["Data Analyst", '["United States-Texas-Houston"]', "Nov 4, 2026"]}],
            "pagingData": {"totalCount": 1}}
    monkeypatch.setattr(fetchers, "http", fake_http({"searchjobs": Resp(page)}, calls))
    c = {"platform": "taleo", "board": "hdr.taleo.net/ex/101430233"}
    j = fetchers.fetch_list(c)[0]
    assert (j.id, j.title, j.location) == ("197703", "Data Analyst", "United States, Texas, Houston")
    assert calls[0][2]["params"]["portal"] == "101430233" and j.url.endswith("/careersection/ex/jobdetail.ftl?job=197703&lang=en")
    state = 'ftlx0!|!short!|!!*!&lt;p&gt;SQL%5C: 2 years&lt;/p&gt;!|!x'
    monkeypatch.setattr(fetchers, "http", fake_http({"jobdetail": Resp(text=f'<input id="initialHistory" value="{state}">')}, calls))
    assert fetchers.fetch_detail(c, j) == "<p>SQL: 2 years</p>"


def test_sfxml_fills_template_fields_from_the_posting(monkeypatch):
    job = Job("1559", "Retail Marketing Analyst", "", "https://career8.successfactors.com/career?company=kia1&career_job_req_id=1559",
              {"description": "<p>Pay [[salaryMin]] - [[salaryMid]]</p>"})
    page = '<div class="joqReqDescription"><p>Pay $57,980 - $75,411</p></div><input id="navBarLevel">'
    monkeypatch.setattr(fetchers, "http", fake_http({"career_job_req_id=1559": Resp(text=page)}, []))
    assert fetchers.fetch_detail({"platform": "sfxml"}, job) == "<p>Pay $57,980 - $75,411</p></div>"
    plain = Job("2", "Analyst", "", "u", {"description": "<p>Pay $50,000</p>"})
    assert fetchers.fetch_detail({"platform": "sfxml"}, plain) == "<p>Pay $50,000</p>"


def test_email_alerts_split_into_roles(monkeypatch):
    body = ('<a href="https://t.co/click?u=https%3A%2F%2Fwww.tesla.com%2Fcareers%2Fsearch%2Fjob%2Fdata-analyst-251234">Data Analyst, Supply Chain</a>'
            '<a href="https://www.tesla.com/careers/search/job/sr-engineer-251999"><b>Senior Engineer</b></a>'
            '<a href="https://www.tesla.com/careers/search">View all jobs</a><a href="https://www.tesla.com/unsubscribe">Unsubscribe</a>')
    again = '<a href="https://t.co/other?u=https%3A%2F%2Fwww.tesla.com%2Fcareers%2Fsearch%2Fjob%2Fdata-analyst-251234">Data Analyst, Supply Chain</a>'
    monkeypatch.setattr(mail, "alerts", lambda q: [body, again])
    jobs = fetchers.fetch_list({"platform": "email", "board": "from:tesla.com"})
    assert [(j.id, j.title) for j in jobs] == [("251234", "Data Analyst, Supply Chain"), ("251999", "Senior Engineer")]
    assert fetchers.fetch_detail({"platform": "email"}, jobs[0]) == ""


def test_inbox_jobs_from_the_browser_button(monkeypatch):
    import db
    monkeypatch.setattr(db, "inbox", lambda cid: [{"id": "280882", "t": "Supply Chain Data Analyst", "w": "Palo Alto, CA"}, {"t": "no id"}])
    jobs = fetchers.fetch_list({"platform": "inbox", "id": 7, "board": "tesla.com/careers"})
    assert [(j.id, j.title, j.location, j.url) for j in jobs] == [
        ("280882", "Supply Chain Data Analyst", "Palo Alto, CA", "https://www.tesla.com/careers/search/job/supply-chain-data-analyst-280882")]
