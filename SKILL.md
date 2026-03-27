---
name: boltzgen-design
version: 1.5.0
description: |
  BoltzGen 나노바디 디자인 자동화 스킬. 사용자의 자연어 요구사항을 BoltzGen spec YAML로
  변환하고, nanobody-designer MSA API에 업로드 → 검증 → 제출 → 상태 추적 → 아티팩트
  다운로드까지 전체 워크플로를 자동화한다.
  Use when asked to "나노바디 디자인", "boltzgen 실행", "design job 제출", "spec yaml 만들어줘".
allowed-tools:
  - Bash
  - Read
  - Write
  - AskUserQuestion
---

# /boltzgen-design

사용자의 자연어 요구사항을 BoltzGen spec YAML로 변환하고, nanobody-designer MSA API에
디자인 잡을 제출하는 자동화 스킬.

## 설치 방법 (웹 설치)

```bash
git clone https://github.com/SungminKo-smko/boltzgen-skill ~/.claude/skills/boltzgen-design
```

## Spec YAML 레퍼런스 로드 (필수)

YAML을 작성하기 전에 항상 레퍼런스 문서를 읽는다:

```bash
cat "$SKILL_DIR/boltzgen_spec_reference.md"
```

또는 Read 툴로:
```
$SKILL_DIR/boltzgen_spec_reference.md
```

이 문서에는 모든 YAML 필드, 패턴, 주의사항이 정의되어 있다.
**YAML 생성 전 반드시 참고할 것.**

## 초기화 (run first)

```bash
# 스킬 디렉토리: SKILL.md와 스크립트가 같은 위치
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
# fallback
[ -z "$SKILL_DIR" ] || [ "$SKILL_DIR" = "." ] && SKILL_DIR=~/.claude/skills/boltzgen-design
echo "SKILL_DIR: $SKILL_DIR"
ls "$SKILL_DIR/generate_yaml.py" "$SKILL_DIR/submit.py" 2>&1
```

스크립트가 없으면:
```bash
git clone https://github.com/SungminKo-smko/boltzgen-skill "$SKILL_DIR"
```

의존성 확인:
```bash
python3 -c "import httpx, yaml; print('OK')" 2>&1 || \
  (bash "$SKILL_DIR/setup.sh" --quiet 2>&1) || \
  pip3 install -r "$SKILL_DIR/requirements.txt" --break-system-packages -q
```

## Step 1: 사용자 요구사항 수집

**딱 3가지만 물어본다. 나머지는 default 사용.**

사용자가 이미 정보를 제공했으면 AskUserQuestion 생략하고 바로 진행.

필수:
1. **구조 파일 경로** — `.cif` 또는 `.pdb` 파일 경로
2. **target chain ID** — 결합 대상 chain (예: `A`, `A,B`)
3. **design length range** — 나노바디 길이 (예: `80..140`, 또는 고정 `110`)

선택 (사용자가 언급한 경우만):
- `--binding-residues` — 결합 잔기 번호 (예: `317,321,324`)
- `--num-designs` — 기본 5
- `--budget` — 기본 1

**복잡한 케이스** (기존 chain 일부를 재설계하는 경우):
사용자가 "A chain의 97~114 재설계" 같이 특정 region을 redesign하려 하면,
`generate_yaml.py` 대신 **`$SKILL_DIR/boltzgen_spec_reference.md`를 Read로 읽고**
적절한 패턴(패턴 2: design_insertions 또는 패턴 3: design)을 적용해 직접 YAML을 작성한다.

레퍼런스의 "패턴 2: 기존 체인 일부 재설계" 예시:
```yaml
entities:
  - file:
      path: targets/<filename>
      include:
        - chain:
            id: <target_chain>
            res_index: 1..<before>,<after>..   # 재설계 구간 제외
        - chain:
            id: <other_chains>
      binding_types:
        - chain:
            id: <binding_chain>
            binding: "<residue_numbers>"
      design_insertions:
        - insertion:
            id: <chain_id>
            res_index: <position_before_gap>
            num_residues: <min>..<max>
```

## Step 2: Spec YAML 생성

**일반 나노바디 디자인 (새 chain 추가):**
```bash
cd "$SKILL_DIR"
python3 generate_yaml.py \
    --structure "<구조파일경로>" \
    --target-chain "<chain_id>" \
    --design-length "<길이범위>" \
    [--binding-residues "<잔기번호>"] \
    [--num-designs <N>] \
    [--budget <B>] \
    --output /tmp/boltzgen_spec.yaml
```

생성된 YAML을 Read로 읽어 사용자에게 보여준다.

## Step 3: API 제출

API 인증: `API_KEY`만 설정하면 된다 (API_BASE_URL은 기본값 내장).
환경변수 또는 `$SKILL_DIR/.env` 파일:
```
API_KEY=<your-api-key>
```

### 방법 A: 템플릿 렌더링 (권장 — YAML 불필요)

서버 템플릿 `nanobody_targeted_binder`를 사용하면 generate_yaml.py 없이 바로 제출 가능.

```bash
cd "$SKILL_DIR"
python3 submit.py render \
    --structure "<구조파일경로>" \
    --include A B \                          # 포함할 체인 ID
    [--design "A:97..114"] \                 # 재설계 구간 (선택)
    [--binding "B:317,321,324,325"] \        # 결합 잔기 (선택)
    [--num-designs <N>] \
    [--budget <B>]
```

### 방법 B: Raw YAML 제출 (복잡한 케이스)

```bash
cd "$SKILL_DIR"
python3 submit.py \
    --spec /tmp/boltzgen_spec.yaml \
    --structure "<구조파일경로>" \
    [--num-designs <N>] \
    [--budget <B>]
```

### 방법 C: MCP Tools 직접 호출 (boltzgen-mcp 설치 시)

`boltzgen-mcp` MCP server가 등록된 경우, Claude가 직접 tool을 호출할 수 있다.
submit.py 없이 Claude가 네이티브 API 호출로 전체 워크플로를 처리한다.

**MCP 설치:**
```bash
git clone https://github.com/SungminKo-smko/boltzgen-mcp ~/workspace/boltzgen-mcp
pip install -r ~/workspace/boltzgen-mcp/requirements.txt

# API_KEY 설정 (입력 중 * 로 표시됨)
python3 ~/workspace/boltzgen-mcp/setup.py
# → API_KEY: ******************  (별표로 마스킹)
# → .env 파일에 저장 후 claude mcp add 명령 안내
```

**MCP Tool 호출 순서:**
1. `upload_structure(file_path)` → `asset_id`
2. `render_template(asset_id, include, design, binding_types)` → `spec_id`
   또는 `validate_spec(raw_yaml, asset_ids)` → `spec_id`
3. `submit_job(spec_id, num_designs, budget, ...)` → `job_id`
4. `get_job(job_id)` — running 도달 시 세부 정보 출력 후 종료
   (완료 대기 시 `get_job` 반복 폴링)
5. `get_artifacts(job_id)` — succeeded 후 아티팩트 URL 조회

**MCP 잡 관리 Tools:**
- `get_job(job_id)` — 상태 확인
- `get_logs(job_id, tail=100)` — 로그 조회 (실제 진행률)
- `list_jobs(status, limit)` — 잡 목록
- `cancel_job(job_id)` — 잡 취소
- `list_templates()` — 템플릿 목록
- `list_workers()` — 워커 상태 (admin)

### 고급 RuntimeOptions

```bash
--alpha 0.3                        # 필터링 가중치 (0.0~1.0)
--no-filter-biased                 # biased 필터링 비활성화
--additional-filters "ALA_fraction<0.3" "HELIX_fraction>0.2"
--metrics-override "plddt>0.8"     # 메트릭 오버라이드 표현식
--inverse-fold-num-sequences 3     # 역접힘 서열 수
--inverse-fold-avoid C M           # 역접힘에서 제외할 아미노산 (예: Cys, Met)
--reuse                            # 기존 워커 리소스 재사용
--diffusion-batch-size 4           # 확산 배치 크기 (GPU VRAM에 맞게 조정)
--client-request-id <unique-id>    # 중복 제출 방지 (idempotency)
```

**429 Concurrent job limit 시**: `--client-request-id`를 동일하게 유지한 채 재시도하면 idempotent_replay로 같은 job_id 반환.

## 잡 관리

### 상태 확인
```bash
python3 "$SKILL_DIR/submit.py" status <job_id>
```

### 실시간 로그 스트리밍 (실제 진행률 확인)
```bash
python3 "$SKILL_DIR/submit.py" logs <job_id> [--tail 30] [--follow]
```

> **참고**: `progress_percent` 필드는 ACA log stream에서 실시간으로 읽어오므로
> `status` 명령과 실제 진행률이 다를 수 있음. `logs`로 정확한 진행률 확인.

### 잡 목록 조회
```bash
python3 "$SKILL_DIR/submit.py" list [--status running|succeeded|failed|...] [--limit 20]
```

### 잡 취소
```bash
python3 "$SKILL_DIR/submit.py" cancel <job_id>
```

### 사용 가능한 템플릿 목록
```bash
python3 "$SKILL_DIR/submit.py" templates
```

### 워커 상태 조회 (admin)
```bash
python3 "$SKILL_DIR/submit.py" workers
```

## Step 4: 결과 출력

잡이 **running** 상태에 도달하면 폴링을 중단하고 세부 정보를 출력한다:

- job_id
- status / current_stage / progress
- protocol, num_designs, budget
- created_at / started_at
- 이후 확인 명령 안내 (status, logs, cancel)

완료까지 기다려야 하는 경우에만 `--wait` 플래그 추가:
```bash
python3 submit.py render ... --wait
```
`--wait` 시: 완료 후 아티팩트 URL 출력 및 `./results/<job_id>_artifacts.json` 저장.

## 오류 처리

- **YAML 검증 실패 (file not found)**: spec YAML의 `path:`가 `targets/<filename>` 형식인지 확인
  (submit.py가 업로드 시 `relative_path: targets/<filename>`으로 저장)
- **YAML 검증 실패 (KeyError insertion)**: `design_insertions` 항목에 `insertion:` 키 감싸기
- **YAML 검증 실패 (chain/residue)**: chain ID 대소문자, 1-based 잔기 인덱스 확인
  → Mol* 뷰어: https://molstar.org/viewer/
- **API 인증 실패**: `$SKILL_DIR/.env`에 API_BASE_URL, API_KEY 확인
- **잡 실패**: failure_message 출력 후 원인 안내
