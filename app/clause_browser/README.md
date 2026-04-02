# Clause Browser

절 단위 문서 탐색/편집 UI는 FastAPI + 정적 프론트엔드로 추가되었다.

구조:

- `app/clause_browser/backend`: FastAPI, API, repository, render/parser, services
- `app/clause_browser/frontend/static`: HTML/CSS와 브라우저 자산
- `app/clause_browser/frontend/static/js/core.js`: 공통 상태, 렌더링, API, 세션 처리
- `app/clause_browser/frontend/static/js/features`: 버튼/기능 단위 이벤트 바인딩
- `app/clause_browser/*.py`: 기존 import 경로 호환용 re-export 래퍼

실행:

```bash
python3 -m app.clause_browser.preprocess --inputs Specs --output artifacts/clause_browser_corpus.jsonl --media-dir artifacts/clause_browser_media
python3 -m uvicorn app.specbot_query_server:create_app --factory --host 0.0.0.0 --port 8010
python3 -m uvicorn app.clause_browser.server:create_app --factory --host 0.0.0.0 --port 8000
```

Node / npm:

- 일반 실행만 할 때는 `npm install` 이 필수는 아니다.
- 현재 에디터 번들 파일 `frontend/static/js/vendor/tinymce-editor.js` 가 저장소에 포함되어 있으므로, 서버 실행만 하면 브라우저 UI는 뜬다.
- 아래 경우에만 Node.js와 `npm install` 이 필요하다.
  - `frontend/src/tinymce-editor.js` 를 수정한 경우
  - `tinymce` / `esbuild` 버전을 바꾸는 경우
  - 에디터 번들을 다시 생성해야 하는 경우

에디터 번들 재빌드:

```bash
cd app/clause_browser/frontend
npm install
npm run build:editor
```

스크립트:

```bash
./scripts/preprocess_clause_browser.sh
./scripts/run_clause_browser_stack.sh foreground
./scripts/run_clause_browser_stack.sh background
./scripts/start_clause_browser_minimal.sh background
```

재부팅 후 최소 시작:

- Vespa 데이터가 남아 있다면 다시 feed할 필요 없이 아래 스크립트만 실행하면 된다.
- 이 스크립트는 `docker compose up -d`로 Vespa를 올리고, readiness 확인 후 Query API와 Clause Browser만 시작한다.

```bash
./scripts/start_clause_browser_minimal.sh background
```

환경 변수:

```bash
SPECBOT_CLAUSE_BROWSER_CORPUS=artifacts/clause_browser_corpus.jsonl
SPECBOT_CLAUSE_BROWSER_EXPORT_DIR=artifacts/clause_exports
SPECBOT_CLAUSE_BROWSER_MEDIA_DIR=artifacts/clause_browser_media
SPECBOT_CLAUSE_BROWSER_CORS_ORIGINS=http://localhost:3000,http://192.168.0.10:3000
SPECBOT_LLM_ACTION_PROVIDER=mock
SPECBOT_LLM_ACTION_MODEL=gpt-4.1-mini
SPECBOT_CLAUSE_BROWSER_LANGUAGES=ko:Korean,en:English
SPECBOT_QUERY_API_URL=http://127.0.0.1:8010
```

접속:

- 브라우저: `http://<server-ip>:8000/clause-browser/`
- 헬스체크: `http://<server-ip>:8000/health`
- SpecBot Query API: `http://<server-ip>:8010/health`

동작 개요:

- 상단: 문서 탐색 버튼, SpecBot query 입력/실행
- 좌측: 선택한 절 목록
- 중앙: 로드된 절 트리, 접기/펼치기, 개별 절 제거
- 우측: SpecBot 결과, 선택 텍스트 기반 LLM 액션 결과

SpecBot Query Server:

- Query API 서버는 프로세스 시작 시 embedding model과 registry를 로드하고 재사용한다.
- Clause Browser 서버는 `SPECBOT_QUERY_API_URL`로 이 서버를 호출한다.
- 다른 PC에서 웹 UI로 접속해도 실제 query 실행은 서버 머신의 Query API 프로세스에서 수행된다.

저장 규칙:

- 출력 디렉토리: `artifacts/clause_exports`
- 이미지 캐시 디렉토리: `artifacts/clause_browser_media`
- 파일명: 입력 제목 기반 `.docx`
- 중복 파일명: `-2`, `-3` suffix 자동 부여

LLM 액션:

- 현재는 `translate` 액션만 구현
- API/서비스 경계는 일반화되어 있어 요약, QA, 키워드 추출을 같은 구조로 확장 가능
- `OPENAI_API_KEY`가 없거나 provider가 `mock`이면 mock 번역 결과를 반환
