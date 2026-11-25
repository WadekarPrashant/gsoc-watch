# -*- coding: utf-8 -*-
"""GSoC issue watcher - cloud edition (runs on GitHub Actions).

Finds newcomer-friendly issues that are genuinely free to claim and pushes a
phone notification via ntfy.sh when a new one appears.

Efficiency note: listing issues is cheap, but the "is it really free?" checks
(timeline + comments, 2 calls each) are not. So we only deep-check issue
numbers we have never seen before. A typical run costs ~25 API calls instead
of several hundred, which keeps us well inside the Actions token's hourly
limit.

Env vars:
  GITHUB_TOKEN  required - provided automatically by Actions
  NTFY_TOPIC    required - your private ntfy topic name
  NTFY_SERVER   optional - defaults to https://ntfy.sh
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "seen.json")
LATEST = os.path.join(HERE, "latest.md")

TOKEN = os.environ.get("GITHUB_TOKEN", "")
# Telegram is used when a bot token is present; ntfy is the fallback.
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")

REPOS = [
    ("zulip/zulip", ["help wanted"]),
    ("zulip/python-zulip-api", ["help wanted", "good first issue"]),
    ("zulip/zulip-terminal", ["help wanted", "good first issue"]),
    ("RocketChat/Rocket.Chat", ["good first issue", "help wanted"]),
    ("oppia/oppia", ["good first issue", "starter issue"]),
    ("OWASP/Nest", ["good first issue", "help wanted"]),
    ("numpy/numpy", ["sprintable"]),
    ("matplotlib/matplotlib", ["first-contribution", "Difficulty: Easy"]),
    ("pandas-dev/pandas", ["good first issue"]),
    ("scikit-learn/scikit-learn", ["good first issue", "Easy"]),
]

CLAIM = re.compile(
    r"(@\w*bot\s+claim|\bclaim(ing|ed)?\b|\bi.{0,3}ll take\b|working on (this|it)|"
    r"assign (this )?to me|like to work on|can i work|i am working|i.{0,3}m working|"
    r"picking (this )?up|started work)", re.I)
ABANDON = re.compile(
    r"(abandon|unassigned from this issue|no longer (working|active)|"
    r"not working on (this|it)|dropping this|free to (take|claim))", re.I)

# Experienced contributors often file a bug AND say in the report that they
# intend to fix it themselves. Such an issue looks completely unclaimed --
# no assignee, no PR, no claim comment -- but taking it means stepping on
# the reporter. Matched against the issue body, and against comments by the
# issue's own author.
SELF_PR = re.compile(
    r"((i|we)\s*(can|will|'ll|would be happy to|am happy to|intend to|plan to|"
    r"would like to|plan on)\s*(open|submit|send|file|put up|raise|make|"
    r"prepare|do)\s*(a|the|my)?\s*(pr|pull request|patch|fix)|"
    r"\bpr incoming\b|\bpatch incoming\b|i have a (fix|patch|pr)\b|"
    r"(i|we)\s*(can|will|'ll)\s*fix (this|it)\b)", re.I)


def api(path, retries=2):
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Authorization": f"Bearer {TOKEN}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "gsoc-watch"})
    for attempt in range(retries + 1):
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except Exception as exc:  # noqa: BLE001
            if attempt == retries:
                print(f"  ! {exc} ({path[:70]})", flush=True)
                return None
            time.sleep(2 * (attempt + 1))
    return None


def is_free(repo, num, body="", author=""):
    """Expensive check: no open linked PR, and no live claim.

    Returns True/False, or None if the API calls failed. None matters: a
    failed call must NOT be read as "free", and the issue must stay unseen
    so the next run re-checks it.
    """
    # The reporter said in the report that they will fix it themselves.
    if SELF_PR.search(body or ""):
        return False

    timeline = api(f"/repos/{repo}/issues/{num}/timeline?per_page=100")
    if timeline is None:
        return None
    for ev in timeline:
        if ev.get("event") in ("cross-referenced", "connected"):
            src = (ev.get("source") or {}).get("issue") or {}
            if src.get("pull_request") and src.get("state") == "open":
                return False

    comments = api(f"/repos/{repo}/issues/{num}/comments?per_page=100")
    if comments is None:
        return None
    last_claim = last_release = None
    for c in comments:
        cbody = c.get("body") or ""
        # The reporter following up to say they are taking it themselves.
        if author and c["user"]["login"] == author and SELF_PR.search(cbody):
            return False
        if ABANDON.search(cbody):
            last_release = c["created_at"]
        elif CLAIM.search(cbody):
            last_claim = c["created_at"]
    if last_claim is None:
        return True
    if last_release and last_release > last_claim:
        return True
    age = (datetime.now(timezone.utc)
           - datetime.fromisoformat(last_claim.replace("Z", "+00:00"))).days
    return age > 45


def send_telegram(new):
    lines = ["*New GSoC issue%s free to claim*" % ("s" if len(new) > 1 else ""), ""]
    for i in new[:10]:
        title = (i["title"].replace("[", "(").replace("]", ")")
                 .replace("*", "").replace("_", "").replace("`", ""))
        lines.append(f"[{i['repo']}#{i['num']}]({i['url']})")
        lines.append(f"{title}")
        lines.append("")
    if len(new) > 10:
        lines.append(f"...and {len(new) - 10} more")
    payload = json.dumps({
        "chat_id": TG_CHAT,
        "text": "\n".join(lines),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30)


def send_ntfy(new):
    if len(new) == 1:
        i = new[0]
        title, body, click = f"Free issue: {i['repo']}", f"#{i['num']} {i['title']}", i["url"]
    else:
        title = f"{len(new)} free GSoC issues"
        body = "\n".join(f"{i['repo']}#{i['num']} {i['title'][:70]}" for i in new[:5])
        click = new[0]["url"]
    req = urllib.request.Request(
        f"{NTFY_SERVER}/{NTFY_TOPIC}", data=body.encode("utf-8"),
        headers={"Title": title.encode("ascii", "replace").decode(),
                 "Priority": "high", "Tags": "rocket", "Click": click})
    urllib.request.urlopen(req, timeout=30)


def notify(new):
    sent = False
    if TG_TOKEN and TG_CHAT:
        try:
            send_telegram(new)
            print(f"telegram: pushed {len(new)} issue(s)", flush=True)
            sent = True
        except Exception as exc:  # noqa: BLE001
            print(f"  ! telegram failed: {exc}", flush=True)
    if NTFY_TOPIC:
        try:
            send_ntfy(new)
            print(f"ntfy: pushed {len(new)} issue(s)", flush=True)
            sent = True
        except Exception as exc:  # noqa: BLE001
            print(f"  ! ntfy failed: {exc}", flush=True)
    if not sent:
        print("WARNING: no notification channel configured or all failed", flush=True)


def main():
    if not TOKEN:
        print("ERROR: GITHUB_TOKEN not set")
        return 1

    # --test exercises the notification path itself. Worth having: an ordinary
    # run only calls notify() when something new turns up, so a misnamed secret
    # would otherwise stay hidden until the first real alert failed silently.
    if "--test" in sys.argv:
        print("Sending a test notification...", flush=True)
        notify([{
            "repo": "zulip/zulip-terminal", "num": 687,
            "title": "TEST - notification path is working",
            "url": "https://github.com/zulip/zulip-terminal/issues/687",
        }])
        return 0

    state = {"seen": [], "free": []}
    if os.path.exists(STATE):
        try:
            state = json.load(open(STATE, encoding="utf-8"))
        except (OSError, ValueError):
            pass
    seen = set(state.get("seen", []))
    first_run = not seen

    # Cheap pass: list candidate issues.
    candidates = {}
    for repo, labels in REPOS:
        for label in labels:
            for it in api(f"/repos/{repo}/issues?state=open&assignee=none"
                          f"&labels={urllib.parse.quote(label)}"
                          "&sort=created&direction=desc&per_page=40") or []:
                if "pull_request" in it:
                    continue
                candidates[f"{repo}#{it['number']}"] = {
                    "repo": repo, "num": it["number"], "title": it["title"],
                    "url": it["html_url"], "created": it["created_at"][:10],
                    "body": it.get("body") or "",
                    "author": (it.get("user") or {}).get("login", ""),
                }

    # Expensive pass: only on keys we have never evaluated.
    unseen = [k for k in candidates if k not in seen]
    print(f"{len(candidates)} candidate(s), {len(unseen)} never checked before",
          flush=True)

    new_free = []
    evaluated = set()
    for key in unseen:
        c = candidates[key]
        verdict = is_free(c["repo"], c["num"], c.get("body", ""), c.get("author", ""))
        if verdict is None:
            continue          # leave unseen; re-check next run
        evaluated.add(key)
        if verdict:
            new_free.append(c)

    still_free = [candidates[k] for k in state.get("free", []) if k in candidates]
    all_free = still_free + new_free

    # Only record issues we actually managed to evaluate.
    json.dump({"seen": sorted(seen | evaluated),
               "free": sorted({f"{i['repo']}#{i['num']}" for i in all_free}),
               "updated": datetime.now(timezone.utc).isoformat()},
              open(STATE, "w", encoding="utf-8"), indent=1)

    with open(LATEST, "w", encoding="utf-8") as fh:
        fh.write(f"# GSoC watcher\n\nLast run: "
                 f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n\n")
        if new_free and not first_run:
            fh.write(f"## New this run ({len(new_free)})\n\n")
            for i in new_free:
                fh.write(f"- **[{i['repo']}#{i['num']}]({i['url']})** {i['title']}\n")
            fh.write("\n")
        fh.write(f"## Currently free ({len(all_free)})\n\n")
        for i in sorted(all_free, key=lambda x: (x["repo"], -x["num"])):
            fh.write(f"- [{i['repo']}#{i['num']}]({i['url']}) {i['title']}\n")

    if first_run:
        print(f"First run: recorded {len(all_free)} free issue(s), no push.",
              flush=True)
    elif new_free:
        print(f"{len(new_free)} NEW free issue(s)", flush=True)
        for i in new_free:
            print(f"   {i['repo']}#{i['num']} {i['title'][:70]}", flush=True)
        notify(new_free)
    else:
        print(f"No new issues ({len(all_free)} still free)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
