# boltzgen-skill

Claude Code 스킬: 자연어 요구사항 → BoltzGen spec YAML → nanobody-designer MSA API 자동 제출.

## 스킬 동작 방식

사용자가 나노바디 디자인 요구사항을 설명하면:
1. spec 생성 (방법 A: 템플릿 렌더링 / 방법 B: generate_yaml.py)
2. `submit.py`로 API 전체 워크플로 실행 (업로드 → 검증/렌더링 → 제출 → running 대기)
3. running 도달 시 job_id 포함 세부 정보 출력 후 종료

## 필수 입력 (딱 3가지만 물어볼 것)

1. **구조 파일 경로** — `.cif` 또는 `.pdb` 파일 (로컬 경로)
2. **target chain ID** — 결합 대상 chain (예: `A`, `A,B`)
3. **design length range** — 나노바디 길이 범위 (예: `80..140`, `110`)

나머지는 **default** 사용 (질문하지 말 것):
- `--num-designs 5`, `--budget 1`

## 환경 설정

`.env` 파일 또는 환경변수:
```
API_KEY=<your-api-key>
```
`API_BASE_URL`은 기본값이 내장되어 있어 설정 불필요.

## 실행 흐름

### 방법 A: 템플릿 렌더링 (권장 — YAML 불필요)

```bash
python3 submit.py render \
    --structure <구조파일경로> \
    --include A B \
    [--design "A:97..114"] \
    [--binding "B:317,321,324"] \
    [--num-designs 5] [--budget 1]
```

### 방법 B: YAML 생성 후 제출

```bash
# Step 1: YAML 생성
python3 generate_yaml.py \
    --structure <구조파일경로> \
    --target-chain <chain_id> \
    --design-length <길이범위> \
    [--binding-residues "317,321,324"] \
    --output /tmp/boltzgen_spec.yaml

# Step 2: API 제출
python3 submit.py \
    --spec /tmp/boltzgen_spec.yaml \
    --structure <구조파일경로>
```

### 기본 동작: running 도달 시 세부 정보 출력 후 종료

잡이 running 상태에 도달하면 아래 정보를 출력하고 종료한다:
- job_id, status, protocol, stage, created_at, started_at
- 이후 확인 명령 (status / logs / cancel)

완료까지 기다려야 할 경우 `--wait` 플래그 추가.

## 잡 관리

```bash
python3 submit.py status <job_id>          # 상태 확인
python3 submit.py logs <job_id> [--follow] # 실시간 로그 (실제 진행률)
python3 submit.py list [--status running]  # 잡 목록
python3 submit.py cancel <job_id>          # 잡 취소
python3 submit.py templates                # 사용 가능한 템플릿 목록
python3 submit.py workers                  # 워커 상태 (admin)
```

> `status`의 `progress_percent`는 ACA log stream 기반으로 지연이 있을 수 있음.
> 정확한 진행률은 `logs`로 확인.

## 오류 처리

- **YAML 검증 실패**: chain ID 대소문자 확인, 잔기 인덱스는 1-based (label_asym_id 기준)
  → Mol* 뷰어: https://molstar.org/viewer/
- **API 인증 실패**: `.env`에 `API_KEY` 설정 확인
- **잡 실패**: `failure_message` 출력 참고
- **429 Concurrent job limit**: `--client-request-id`를 동일하게 유지하면 같은 job_id 반환

## 의존성

```
httpx>=0.27.0
pyyaml>=6.0.2
```

```bash
bash setup.sh   # 또는: pip install -r requirements.txt
```

## 관련 레포

- **[boltzgen-mcp](https://github.com/SungminKo-smko/boltzgen-mcp)** — MCP Server (Claude가 직접 tool로 호출)
