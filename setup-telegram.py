# -*- coding: utf-8 -*-
"""One-time Telegram setup helper.

Finds your chat ID, sends a test message, and prints the two `gh secret set`
commands to run. Your bot token stays on this machine -- it is only sent to
Telegram's own API.

Usage:
    python setup-telegram.py <your-bot-token>
"""
import json
import sys
import urllib.request


def api(token, method, params=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(params).encode() if params else None
    headers = {"Content-Type": "application/json"} if params else {}
    req = urllib.request.Request(url, data=data, headers=headers)
    return json.load(urllib.request.urlopen(req, timeout=30))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    token = sys.argv[1].strip()

    try:
        me = api(token, "getMe")
    except Exception as exc:  # noqa: BLE001
        print(f"Could not reach Telegram with that token: {exc}")
        print("Double-check you copied the whole token from @BotFather.")
        return 1
    if not me.get("ok"):
        print("Telegram rejected that token.")
        return 1
    print(f"Bot found: @{me['result']['username']}")

    updates = api(token, "getUpdates")
    chats = {}
    for u in updates.get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        chat = msg.get("chat")
        if chat:
            chats[chat["id"]] = chat.get("first_name") or chat.get("title") or "chat"

    if not chats:
        print()
        print("No messages seen yet.")
        print(f"Open Telegram, search for @{me['result']['username']},")
        print("press Start (or send it any message), then run this again.")
        return 1

    chat_id, name = next(iter(chats.items()))
    print(f"Chat found: {name} (id {chat_id})")

    api(token, "sendMessage", {
        "chat_id": chat_id,
        "text": "GSoC watcher connected. You'll get a message here whenever a "
                "new issue becomes free to claim.",
    })
    print("Test message sent -- check Telegram.")
    print()
    print("Now run these two commands:")
    print()
    print(f'  gh secret set TELEGRAM_TOKEN --body "{token}"')
    print(f'  gh secret set TELEGRAM_CHAT_ID --body "{chat_id}"')
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
