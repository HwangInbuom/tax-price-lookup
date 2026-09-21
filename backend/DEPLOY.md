# 백엔드를 Render에 무료로 배포하기 (주소 자동조회 기능용)

이 문서는 `tax-price-lookup/backend`를 인터넷에 올려서, 모바일 앱에서 주소 자동조회
기능을 쓸 수 있게 만드는 과정입니다. 계정 만들기·키 입력은 본인 계정으로 직접 하셔야
하는 부분이라 화면 클릭 위주로 최대한 쉽게 풀어놨습니다.

## 준비물

- GitHub 계정 (무료, 이메일만 있으면 가입 가능) — 코드를 올려둘 곳
- Render 계정 (무료, GitHub 계정으로 바로 가입 가능) — 서버를 돌려줄 곳
- 지금 쓰고 있는 카카오·브이월드·data.go.kr API 키 (`backend/.env` 파일 안에 이미 있음)

## 1단계 — GitHub에 코드 올리기

1. https://github.com 에서 계정 만들기 (이미 있으면 로그인)
2. 오른쪽 위 `+` → `New repository` 클릭
3. 이름은 아무거나 (예: `tax-price-lookup`), `Public` 또는 `Private` 아무거나 선택 →
   `Create repository`
4. 이 폴더(`tax-price-lookup`) 전체를 그 저장소에 업로드합니다. GitHub 데스크톱 앱
   (https://desktop.github.com) 을 설치하면 폴더를 끌어다 놓는 것만으로 올릴 수 있어서
   제일 쉽습니다.
   - **주의**: `backend/.env` 파일(실제 API 키가 들어있는 파일)은 절대 올리면 안 됩니다.
     이미 `.gitignore`에 등록해놔서 GitHub 데스크톱 앱을 쓰면 자동으로 빠집니다. 다른
     방법으로 올릴 경우 `.env` 파일이 목록에 안 보이는지 한 번 확인해주세요.

## 2단계 — Render에서 서버 만들기

1. https://render.com 에서 "Get Started" → GitHub 계정으로 가입/로그인
2. 대시보드에서 `New +` → `Web Service` 클릭
3. 방금 만든 GitHub 저장소를 선택하고 연결
4. 아래처럼 설정 (이 폴더 안의 `render.yaml`을 인식하면 자동으로 채워줍니다):
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free
5. `Create Web Service` 누르기 전에 3단계(환경변수)부터 먼저 등록하는 게 편합니다.

## 3단계 — API 키 등록 (환경변수)

같은 화면(또는 만든 뒤 Settings → Environment)에서 `Add Environment Variable`로 아래를
하나씩 추가합니다. 값은 `backend/.env` 파일에 있는 그대로 복사해서 넣으면 됩니다.

| Key | Value |
|---|---|
| `KAKAO_REST_API_KEY` | (카카오 REST API 키) |
| `VWORLD_API_KEY` | (브이월드 인증키) |
| `VWORLD_DOMAIN` | 일단 `localhost`로 두고 5단계에서 바꿉니다 |
| `PRICE_API_YEAR` | `2026` |
| `PRICE_API_PREV_YEAR` | `2025` |
| `DATA_GO_KR_SERVICE_KEY` | (공공데이터포털 서비스키) |

다 입력했으면 `Create Web Service` (또는 `Deploy`) 클릭 — 몇 분 기다리면 배포가 끝나고,
`https://무언가.onrender.com` 형태의 주소가 생깁니다. 이 주소를 꼭 저장해두세요.

## 4단계 — 잘 됐는지 확인

브라우저에서 `https://그주소.onrender.com/health` 를 열어봐서 `{"ok":true}`가 뜨면
성공입니다.

## 5단계 — 브이월드 키 도메인 재등록 (중요, 빠뜨리기 쉬움)

브이월드 API 키는 "이 도메인에서 오는 요청만 허용" 방식으로 등록되어 있어서, 지금
`localhost`로 등록된 상태 그대로면 Render에서 호출할 때 막힙니다.

1. https://www.vworld.kr → 마이페이지 → 오픈API 인증키 관리
2. 아까 4단계에서 받은 주소(`무언가.onrender.com`, `https://`는 빼고 도메인만)를
   등록 도메인에 추가
3. Render의 환경변수 `VWORLD_DOMAIN` 값도 같은 도메인으로 수정 → 자동으로 재배포됨

## 이후 — 모바일 앱 연결

여기까지 되면 `https://그주소.onrender.com/lookup?address=...` 처럼 어디서든 호출
가능한 상태가 됩니다. 이 주소를 모바일 앱에 연결하는 화면 개발(주소 입력창, 자동조회
버튼, 결과 표시, 실거래가 표 클릭 시 자동입력)은 제가 이어서 진행하면 되니, Render
배포까지 끝나면 그 주소만 알려주세요.

## 참고 — 무료 플랜 특성

Render 무료 플랜은 15분간 요청이 없으면 서버가 잠들고, 그 다음 첫 요청이 살아나는 데
30초~1분 정도 걸립니다(그 뒤로는 빠릅니다). 가끔 쓰는 개인 앱 용도로는 문제없는
수준이지만, 매번 즉각 응답이 필요하면 나중에 유료 플랜(월 몇 달러)으로 올리면 됩니다.
