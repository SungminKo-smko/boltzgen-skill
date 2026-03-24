---
name: boltzgen-design
version: 1.2.0
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

```bash
cd "$SKILL_DIR"
python3 submit.py \
    --spec /tmp/boltzgen_spec.yaml \
    --structure "<구조파일경로>" \
    [--num-designs <N>] \
    [--budget <B>]
```

API 인증: `API_KEY`만 설정하면 된다 (API_BASE_URL은 기본값 내장).

환경변수 또는 `$SKILL_DIR/.env` 파일:
```
API_KEY=<your-api-key>
```

없으면 사용자에게 설정 요청.

**429 Concurrent job limit 시**: 30초 간격으로 최대 60회 재시도.
이미 validated spec_id가 있으면 직접 재제출:
```bash
python3 -c "
import os, json, time
from pathlib import Path
import httpx
for line in Path('$SKILL_DIR/.env').read_text().splitlines():
    line=line.strip()
    if line and '=' in line and not line.startswith('#'):
        k,v=line.split('=',1); os.environ.setdefault(k.strip(),v.strip())
base_url=os.environ['API_BASE_URL'].rstrip('/')
api_key=os.environ['API_KEY']
headers={'x-api-key':api_key,'content-type':'application/json'}
spec_id='<SPEC_ID>'
for i in range(60):
    with httpx.Client(headers=headers,timeout=30) as c:
        r=c.post(f'{base_url}/v1/design-jobs',content=json.dumps({'validated_spec_id':spec_id,'runtime_options':{'num_designs':<N>,'budget':<B>}}))
    if r.status_code in(200,201): print('job_id:',r.json()['job_id']); break
    print(f'[{i+1}] 429 - wait 30s'); time.sleep(30)
"
```

## Step 4: 결과 출력

- job_id, 최종 status 출력
- 아티팩트 URL 목록 출력
- 저장된 JSON 파일 경로 안내 (`./results/<job_id>_artifacts.json`)

## 오류 처리

- **YAML 검증 실패 (file not found)**: spec YAML의 `path:`가 `targets/<filename>` 형식인지 확인
  (submit.py가 업로드 시 `relative_path: targets/<filename>`으로 저장)
- **YAML 검증 실패 (KeyError insertion)**: `design_insertions` 항목에 `insertion:` 키 감싸기
- **YAML 검증 실패 (chain/residue)**: chain ID 대소문자, 1-based 잔기 인덱스 확인
  → Mol* 뷰어: https://molstar.org/viewer/
- **API 인증 실패**: `$SKILL_DIR/.env`에 API_BASE_URL, API_KEY 확인
- **잡 실패**: failure_message 출력 후 원인 안내
