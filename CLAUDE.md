# boltzgen-skill

Claude Code 스킬: boltzgen MCP 서버를 통해 나노바디 디자인 잡을 제출한다.

## API KEY 관리 (중요)

boltzgen MCP 서버는 **공유 서버**다. API KEY는 사용자 각자가 스킬 설정 파일에 보관하며,
**모든 tool 호출 시 `api_key` 인수로 직접 전달**한다. MCP 서버 환경변수에 의존하지 않는다.

API KEY 설정:
```bash
echo "API_KEY=<your-boltzgen-api-key>" > ~/.claude/skills/boltzgen-design/.env
```

스킬 실행 시 Step 0에서 이 파일을 읽어 `BOLTZGEN_API_KEY` 변수에 로드하고,
이후 모든 tool 호출에 `api_key=<BOLTZGEN_API_KEY>`를 인수로 전달한다.

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

`setup.py`가 의존성 설치 + MCP 등록을 한 번에 처리한다.
(API KEY는 스킬 설정 파일 `~/.claude/skills/boltzgen-design/.env`에 별도 보관)

## 워크플로

```
[Step 0] ~/.claude/skills/boltzgen-design/.env 에서 API KEY 로드
  ↓
[Step 2 — remote] create_upload_url(filename, api_key=<KEY>) → asset_id + upload_url
  → Bash: curl -X PUT -T <file_path> -H "x-ms-blob-type: BlockBlob" -H "Content-Type: ..." <upload_url>
[Step 2 — local]  upload_structure(file_path, api_key=<KEY>) → asset_id
  ↓
render_template(asset_id, include, design, binding_types, api_key=<KEY>) → spec_id
  또는 validate_spec(raw_yaml, asset_ids, api_key=<KEY>) → spec_id
  ↓
submit_job(spec_id, num_designs, budget, api_key=<KEY>) → job_id
  ↓
get_job(job_id, api_key=<KEY>) — running 도달 시 세부 정보 출력 후 종료
```

## 파일 업로드 방식 선택

- **remote MCP 서버** (`boltzgen-remote`): `create_upload_url` + `curl PUT` 사용.
  파일 내용이 Claude 컨텍스트를 거치지 않아 대용량 CIF/PDB 파일도 처리 가능.
  `upload_structure(file_content_base64=...)` 방식은 컨텍스트 초과를 유발하므로 **사용 금지**.
- **local stdio 서버** (`boltzgen`): `upload_structure(file_path=...)` 사용.

## 기본 동작

잡이 **running** 상태에 도달하면 아래 정보를 출력하고 종료:
- job_id, status, protocol, stage, created_at, started_at
- 이후 확인 명령 (get_job / get_logs / cancel_job)

완료까지 대기 시 `get_job` 폴링 → `succeeded` 후 `get_artifacts`로 URL 조회.

## 잡 관리

```python
get_job(job_id, api_key=<KEY>)               # 상태 확인
get_logs(job_id, tail=100, api_key=<KEY>)    # 실시간 로그 (실제 진행률)
list_jobs(status="running", api_key=<KEY>)   # 잡 목록
cancel_job(job_id, api_key=<KEY>)            # 잡 취소
list_templates(api_key=<KEY>)               # 템플릿 목록
list_workers(api_key=<KEY>)                 # 워커 상태 (admin)
```

> `progress_percent`는 ACA log stream 기반으로 지연 가능. 정확한 진행률은 `get_logs`로 확인.

## 오류 처리

- **API KEY 미설정**: `~/.claude/skills/boltzgen-design/.env`에 `API_KEY=<key>` 추가
- **MCP 미등록**: boltzgen-mcp 설치 후 `python3 setup.py` 재실행
- **YAML 검증 실패**: chain ID 대소문자, 잔기 인덱스는 1-based (label_asym_id 기준)
  → Mol* 뷰어: https://molstar.org/viewer/
- **API 인증 실패 (401)**: API KEY 값 확인
- **잡 실패**: `get_job`의 `failure_message` 참고
- **429 Concurrent limit**: 동일 `client_request_id`로 재시도 시 같은 job_id 반환

## 관련 레포

- **[boltzgen-mcp](https://github.com/SungminKo-smko/boltzgen-mcp)** — MCP Server (Claude가 직접 tool로 호출)
