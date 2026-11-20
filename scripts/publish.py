#!/usr/bin/env python3
"""out/<날짜>/manifest.json 을 읽어 인스타그램에 올린다.

필요한 환경 변수 (GitHub Secrets/Variables):
  IG_ACCESS_TOKEN  인스타그램(메타) 액세스 토큰
  IG_USER_ID       인스타그램 프로페셔널 계정 ID
  GRAPH_HOST       graph.facebook.com (페이스북 로그인으로 받은 토큰) 또는 graph.instagram.com
  GRAPH_VERSION    기본 v26.0
  MEDIA_BASE_URL   캐러셀 그림이 올라간 공개 주소 (GitHub Pages)  예) https://hyunmu81.github.io/textmon-insta
  DRY_RUN=1        실제로 올리지 않고 확인만

사용: python scripts/publish.py out/2026-11-21
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def log(msg):
    print(msg, flush=True)


TOKEN = os.environ.get("IG_ACCESS_TOKEN", "").strip()
IG_ID = os.environ.get("IG_USER_ID", "").strip()
HOST = os.environ.get("GRAPH_HOST", "").strip() or "graph.facebook.com"
VER = os.environ.get("GRAPH_VERSION", "").strip() or "v26.0"
BASE = f"https://{HOST}/{VER}"
DRY = os.environ.get("DRY_RUN", "") == "1"


def call(method, path_or_url, params=None, data=None, headers=None, timeout=300):
    url = path_or_url if path_or_url.startswith("http") else f"{BASE}/{path_or_url}"
    params = dict(params or {})
    hdrs = dict(headers or {})
    body = None
    if data is not None:          # 동영상 바이트
        body = data
    elif method == "POST":
        params["access_token"] = TOKEN
        body = urllib.parse.urlencode(params).encode()
        params = {}
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    else:
        params["access_token"] = TOKEN
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=body, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise SystemExit(f"인스타 API 오류 {e.code}: {detail}")


def wait_ready(cid, label, limit=900):
    t0 = time.time()
    while True:
        r = call("GET", cid, {"fields": "status_code,status"})
        st = r.get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise SystemExit(f"{label} 처리 실패: {r}")
        if time.time() - t0 > limit:
            raise SystemExit(f"{label} 처리가 {limit}초 안에 끝나지 않았어요: {r}")
        time.sleep(8)


def wait_url(url, limit=600):
    """GitHub Pages 에 그림이 실제로 뜰 때까지 기다린다."""
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(10)
    raise SystemExit(f"공개 주소에서 그림을 찾지 못했어요: {url}")


def publish(cid):
    r = call("POST", f"{IG_ID}/media_publish", {"creation_id": cid})
    mid = r.get("id")
    link = call("GET", mid, {"fields": "permalink"}).get("permalink", "")
    return mid, link


def do_reel(out, man):
    video = out / man["video"]
    size = video.stat().st_size
    log(f"릴스 올리기: {video.name} ({size / 1e6:.1f}MB)")
    r = call("POST", f"{IG_ID}/media", {
        "media_type": "REELS", "upload_type": "resumable", "caption": man["caption"],
        "share_to_feed": "true", "thumb_offset": str(man.get("thumb_offset_ms", 600)),
    })
    cid, uri = r["id"], r.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{VER}/{r['id']}"
    call("POST", uri, data=video.read_bytes(), headers={
        "Authorization": f"OAuth {TOKEN}", "offset": "0", "file_size": str(size),
        "Content-Type": "application/octet-stream"})
    wait_ready(cid, "릴스")
    return publish(cid)


def do_carousel(out, man, date):
    base = os.environ.get("MEDIA_BASE_URL", "").rstrip("/")
    if not base:
        raise SystemExit("MEDIA_BASE_URL 이 없어요 (GitHub Pages 주소).")
    urls = [f"{base}/{date}/{name}" for name in man["images"]]
    wait_url(urls[-1])
    kids = []
    for i, u in enumerate(urls, 1):
        log(f"캐러셀 {i}/{len(urls)}: {u}")
        r = call("POST", f"{IG_ID}/media", {"image_url": u, "is_carousel_item": "true"})
        kids.append(r["id"])
    for k in kids:
        wait_ready(k, "캐러셀 그림", limit=300)
    r = call("POST", f"{IG_ID}/media", {
        "media_type": "CAROUSEL", "children": ",".join(kids), "caption": man["caption"]})
    wait_ready(r["id"], "캐러셀", limit=300)
    return publish(r["id"])


def main():
    out = Path(sys.argv[1])
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    date = man.get("date") or out.name
    if DRY:
        log(f"[확인만] {date} {man['media_type']} — 실제로 올리지 않았어요.")
        return
    if not TOKEN or not IG_ID:
        raise SystemExit("IG_ACCESS_TOKEN / IG_USER_ID 비밀값이 없어요.")
    if man["media_type"] == "REELS":
        mid, link = do_reel(out, man)
    else:
        mid, link = do_carousel(out, man, date)
    log(f"올림 완료: {link or mid}")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"permalink={link or mid}\n")


if __name__ == "__main__":
    main()
