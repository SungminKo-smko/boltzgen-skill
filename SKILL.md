---
name: boltzgen-design
version: 2.5.0
description: |
  BoltzGen 나노바디 디자인 자동화 스킬. 사용자의 자연어 요구사항을 BoltzGen API에
  직접 제출하여 업로드 → 렌더링/검증 → 제출 → 상태 추적까지 전체 워크플로를 자동화한다.
  Use when asked to "나노바디 디자인", "boltzgen 실행", "design job 제출", "spec yaml 만들어줘".
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# /boltzgen-design

boltzgen MCP 서버를 통해 나노바디 디자인 잡을 제출하는 스킬.

## 설치

```bash
git clone https://github.com/SungminKo-smko/boltzgen-skill ~/.claude/skills/boltzgen-design
```

## MCP 서버 확인 (run first)

```bash
claude mcp list 2>/dev/null | grep boltzgen || echo "NOT_REGISTERED"
```

**NOT_REGISTERED** 출력 시 — boltzgen API 내장 MCP를 Streamable HTTP로 등록:
```bash
claude mcp add boltzgen-mcp \
  --transport streamable-http \
  https://nanobody-aca-api.politebay-55ff119b.westus3.azurecontainerapps.io/mcp/mcp
```

> 최초 접속 시 MCP OAuth 2.1 흐름이 자동 실행되어 브라우저 인증 후 API KEY가 발급된다.

## Step 0: API KEY 자동 발급 + 로드

**API KEY는 모든 tool 호출 시 `api_key` 인수로 전달한다.**

### .env에서 기존 키 로드

```bash
SKILL_ENV="$HOME/.claude/skills/boltzgen-design/.env"
BOLTZGEN_API_KEY=""

if [ -f "$SKILL_ENV" ]; then
    BOLTZGEN_API_KEY=$(grep -E "^API_KEY=" "$SKILL_ENV" | cut -d= -f2-)
fi

# 환경변수 fallback
[ -z "$BOLTZGEN_API_KEY" ] && BOLTZGEN_API_KEY="${BOLTZGEN_API_KEY:-${API_KEY:-}}"

echo "BOLTZGEN_API_KEY=${BOLTZGEN_API_KEY}"
```

### 키가 없으면: provision_api_key로 자동 발급

**값이 비어있으면** → MCP 도구 `provision_api_key()`를 호출하여 자동 발급한다.
(MCP OAuth 2.1이 자동으로 브라우저 인증을 진행한다.)

```python
provision_api_key()
# → {"api_key": "b2_xxxxx", "profile_email": "user@example.com", "created": true, "service": "boltzgen"}
```

반환된 `api_key`를 `.env` 파일에 저장:

```bash
mkdir -p "$HOME/.claude/skills/boltzgen-design"
echo "API_KEY=<반환된 api_key 값>" > "$HOME/.claude/skills/boltzgen-design/.env"
```

저장된 키를 `BOLTZGEN_API_KEY` 변수에 설정하고 이후 모든 tool 호출에 `api_key=<BOLTZGEN_API_KEY>`로 전달한다.

> **참고**: @shaperon.com 계정은 자동 승인된다. 그 외 계정은 관리자 승인이 필요하다.

### 크로스 서비스 인증

API KEY는 boltz2 플랫폼(platform_core)과 동일한 Supabase identity를 공유한다.
단, 키 자체는 서비스별로 분리되어 있다 (boltzgen 키는 boltzgen에서만 동작).

이 단계에서 확정된 `BOLTZGEN_API_KEY` 값을 이후 **모든 tool 호출의 `api_key` 인수**로 전달한다.

## Step 1: 환경 감지 및 사용자 요구사항 수집

### Claude Desktop 감지

```bash
if [ -d "/mnt/user-data/uploads" ]; then
    echo "CLAUDE_DESKTOP=true"
    ls /mnt/user-data/uploads/
else
    echo "CLAUDE_DESKTOP=false"
fi
```

**CLAUDE_DESKTOP=true** 이면:
- 사용자가 채팅에 첨부한 파일은 `/mnt/user-data/uploads/<파일명>`에 저장된다.
- 파일명의 `#` 등 특수문자는 `_`로 변환될 수 있으므로 `ls` 결과로 실제 파일명을 확인한다.
- 사용자에게 파일 경로를 묻지 말고 위 경로를 직접 사용한다.

**CLAUDE_DESKTOP=false** 이면:
- 사용자에게 구조 파일 절대경로를 묻는다.

### 요구사항 수집

**딱 3가지만 물어본다. 나머지는 default 사용.**

사용자가 이미 정보를 제공했으면 AskUserQuestion 생략하고 바로 진행.

필수:
1. **구조 파일 경로** — `.cif` 또는 `.pdb` 파일 경로 (Claude Desktop이면 위에서 자동 확인)
2. **target chain ID** — 결합 대상 chain (예: `A`, `A B`)
3. **design 범위** — 새 나노바디 길이(예: `80..140`) 또는 재설계 구간(예: `A:97..114`)

선택 (사용자가 언급한 경우만):
- **binding residues** — 결합 잔기 번호 (예: `B:317,321,324`)
- **num_designs** — 기본 5
- **budget** — 기본 1

## Step 2: 구조 파일 업로드

> **절대 금지**: base64 인코딩, `upload_structure(...)`, Read로 파일 읽기 — 모두 사용 금지. 컨텍스트 초과를 유발한다.
>
> **remote MCP여도 curl은 로컬 Bash에서 실행된다.** MCP 서버가 로컬 파일에 접근할 필요 없다. `create_upload_url`로 SAS URL을 받아 로컬 curl이 직접 업로드한다.

```python
create_upload_url(
    filename="<파일명>",        # 예: "target.cif"
    api_key="<BOLTZGEN_API_KEY>"
)
# → asset_id, upload_url, content_type, curl_hint 반환
```

반환된 `curl_hint`의 `<FILE_PATH>`를 실제 절대경로로 교체 후 Bash로 실행:

```bash
curl -s -X PUT -T "<절대경로>" \
  -H "x-ms-blob-type: BlockBlob" \
  -H "Content-Type: <content_type>" \
  "<upload_url>"
# 성공 시 빈 응답(200/201). 오류 시 XML 에러 메시지 출력.
```

## Step 3: Spec 생성

### 일반 나노바디 (템플릿 렌더링 — 권장)

```python
render_template(
    asset_id="<asset_id>",
    include=["A", "B"],
    design=[{"chain_id": "A", "res_index": "97..114"}],   # 재설계 구간 (선택)
    binding_types=[{"chain_id": "B", "binding": "317,321,324"}],  # 결합 잔기 (선택)
    api_key="<BOLTZGEN_API_KEY>"
)
# → spec_id 반환
```

### 복잡한 케이스 (raw YAML)

`boltzgen_spec_reference.md`를 Read로 읽고 패턴 적용 후:

```python
validate_spec(
    raw_yaml="<yaml 문자열>",
    asset_ids=["<asset_id>"],
    api_key="<BOLTZGEN_API_KEY>"
)
# → spec_id 반환
```

## Step 4: Spec 검증

`render_template` 또는 `validate_spec`이 반환한 결과를 확인한다.

- `spec_id` 값이 있으면 → Step 5 진행
- `error` 키가 있으면 → 에러 내용을 사용자에게 보여주고 중단
- `warnings` 가 있으면 → 사용자에게 경고 내용 표시 후 계속 진행

## Step 5: 잡 제출

```python
submit_job(
    spec_id="<spec_id>",
    num_designs=5,
    budget=1,
    api_key="<BOLTZGEN_API_KEY>"
)
# → job_id 반환
```

## Step 6: 상태 확인

잡이 **running** 상태에 도달하면 세부 정보 출력 후 종료:

```python
get_job(
    job_id="<job_id>",
    api_key="<BOLTZGEN_API_KEY>"
)
```

완료 대기 시 `get_job` 폴링 → `succeeded` 후:
```python
get_artifacts(
    job_id="<job_id>",
    api_key="<BOLTZGEN_API_KEY>"
)
```

## 잡 관리

```python
get_job(job_id, api_key="<key>")               # 상태 확인
get_logs(job_id, tail=100, api_key="<key>")    # 실시간 로그
list_jobs(status="running", api_key="<key>")   # 잡 목록
cancel_job(job_id, api_key="<key>")            # 잡 취소
list_templates(api_key="<key>")               # 템플릿 목록
list_workers(api_key="<key>")                 # 워커 상태 (admin)
```

## 로그 스트리밍 Artifact

사용자가 "로그 스트리밍", "실시간 로그", "로그 보여줘" 등을 요청하면:

> `get_logs`는 snapshot 방식이므로, **폴링으로 실시간처럼 보여주는 HTML artifact를 생성**한다.

artifact는 MCP Streamable HTTP를 직접 호출하는 방식으로 구현한다:

1. `POST <MCP_URL>` — `initialize` → `mcp-session-id` 헤더 획득
2. `POST <MCP_URL>` + `mcp-session-id` 헤더 — `tools/call` (`get_logs`) 5초마다 반복

artifact에 하드코딩할 값:
- **MCP_URL**: `https://nanobody-aca-api.politebay-55ff119b.westus3.azurecontainerapps.io/mcp/mcp`
- **API_KEY**: `<BOLTZGEN_API_KEY>` (Step 0에서 읽은 값)
- **JOB_ID**: 제출된 job_id

```javascript
// initialize → session ID 획득
const initRes = await fetch(MCP_URL, {
  method: "POST",
  headers: { "Content-Type": "application/json", "Accept": "application/json, text/event-stream" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize",
    params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "artifact", version: "1.0" } } })
});
const sessionId = initRes.headers.get("mcp-session-id");

// get_logs 폴링 (5초 간격)
async function fetchLogs() {
  const res = await fetch(MCP_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                "mcp-session-id": sessionId },
    body: JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/call",
      params: { name: "get_logs", arguments: { job_id: JOB_ID, tail: 100, api_key: API_KEY } } })
  });
  // SSE 파싱: "data: {...}" 라인에서 result.content[0].text 추출
}
setInterval(fetchLogs, 5000);
```

## 오류 처리

- **API_KEY 미설정**: `/auth/login` OAuth 로그인으로 발급받거나, `~/.claude/skills/boltzgen-design/.env`에 `API_KEY=<key>` 추가
- **인증 실패 (401)**: API KEY 만료 시 `/auth/login`으로 재발급. boltz2와 동일 키 사용 가능
- **MCP 미등록**: `claude mcp add boltzgen-mcp --transport streamable-http https://nanobody-aca-api.politebay-55ff119b.westus3.azurecontainerapps.io/mcp/mcp`
- **YAML 검증 실패**: chain ID 대소문자, 1-based 잔기 인덱스 확인
  → Mol* 뷰어: https://molstar.org/viewer/
- **잡 실패**: `get_job`의 `failure_message` 참고
- **429 Concurrent limit**: 동일 `client_request_id`로 재시도 시 같은 job_id 반환
