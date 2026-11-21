# GSoC issue watcher

Checks GSoC-organization repos every 30 minutes for newcomer-friendly issues
that are genuinely free to claim, and pushes a notification to your phone.

Runs on GitHub Actions, so it works whether or not your laptop is on.

## What counts as "free"

An issue is only reported when all of these hold:

1. open, with **no assignee**
2. carries a newcomer label (`help wanted`, `good first issue`, ...)
3. **no open pull request is linked to it** — checked through the timeline
   API, so it catches PRs linked via GitHub's Development panel, not just
   ones that mention the issue number in their body
4. **no live claim** in the comments — a claim that was later abandoned, or
   auto-unassigned for inactivity, does not count

Point 3 matters. An issue can look completely unclaimed and still have someone
five weeks into a PR on it.

## Setup (one time, ~10 minutes)

### 1. Install the ntfy app on your phone

[Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) ·
[iOS](https://apps.apple.com/us/app/ntfy/id1625396347)

Open it, tap **+**, and subscribe to your topic name.

> Your topic name is a password. Anyone who knows it can read your
> notifications. Keep it unguessable and don't post it anywhere.

### 2. Create the repo

```bash
cd cloud
git init
git add .
git commit -m "Add GSoC issue watcher."
gh repo create gsoc-watch --public --source=. --push
```

Public is recommended: GitHub Actions minutes are unlimited on public repos.
Nothing secret is stored in the files — the topic name lives in a secret.

### 3. Add your topic as a secret

```bash
gh secret set NTFY_TOPIC --body "your-topic-name-here"
```

### 4. Turn it on

Go to the repo's **Actions** tab and enable workflows. Then trigger the first
run by hand: **GSoC issue watcher → Run workflow**.

The first run records what already exists and pushes nothing. From then on you
only hear about genuinely new issues.

## Day to day

- `latest.md` in the repo always lists everything currently free
- A push arrives within ~30 minutes of a new issue appearing
- Tapping the notification opens the issue

## Changing what it watches

Edit the `REPOS` list at the top of `watch.py` and push. Each entry is
`("owner/repo", ["label", "label"])`. Labels vary between projects — numpy uses
`sprintable`, matplotlib uses `first-contribution`, most others use
`good first issue` or `help wanted`.

## Things worth knowing

- **Scheduled runs can be late.** GitHub delays cron jobs when busy; 30 minutes
  can become 45. Fine for this purpose.
- **Actions disables cron on repos with no activity for 60 days.** This one
  commits its state back on every run, so it stays active by itself.
- **API budget.** Listing issues is cheap; the "really free?" checks are not.
  Only issues never evaluated before get deep-checked, so a run costs ~25 API
  calls rather than several hundred.
- **Failed API calls are fail-safe.** If a check errors, the issue is left
  unrecorded and re-checked next run, rather than being wrongly announced.

## Running it locally instead

```bash
GITHUB_TOKEN=$(gh auth token) NTFY_TOPIC=your-topic python watch.py
```
