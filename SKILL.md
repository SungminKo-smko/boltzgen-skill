---
name: boltzgen-design
version: 2.2.0
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

**NOT_REGISTERED** 출력 시:
```bash
git clone https://github.com/SungminKo-smko/boltzgen-mcp ~/workspace/boltzgen-mcp
python3 ~/workspace/boltzgen-mcp/setup.py
```

## Step 0: API KEY 로드

사용자의 API KEY를 스킬 설정 파일에서 읽는다.
**API KEY는 사용자가 직접 관리하며, 모든 tool 호출 시 인수로 전달한다.**

```bash
# 스킬 설정에서 API_KEY 읽기
SKILL_ENV="$HOME/.claude/skills/boltzgen-design/.env"
BOLTZGEN_API_KEY=""

if [ -f "$SKILL_ENV" ]; then
    BOLTZGEN_API_KEY=$(grep -E "^API_KEY=" "$SKILL_ENV" | cut -d= -f2-)
fi

# 환경변수 fallback
[ -z "$BOLTZGEN_API_KEY" ] && BOLTZGEN_API_KEY="${BOLTZGEN_API_KEY:-${API_KEY:-}}"

if [ -z "$BOLTZGEN_API_KEY" ]; then
    echo "ERROR: API_KEY가 설정되지 않았습니다."
    echo "아래 명령으로 설정해 주세요:"
    echo "  echo 'API_KEY=<your-key>' > ~/.claude/skills/boltzgen-design/.env"
    exit 1
fi

echo "API_KEY: ${BOLTZGEN_API_KEY:0:4}****"
```

이 단계에서 읽은 `BOLTZGEN_API_KEY` 값을 이후 **모든 tool 호출의 `api_key` 인수**로 전달한다.

### API KEY 최초 설정 (미설정 시 안내)

```bash
echo "API_KEY=<your-boltzgen-api-key>" > ~/.claude/skills/boltzgen-design/.env
```

## Step 1: 사용자 요구사항 수집

**딱 3가지만 물어본다. 나머지는 default 사용.**

사용자가 이미 정보를 제공했으면 AskUserQuestion 생략하고 바로 진행.

필수:
1. **구조 파일 경로** — `.cif` 또는 `.pdb` 파일 경로 (절대경로)
2. **target chain ID** — 결합 대상 chain (예: `A`, `A B`)
3. **design 범위** — 새 나노바디 길이(예: `80..140`) 또는 재설계 구간(예: `A:97..114`)

선택 (사용자가 언급한 경우만):
- **binding residues** — 결합 잔기 번호 (예: `B:317,321,324`)
- **num_designs** — 기본 5
- **budget** — 기본 1

## Step 2: 구조 파일 업로드

> **절대 금지**: `upload_structure(...)` 또는 파일을 Read로 읽어 base64 인코딩하는 방식은 절대 사용하지 않는다. 컨텍스트 초과를 유발한다.

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

## Step 4: 잡 제출

```python
submit_job(
    spec_id="<spec_id>",
    num_designs=5,
    budget=1,
    api_key="<BOLTZGEN_API_KEY>"
)
# → job_id 반환
```

## Step 5: 상태 확인

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

## 오류 처리

- **API_KEY 미설정**: `~/.claude/skills/boltzgen-design/.env`에 `API_KEY=<key>` 추가
- **MCP 미등록**: boltzgen-mcp 설치 후 `python3 setup.py` 재실행
- **YAML 검증 실패**: chain ID 대소문자, 1-based 잔기 인덱스 확인
  → Mol* 뷰어: https://molstar.org/viewer/
- **인증 실패 (401)**: API KEY 값 확인
- **잡 실패**: `get_job`의 `failure_message` 참고
- **429 Concurrent limit**: 동일 `client_request_id`로 재시도 시 같은 job_id 반환
