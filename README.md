# boltzgen-skill

자연어 요구사항 → BoltzGen spec YAML 생성 → nanobody-designer MSA API 자동 제출

## 개요

연구자가 나노바디 디자인 요구사항을 자연어로 설명하면:
1. BoltzGen spec YAML을 자동 생성
2. MSA API 전체 워크플로 자동화 (업로드 → 검증 → 제출 → 상태 추적 → 아티팩트 다운로드)

## 설치

```bash
pip install httpx pyyaml
```

## 설정

```bash
export API_BASE_URL="https://<your-api-host>"
export API_KEY="<your-api-key>"
```

또는 프로젝트 루트에 `.env` 파일 생성:
```
API_BASE_URL=https://<your-api-host>
API_KEY=<your-api-key>
```

## 사용법

### 1. Spec YAML 생성

```bash
python generate_yaml.py \
    --structure targets/input.cif \
    --target-chain A \
    --design-length 80..140 \
    --output spec.yaml
```

**옵션:**

| 옵션 | 필수 | 설명 | 기본값 |
|------|------|------|--------|
| `--structure` | ✅ | 구조 파일 경로 (.cif/.pdb) | — |
| `--target-chain` | ✅ | 결합 대상 chain ID (콤마로 복수 지정 가능) | — |
| `--design-length` | ✅ | 나노바디 길이 범위 (예: `80..140`) 또는 고정값 | — |
| `--design-chain` | | 디자인 chain ID | `B` |
| `--binding-residues` | | 결합해야 할 잔기 인덱스 (예: `317,321,324`) | — |
| `--num-designs` | | 생성할 디자인 수 | `5` |
| `--budget` | | 예산 (≤ num-designs) | `1` |
| `--output` | | 출력 YAML 경로 | `spec.yaml` |

### 2. API 제출 및 결과 추적

```bash
python submit.py \
    --spec spec.yaml \
    --structure targets/input.cif \
    --num-designs 5 \
    --budget 1
```

**전체 워크플로 자동 실행:**
1. 구조 파일 → Azure Blob 업로드
2. spec YAML → `/v1/specs/validate` API 검증
3. 검증된 spec → `/v1/design-jobs` 제출
4. job 상태 polling (5초 간격, 최대 1시간)
5. 완료 시 아티팩트 URL 출력 + JSON 저장

## 예제

```bash
# 나노바디 디자인: A 체인 target, 80~140 잔기
python generate_yaml.py \
    --structure examples/target.cif \
    --target-chain A \
    --design-length 80..140 \
    --binding-residues "317,321,324,325,326" \
    --output spec.yaml

python submit.py \
    --spec spec.yaml \
    --structure examples/target.cif
```

## 주의사항

- 잔기 인덱스는 **1-based**, `label_asym_id` 기준 (Mol* 뷰어로 확인 권장)
- Mol* 뷰어: https://molstar.org/viewer/

## 파일 구조

```
boltzgen-skill/
  CLAUDE.md         ← Claude Code 스킬 지시 문서
  generate_yaml.py  ← 자연어 입력 → spec YAML 생성
  submit.py         ← API 전체 워크플로 (upload → validate → submit → poll → artifacts)
  README.md
```
