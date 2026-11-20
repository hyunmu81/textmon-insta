#!/usr/bin/env python3
"""텍스트몬 인스타 게시물 만들기.

posts/<날짜>/post.json 을 읽어
  - REELS    → reel.mp4 (1080x1920, 30fps, H.264 + AAC)
  - CAROUSEL → carousel_01.jpg ... (1080x1350)
을 만들고, 올리기에 필요한 정보를 manifest.json 에 적는다.

사용: python scripts/render.py posts/2026-11-21 out/2026-11-21
"""
import base64
import json
import math
import os
import re
import subprocess
import sys
import urllib.request
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"

# 브랜드 색 (dreamReader public/js/textmon/textmon-tokens.css)
PAPER = (255, 251, 242)      # --tm-paper
BRAND = (249, 115, 22)       # --tm-brand
BRAND_DARK = (194, 65, 12)   # --tm-brand-dark
BRAND_LIGHT = (253, 186, 116)
BRAND_BG = (255, 244, 232)   # --tm-brand-bg
INK = (31, 42, 55)           # --tm-ink
LINE = (241, 228, 209)

FPS = 30
XFADE = 0.25          # 장면 사이 겹침(초)
TEXT_IN = 0.35        # 글자 나타나는 시간(초)
SITE = "www.textmon.com"


def log(msg):
    print(msg, flush=True)


# ───────────────────────── 글꼴 ─────────────────────────
_font_cache = {}


def font(weight, size):
    key = (weight, size)
    if key in _font_cache:
        return _font_cache[key]
    if weight == "logo":
        f = ImageFont.truetype(str(FONTS / "Fredoka.ttf"), size)
        try:
            f.set_variation_by_name("SemiBold")
        except Exception:
            pass
    else:
        name = {"xbold": "Pretendard-ExtraBold.otf", "bold": "Pretendard-Bold.otf",
                "semi": "Pretendard-SemiBold.otf"}[weight]
        f = ImageFont.truetype(str(FONTS / name), size)
    _font_cache[key] = f
    return f


def text_w(f, s):
    return f.getlength(s)


def wrap(f, text, max_w):
    """한글 줄바꿈: 띄어쓰기 기준, 너무 긴 낱말은 글자 단위로 자른다. \\n 은 그대로 줄바꿈."""
    lines = []
    for para in str(text).split("\n"):
        words = para.split(" ")
        cur = ""
        for w in words:
            cand = (cur + " " + w).strip()
            if text_w(f, cand) <= max_w:
                cur = cand
                continue
            if cur:
                lines.append(cur)
            cur = ""
            while text_w(f, w) > max_w:  # 긴 낱말
                cut = len(w)
                while cut > 1 and text_w(f, w[:cut]) > max_w:
                    cut -= 1
                lines.append(w[:cut])
                w = w[cut:]
            cur = w
        lines.append(cur)
    return [l for l in lines if l.strip() != ""] or [""]


def draw_lines(draw, lines, f, x, y, fill, line_h, align="left", box_w=None):
    for i, line in enumerate(lines):
        lx = x
        if align == "center":
            lx = x + (box_w - text_w(f, line)) / 2
        draw.text((lx, y + i * line_h), line, font=f, fill=fill)


# ───────────────────────── 그림 도구 ─────────────────────────
def paper(w, h):
    im = Image.new("RGBA", (w, h), PAPER + (255,))
    d = ImageDraw.Draw(im)
    for y in range(140, h, 72):          # 공책 줄
        d.line([(0, y), (w, y)], fill=LINE + (255,), width=2)
    d.line([(96, 0), (96, h)], fill=BRAND_LIGHT + (150,), width=3)   # 여백 선
    return im


def cover_fit(img, w, h, scale=1.0):
    img = img.convert("RGBA")
    s = max(w / img.width, h / img.height) * scale
    nw, nh = max(1, int(img.width * s)), max(1, int(img.height * s))
    r = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return r.crop((left, top, left + w, top + h))


def top_scrim(w, h, reach):
    """위쪽을 종이색으로 덮어 글자가 잘 보이게 하는 그라데이션."""
    a = np.zeros((h, w), dtype=np.uint8)
    ys = np.arange(reach)
    a[:reach, :] = (235 * (1 - ys / reach) ** 1.4).astype(np.uint8)[:, None]
    layer = Image.new("RGBA", (w, h), PAPER + (0,))
    layer.putalpha(Image.fromarray(a))
    return layer


def with_alpha(layer, k):
    if k >= 0.999:
        return layer
    r, g, b, a = layer.split()
    a = a.point(lambda v: int(v * max(0.0, k)))
    return Image.merge("RGBA", (r, g, b, a))


def ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def rounded_icon(size):
    p = ASSETS / "brand" / "icon-512.png"
    icon = Image.open(p).convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.24), fill=255)
    icon.putalpha(mask)
    return icon


def logo_small(h=54):
    mark = Image.open(ASSETS / "brand" / "mark.png").convert("RGBA")
    mw = int(mark.width * h / mark.height)
    mark = mark.resize((mw, h), Image.LANCZOS)
    f = font("logo", int(h * 0.82))
    tw = int(text_w(f, "textmon")) + 4
    im = Image.new("RGBA", (mw + 14 + tw, h + 10), (0, 0, 0, 0))
    im.alpha_composite(mark, (0, 5))
    ImageDraw.Draw(im).text((mw + 14, int(h * 0.02)), "textmon", font=f, fill=INK + (255,))
    return im


# ───────────────────────── 소재 읽기 ─────────────────────────
def resolve_asset(raw, post_dir):
    """asset 값 해석.
    character/kid.webp            → 캐릭터 원본
    character/kid.webp > character/kid-happy.webp → 표정 바꾸기
    brand/mark.png                → 로고
    scene2.jpg                    → 게시물 폴더의 그림
    video:clip1.mp4               → 게시물 폴더의 영상
    없거나 못 찾으면              → 종이 배경(글자만)
    """
    raw = (raw or "").split("|")[0].strip()
    if not raw or raw.startswith("new:"):
        if raw.startswith("new:"):
            log(f"  ! 아직 그림 파일이 없는 장면이 있어요 ({raw[:40]}…) → 글자 화면으로 만듭니다")
        return {"kind": "none"}
    if raw.startswith("video:"):
        p = post_dir / raw[6:].strip()
        if p.exists():
            return {"kind": "video", "path": p}
        log(f"  ! 영상 파일이 없어요: {p.name} → 글자 화면으로 만듭니다")
        return {"kind": "none"}
    parts = [x.strip() for x in raw.split(">") if x.strip()]
    imgs, kind = [], "char"
    for part in parts:
        if part.startswith("character/") or part.startswith("brand/"):
            p = ASSETS / part
        else:
            p = post_dir / part
            kind = "image"
        if not p.exists():
            log(f"  ! 그림 파일이 없어요: {part} → 건너뜁니다")
            continue
        im = Image.open(p).convert("RGBA")
        if kind == "char" and part.startswith("brand/"):
            kind = "brand"
        imgs.append(im)
    if not imgs:
        return {"kind": "none"}
    # 투명 배경이 아닌 사진이면 화면 가득
    if kind == "char":
        a = np.array(imgs[0].split()[3])
        if a.min() > 250:
            kind = "image"
    return {"kind": kind, "imgs": imgs}


class VideoReader:
    def __init__(self, path, w, h):
        self.w, self.h = w, h
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS}"
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-vf", vf, "-f", "rawvideo",
                                   "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        self.last = Image.new("RGBA", (w, h), PAPER + (255,))

    def next(self):
        buf = self.p.stdout.read(self.w * self.h * 3)
        if buf and len(buf) == self.w * self.h * 3:
            self.last = Image.frombytes("RGB", (self.w, self.h), buf).convert("RGBA")
        return self.last

    def close(self):
        try:
            self.p.stdout.close()
            self.p.kill()
        except Exception:
            pass


# ───────────────────────── 목소리 (Gemini TTS) ─────────────────────────
def tts(text):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    text = (text or "").replace("\n", " ").strip()
    if not key or not text:
        return None, 24000
    model = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
    voice = os.environ.get("GEMINI_TTS_VOICE", "Kore")
    style = os.environ.get(
        "GEMINI_TTS_STYLE",
        "차분하고 따뜻한 한국어 목소리로, 쉼표마다 숨을 쉬듯 짧게 쉬면서 또박또박 천천히 읽어 주세요. "
        "몰아서 읽지 말고, 울리지 않는 자연스러운 목소리로 읽어 주세요.")
    body = {
        "contents": [{"parts": [{"text": f"{style}\n\n{text}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                res = json.loads(r.read())
            part = res["candidates"][0]["content"]["parts"][0]["inlineData"]
            rate = 24000
            m = re.search(r"rate=(\d+)", part.get("mimeType", ""))
            if m:
                rate = int(m.group(1))
            pcm = np.frombuffer(base64.b64decode(part["data"]), dtype="<i2")
            return pcm, rate
        except Exception as e:  # noqa: BLE001
            log(f"  ! 목소리 만들기 실패 ({attempt + 1}/3): {e}")
    return None, 24000


# ───────────────────────── 릴스 ─────────────────────────
def split_subs(text, f, max_w):
    """자막 덩어리: 한 덩어리가 두 줄을 넘지 않게 문장·쉼표 단위로 나눈다."""
    text = (text or "").replace("\n", " ").strip()
    if not text:
        return []
    pieces = [p.strip() for p in re.split(r"(?<=[.?!。])\s+", text) if p.strip()]
    out = []
    for p in pieces:
        if len(wrap(f, p, max_w)) <= 2:
            out.append(p)
            continue
        cur = ""
        for c in [c.strip() for c in re.split(r"(?<=,)\s*", p) if c.strip()]:
            cand = (cur + " " + c).strip()
            if cur and len(wrap(f, cand, max_w)) > 2:
                out.append(cur)
                cur = c
            else:
                cur = cand
        if cur:
            out.append(cur)
    return out


def headline_layer(w, h, text, center=False):
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if not text:
        return layer
    d = ImageDraw.Draw(layer)
    if center:   # 그림 없는 장면: 화면 가운데에 크게
        size = 118 if len(text) <= 10 else 100
        f = font("xbold", size)
        lines = wrap(f, text, w - 220)
        lh = int(size * 1.26)
        y = 860 - lh * len(lines) // 2
        d.rounded_rectangle([110, y - 56, 196, y - 42], radius=7, fill=BRAND + (255,))
        draw_lines(d, lines, f, 110, y, INK + (255,), lh)
        return layer
    size = 92 if len(text) <= 12 else 80
    f = font("xbold", size)
    lines = wrap(f, text, w - 200)
    lh = int(size * 1.28)
    y = 330
    d.rounded_rectangle([100, y - 44, 172, y - 32], radius=6, fill=BRAND + (255,))
    draw_lines(d, lines, f, 100, y, INK + (255,), lh)
    return layer


def subtitle_layer(w, h, text):
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if not text:
        return layer
    d = ImageDraw.Draw(layer)
    f = font("semi", 46)
    lines = wrap(f, text, w - 260)
    lh = 64
    bw = max(text_w(f, l) for l in lines) + 64
    bh = lh * len(lines) + 34
    x0 = (w - bw) / 2
    y0 = 1540 - bh   # 인스타 아래쪽 글자·버튼 자리를 피함
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=24, fill=INK + (215,))
    draw_lines(d, lines, f, x0 + 32, y0 + 14, (255, 255, 255, 255), lh)
    return layer


def end_layer(w, h, text):
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    icon = rounded_icon(280)
    layer.alpha_composite(icon, ((w - 280) // 2, 470))
    d = ImageDraw.Draw(layer)
    f = font("logo", 92)
    d.text(((w - text_w(f, "textmon")) / 2, 780), "textmon", font=f, fill=INK + (255,))
    y = 960
    if text:
        hf = font("xbold", 72)
        lines = wrap(hf, text, w - 200)
        draw_lines(d, lines, hf, 100, y, INK + (255,), 94, align="center", box_w=w - 200)
        y += 94 * len(lines)
    f2 = font("semi", 40)
    d.text(((w - text_w(f2, SITE)) / 2, y + 30), SITE, font=f2, fill=BRAND_DARK + (255,))
    return layer


def place_char(frame, img, motion, t, dur, end=False):
    w, h = frame.size
    target_h = 520 if end else 640
    s = min(target_h / img.height, 4.2)
    if motion == "zoom_in":
        s *= 1.0 + 0.08 * ease_out(t / max(dur, 0.1))
    if motion == "bounce":
        s *= 1.0 + 0.05 * abs(math.sin(t * math.pi * 1.6))
    im = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)
    if motion == "shake":
        im = im.rotate(4 * math.sin(t * math.pi * 1.4), resample=Image.BICUBIC, expand=True)
    dy = 0
    if motion == "bounce":
        dy = -int(26 * abs(math.sin(t * math.pi * 1.6)))
    cx, base = w // 2, (1040 if end else 1330)
    # 그림자
    sm = Image.new("L", (w, h), 0)
    ImageDraw.Draw(sm).ellipse([cx - im.width * 0.36, base - 18, cx + im.width * 0.36, base + 18], fill=45)
    sh = Image.new("RGBA", (w, h), INK + (0,))
    sh.putalpha(sm.filter(ImageFilter.GaussianBlur(8)))
    frame.alpha_composite(sh)
    frame.alpha_composite(im, (int(cx - im.width / 2), int(base - im.height + dy)))


def render_reel(post, post_dir, out_dir):
    W, H = 1080, 1920
    reel = post.get("reel") or {}
    scenes = sorted(reel.get("scenes") or [], key=lambda s: s.get("order", 0))
    if not scenes:
        raise SystemExit("reel.scenes 가 비어 있어요.")

    bg = paper(W, H)
    gm = Image.new("L", (W, H), 0)
    ImageDraw.Draw(gm).ellipse([W / 2 - 420, 640, W / 2 + 420, 1480], fill=255)
    glow = Image.new("RGBA", (W, H), (255, 236, 214, 0))
    glow.putalpha(gm.filter(ImageFilter.GaussianBlur(70)))
    logo = logo_small()
    sub_font = font("semi", 46)

    # 1) 장면마다 목소리·길이 정하기
    plan = []
    for i, sc in enumerate(scenes):
        want = float(sc.get("end", 0)) - float(sc.get("start", 0))
        if want <= 0:
            want = 3.0
        pcm, rate = tts(sc.get("narration"))
        voice_len = (len(pcm) / rate) if pcm is not None else 0.0
        dur = max(want, voice_len + 0.6 if voice_len else want, 1.2)
        plan.append({"sc": sc, "dur": dur, "pcm": pcm, "rate": rate, "voice_len": voice_len,
                     "vis": resolve_asset(sc.get("asset"), post_dir),
                     "last": i == len(scenes) - 1})
        log(f"  장면 {i + 1}: {dur:.1f}초  목소리 {voice_len:.1f}초  소재 {plan[-1]['vis']['kind']}")
    total = sum(p["dur"] for p in plan)
    if total > 90:
        log(f"  ! 전체 {total:.0f}초 — 90초를 넘지 않게 장면을 줄여 주세요")

    # 2) 목소리 한 줄로 이어 붙이기 (48kHz)
    SR = 48000
    narr = np.zeros(int((total + 1) * SR), dtype=np.float32)
    t0 = 0.0
    has_voice = False
    for p in plan:
        if p["pcm"] is not None and len(p["pcm"]):
            x = p["pcm"].astype(np.float32) / 32768.0
            n = int(len(x) * SR / p["rate"])
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
            s = int((t0 + 0.2) * SR)
            narr[s:s + n] += x[: max(0, len(narr) - s)]
            has_voice = True
        p["t0"] = t0
        t0 += p["dur"]
    narr_path = out_dir / "_narration.wav"
    with wave.open(str(narr_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((np.clip(narr, -1, 1) * 32767).astype("<i2").tobytes())

    # 3) 배경음악
    music = pick_music(reel.get("music_mood", ""), post.get("date", ""))

    # 4) 영상 만들기
    out_mp4 = out_dir / "reel.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", str(narr_path)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        mv = 0.10 if has_voice else 0.35
        fc = (f"[2:a]volume={mv},afade=t=in:d=0.5,afade=t=out:st={max(0, total - 1.5):.2f}:d=1.5[m];"
              f"[1:a]volume=1.0[n];[n][m]amix=inputs=2:duration=first:normalize=0,"
              f"aresample=48000[a]")
        cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart",
            str(out_mp4)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    prev_last = None
    for p in plan:
        sc, dur, vis = p["sc"], p["dur"], p["vis"]
        motion = (sc.get("motion") or "none").split("|")[0].strip()
        first = p is plan[0]
        endl = end_layer(W, H, sc.get("on_screen_text", "")) if p["last"] else None
        head = Image.new("RGBA", (W, H), (0, 0, 0, 0)) if p["last"] else \
            headline_layer(W, H, sc.get("on_screen_text", ""), center=(vis["kind"] == "none"))
        subs = split_subs(sc.get("narration", ""), sub_font, W - 260)
        span = p["voice_len"] if p["voice_len"] else dur - 0.3
        weights = [max(1, len(s)) for s in subs]
        sub_times, acc = [], 0.2
        for s, wgt in zip(subs, weights):
            seg = span * wgt / sum(weights)
            sub_times.append((acc, acc + seg, subtitle_layer(W, H, s)))
            acc += seg
        reader = VideoReader(vis["path"], W, H) if vis["kind"] == "video" else None
        scrim = top_scrim(W, H, 820)
        n = max(1, int(round(dur * FPS)))
        for k in range(n):
            t = k / FPS
            if vis["kind"] in ("image", "video"):
                if vis["kind"] == "video":
                    base = reader.next().copy()
                else:
                    z = 1.0 + (0.08 * ease_out(t / dur) if motion == "zoom_in" else 0.0)
                    base = cover_fit(vis["imgs"][0], W, H, z)
                frame = base
                frame.alpha_composite(scrim)
            else:
                frame = bg.copy()
                if vis["kind"] in ("char", "brand") and not p["last"]:
                    frame.alpha_composite(glow)
            if vis["kind"] in ("char", "brand") and not (p["last"] and vis["kind"] == "brand"):
                imgs = vis["imgs"]
                img = imgs[0]
                if len(imgs) == 2:          # 표정 바꾸기: 장면 45% 지점에서 바뀜
                    img = imgs[0] if t < dur * 0.45 else imgs[1]
                elif len(imgs) > 2:         # 성장 이야기: 차례로 바뀜
                    img = imgs[min(len(imgs) - 1, int(t / dur * len(imgs)))]
                place_char(frame, img, motion if motion != "swap_face" else "none", t, dur, end=p["last"])
            if endl is not None:
                frame.alpha_composite(endl)
            else:
                frame.alpha_composite(logo, (96, 150))
            # 글자: 첫 장면은 처음부터 보이게(커버), 나머지는 살짝 올라오며 나타남
            if first:
                frame.alpha_composite(head)
            else:
                a = ease_out((t - 0.1) / TEXT_IN)
                if a > 0:
                    frame.alpha_composite(with_alpha(head, a), (0, int(24 * (1 - a))))
            for (s0, s1, layer) in sub_times:
                if s0 <= t < s1:
                    frame.alpha_composite(layer)
            # 장면 사이 부드럽게
            if prev_last is not None and t < XFADE:
                frame = Image.blend(prev_last, frame, ease_out(t / XFADE))
            enc.stdin.write(frame.convert("RGB").tobytes())
            if k == n - 1:
                prev_last = frame
        if reader:
            reader.close()
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit("영상 만들기(ffmpeg)에 실패했어요.")
    narr_path.unlink(missing_ok=True)

    # 미리보기용 첫 화면
    cover = out_dir / "cover.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.6", "-i", str(out_mp4), "-frames:v", "1",
                    "-q:v", "3", str(cover)], check=True)
    log(f"  → reel.mp4 ({total:.1f}초)")
    return {"media_type": "REELS", "video": "reel.mp4", "cover": "cover.jpg", "thumb_offset_ms": 600,
            "duration": round(total, 2)}


def pick_music(mood, seed):
    folder = ASSETS / "music"
    files = sorted([p for p in folder.glob("*") if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".aac")])
    if not files:
        log("  (배경음악 없음 — assets/music 에 음악 파일을 넣으면 깔립니다)")
        return None
    words = re.findall(r"[가-힣A-Za-z]+", mood or "")
    for w in words:
        for p in files:
            if w.lower() in p.stem.lower():
                log(f"  배경음악: {p.name}")
                return p
    p = files[sum(map(ord, seed or "x")) % len(files)]
    log(f"  배경음악: {p.name}")
    return p


# ───────────────────────── 캐러셀 ─────────────────────────
def render_carousel(post, post_dir, out_dir):
    W, H = 1080, 1350
    items = [x for x in (post.get("images") or []) if isinstance(x, dict)]
    items.sort(key=lambda x: x.get("order", 0))
    if not 2 <= len(items) <= 10:
        raise SystemExit(f"캐러셀은 2~10장이어야 해요 (지금 {len(items)}장).")
    bg = paper(W, H)
    logo = logo_small(44)
    files = []
    for i, it in enumerate(items):
        first, last = i == 0, i == len(items) - 1
        frame = bg.copy()
        has_photo = False
        fpath = post_dir / str(it.get("file", "")) if it.get("file") else None
        if fpath and fpath.exists():
            frame = cover_fit(Image.open(fpath), W, H)
            frame.alpha_composite(top_scrim(W, H, 640))
            has_photo = True
        d = ImageDraw.Draw(frame)
        if last:
            frame.alpha_composite(rounded_icon(240), ((W - 240) // 2, 330))
            f = font("logo", 80)
            d.text(((W - text_w(f, "textmon")) / 2, 600), "textmon", font=f, fill=INK + (255,))
            hf = font("xbold", 64)
            lines = wrap(hf, it.get("headline", ""), W - 200)
            draw_lines(d, lines, hf, 100, 790, INK + (255,), 84, align="center", box_w=W - 200)
            sf = font("semi", 38)
            y2 = 790 + 84 * len(lines) + 30
            sl = wrap(sf, it.get("subline", ""), W - 200)
            draw_lines(d, sl, sf, 100, y2, INK + (200,), 54, align="center", box_w=W - 200)
            d.text(((W - text_w(sf, SITE)) / 2, 1190), SITE, font=sf, fill=BRAND_DARK + (255,))
        else:
            size = 88 if first else 70
            hf = font("xbold", size)
            lines = wrap(hf, it.get("headline", ""), W - 200)
            y = 210 if first else 190
            d.rounded_rectangle([100, y - 40, 172, y - 28], radius=6, fill=BRAND + (255,))
            draw_lines(d, lines, hf, 100, y, INK + (255,), int(size * 1.3))
            sf = font("semi", 40)
            sl = wrap(sf, it.get("subline", ""), W - 200)
            draw_lines(d, sl, sf, 100, y + int(size * 1.3) * len(lines) + 26, INK + (190,), 58)
            ch = it.get("character")
            if ch and not has_photo:
                cp = ASSETS / ch
                if cp.exists():
                    img = Image.open(cp).convert("RGBA")
                    s = min(440 / img.height, 3.2)
                    img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
                    frame.alpha_composite(img, (W - img.width - 110, H - img.height - 140))
            if not first:
                pf = font("semi", 30)
                pn = f"{i + 1}/{len(items)}"
                d.text((W - 100 - text_w(pf, pn), 90), pn, font=pf, fill=INK + (150,))
            frame.alpha_composite(logo, (100, H - 110))
        name = f"carousel_{i + 1:02d}.jpg"
        frame.convert("RGB").save(out_dir / name, "JPEG", quality=92)
        files.append(name)
        log(f"  → {name}")
    return {"media_type": "CAROUSEL", "images": files}


# ───────────────────────── 시작 ─────────────────────────
def main():
    if len(sys.argv) < 3:
        raise SystemExit("사용: python scripts/render.py posts/<날짜> out/<날짜>")
    post_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    pj = post_dir / "post.json"
    if not pj.exists():
        raise SystemExit(f"{pj} 가 없어요.")
    try:
        post = json.loads(pj.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"post.json 문법 오류: {e}")
    out_dir.mkdir(parents=True, exist_ok=True)
    mt = str(post.get("media_type", "")).upper()
    log(f"[{post_dir.name}] {mt} 만들기")
    if mt == "REELS":
        man = render_reel(post, post_dir, out_dir)
    elif mt == "CAROUSEL":
        man = render_carousel(post, post_dir, out_dir)
    else:
        raise SystemExit("media_type 은 REELS 또는 CAROUSEL 이어야 해요.")
    caption = str(post.get("caption", "")).replace("\\n", "\n").strip()
    if len(caption) > 2200:
        raise SystemExit("캡션이 2,200자를 넘어요.")
    man.update({"date": post.get("date", post_dir.name), "caption": caption})
    (out_dir / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
    log("완료")


if __name__ == "__main__":
    main()
