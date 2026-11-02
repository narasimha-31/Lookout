# Lookout

Checks company job boards every 10 minutes and sends one email per new matching job, with the full description.

Supported job boards: Greenhouse, Lever, Ashby, Workday, UKG (UltiPro) and Workable.

## Setup

1. Create a free Supabase project and run the schema script in its SQL editor.
2. Add these repository secrets in GitHub: `SUPABASE_URL`, `SUPABASE_KEY` (secret key), `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `ALERT_TO`.
3. The scheduled workflow does the rest. It can also be started by hand from the Actions tab.

To run it on your own computer, set the same five values as environment variables (or in a local env file) and run the main script with Python.

## Adding a company

Open the company's careers page, click any job, and look at the address of the job page. It tells you the board type and what to put in the `board` and `site` columns.

Then add one row to the `companies` table in Supabase (Table Editor, Insert row). Fill in `name`, `platform`, `board` and, for Workday only, `site`. Leave the other columns as they are.

| Job page address looks like | platform | board | site |
|---|---|---|---|
| `boards.greenhouse.io/acme/jobs/123` or `job-boards.greenhouse.io/acme/...` | greenhouse | `acme` | |
| `jobs.lever.co/acme/...` | lever | `acme` | |
| `jobs.ashbyhq.com/acme/...` | ashby | `acme` | |
| `acme.wd5.myworkdayjobs.com/en-US/AcmeCareers/job/...` | workday | `acme.wd5.myworkdayjobs.com/acme` | `AcmeCareers` |
| `recruiting.ultipro.com/ACM1000/JobBoard/1a2b.../OpportunityDetail?...` | ukg | `recruiting.ultipro.com/ACM1000/JobBoard/1a2b...` | |
| `apply.workable.com/acme/j/ABC123/` | workable | `acme` | |

Notes:

- Workday: the part before `.wd` is the tenant. The site is the word after `en-US/` (or right after the host when there is no language part). Use `wd1`, `wd5`, `wd12` and so on exactly as in the address.
- UKG: copy everything from the host up to and including the long id after `JobBoard/`. Some companies use a host ending in `ukg.net`, which works the same way.
- The first check of a new company saves its current jobs without sending email. Only jobs posted after that are sent.
- To stop watching a company, set `active` to false.

## Changing filters

Edit the single row in the `filters` table. No code change needed.

- `title_include`: a job title must contain one of these.
- `title_exclude`: a title with any of these is skipped (senior, lead, manager and so on).
- `dealbreakers`: phrases in the description that stop the email, such as "unable to sponsor".
- `locations_allowed`: US states and state codes. Two-letter codes only match in capitals.
- `locations_blocked`: other countries. A location that matches neither list still gets through.

Jobs asking for more than 3 years of experience are saved but not emailed.

A company can override any filter list with its `overrides` column, for example `{"title_include": ["analyst"]}`. Workday companies can also narrow the search there with `search_text` or `workday_facets`.

## Alerts

- A company whose board fails sends one "fetch failed" email, then stays quiet until it works again.
- A company that suddenly lists zero jobs sends one warning, since the board may have moved.
- If the whole run crashes, a "tracker failed" email is sent.

Logs show counts only.
