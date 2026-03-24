# boltzgen-skill

Claude Code skill: 사용자의 자연어 요구사항을 BoltzGen spec YAML로 변환하고, nanobody-designer MSA API에 디자인 잡을 제출하는 자동화 스킬.

## 스킬 동작 방식

사용자가 나노바디 디자인 요구사항을 설명하면:
1. `generate_yaml.py`로 spec YAML 생성
2. `submit.py`로 API 업로드 → 검증 → 제출 → 상태 추적 → 아티팩트 URL 출력

## 필수 입력 (딱 3가지만 물어볼 것)

사용자에게 반드시 확인해야 하는 정보:

1. **구조 파일 경로** — `.cif` 또는 `.pdb` 파일 (로컬 경로)
2. **target chain ID** — 결합 대상 chain (예: `A`, `A,B`)
3. **design length range** — 나노바디 길이 범위 (예: `80..140`, `110`)

나머지는 모두 **default** 사용 (질문하지 말 것):
- `--design-chain B`
- `--num-designs 5`
- `--budget 1`
- `--output spec.yaml`

## 환경 설정

`.env` 파일 또는 환경변수 설정 필요:
```
API_BASE_URL=https://<your-api-host>
API_KEY=<your-api-key>
```

## 실행 흐름

### Step 1: spec YAML 생성

```bash
python generate_yaml.py \
    --structure <구조파일경로> \
    --target-chain <chain_id> \
    --design-length <길이범위> \
    [--binding-residues "317,321,324"] \  # 선택사항
    [--num-designs 5] \
    [--budget 1] \
    --output spec.yaml
```

### Step 2: API 제출 (upload → validate → submit → poll → artifacts)

```bash
python submit.py \
    --spec spec.yaml \
    --structure <구조파일경로> \
    [--num-designs 5] \
    [--budget 1]
```

## 예시 대화

**사용자**: "input.cif 파일의 A 체인을 target으로 80에서 140 잔기 나노바디 디자인해줘"

**Claude 실행 순서**:
```bash
# 1. YAML 생성
python generate_yaml.py \
    --structure input.cif \
    --target-chain A \
    --design-length 80..140 \
    --output spec.yaml

# 2. API 제출
python submit.py \
    --spec spec.yaml \
    --structure input.cif
```

## 오류 처리 안내

- **YAML 검증 실패**: chain ID 대소문자 확인, 잔기 인덱스는 1-based (label_asym_id 기준)
  - Mol*로 구조 확인: https://molstar.org/viewer/
- **API 연결 실패**: `.env`에 `API_BASE_URL`, `API_KEY` 설정 확인
- **잡 실패**: `failure_message` 출력 참고

## 의존성

```
httpx>=0.27.0
pyyaml>=6.0.2
```

설치:
```bash
pip install httpx pyyaml
```
