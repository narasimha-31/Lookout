create table companies (
  id bigint generated always as identity primary key,
  name text not null,
  platform text not null check (platform in ('greenhouse', 'lever', 'ashby', 'workday')),
  -- workday: host/tenant, e.g. acme.wd5.myworkdayjobs.com/acme
  board text not null,
  site text,
  overrides jsonb not null default '{}',
  active boolean not null default true,
  first_run_done boolean not null default false,
  added_at timestamptz not null default now()
);

create table seen_jobs (
  id bigint generated always as identity primary key,
  company_id bigint not null references companies on delete cascade,
  external_job_id text not null,
  title text,
  location text,
  url text,
  first_seen_at timestamptz not null default now(),
  emailed boolean not null default false,
  possible_repost boolean not null default false,
  unique (company_id, external_job_id)
);

create index seen_jobs_repost on seen_jobs (company_id, title, location);

create table filters (
  id int primary key default 1 check (id = 1),
  title_include text[] not null,
  title_exclude text[] not null,
  dealbreakers text[] not null,
  locations_allowed text[] not null,
  locations_blocked text[] not null
);

create table company_health (
  company_id bigint primary key references companies on delete cascade,
  last_success_at timestamptz,
  last_job_count int,
  last_error text
);

alter table companies enable row level security;
alter table seen_jobs enable row level security;
alter table filters enable row level security;
alter table company_health enable row level security;

insert into filters values (
  1,
  array['analyst', 'analytics', 'data engineer', 'business intelligence', 'bi developer',
        'sql', 'python', 'it support', 'it specialist', 'systems administrator',
        'software engineer', 'developer', 'associate engineer'],
  array['senior', 'sr', 'lead', 'manager', 'principal', 'director', 'staff', 'head',
        'vp', 'iii', 'iv'],
  array['unable to sponsor', 'not able to sponsor', 'will not sponsor', 'does not sponsor',
        'no sponsorship', 'without current or future sponsorship',
        'sponsorship is not available', 'must not require sponsorship',
        'us citizens or permanent residents only', 'green card holders only',
        'no h-1b', 'no opt', 'no cpt',
        'security clearance', 'active clearance', 'us citizenship required',
        'must be a us citizen'],
  -- two-letter codes are matched case-sensitively
  array['United States', 'USA', 'US', 'Remote', 'Multiple',
        'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut',
        'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa',
        'Kansas', 'Kentucky', 'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan',
        'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
        'New Hampshire', 'New Jersey', 'New Mexico', 'New York', 'North Carolina',
        'North Dakota', 'Ohio', 'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island',
        'South Carolina', 'South Dakota', 'Tennessee', 'Texas', 'Utah', 'Vermont',
        'Virginia', 'Washington', 'West Virginia', 'Wisconsin', 'Wyoming',
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN',
        'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV',
        'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN',
        'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC'],
  array['Canada', 'India', 'United Kingdom', 'UK', 'Mexico', 'Germany', 'Ireland',
        'Philippines', 'Brazil', 'Poland', 'Australia', 'Singapore']
);
