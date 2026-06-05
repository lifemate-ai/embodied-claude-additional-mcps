#!/usr/bin/env bash
# UserPromptSubmit hook: drain ~/.claude/line_inbox.jsonl and inject
# `[line] kouta: ...` lines into the prompt. AWS-independent (reads only the
# local file the poller writes) so it stays well within the 3s hook timeout
# and runs on the system python3 (3.9.6, stdlib only).
#
# Install: copy to ~/.claude/hooks/ and add to ~/.claude/settings.json
#   { "type": "command", "command": "$HOME/.claude/hooks/line-input.sh", "timeout": 3 }

inbox="${LINE_INBOX_JSONL:-$HOME/.claude/line_inbox.jsonl}"
[ -s "$inbox" ] || exit 0

tmp="$inbox.draining.$$"
mv "$inbox" "$tmp" 2>/dev/null || exit 0

python3 - "$tmp" "$HOME/.claude/line_seen.txt" <<'PY'
import json, sys

src, seen_path = sys.argv[1], sys.argv[2]
try:
    seen = set(open(seen_path).read().split())
except OSError:
    seen = set()

out, new_ids = [], []
for ln in open(src, encoding="utf-8"):
    ln = ln.strip()
    if not ln:
        continue
    try:
        m = json.loads(ln)
    except ValueError:
        continue
    mid = m.get("message_id", "")
    if mid and mid in seen:
        continue
    if mid:
        seen.add(mid)
        new_ids.append(mid)
    out.append("[line] %s: %s" % (m.get("person", "kouta"), m.get("text", "")))

if new_ids:
    with open(seen_path, "a", encoding="utf-8") as sf:
        sf.write("\n".join(new_ids) + "\n")
if out:
    print("\n".join(out))
PY

rm -f "$tmp"
