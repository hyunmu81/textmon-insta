# textmon-insta — 텍스트몬 인스타그램 자동 게시

ChatGPT가 만든 게시물(JSON)을 넣어 두면, 매일 저녁 **8시 47분**에 GitHub가 알아서
- 릴스: 장면표대로 **세로 영상(mp4)** 을 만들고 (자막·목소리·배경음악·캐릭터 움직임)
- 캐러셀: **5~10장 그림**에 브랜드 글꼴로 글자를 얹어

인스타그램에 올립니다. 올린 기록은 `posted.md`에 쌓이고, ChatGPT는 이 기록을 보고 지난 게시물과 겹치지 않게 만듭니다.

---

## 1. 처음 한 번만 하는 설정

### ① 새 저장소 만들기
GitHub에서 **`textmon-insta`** 저장소를 **공개(Public)** 로 만듭니다. 아무 파일도 추가하지 않습니다.

> 왜 dreamReader가 아니라 따로 만드나요?
> - dreamReader에 올리면 파일을 올릴 때마다 Railway가 서비스를 다시 배포합니다.
> - 캐러셀 그림은 인스타가 가져갈 수 있는 **공개 주소**에 있어야 합니다. GitHub Pages가 그 주소를 무료로 만들어 주는데, 무료 계정은 공개 저장소에서만 됩니다.
> - 이 저장소에는 게시물과 영상 만드는 프로그램만 있습니다. 텍스트몬 코드·채점 방식 같은 대외비는 없습니다.

압축을 푼 폴더에서:
```
git init
git add .
git commit -m "인스타 자동 게시 시작"
git branch -M main
git remote add origin https://github.com/hyunmu81/textmon-insta.git
git push -u origin main
```

### ② GitHub Pages 켜기
저장소 **Settings → Pages → Build and deployment → Source** 를 **GitHub Actions** 로 바꿉니다.

### ③ 비밀값 넣기
**Settings → Secrets and variables → Actions → Secrets → New repository secret**

| 이름 | 값 |
|---|---|
| `IG_ACCESS_TOKEN` | 메타에서 발급받은 인스타그램 액세스 토큰 |
| `IG_USER_ID` | 인스타그램 프로페셔널 계정 ID (숫자) |
| `GEMINI_API_KEY` | (선택) 내레이션 목소리용. 텍스트몬에서 쓰는 제미나이 키를 그대로 써도 됩니다. 없으면 목소리 없이 자막과 음악만 나옵니다. |

> dreamReader에 넣어 둔 비밀값은 다른 저장소로 옮길 수 없어서, 여기에 다시 붙여 넣어야 합니다.

**Variables 탭 (선택)** — 필요할 때만 넣습니다.

| 이름 | 언제 |
|---|---|
| `GRAPH_HOST` | 토큰을 **인스타그램 로그인** 방식으로 받았으면 `graph.instagram.com`. 페이스북 로그인 방식이면 넣지 않습니다(기본 `graph.facebook.com`). |
| `GRAPH_VERSION` | 기본 `v26.0`. 메타가 버전을 없앤다고 알리면 바꿉니다. |
| `GEMINI_TTS_VOICE` | 목소리 바꾸기 (기본 `Kore`) |
| `GEMINI_TTS_MODEL` | 목소리 모델 바꾸기 (기본 `gemini-3.1-flash-tts-preview`) |

### ④ 배경음악 (선택)
`assets/music/` 에 **저작권 걱정 없는 음악**(예: 유튜브 오디오 보관함에서 받은 곡)을 넣습니다.
파일 이름에 분위기 단어를 넣으면 ChatGPT가 적은 분위기와 맞는 곡을 고릅니다. 예) `잔잔한피아노.mp3`, `밝은어쿠스틱.mp3`

### ⑤ ChatGPT 연결
ChatGPT의 GitHub 연결에 **`textmon-insta`** 저장소도 추가합니다. 그래야 `posted.md`를 읽고 지난 게시물과 겹치지 않게 만듭니다.

---

## 2. 매일 하는 일

1. ChatGPT에 `오늘 날짜 2026-11-21. 오늘 게시물 만들어 줘.`
2. 나온 **JSON** 을 복사합니다.
3. GitHub 저장소 화면에서 **Add file → Create new file**
   - 파일 이름 칸에 `posts/2026-11-21/post.json` 이라고 쓰고, JSON을 붙여 넣고 **Commit**
4. ChatGPT가 새로 그린 그림이 있으면 **Add file → Upload files** 로 같은 `posts/2026-11-21/` 폴더에 올립니다. 파일 이름은 JSON에 적힌 그대로(예: `2026-11-21_3.jpg`).
   원장님이 찍은 영상도 같은 폴더에 올리고, JSON의 `asset`에 `video:파일이름.mp4` 로 적습니다.
5. 올리면 바로 **미리보기**가 만들어집니다.
   **Actions → 맨 위 실행 → 아래 Artifacts → preview-날짜** 를 내려받아 영상을 확인합니다.
6. 저녁 8시 47분에 자동으로 인스타에 올라갑니다. 고칠 게 있으면 그 전에 post.json을 고치면 됩니다.

> 며칠 치를 미리 넣어 두어도 됩니다. 매일 그날 날짜 폴더만 올립니다.
> 휴대폰 GitHub 앱이나 휴대폰 브라우저로도 3~4번을 할 수 있습니다.

### 바로 올리고 싶을 때
**Actions → 텍스트몬 인스타 올리기 → Run workflow**
- 날짜: 비우면 오늘
- **인스타그램에 올리기** 체크 → Run

체크하지 않고 실행하면 미리보기만 만듭니다.

---

## 3. 잘 안 될 때

실패하면 GitHub가 메일로 알려 줍니다. Actions에서 빨간 실행을 눌러 오류 문장을 확인하세요.

| 오류 문장 | 할 일 |
|---|---|
| `인스타 API 오류 400 ... code 190` | 토큰이 만료됐어요. 새로 발급해 `IG_ACCESS_TOKEN` 을 바꿔 주세요. 일반 장기 토큰은 약 60일이면 끊깁니다. |
| `인스타 API 오류 ... does not exist` | `IG_USER_ID` 가 틀렸거나, 토큰 방식과 `GRAPH_HOST` 가 맞지 않아요. |
| `post.json 문법 오류` | JSON을 복사할 때 앞뒤가 잘렸어요. 처음 `{` 부터 마지막 `}` 까지 다시 붙여 넣으세요. |
| `공개 주소에서 그림을 찾지 못했어요` | ② GitHub Pages 설정을 확인하세요. |
| `그림 파일이 없어요: ...` (경고) | 그림 이름이 JSON과 달라요. 그 장면은 글자 화면으로 대신 만들어집니다. |
| `목소리 만들기 실패` (경고) | 제미나이 키나 한도를 확인하세요. 목소리 없이 자막만 나갑니다. |

---

## 4. 폴더 구성

```
posts/날짜/post.json      ChatGPT가 만든 게시물 (+ 그림·영상)
assets/character/         텍스트몬 캐릭터 원본 (dreamReader에서 복사)
assets/brand/             로고 마크·앱 아이콘
assets/fonts/             Pretendard, Fredoka (무료 글꼴, 라이선스 동봉)
assets/music/             배경음악 (원장님이 넣음)
scripts/render.py         영상·그림 만들기
scripts/publish.py        인스타에 올리기
scripts/decide.py         오늘 할 일 정하기
examples/                 릴스·캐러셀 예시 게시물
posted.md                 올린 기록 (자동)
```

캐릭터 그림을 새로 바꾸면 dreamReader의 `public/img/textmon/character/` 파일을 `assets/character/` 에도 똑같이 넣어 주세요.

### 내 컴퓨터에서 미리 만들어 보기 (선택)
```
pip install -r scripts/requirements.txt     # ffmpeg 도 필요
python scripts/render.py examples/reel out/reel
python scripts/render.py examples/carousel out/carousel
```
