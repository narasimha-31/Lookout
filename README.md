# Lookout

Checks company job boards every 10 minutes and sends one email per new matching job, with the full description.

Supported boards: Greenhouse, Lever, Ashby and Workday.

## Setup

1. Create a free Supabase project and run the schema script in its SQL editor.
2. Add these repository secrets in GitHub: `SUPABASE_URL`, `SUPABASE_KEY` (service role key), `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `ALERT_TO`.
3. The scheduled workflow does the rest.

## Adding a company

Add a row to the `companies` table in Supabase. It is picked up on the next run. The first check saves the current jobs without sending email, so only jobs posted after that are sent.

## Changing filters

Edit the single row in the `filters` table. No code change needed.

Logs show counts only.
