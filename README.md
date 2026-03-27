# boltzgen-skill

자연어 요구사항 → BoltzGen API 자동 제출 (MCP 기반)

Claude Code 스킬로 설치하면 "나노바디 디자인해줘"라는 한 마디로 업로드 → 렌더링 → 제출 → running 확인까지 자동 실행된다.

## 설치

```bash
git clone https://github.com/SungminKo-smko/boltzgen-skill ~/.claude/skills/boltzgen-design
```

## 전제 조건: boltzgen MCP 서버

이 스킬은 [boltzgen-mcp](https://github.com/SungminKo-smko/boltzgen-mcp) MCP 서버를 사용한다.

```bash
git clone https://github.com/SungminKo-smko/boltzgen-mcp ~/workspace/boltzgen-mcp
python3 ~/workspace/boltzgen-mcp/setup.py
```

`setup.py`가 한 번에 처리:
- 의존성 설치 (`mcp[cli]`, `httpx`)
- API_KEY 입력 (별표 마스킹)
- Claude Code 또는 Claude Desktop에 MCP 등록

## 사용법

Claude Code에서:
```
/boltzgen-design
나노바디 디자인해줘. 구조 파일: input.cif, A 체인 대상, 길이 80~140
```

## 워크플로

```
upload_structure → render_template/validate_spec → submit_job → get_job(running)
```

잡이 **running** 상태에 도달하면 job_id 등 세부 정보를 출력하고 종료.

## 잡 관리

MCP tools로 직접 호출:

```python
get_job(job_id)               # 상태 확인
get_logs(job_id, tail=100)    # 실시간 로그 (실제 진행률)
list_jobs(status="running")   # 잡 목록
cancel_job(job_id)            # 잡 취소
get_artifacts(job_id)         # 완료 후 아티팩트 URL
```

## 파일 구조

```
boltzgen-skill/
  SKILL.md                   ← Claude Code 스킬 진입점
  CLAUDE.md                  ← 스킬 동작 상세 가이드
  boltzgen_spec_reference.md ← YAML 스펙 레퍼런스 (복잡한 케이스용)
  smithery.json
```

## 관련 레포

- **[boltzgen-mcp](https://github.com/SungminKo-smko/boltzgen-mcp)** — MCP Server: Claude가 BoltzGen API를 직접 tool로 호출
