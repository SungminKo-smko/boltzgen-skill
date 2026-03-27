# boltzgen-skill

Claude Code 스킬: boltzgen MCP 서버를 통해 나노바디 디자인 잡을 제출한다.

## 필수 입력 (딱 3가지만 물어볼 것)

1. **구조 파일 경로** — `.cif` 또는 `.pdb` 파일 (절대경로)
2. **target chain ID** — 결합 대상 chain (예: `A`, `A B`)
3. **design 범위** — 길이 범위(예: `80..140`) 또는 재설계 구간(예: `A:97..114`)

나머지는 **default** 사용 (질문하지 말 것):
- `num_designs=5`, `budget=1`

## MCP 전제 조건

boltzgen MCP 서버가 등록되어 있어야 한다:

```bash
git clone https://github.com/SungminKo-smko/boltzgen-mcp ~/workspace/boltzgen-mcp
python3 ~/workspace/boltzgen-mcp/setup.py
```

`setup.py`가 의존성 설치 + API_KEY 설정 + MCP 등록을 한 번에 처리한다.

## 워크플로

```
upload_structure(file_path) → asset_id
  ↓
render_template(asset_id, include, design, binding_types) → spec_id
  또는 validate_spec(raw_yaml, asset_ids) → spec_id
  ↓
submit_job(spec_id, num_designs, budget) → job_id
  ↓
get_job(job_id) — running 도달 시 세부 정보 출력 후 종료
```

## 기본 동작

잡이 **running** 상태에 도달하면 아래 정보를 출력하고 종료:
- job_id, status, protocol, stage, created_at, started_at
- 이후 확인 명령 (get_job / get_logs / cancel_job)

완료까지 대기 시 `get_job` 폴링 → `succeeded` 후 `get_artifacts`로 URL 조회.

## 잡 관리

```python
get_job(job_id)               # 상태 확인
get_logs(job_id, tail=100)    # 실시간 로그 (실제 진행률)
list_jobs(status="running")   # 잡 목록
cancel_job(job_id)            # 잡 취소
list_templates()              # 템플릿 목록
list_workers()                # 워커 상태 (admin)
```

> `progress_percent`는 ACA log stream 기반으로 지연 가능. 정확한 진행률은 `get_logs`로 확인.

## 오류 처리

- **MCP 미등록**: boltzgen-mcp 설치 후 `python3 setup.py` 재실행
- **YAML 검증 실패**: chain ID 대소문자, 잔기 인덱스는 1-based (label_asym_id 기준)
  → Mol* 뷰어: https://molstar.org/viewer/
- **API 인증 실패**: `~/workspace/boltzgen-mcp/.env`의 `API_KEY` 확인
- **잡 실패**: `get_job`의 `failure_message` 참고
- **429 Concurrent limit**: 동일 `client_request_id`로 재시도 시 같은 job_id 반환

## 관련 레포

- **[boltzgen-mcp](https://github.com/SungminKo-smko/boltzgen-mcp)** — MCP Server (Claude가 직접 tool로 호출)
