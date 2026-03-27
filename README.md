# boltzgen-skill

자연어 요구사항 → BoltzGen spec YAML 생성 → nanobody-designer MSA API 자동 제출

Claude Code 스킬로 설치하면 "나노바디 디자인해줘"라는 자연어 요청 한 마디로 전체 워크플로가 자동 실행된다.

## 설치

```bash
git clone https://github.com/SungminKo-smko/boltzgen-skill ~/.claude/skills/boltzgen-design
bash ~/.claude/skills/boltzgen-design/setup.sh
```

## 설정

`.env` 파일 생성 (`API_BASE_URL`은 기본값 내장, `API_KEY`만 설정하면 됨):

```
API_KEY=<your-api-key>
```

## 사용법

### 방법 A: 템플릿 렌더링 (권장 — YAML 불필요)

```bash
python3 submit.py render \
    --structure targets/input.cif \
    --include A B \
    [--design "A:97..114"] \
    [--binding "B:317,321,324"] \
    [--num-designs 5] [--budget 1]
```

### 방법 B: YAML 생성 후 제출

```bash
# 1. spec YAML 생성
python3 generate_yaml.py \
    --structure targets/input.cif \
    --target-chain A \
    --design-length 80..140 \
    --binding-residues "317,321,324" \
    --output /tmp/spec.yaml

# 2. API 제출
python3 submit.py \
    --spec /tmp/spec.yaml \
    --structure targets/input.cif
```

### 기본 동작

잡이 **running** 상태에 도달하면 job_id 등 세부 정보를 출력하고 종료한다.
완료까지 기다리려면 `--wait` 플래그를 추가한다.

## 잡 관리

```bash
python3 submit.py status <job_id>           # 상태 확인
python3 submit.py logs <job_id> [--follow]  # 실시간 로그 (실제 진행률)
python3 submit.py list [--status running]   # 잡 목록
python3 submit.py cancel <job_id>           # 잡 취소
python3 submit.py templates                 # 사용 가능한 템플릿 목록
python3 submit.py workers                   # 워커 상태 (admin)
```

## generate_yaml.py 옵션

| 옵션 | 필수 | 설명 | 기본값 |
|------|------|------|--------|
| `--structure` | ✅ | 구조 파일 경로 (.cif/.pdb) | — |
| `--target-chain` | ✅ | 결합 대상 chain ID | — |
| `--design-length` | ✅ | 나노바디 길이 범위 (예: `80..140`) | — |
| `--binding-residues` | | 결합 잔기 인덱스 (예: `317,321,324`) | — |
| `--num-designs` | | 생성할 디자인 수 | `5` |
| `--budget` | | 최종 유지할 디자인 수 | `1` |
| `--output` | | 출력 YAML 경로 | `spec.yaml` |

## 주의사항

- 잔기 인덱스는 **1-based**, `label_asym_id` 기준
- 구조 확인: [Mol* 뷰어](https://molstar.org/viewer/)
- `progress_percent`는 ACA log stream 기반으로 지연 가능 — `logs`로 실제 진행률 확인

## 파일 구조

```
boltzgen-skill/
  SKILL.md                   ← Claude Code 스킬 진입점
  CLAUDE.md                  ← 스킬 동작 상세 가이드
  submit.py                  ← API 전체 워크플로 (upload → validate/render → submit → poll)
  generate_yaml.py           ← 자연어 파라미터 → spec YAML 생성
  boltzgen_spec_reference.md ← YAML 스펙 레퍼런스 (복잡한 케이스용)
  setup.sh                   ← 의존성 설치 스크립트
  requirements.txt
  docs/
    workflow.md              ← API 워크플로 다이어그램
```

## 관련 레포

- **[boltzgen-mcp](https://github.com/SungminKo-smko/boltzgen-mcp)** — MCP Server: Claude가 BoltzGen API를 직접 tool로 호출
