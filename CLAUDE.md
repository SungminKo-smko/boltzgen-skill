# boltzgen-skill

Claude Code 스킬: boltzgen MCP 서버를 통해 나노바디 디자인 잡을 제출한다.

## 인증 (자동)

MCP가 streamable-http로 등록되어 있으면 **최초 연결 시 OAuth 2.1 브라우저 인증이 자동 실행**된다.
이후 모든 tool 호출은 별도 인증 파라미터 없이 동작한다.

> **참고**: @shaperon.com 계정은 자동 승인.

## 필수 입력 (딱 3가지만 물어볼 것)

1. **구조 파일 경로** — `.cif` 또는 `.pdb` 파일 (절대경로)
2. **target chain ID** — 결합 대상 chain (예: `A`, `A B`)
3. **design 범위** — 길이 범위(예: `80..140`) 또는 재설계 구간(예: `A:97..114`)

나머지는 **default** 사용 (질문하지 말 것):
- `num_designs=5`, `budget=1`

## MCP 전제 조건

boltzgen API 내장 MCP 서버가 Streamable HTTP로 등록되어 있어야 한다:

```bash
claude mcp add boltzgen-mcp \
  --transport streamable-http \
  https://nanobody-aca-api.politebay-55ff119b.westus3.azurecontainerapps.io/mcp/mcp
```

최초 접속 시 MCP OAuth 2.1이 자동으로 브라우저 인증을 진행한다.

## 워크플로

```
[Step 0] MCP OAuth 자동 인증 (별도 설정 불필요)
  ↓
[Step 2] create_upload_url(filename) → asset_id + upload_url
  → Bash: curl -X PUT -T <file_path> -H "x-ms-blob-type: BlockBlob" -H "Content-Type: ..." <upload_url>
  ↓
render_template(asset_id, include, design, binding_types) → spec_id
  또는 validate_spec(raw_yaml, asset_ids) → spec_id
  ↓
submit_job(spec_id, num_designs, budget) → job_id
  ↓
get_job(job_id) — running 도달 시 세부 정보 출력 후 종료
```

## 파일 업로드

`create_upload_url` + `curl PUT` 방식만 사용한다.
파일 내용이 Claude 컨텍스트를 거치지 않아 대용량 CIF/PDB 파일도 처리 가능.
`upload_structure(...)` 및 base64 인코딩 방식은 컨텍스트 초과를 유발하므로 **절대 사용 금지**.

## 기본 동작

잡이 **running** 상태에 도달하면 아래 정보를 출력하고 종료:
- job_id, status, protocol, stage, created_at, started_at
- 이후 확인 명령 (get_job / get_logs / cancel_job)

완료까지 대기 시 `get_job` 폴링 → `succeeded` 후 `get_artifacts`로 URL 조회.

## 잡 관리

```python
get_job(job_id)                        # 상태 확인
get_logs(job_id, tail=100)             # 실시간 로그 (실제 진행률)
list_jobs(status="running")            # 잡 목록
cancel_job(job_id)                     # 잡 취소
list_templates()                       # 템플릿 목록
list_workers()                         # 워커 상태 (admin)
```

> `progress_percent`는 ACA log stream 기반으로 지연 가능. 정확한 진행률은 `get_logs`로 확인.

## 오류 처리

- **인증 실패**: MCP streamable-http 연결을 재시도하면 OAuth 2.1이 다시 실행된다
- **401 오류**: OAuth 토큰 만료 시 MCP 재연결로 자동 갱신
- **MCP 미등록**: `claude mcp add boltzgen-mcp --transport streamable-http https://nanobody-aca-api.politebay-55ff119b.westus3.azurecontainerapps.io/mcp/mcp`
- **YAML 검증 실패**: chain ID 대소문자, 잔기 인덱스는 1-based (label_asym_id 기준)
  → Mol* 뷰어: https://molstar.org/viewer/
- **잡 실패**: `get_job`의 `failure_message` 참고
- **429 Concurrent limit**: 동일 `client_request_id`로 재시도 시 같은 job_id 반환

## 관련 레포

- **[boltzgen_MSA](https://github.com/SungminKo-smko/boltzgen_MSA)** — BoltzGen API + 내장 MCP Server (Streamable HTTP)
