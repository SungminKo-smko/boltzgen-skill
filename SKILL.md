---
name: boltzgen-design
version: 2.0.0
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

boltzgen MCP 서버가 등록되어 있어야 한다.

```bash
claude mcp list 2>/dev/null | grep boltzgen || echo "NOT_REGISTERED"
```

**NOT_REGISTERED** 출력 시 사용자에게 안내:
```
boltzgen MCP 서버가 등록되지 않았습니다. 먼저 설치해 주세요:

git clone https://github.com/SungminKo-smko/boltzgen-mcp ~/workspace/boltzgen-mcp
python3 ~/workspace/boltzgen-mcp/setup.py
```
→ setup.py가 의존성 설치 + API_KEY 설정 + MCP 등록을 자동으로 처리한다.

## Spec YAML 레퍼런스 (복잡한 케이스)

복잡한 YAML이 필요한 경우(`validate_spec` 사용 시) 반드시 참고:

```
$SKILL_DIR/boltzgen_spec_reference.md
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

```python
upload_structure(file_path="<절대경로>")
# → asset_id 반환
```

## Step 3: Spec 생성

### 일반 나노바디 (템플릿 렌더링 — 권장)

```python
render_template(
    asset_id="<asset_id>",
    include=["A", "B"],            # 포함할 chain ID 목록
    design="A:97..114",            # 재설계 구간 (선택)
    binding_types=["B:317,321,324"] # 결합 잔기 (선택)
)
# → spec_id 반환
```

### 복잡한 케이스 (raw YAML 직접 작성)

`boltzgen_spec_reference.md`를 Read로 읽고 적절한 패턴을 적용해 YAML 작성 후:

```python
validate_spec(
    raw_yaml="<yaml 문자열>",
    asset_ids={"targets/<filename>": "<asset_id>"}
)
# → spec_id 반환
```

## Step 4: 잡 제출

```python
submit_job(
    spec_id="<spec_id>",
    num_designs=5,    # 기본값
    budget=1          # 기본값
)
# → job_id 반환
```

## Step 5: 상태 확인

잡이 **running** 상태에 도달하면 세부 정보를 출력하고 종료:

```python
get_job(job_id="<job_id>")
```

출력 정보:
- job_id, status, protocol, stage
- created_at, started_at
- 이후 확인 방법 안내

완료까지 대기가 필요한 경우 `get_job`을 폴링하며 `succeeded` 상태 확인 후:
```python
get_artifacts(job_id="<job_id>")
# → 아티팩트 URL 목록
```

## 잡 관리

```python
get_job(job_id)               # 상태 확인
get_logs(job_id, tail=100)    # 실시간 로그 (실제 진행률)
list_jobs(status="running")   # 잡 목록
cancel_job(job_id)            # 잡 취소
list_templates()              # 사용 가능한 템플릿 목록
list_workers()                # 워커 상태 (admin)
```

> `progress_percent`는 ACA log stream 기반으로 지연 가능. 정확한 진행률은 `get_logs`로 확인.

## 오류 처리

- **YAML 검증 실패 (chain/residue)**: chain ID 대소문자, 1-based 잔기 인덱스 확인
  → Mol* 뷰어: https://molstar.org/viewer/
- **MCP 미등록**: `claude mcp list`에 boltzgen 없으면 boltzgen-mcp 설치 필요
- **API 인증 실패**: `~/workspace/boltzgen-mcp/.env`의 `API_KEY` 확인
- **잡 실패**: `get_job`의 `failure_message` 참고
- **429 Concurrent limit**: `submit_job`에 동일 `client_request_id` 전달 시 같은 job_id 반환 (idempotent)
