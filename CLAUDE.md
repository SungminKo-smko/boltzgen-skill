# boltzgen-skill

Claude Code 스킬: boltzgen MCP 서버를 통해 나노바디 디자인 잡을 제출한다.

## API KEY 관리 (중요)

boltzgen MCP 서버는 **공유 서버**다. API KEY는 사용자 각자가 취득하며,
**모든 tool 호출 시 `api_key` 인수로 직접 전달**한다. MCP 서버 환경변수에 의존하지 않는다.

### API KEY 취득 방법

**방법 1 (권장): 브라우저 OAuth 로그인**

아래 URL을 브라우저에서 열면 Google OAuth (Supabase) 로그인 후 API KEY가 발급된다:
```
https://nanobody-designer-api.politebay-55ff119b.westus3.azurecontainerapps.io/auth/login
```
콜백 페이지에서 `api_key` 값을 복사하여 `.env` 파일에 저장한다.

**방법 2: MCP OAuth 2.1 (자동)**

HTTP transport로 MCP 서버에 최초 접속 시 OAuth 2.1 흐름이 자동으로 실행된다.
별도 설정 없이 API KEY가 자동 발급된다.

**방법 3 (fallback): .env 파일 수동 설정**
```bash
echo "API_KEY=<your-boltzgen-api-key>" > ~/.claude/skills/boltzgen-design/.env
```

> **참고**: @shaperon.com 계정은 자동 승인된다.

### 크로스 서비스 인증

API KEY는 boltz2 플랫폼(platform_core)과 동일한 Supabase identity를 공유한다.
boltzgen `/auth/login`으로 발급받은 키는 boltz2 서비스에서도 동일하게 사용 가능하다.

### API KEY 로드

스킬 실행 시 Step 0에서 `.env` 파일을 읽어 `BOLTZGEN_API_KEY` 변수에 로드하고,
이후 모든 tool 호출에 `api_key=<BOLTZGEN_API_KEY>`를 인수로 전달한다.

## 필수 입력 (딱 3가지만 물어볼 것)

1. **구조 파일 경로** — `.cif` 또는 `.pdb` 파일 (절대경로)
2. **target chain ID** — 결합 대상 chain (예: `A`, `A B`)
3. **design 범위** — 길이 범위(예: `80..140`) 또는 재설계 구간(예: `A:97..114`)

나머지는 **default** 사용 (질문하지 말 것):
- `num_designs=5`, `budget=1`

## MCP 전제 조건

boltzgen API 내장 MCP 서버가 Streamable HTTP로 등록되어 있어야 한다:

```bash
claude mcp add boltzgen-mcp \
  --transport streamable-http \
  https://nanobody-designer-api.politebay-55ff119b.westus3.azurecontainerapps.io/mcp/mcp
```

최초 접속 시 MCP OAuth 2.1이 자동으로 브라우저 인증을 진행한다.
(API KEY는 스킬 설정 파일 `~/.claude/skills/boltzgen-design/.env`에도 보관 가능)

## 워크플로

```
[Step 0] API KEY 확인
  ├─ .env 파일에서 로드 (기존 키가 있는 경우)
  ├─ 또는 /auth/login OAuth 로그인으로 발급
  └─ 또는 MCP OAuth 2.1 자동 발급
  ↓
[Step 2] create_upload_url(filename, api_key=<KEY>) → asset_id + upload_url
  → Bash: curl -X PUT -T <file_path> -H "x-ms-blob-type: BlockBlob" -H "Content-Type: ..." <upload_url>
  ↓
render_template(asset_id, include, design, binding_types, api_key=<KEY>) → spec_id
  또는 validate_spec(raw_yaml, asset_ids, api_key=<KEY>) → spec_id
  ↓
submit_job(spec_id, num_designs, budget, api_key=<KEY>) → job_id
  ↓
get_job(job_id, api_key=<KEY>) — running 도달 시 세부 정보 출력 후 종료
```

## 파일 업로드

`create_upload_url` + `curl PUT` 방식만 사용한다.
파일 내용이 Claude 컨텍스트를 거치지 않아 대용량 CIF/PDB 파일도 처리 가능.
`upload_structure(...)` 및 base64 인코딩 방식은 컨텍스트 초과를 유발하므로 **절대 사용 금지**.

## 기본 동작

잡이 **running** 상태에 도달하면 아래 정보를 출력하고 종료:
- job_id, status, protocol, stage, created_at, started_at
- 이후 확인 명령 (get_job / get_logs / cancel_job)

완료까지 대기 시 `get_job` 폴링 → `succeeded` 후 `get_artifacts`로 URL 조회.

## 잡 관리

```python
get_job(job_id, api_key=<KEY>)               # 상태 확인
get_logs(job_id, tail=100, api_key=<KEY>)    # 실시간 로그 (실제 진행률)
list_jobs(status="running", api_key=<KEY>)   # 잡 목록
cancel_job(job_id, api_key=<KEY>)            # 잡 취소
list_templates(api_key=<KEY>)               # 템플릿 목록
list_workers(api_key=<KEY>)                 # 워커 상태 (admin)
```

> `progress_percent`는 ACA log stream 기반으로 지연 가능. 정확한 진행률은 `get_logs`로 확인.

## 오류 처리

- **API KEY 미설정**: OAuth 로그인(`/auth/login`)으로 발급받거나, `~/.claude/skills/boltzgen-design/.env`에 `API_KEY=<key>` 추가
- **API 인증 실패 (401)**: API KEY 만료 시 `/auth/login`으로 재발급
- **MCP 미등록**: `claude mcp add boltzgen-mcp --transport streamable-http https://nanobody-designer-api.politebay-55ff119b.westus3.azurecontainerapps.io/mcp/mcp`
- **YAML 검증 실패**: chain ID 대소문자, 잔기 인덱스는 1-based (label_asym_id 기준)
  → Mol* 뷰어: https://molstar.org/viewer/
- **잡 실패**: `get_job`의 `failure_message` 참고
- **429 Concurrent limit**: 동일 `client_request_id`로 재시도 시 같은 job_id 반환

## 관련 레포

- **[boltzgen_MSA](https://github.com/SungminKo-smko/boltzgen_MSA)** — BoltzGen API + 내장 MCP Server (Streamable HTTP)
