# Fit model, phase 1: score and learn

## Why

The word filters keep letting through jobs that match the words but not the person: "Data Storage" physics research, senior client-lead consulting, customs compliance, actuarial roles. Each one needs a new rule after it has already reached the inbox. A model that learns from what gets starred or deleted can pick up the patterns rules miss.

## Goals

- Every job email shows a fit score from a model that learns daily from the user's reactions.
- The user can see whether it is learning: the daily summary reports how often the score agreed with them.
- It stays free and runs in the existing scheduled jobs.

## Non-goals (phase 1)

- The model does not block, hold back or reorder any job. Every job that passes the filters is emailed exactly as today.
- No change to the existing filters (title, location, years, sponsorship, data tools, student-only).
- No buttons, links or new web endpoints in the email.

## Anti-goals

- Never lose a job the user would want because of the model. In phase 1 that is guaranteed because the model only scores.
- Never mistake a job email the user hasn't touched for a reaction.
- Never write to Gmail. Reading is read-only, like the alert-email reader.

## How it works

### Order
Filters run first, unchanged. The model only scores jobs that already passed every filter and are about to be emailed.

### Input to the model
Title plus description text. A job with no description gets a score from the title alone, and the email shows it as low confidence.

### Feedback (decided by the user)
- Starred job email = good (+1).
- Job email in Trash = bad (-1).
- Untouched = no signal.
- Each job email carries a hidden header with the company id and job id, so a reaction maps to the exact job.
- Once a day, the daily job reads reactions since the last read, read-only, and saves each one permanently as a lesson. After that the email is never needed again, so Gmail emptying Trash after 30 days loses nothing.
- If the user stars an email and later deletes it (or the other way round), the latest reaction wins.

### Learning (decided by the user: daily)
- Every day, after saving new lessons, the model retrains on all lessons so far. Lessons are never discarded.
- Starting lessons come from the emails already sent, but only where the reason is the kind of work itself:
  - Bad: rejected because the title is not a wanted role (excluded words like design engineer, embedded software, actuarial, data storage), or because the description names no real data work.
  - Left out: anything rejected for years, location, sponsorship, senior with no years, or no description. Those are rule decisions, not taste, and the same kind of work might be wanted at another company.
  - Left out: AI engineer roles. They're paused, not disliked, and learning them as bad would follow the user when they're resumed.
  - Good (weak): emails that still pass today's rules. Real stars and deletes replace them over time.
  - Descriptions are re-fetched where the posting is still open. Jobs whose description can't be fetched are left out.

### Score in the email (decided by the user)
- A "Fit" row in the table at the top of every job email, next to Company, Title, Location and Pay: "Fit: 82% (learned from 312 reactions)".
- Before any model exists, it reads "Fit: learning, no score yet".

### Is it learning? (decided by the user)
The daily summary adds one line: of the reactions since yesterday, how many the score agreed with (score of 50% or more and starred, or under 50% and deleted), plus the same figure for the last 50 reactions.

### Storage
- The description text of each emailed job is saved with that job, so it can become a lesson later. That's only emailed jobs, a few hundred a month.
- Lessons: company, job id, title, description, good or bad, where it came from (star, trash, starting set), when.
- The trained model is saved as a small set of word weights, read once per run. It has to stay small (well under 1 MB) so per-run reads stay inside the free plan's egress.

### A delete with no reason
A delete only says "bad", not why. One delete barely moves the model, since it learns from patterns across many reactions. When a delete is really about years or location, the fix belongs in the rules, and the replay check (re-running sent emails against the current rules) is how those get found.

## Phase 2 (later, separate approval)
When the user decides the score agrees with them often enough, jobs scoring low are still emailed, but with "[low fit]" at the start of the subject. A one-time Gmail filter files those out of the inbox under a label. Starring a low-fit job is the strongest correction. Nothing is ever dropped.

## Builder's calls (marked as mine, open to change)
- **Model:** word and two-word features from title plus description (TF-IDF) with logistic regression, using scikit-learn. Trains in seconds on a few thousand lessons. Reinforcement in the sense of learning from rewards on its own choices (a contextual bandit with daily batch updates), not a game-style agent.
- **Saved model:** the vocabulary and weights for the top-weighted terms are stored as one database row and loaded once per run.
- **Where it runs:** reading reactions and retraining run in the existing daily job. Scoring runs in the 10-minute job.
- **Few lessons:** with fewer than 20 good or fewer than 20 bad lessons, the email shows "learning, no score yet" instead of a misleading number.
