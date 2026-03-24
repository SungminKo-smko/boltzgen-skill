# BoltzGen Spec YAML 레퍼런스

> 출처: https://github.com/SungminKo-smko/boltzgen
> 섹션: "How to make a design specification .yaml" + "All command line arguments"

---

## ⚠️ 핵심 주의사항

- 잔기 인덱스는 **1-based**, `label_asym_id` 기준 (auth_asym_id 아님)
- Mol* 뷰어에서 확인: https://molstar.org/viewer/ → 우하단 인덱스 사용
- YAML 내 파일 경로는 **YAML 파일 기준 상대경로** (MSA API 업로드 시 `targets/<filename>`)

---

## Spec YAML 기본 구조

```yaml
entities:
  - protein: ...    # 디자인할 단백질 체인
  - ligand: ...     # 소분자 리간드
  - file: ...       # 기존 구조 파일 (.cif/.pdb)

constraints:        # (선택) 공유결합 등 구조 제약
  - bond: ...
  - total_len: ...
```

---

## entities 상세

### protein — 디자인할 단백질 체인

```yaml
- protein:
    id: B                          # 체인 ID (필수)
    sequence: 80..140              # 길이 범위 (80~140 랜덤 샘플)
    # sequence: 17                 # 고정 길이
    # sequence: 3..5C6C3           # 가변+고정 혼합: 3~5개 디자인, Cys, 6개 디자인, 3개 디자인
    # sequence: 15..20AAAVTTT18PP  # 고정 서열 + 디자인 구간 혼합
    binding_types: uuuBBBuNN       # B=결합, N=비결합, u=미지정 (선택)
    secondary_structure: HHHLLLEE  # 2차 구조 제약 (선택)
    cyclic: false                  # 고리형 펩타이드 여부 (선택)
```

**sequence 표기법:**
| 표기 | 의미 |
|------|------|
| `80..140` | 80~140 잔기 랜덤 길이 디자인 |
| `17` | 정확히 17개 디자인 잔기 |
| `AAVTTT` | 고정 아미노산 서열 |
| `3..5C6C3` | 가변(3~5) + Cys + 6개 디자인 + Cys + 3개 디자인 |

**binding_types 문자:**
- `B` — 결합 잔기
- `N` — 비결합 잔기
- `u` — 미지정 (기본값)

---

### ligand — 소분자

```yaml
- ligand:
    id: Q
    ccd: WHL          # CCD 코드 사용
    # smiles: 'N[C@@H](Cc1ccc(O)cc1)C(=O)O'  # 또는 SMILES
    binding_types: B
```

---

### file — 기존 구조 파일

```yaml
- file:
    path: targets/input.cif     # YAML 기준 상대경로 (MSA API: targets/<filename>)

    # 포함할 체인/잔기 지정
    include:
      - chain:
          id: A
          res_index: 2..50,55..  # 2~50번, 55번 이후 포함
      - chain:
          id: B                  # 체인 전체 포함

    # 제외할 잔기
    exclude:
      - chain:
          id: A
          res_index: ..5         # 1~5번 제외

    # 결합 위치 지정 (선택)
    binding_types:
      - chain:
          id: A
          binding: "5..7,13"     # 결합해야 할 잔기
      - chain:
          id: B
          not_binding: "all"     # B 체인에는 결합하지 말 것

    # 구조 가시성 그룹 (선택)
    structure_groups:
      - group:
          visibility: 1          # 1=구조 지정됨, 0=지정 안 됨, 2=별도 그룹
          id: A
          res_index: 10..13

    # 특정 잔기 재설계 (선택)
    design:
      - chain:
          id: A
          res_index: 14..19

    # 2차 구조 제약 (선택)
    secondary_structure:
      - chain:
          id: A
          loop: 14
          helix: 15..17
          sheet: 19

    # 삽입 디자인 (선택) — 기존 구조 중간에 새 잔기 삽입
    design_insertions:
      - insertion:
          id: A                  # 삽입이 일어날 체인 ID
          res_index: 20          # 20번 잔기 다음에 삽입
          num_residues: 2..9     # 2~9개 잔기 삽입
          secondary_structure: HELIX  # UNSPECIFIED, LOOP, HELIX, SHEET

    # 근접 잔기 포함 (선택)
    include_proximity:
      - chain:
          id: A
          res_index: 10..16
          radius: 35             # 35 Å 이내 잔기 포함
```

---

## constraints 상세

### bond — 공유결합

```yaml
constraints:
  - bond:
      atom1: [R, 4, SG]    # [체인ID, 잔기번호, 원자명]
      atom2: [Q, 1, CK]    # 리간드 Q의 CK 원자와 결합
```

- 소분자(CCD): atom_name은 CCD에서 확인
- 소분자(SMILES): SMILES에서 원소 인덱스 기준 (예: `C6` = 6번째 탄소)

### total_len — 총 길이 제약

```yaml
constraints:
  - total_len:
      min: 100
      max: 200
```

---

## 주요 사용 패턴

### 패턴 1: 새 나노바디 디자인 (표준)

```yaml
entities:
  - protein:
      id: B
      sequence: 80..140          # 나노바디 (80~140 잔기)

  - file:
      path: targets/input.cif
      include:
        - chain:
            id: A                # 타겟 체인
      binding_types:
        - chain:
            id: A
            binding: "317,321,324"  # 결합 잔기
```

### 패턴 2: 기존 체인 일부 재설계 (design_insertions)

A 체인의 97~114 서열을 제거하고 그 자리에 12~18개 새 잔기 삽입:

```yaml
entities:
  - file:
      path: targets/input.cif
      include:
        - chain:
            id: A
            res_index: 1..96,115..   # 97~114 제외
        - chain:
            id: B
      binding_types:
        - chain:
            id: B
            binding: "227,230,321,325"
      design_insertions:
        - insertion:
            id: A
            res_index: 96            # 96번 잔기 다음에 삽입
            num_residues: 12..18
```

### 패턴 3: 특정 잔기만 재설계 (design)

```yaml
entities:
  - file:
      path: targets/input.cif
      include:
        - chain:
            id: A
      design:
        - chain:
            id: A
            res_index: 14..19       # 14~19번 잔기만 재설계
```

### 패턴 4: 소분자 결합 설계

```yaml
entities:
  - protein:
      id: B
      sequence: 80..140

  - file:
      path: targets/input.cif
      include:
        - chain:
            id: A

  - ligand:
      id: L
      ccd: ATP
      binding_types: B
```

---

## boltzgen run 주요 인수

```bash
boltzgen run <design_spec.yaml> \
  --protocol {protein-anything,peptide-anything,protein-small_molecule,nanobody-anything,antibody-anything} \
  --output <output_dir> \
  --num_designs <N>       # 생성할 총 디자인 수 (예: 10000)
  --budget <B>            # 최종 선별 개수 (필터링 후)
  --devices <D>           # 사용할 GPU 수
  --steps <step1> ...     # 특정 단계만 실행 (선택)
```

### 프로토콜별 특징

| 프로토콜 | 적합 대상 | 특이사항 |
|---------|-----------|---------|
| `protein-anything` | 단백질 → 단백질/펩타이드 | design folding 포함 |
| `peptide-anything` | (고리형) 펩타이드 디자인 | Cys 생성 안 함, design folding 없음 |
| `protein-small_molecule` | 단백질 → 소분자 | affinity prediction 포함 |
| `nanobody-anything` | 나노바디 CDR 디자인 | antibody와 동일 설정 |
| `antibody-anything` | 항체 CDR 디자인 | Cys 생성 안 함 |

### 파이프라인 단계

| 단계 | 설명 |
|------|------|
| `design` | 확산 모델로 백본 생성 |
| `inverse_folding` | 백본에서 서열 재설계 |
| `folding` | Boltz-2로 복합체 재접힘 |
| `design_folding` | 바인더 단독 재접힘 (나노바디/펩타이드 제외) |
| `affinity` | 소분자 결합 친화력 예측 |
| `analysis` | 품질 지표 분석 |
| `filtering` | 최종 선별/랭킹 |

### 주요 옵션

```bash
# 일부 단계만 실행
--steps design inverse_folding

# 필터링 재실행 (파라미터 조정)
boltzgen run spec.yaml --steps filtering \
  --refolding_rmsd_threshold 3.0 \
  --filter_biased=false \
  --additional_filters 'ALA_fraction<0.3' \
  --alpha 0.2

# 여러 실행 병합 후 필터링
boltzgen merge run_a/ run_b/ --output merged/
boltzgen run spec.yaml --steps filtering --output merged/ --budget 60
```

---

## MSA API 사용 시 차이점

로컬 boltzgen CLI가 아닌 **MSA API (submit.py)** 사용 시:

| 항목 | 로컬 CLI | MSA API |
|------|---------|---------|
| 구조 파일 경로 | YAML 상대경로 | `targets/<filename>` (업로드 후) |
| 실행 방법 | `boltzgen run spec.yaml` | `python submit.py --spec spec.yaml --structure file.cif` |
| 결과 | 로컬 디렉토리 | 아티팩트 URL (JSON) |
| num_designs/budget | CLI 인수 | API `runtime_options` |
