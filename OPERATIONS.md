# Operations: the weekly website check

A safety net for changeanesthesiology.com (Q14, Sukant, 18 Oct 2026, D64). This file is not part of
the website; like every `.md` file and `.github/`, it is never served.

## What it does

Every Monday at 7:47 am Saskatchewan time, GitHub runs `.github/workflows/weekly-check.yml`. It
checks both changeanesthesiology.com and www.changeanesthesiology.com:

1. **Live pages match GitHub.** The live home page and article are byte for byte the same as
   `index.html` and `article.html` on `main`.
2. **Every test passes.** The test files in `tests/` (Q13, Q12, Q10/Q11, Q04, Q08, and Q06 apart
   from its 3 known PR-04 lines) run against the live site, as they are.
3. **Nothing calls out.** No requests to prechangeway.com or YouTube when the pages load, and no
   console errors.
4. **The rollback point still loads.** The build link of the version we would roll back to opens
   the site. It needs no token or password.

It only looks. It never changes the site, commits, pushes, deploys or changes a setting, and it uses
no secrets.

## Where to see the results

On GitHub: the repo's **Actions** tab, then **Weekly website check**. Each run opens with a short
summary: one line per check, for each host. A green tick means everything passed. If anything
fails, the run is marked as failed and GitHub emails Sukant.

## Run it by hand

Actions tab, **Weekly website check**, then **Run workflow** (branch `main`), then **Run workflow**.
Or, from a terminal: `gh workflow run weekly-check.yml`. A run takes about half an hour.

## After each merge: update the rollback point

The rollback point is the one line `ROLLBACK_URL:` near the top of
`.github/workflows/weekly-check.yml`. After a merge goes live, set it to the build link of the
version that was live just before (`https://<first 8 characters of the version ID>-changeanesthesiology.sukantratnakar.workers.dev`).

## If GitHub turns it off

GitHub turns off scheduled runs in a public repo after 60 days with no activity in the repo (no
commits, for example). It emails a warning first. To turn it back on: Actions tab, **Weekly website
check**, then **Enable workflow**. Or, from a terminal: `gh workflow enable weekly-check.yml`.

## If a run fails

Open the run and read its summary: it says which check failed and on which host. Nothing is rolled
back automatically; Sukant decides what to do.
