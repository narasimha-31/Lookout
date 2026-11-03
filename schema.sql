create table companies (
  id bigint generated always as identity primary key,
  name text not null,
  platform text not null,
  -- workday: host/tenant, e.g. acme.wd5.myworkdayjobs.com/acme
  -- ukg: board address, e.g. recruiting.ultipro.com/ACM1000/JobBoard/<id>
  board text not null,
  site text,
  overrides jsonb not null default '{}',
  active boolean not null default true,
  first_run_done boolean not null default false,
  added_at timestamptz not null default now(),
  -- why a company is switched off
  note text
);
-- a board can only be added once, so blocked companies are caught on re-add
create unique index companies_board_unique on companies (lower(board), coalesce(site, ''));

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
  last_error text,
  ids_hash text
);

alter table companies enable row level security;
alter table seen_jobs enable row level security;
alter table filters enable row level security;
alter table company_health enable row level security;

insert into filters values (
  1,
  array['analyst', 'analytics', 'data engineer', 'analytics engineer', 'data scientist', 'data science', 'business intelligence', 'bi developer', 'bi engineer', 'power bi', 'tableau', 'sql', 'etl', 'data platform', 'data integration', 'data operations', 'data specialist', 'database', 'reporting', 'machine learning', 'ml engineer', 'ai engineer', 'applied ai', 'ai developer', 'ai specialist', 'artificial intelligence', 'llm', 'genai', 'generative ai', 'gis', 'sap', 'analysis', 'data', 'insights', 'visualization', 'metrics', 'intelligence', 'procurement', 'sourcing', 'information systems', 'fp&a', 'etl developer', 'sql developer', 'data analyst', 'operations research', 'supply chain planner', 'demand planner', 'demand planning', 'supply planner', 'supply planning', 'inventory planner', 'materials planner', 'material planner', 's&op'],
  array['senior', 'sr', 'lead', 'manager', 'principal', 'director', 'staff', 'head', 'vp', 'iii', 'iv', 'architect', 'president', 'chief', 'static timing', 'timing analysis', 'physical design', 'design engineer', 'asic', 'soc', 'rtl', 'verification', 'dft', 'analog', 'layout', 'firmware', 'hardware', 'mechanical', 'electrical', 'process engineer', 'chemical engineer', 'civil', 'structural', 'technician', 'nurse', 'rn', 'lpn', 'physician', 'pharmacist', 'therapist', 'driver', 'welder', 'machinist', 'electrician', 'mechanic', 'scheduler', 'turnaround', 'tar', 'maintenance', 'sales specialist', 'sales representative', 'sales engineer', 'sales executive', 'account executive', 'business development', 'data protection', 'controller'],
  array['unable to sponsor', 'not able to sponsor', 'will not sponsor', 'does not sponsor',
        'no sponsorship', 'without current or future sponsorship',
        'sponsorship is not available', 'must not require sponsorship',
        'us citizens or permanent residents only', 'green card holders only',
        'no h-1b', 'no opt', 'no cpt',
        'security clearance', 'active clearance', 'us citizenship required',
        'must be a us citizen'],
  -- two-letter codes are matched case-sensitively
  array['United States', 'USA', 'US', 'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire', 'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota', 'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington', 'West Virginia', 'Wisconsin', 'Wyoming', 'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC'],
  array['Canada', 'Alberta', 'Ontario', 'British Columbia', 'Quebec', 'India', 'United Kingdom', 'UK', 'England', 'Scotland', 'Wales', 'Mexico', 'Germany', 'Ireland', 'Philippines', 'Brazil', 'Poland', 'Australia', 'Singapore', 'Europe', 'Spain', 'France', 'Italy', 'Netherlands', 'Belgium', 'Norway', 'Sweden', 'Denmark', 'Greece', 'Turkey', 'Romania', 'Bulgaria', 'Hungary', 'Portugal', 'Switzerland', 'Austria', 'Ukraine', 'United Arab Emirates', 'UAE', 'Saudi Arabia', 'Qatar', 'Kuwait', 'Oman', 'Egypt', 'Nigeria', 'Angola', 'Tanzania', 'South Africa', 'China', 'Japan', 'Korea', 'Vietnam', 'Thailand', 'Malaysia', 'Indonesia', 'New Zealand', 'Jamaica', 'Trinidad', 'Guyana', 'Colombia', 'Argentina', 'Chile', 'Peru', 'Costa Rica', 'Israel', 'Pakistan', 'GBR', 'BGR', 'IND', 'CAN', 'MEX', '(GB)', '(UK)', '(ES)', '(FR)', '(IT)', '(DE)', '(NL)', '(IE)', '(CN)', '(JP)', '(NZ)', '(AU)', '(IN)', '(CA)', 'Pune', 'Bangalore', 'Bengaluru', 'Hyderabad', 'Chennai', 'Mumbai', 'Delhi', 'New Delhi', 'Noida', 'Gurgaon', 'Gurugram', 'Kolkata', 'London', 'Manchester', 'Toronto', 'Vancouver', 'Montreal', 'Calgary', 'Edmonton', 'Ottawa', 'Tokyo', 'Sydney', 'Melbourne', 'Seoul', 'Berlin', 'Munich', 'Amsterdam', 'Warsaw', 'Krakow', 'Zurich', 'Tel Aviv', 'Manila', 'Bogota', 'Sao Paulo', 'Shanghai', 'Beijing', 'Shenzhen', 'Hong Kong', 'Taipei', 'Taiwan', 'Lisbon', 'Madrid', 'Barcelona', 'Prague', 'Bucharest', 'Kyiv', 'Dubai', 'Riyadh', 'Doha', 'Lagos', 'Nairobi', 'Johannesburg', 'Cape Town', 'Czech Republic', 'Finland', 'Remote (GB)', 'Aberdeen', 'Algeria', 'Kazakhstan', 'Bahrain', 'Azerbaijan', 'Budapest', 'Cologne', 'Cork', 'Dublin', 'EMEA', 'Espoo', 'Frankfurt', 'Gdansk', 'QLD', 'Great Britain', 'Guadalajara', 'Hamburg', 'Hsinchu', 'Islamabad', 'Lahore', 'Kuala Lumpur', 'Slovenia', 'Ljubljana', 'Luxembourg', 'Manitoba', 'Milan', 'Monterrey', 'Nova Scotia', 'Oslo', 'Paris', 'Perth', 'Cambodia', 'Phnom Penh', 'Iceland', 'Rio de Janeiro', 'Rome', 'Stavanger', 'Stockholm', 'Stuttgart', 'Paulo', 'Viet Nam', 'Vilnius', 'Lithuania', 'APAC', 'LATAM', 'Afghanistan', 'Albania', 'Andorra', 'Antigua and Barbuda', 'Armenia', 'Bahamas', 'Bangladesh', 'Barbados', 'Belarus', 'Belize', 'Benin', 'Bhutan', 'Bolivia', 'Bosnia and Herzegovina', 'Botswana', 'Brunei', 'Burkina Faso', 'Burundi', 'Cabo Verde', 'Cameroon', 'Central African Republic', 'Chad', 'Comoros', 'Congo', 'Croatia', 'Cuba', 'Cyprus', 'Czechia', 'Djibouti', 'Dominica', 'Dominican Republic', 'Ecuador', 'El Salvador', 'Equatorial Guinea', 'Eritrea', 'Estonia', 'Eswatini', 'Ethiopia', 'Fiji', 'Gabon', 'Gambia', 'Ghana', 'Grenada', 'Guatemala', 'Guinea', 'Guinea-Bissau', 'Haiti', 'Honduras', 'Iran', 'Iraq', 'Ivory Coast', 'Jordan', 'Kenya', 'Kiribati', 'Kosovo', 'Kyrgyzstan', 'Laos', 'Latvia', 'Lebanon', 'Lesotho', 'Liberia', 'Libya', 'Liechtenstein', 'Madagascar', 'Malawi', 'Maldives', 'Mali', 'Malta', 'Marshall Islands', 'Mauritania', 'Mauritius', 'Micronesia', 'Moldova', 'Monaco', 'Mongolia', 'Montenegro', 'Morocco', 'Mozambique', 'Myanmar', 'Namibia', 'Nauru', 'Nepal', 'Nicaragua', 'Niger', 'North Korea', 'North Macedonia', 'Palau', 'Palestine', 'Panama', 'Papua New Guinea', 'Paraguay', 'Russia', 'Rwanda', 'Saint Lucia', 'Samoa', 'San Marino', 'Senegal', 'Serbia', 'Seychelles', 'Sierra Leone', 'Slovakia', 'Solomon Islands', 'Somalia', 'South Korea', 'South Sudan', 'Sri Lanka', 'Sudan', 'Suriname', 'Syria', 'Tajikistan', 'Timor-Leste', 'Togo', 'Tonga', 'Trinidad and Tobago', 'Tunisia', 'Turkiye', 'Turkmenistan', 'Tuvalu', 'Uganda', 'Uruguay', 'Uzbekistan', 'Vanuatu', 'Venezuela', 'Yemen', 'Zambia', 'Zimbabwe', 'Northern Ireland', 'Asia', 'Africa']
);

-- last time each active company had a new job, for the daily stale check
create or replace view company_activity with (security_invoker = true) as
select c.id, c.name, c.added_at, max(s.first_seen_at) as last_new
from companies c left join seen_jobs s on s.company_id = c.id
where c.active group by c.id;
