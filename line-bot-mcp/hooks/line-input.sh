#!/usr/bin/env bash
# UserPromptSubmit hook: drain ~/.claude/line_inbox.jsonl and inject
# `[line] owner: ...` lines into the prompt. Display-only and AWS-independent
# (reads only the local file the poller writes), so it stays well within the 3s
# hook timeout and runs on the system python3 (stdlib only). It coordinates with
# the poller via a sidecar lockfile so a rename cannot interleave with an
# in-progress append (rename ignores flock on the inbox inode itself).
#
# Install: copy to ~/.claude/hooks/ and add to ~/.claude/settings.json
#   { "type": "command", "command": "$HOME/.claude/hooks/line-input.sh", "timeout": 3 }

inbox="${LINE_INBOX_JSONL:-$HOME/.claude/line_inbox.jsonl}"
[ -s "$inbox" ] || exit 0

python3 - "$inbox" "$HOME/.claude/line_seen.txt" <<'PY'
import fcntl
import json
import os
import sys

inbox, seen_path = sys.argv[1], sys.argv[2]
tmp = inbox + ".draining"
lock_path = inbox + ".lock"
_SEEN_CAP = 1000

# Hold the same sidecar lock the poller uses, across rename+read+remove, so the
# poller's append can't interleave with our rename (which ignores flock).
try:
    lock = open(lock_path, "w")
except OSError:
    sys.exit(0)
lines = []
try:
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        os.rename(inbox, tmp)
    except OSError:
        sys.exit(0)  # nothing to drain (or another drainer won the race)
    try:
        lines = open(tmp, encoding="utf-8").read().splitlines()
    except OSError:
        lines = []
    try:
        os.remove(tmp)
    except OSError:
        pass
finally:
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()

try:
    seen = open(seen_path).read().split()
except OSError:
    seen = []
seen_set = set(seen)

out, new_ids = [], []
for ln in lines:
    ln = ln.strip()
    if not ln:
        continue
    try:
        m = json.loads(ln)
    except ValueError:
        continue
    mid = m.get("message_id", "")
    if mid and mid in seen_set:
        continue
    if mid:
        seen_set.add(mid)
        new_ids.append(mid)
    person = m.get("person", "owner")
    mtype = m.get("type", "text")  # legacy rows have no type -> treat as text
    text = (m.get("text", "") or "").replace("\n", " ").replace("\r", " ").strip()
    media_path = m.get("media_path", "")
    if mtype == "image":
        if media_path:
            out.append("[line] %s が画像を送信（保存: %s）。fetch_line_image で見れる" % (person, media_path))
        else:
            out.append("[line] %s が画像を送信（未取得）" % person)
    elif mtype == "audio":
        if text:
            out.append("[line] %s（音声）: %s" % (person, text))
        else:
            out.append("[line] %s が音声を送信（未取得）" % person)
    elif mtype == "text":
        out.append("[line] %s: %s" % (person, text))
    else:
        out.append("[line] %s: （未対応のメッセージ: %s）" % (person, mtype))

if new_ids:
    combined = seen + new_ids
    if len(combined) > _SEEN_CAP:
        combined = combined[-_SEEN_CAP:]  # bound the on-disk seen set
    try:
        with open(seen_path, "w", encoding="utf-8") as sf:
            sf.write("\n".join(combined) + "\n")
    except OSError:
        pass
if out:
    print("\n".join(out))
PY
