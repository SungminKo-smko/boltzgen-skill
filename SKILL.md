---
name: boltzgen-design
version: 3.4.0
description: |
  BoltzGen 나노바디 디자인 자동화 스킬. 사용자의 자연어 요구사항을 BoltzGen API에
  직접 제출하여 업로드 → 렌더링/검증 → 제출 → 상태 추적까지 전체 워크플로를 자동화한다.
  Use when asked to "나노바디 디자인", "boltzgen 실행", "design job 제출", "spec yaml 만들어줘".
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# /boltzgen-design

boltzgen MCP 서버를 통해 나노바디 디자인 잡을 제출하는 스킬.

## 설치

```bash
git clone https://github.com/SungminKo-smko/boltzgen-skill ~/.claude/skills/boltzgen-design
```

## MCP 서버 확인 (run first)

```bash
claude mcp list 2>/dev/null | grep boltzgen || echo "NOT_REGISTERED"
```

**NOT_REGISTERED** 출력 시 — boltzgen API 내장 MCP를 Streamable HTTP로 등록:
```bash
claude mcp add boltzgen-mcp \
  --transport streamable-http \
  https://nanobody-aca-api.politebay-55ff119b.westus3.azurecontainerapps.io/mcp/mcp
```

> 최초 접속 시 MCP OAuth 2.1 흐름이 자동 실행되어 브라우저 인증 후 API KEY가 발급된다.

## Step 0: 인증 (자동)

MCP가 streamable-http로 등록되어 있으면 **최초 연결 시 OAuth 2.1 브라우저 인증이 자동 실행**된다.
이후 모든 tool 호출은 별도 인증 파라미터 없이 동작한다.

> **참고**: @shaperon.com 계정은 자동 승인. 그 외 계정은 관리자 승인 필요.

### 크로스 서비스 인증

API KEY는 boltz2 플랫폼(platform_core)과 동일한 Supabase identity를 공유한다.
단, 키 자체는 서비스별로 분리되어 있다 (boltzgen 키는 boltzgen에서만 동작).

## Step 1: 환경 감지 및 사용자 요구사항 수집

### Claude Desktop 감지

```bash
if [ -d "/mnt/user-data/uploads" ]; then
    echo "CLAUDE_DESKTOP=true"
    ls /mnt/user-data/uploads/
else
    echo "CLAUDE_DESKTOP=false"
fi
```

**CLAUDE_DESKTOP=true** 이면:
- 사용자가 채팅에 첨부한 파일은 `/mnt/user-data/uploads/<파일명>`에 저장된다.
- 파일명의 `#` 등 특수문자는 `_`로 변환될 수 있으므로 `ls` 결과로 실제 파일명을 확인한다.
- 사용자에게 파일 경로를 묻지 말고 위 경로를 직접 사용한다.

**CLAUDE_DESKTOP=false** 이면:
- 사용자에게 구조 파일 절대경로를 묻는다.

### 요구사항 수집

**딱 3가지만 물어본다. 나머지는 default 사용.**

사용자가 이미 정보를 제공했으면 AskUserQuestion 생략하고 바로 진행.

필수:
1. **구조 파일 경로** — `.cif` 또는 `.pdb` 파일 경로 (Claude Desktop이면 위에서 자동 확인)
2. **target chain ID** — 결합 대상 chain (예: `A`, `A B`)
3. **design 범위** — 새 나노바디 길이(예: `80..140`) 또는 재설계 구간(예: `A:97..114`)

선택 (사용자가 언급한 경우만):
- **binding residues** — 결합 잔기 번호 (예: `B:317,321,324`)
- **num_designs** — 기본 5
- **budget** — 기본 1

## Step 2: 구조 파일 업로드

> **절대 금지**: base64 인코딩, `upload_structure(...)`, Read로 파일 읽기 — 모두 사용 금지. 컨텍스트 초과를 유발한다.
>
> **remote MCP여도 curl은 로컬 Bash에서 실행된다.** MCP 서버가 로컬 파일에 접근할 필요 없다. `create_upload_url`로 SAS URL을 받아 로컬 curl이 직접 업로드한다.

```python
create_upload_url(filename="<파일명>")   # 예: "target.cif"
# → asset_id, upload_url, content_type, curl_hint 반환
```

반환된 `curl_hint`의 `<FILE_PATH>`를 실제 절대경로로 교체 후 Bash로 실행:

```bash
curl -s -X PUT -T "<절대경로>" \
  -H "x-ms-blob-type: BlockBlob" \
  -H "Content-Type: <content_type>" \
  "<upload_url>"
# 성공 시 빈 응답(200/201). 오류 시 XML 에러 메시지 출력.
```

## Step 3: Spec 생성

두 가지 방법이 있다. **render_template (권장)** 또는 **validate_spec (raw YAML)**.
두 방법 모두 `spec_id`를 반환하며, 이 `spec_id`를 Step 4에서 `submit_job`에 전달한다.

### 방법 A: render_template (권장, 대부분의 경우)

```python
result = render_template(
    asset_id="<asset_id>",
    include=["A", "B"],                                      # 포함할 체인 ID
    design=[{"chain_id": "A", "res_index": "97..114"}],      # 재설계 구간 (선택)
    binding_types=[{"chain_id": "B", "binding": "317,321,324"}]  # 결합 잔기 (선택)
)
# 반환값: {"spec_id": "xxx", "canonical_yaml": "..."} 또는 {"error": "..."}
```

**design, binding_types 딕셔너리 키:**
- `chain_id` 또는 `id` — 체인 식별자 (예: `"A"`)
- `res_index` — 잔기 범위 (예: `"97..114"`, `"14..19"`)
- `binding` — 결합 잔기 번호 (예: `"317,321,324"`)

### 방법 B: validate_spec (복잡한 케이스 — design_insertions, 소분자 등)

`render_template`으로 표현할 수 없는 경우 raw YAML을 직접 작성한다.
`boltzgen_spec_reference.md`를 Read로 읽고 패턴을 참고한다.

**주의: raw YAML의 키 이름은 render_template과 다르다.**
- `include` 내부: `chain: { id: A }` (중첩 구조)
- `binding_types` 내부: `chain: { id: A, binding: "..." }` (중첩 구조)
- `design` 내부: `chain: { id: A, res_index: "..." }` (중첩 구조)

```python
# 예: CDR3 재설계 (design_insertions)
yaml_spec = """
entities:
  - file:
      path: targets/<파일명>
      include:
        - chain:
            id: A
            res_index: 1..96,115..
        - chain:
            id: B
      binding_types:
        - chain:
            id: B
            binding: "317,321,324,325,326"
      design_insertions:
        - insertion:
            id: A
            res_index: 96
            num_residues: 12..18
"""

result = validate_spec(
    raw_yaml=yaml_spec,
    asset_ids=["<asset_id>"]
)
# 반환값: {"spec_id": "xxx"} 또는 {"error": "...", "validation_errors": [...]}
```

### render_template vs validate_spec 선택 기준

| 상황 | 방법 |
|------|------|
| 새 나노바디 디자인 (기본) | `render_template` |
| 특정 잔기 재설계 (design) | `render_template` (design 파라미터) |
| CDR 길이 변경 (design_insertions) | `validate_spec` (raw YAML) |
| 소분자 결합 설계 (ligand) | `validate_spec` (raw YAML) |
| 고리형 펩타이드 | `validate_spec` (raw YAML) |

## Step 4: 잡 제출

Step 3에서 반환된 `spec_id`로 잡을 제출한다.
반환값에 `error`가 있으면 에러 내용을 사용자에게 보여주고 중단한다.

```python
result = submit_job(
    spec_id="<spec_id>",    # render_template 또는 validate_spec에서 반환된 값
    num_designs=5,
    budget=1
)
# 반환값: {"job_id": "xxx", "status": "queued"} 또는 {"error": "..."}
```

## Step 6: 상태 확인

잡이 **running** 상태에 도달하면 세부 정보 출력 후 종료:

```python
get_job(job_id="<job_id>")
```

완료 대기 시 `get_job` 폴링 → `succeeded` 후:
```python
get_artifacts(job_id="<job_id>")
```

## 잡 관리

```python
get_job(job_id)                        # 상태 확인
get_logs(job_id, tail=100)             # 실시간 로그
list_jobs(status="running")            # 잡 목록
cancel_job(job_id)                     # 잡 취소
list_templates()                       # 템플릿 목록
list_workers()                         # 워커 상태 (admin)
```

## 로그 스트리밍 Artifact

사용자가 "로그 스트리밍", "실시간 로그", "로그 보여줘" 등을 요청하면:

> **반드시 공개 REST API 엔드포인트를 사용한다.**
> **절대 MCP 엔드포인트(`/mcp/mcp`)를 사용하지 않는다** — OAuth 인증 필요 + sandbox 차단.

아래 HTML 템플릿을 그대로 사용하되, 다음 4개 값만 교체한다:
- `JOB_ID` → 실제 job_id
- `INIT_STATUS` → 현재 상태 (queued, running 등)
- `INIT_STAGE` → 현재 단계 (design, inverse_folding 등, 없으면 빈 문자열)
- `INIT_PROGRESS` → 현재 진행률 숫자 (0~100, 없으면 0)

```html
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
#root { padding: 1rem 0; font-family: var(--font-sans); }
.top { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 12px; }
.title-block { flex: 1; }
.title-block h3 { font-size: 13px; font-weight: 500; color: var(--color-text-primary); margin-bottom: 3px; }
.job-id { font-size: 11px; color: var(--color-text-tertiary); font-family: var(--font-mono); }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 500; white-space: nowrap; }
.b-queued   { background: var(--color-background-warning); color: var(--color-text-warning); }
.b-running  { background: var(--color-background-info);    color: var(--color-text-info); }
.b-succeeded{ background: var(--color-background-success); color: var(--color-text-success); }
.b-failed   { background: var(--color-background-danger);  color: var(--color-text-danger); }
.b-canceled { background: var(--color-background-secondary); color: var(--color-text-secondary); }
.pipeline { display: flex; gap: 4px; margin-bottom: 10px; align-items: center; }
.pstep { flex: 1; text-align: center; font-size: 10px; padding: 4px 2px; border-radius: 4px; border: 0.5px solid var(--color-border-tertiary); color: var(--color-text-tertiary); transition: all 0.3s; }
.pstep.done { background: var(--color-background-success); color: var(--color-text-success); border-color: transparent; }
.pstep.active { background: var(--color-background-info); color: var(--color-text-info); border-color: transparent; font-weight: 500; }
.parrow { font-size: 10px; color: var(--color-text-tertiary); }
.progress-track { height: 3px; background: var(--color-background-secondary); border-radius: 2px; margin-bottom: 10px; }
.progress-fill  { height: 100%; background: var(--color-text-info); border-radius: 2px; transition: width 0.6s ease; }
.toolbar { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; }
.btn { font-size: 12px; padding: 4px 10px; border: 0.5px solid var(--color-border-secondary); border-radius: var(--border-radius-md); background: transparent; color: var(--color-text-primary); cursor: pointer; }
.btn:hover { background: var(--color-background-secondary); }
.btn-on { background: var(--color-background-info); color: var(--color-text-info); border-color: var(--color-border-info); }
.log-wrap { background: var(--color-background-secondary); border: 0.5px solid var(--color-border-tertiary); border-radius: var(--border-radius-md); padding: 10px 12px; height: 320px; overflow-y: auto; }
.line { font-family: var(--font-mono); font-size: 11px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; color: var(--color-text-secondary); }
.line.dim  { color: var(--color-text-tertiary); }
.line.info { color: var(--color-text-info); font-weight: 500; }
.line.ok   { color: var(--color-text-success); font-weight: 500; }
.line.warn { color: var(--color-text-warning); }
.line.err  { color: var(--color-text-danger); }
.footer { display: flex; justify-content: space-between; margin-top: 8px; font-size: 11px; color: var(--color-text-tertiary); align-items: center; }
.dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; margin-right: 4px; vertical-align: middle; background: var(--color-text-info); }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }
.blink { animation: blink 1.2s infinite; }
</style>

<div id="root">
  <div class="top">
    <div class="title-block">
      <h3>BoltzGen Log Stream</h3>
      <div class="job-id">JOB_ID</div>
    </div>
    <span id="badge" class="badge b-INIT_STATUS">INIT_STATUS</span>
  </div>
  <div class="pipeline">
    <div class="pstep" id="ps1">1 design</div><div class="parrow">›</div>
    <div class="pstep" id="ps2">2 inv_fold</div><div class="parrow">›</div>
    <div class="pstep" id="ps3">3 folding</div><div class="parrow">›</div>
    <div class="pstep" id="ps4">4 scoring</div><div class="parrow">›</div>
    <div class="pstep" id="ps5">5 ranking</div>
  </div>
  <div class="progress-track"><div class="progress-fill" id="pbar" style="width:INIT_PROGRESS%"></div></div>
  <div class="toolbar">
    <button class="btn btn-on" id="toggleBtn" onclick="toggle()">⏹ 정지</button>
    <button class="btn" onclick="clearLogs()">지우기</button>
    <span style="font-size:11px;color:var(--color-text-tertiary);margin-left:auto;" id="interval-label">5초 간격</span>
  </div>
  <div class="log-wrap" id="logbox"></div>
  <div class="footer">
    <span><span class="dot blink" id="liveDot"></span><span id="lastUpdate">로딩 중...</span></span>
    <span id="pct-label">INIT_PROGRESS%</span>
  </div>
</div>

<script>
const JOB_ID = "JOB_ID";
const API = "https://nanobody-aca-api.politebay-55ff119b.westus3.azurecontainerapps.io";

let active = true, timer = null;
const seen = new Set();

function classify(l) {
  if (/✓|completed successfully/i.test(l)) return "ok";
  if (/error|fail|traceback|exception/i.test(l)) return "err";
  if (/warn|deprecated/i.test(l)) return "warn";
  if (/\[Step \d\/5\]|Pipeline step|Running command/i.test(l)) return "info";
  if (!l.trim() || /^\*+$/.test(l.trim())) return "dim";
  return "";
}

function addLines(text) {
  const box = document.getElementById("logbox");
  let added = 0;
  (text||"").split("\n").forEach(l => {
    const clean = l.replace(/^\d{4}-\d{2}-\d{2}T[\d:.]+Z?\s+(stdout F\s+)?/,"").trimEnd();
    if (!clean || seen.has(clean)) return;
    seen.add(clean);
    const d = document.createElement("div");
    d.className = "line " + classify(clean);
    d.textContent = clean;
    box.appendChild(d);
    added++;
  });
  if (added) box.scrollTop = box.scrollHeight;
}

function updatePipeline(stage, pct) {
  const map = {design:1, inverse_folding:2, folding:3, scoring:4, ranking:5};
  const cur = map[stage] || 0;
  for (let i = 1; i <= 5; i++) {
    const el = document.getElementById("ps"+i);
    if (!el) continue;
    el.className = "pstep" + (i < cur ? " done" : i === cur ? " active" : "");
  }
  if (pct != null) {
    document.getElementById("pbar").style.width = pct + "%";
    document.getElementById("pct-label").textContent = pct + "%";
  }
}

function setStatus(s) {
  const b = document.getElementById("badge");
  b.textContent = s; b.className = "badge b-" + s;
  const dot = document.getElementById("liveDot");
  if (s === "running")        { dot.style.background = "var(--color-text-info)";    dot.classList.add("blink"); }
  else if (s === "succeeded") { dot.style.background = "var(--color-text-success)"; dot.classList.remove("blink"); }
  else if (s === "failed")    { dot.style.background = "var(--color-text-danger)";  dot.classList.remove("blink"); }
  else                        { dot.style.background = "var(--color-text-tertiary)"; dot.classList.remove("blink"); }
  if (["succeeded","failed","canceled"].includes(s)) stop();
}

async function poll() {
  try {
    // 상태 조회 (공개 REST API — 인증 불필요)
    const sr = await fetch(`${API}/v1/design-jobs/${JOB_ID}/status/public`);
    if (sr.ok) {
      const j = await sr.json();
      if (j.status) setStatus(j.status);
      updatePipeline(j.current_stage, j.progress_percent);
      if (j.status_message) addLines(j.status_message);
    }
    // 로그 조회 (공개 REST API — 인증 불필요)
    const lr = await fetch(`${API}/v1/design-jobs/${JOB_ID}/logs/public?tail=200`);
    if (lr.ok) {
      const text = await lr.text();
      addLines(text);
    }
    document.getElementById("lastUpdate").textContent = "갱신: " + new Date().toLocaleTimeString("ko-KR");
  } catch(e) {
    addLines("[오류] " + e.message);
  }
}

function stop() {
  active=false; clearInterval(timer);
  document.getElementById("toggleBtn").textContent="▶ 시작";
  document.getElementById("toggleBtn").classList.remove("btn-on");
  document.getElementById("interval-label").textContent="정지됨";
  document.getElementById("liveDot").classList.remove("blink");
}
function start() {
  active=true;
  document.getElementById("toggleBtn").textContent="⏹ 정지";
  document.getElementById("toggleBtn").classList.add("btn-on");
  document.getElementById("interval-label").textContent="5초 간격";
  poll(); timer=setInterval(poll,5000);
}
function toggle() { active ? stop() : start(); }
function clearLogs() { document.getElementById("logbox").innerHTML=""; seen.clear(); }

updatePipeline("INIT_STAGE", INIT_PROGRESS);
setStatus("INIT_STATUS");
start();
</script>
```

## 오류 처리

- **인증 실패**: MCP streamable-http 연결을 재시도하면 OAuth 2.1이 다시 실행된다
- **401 오류**: OAuth 토큰 만료 시 MCP 재연결로 자동 갱신
- **MCP 미등록**: `claude mcp add boltzgen-mcp --transport streamable-http https://nanobody-aca-api.politebay-55ff119b.westus3.azurecontainerapps.io/mcp/mcp`
- **YAML 검증 실패**: chain ID 대소문자, 1-based 잔기 인덱스 확인
  → Mol* 뷰어: https://molstar.org/viewer/
- **잡 실패**: `get_job`의 `failure_message` 참고
- **429 Concurrent limit**: 동일 `client_request_id`로 재시도 시 같은 job_id 반환
