#!/usr/bin/env python3
"""이번 실행에서 어떤 날짜를 만들고, 인스타에 올릴지 정한다 (GitHub Actions 용)."""
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
event = os.environ.get("EVENT", "")
inp_date = os.environ.get("INPUT_DATE", "").strip()
inp_pub = os.environ.get("INPUT_PUBLISH", "") == "true"
today = datetime.now(KST).strftime("%Y-%m-%d")
posted = Path("posted.md").read_text(encoding="utf-8") if Path("posted.md").exists() else ""

date, publish, reason = "", False, ""
if event == "schedule":
    # 저녁 8~11시 사이 여러 번 실행된다. GitHub 예약 실행이 늦어져 자정을 넘기면 전날 게시물을 올린다.
    now = datetime.now(KST)
    target = now - timedelta(days=1) if now.hour < 6 else now
    date, publish = target.strftime("%Y-%m-%d"), True
elif event == "workflow_dispatch":
    date, publish = inp_date or today, inp_pub
elif event == "push":   # 올린 파일 미리보기만
    before, sha = os.environ.get("BEFORE", ""), os.environ.get("SHA", "")
    try:
        names = subprocess.run(["git", "diff", "--name-only", before, sha, "--", "posts/"],
                               capture_output=True, text=True, check=True).stdout.split()
    except Exception:
        names = []
    dates = sorted({n.split("/")[1] for n in names if n.count("/") >= 2})
    date = dates[-1] if dates else ""

post = Path("posts") / date / "post.json" if date else None
if not date or not post.exists():
    reason = f"{date or '날짜 없음'} 게시물(post.json)이 없어요"
    date, publish = "", False
elif publish and f"| {date} |" in posted:
    reason = f"{date} 는 이미 올렸어요"
    publish = False

media = ""
if date:
    try:
        media = str(json.loads(post.read_text(encoding="utf-8")).get("media_type", "")).upper()
    except Exception:
        media = ""
print(f"날짜={date or '-'} 올리기={publish} 형식={media or '-'} {reason}")
with open(os.environ["GITHUB_OUTPUT"], "a") as f:
    f.write(f"date={date}\npublish={'true' if publish else 'false'}\nmedia={media}\n")
