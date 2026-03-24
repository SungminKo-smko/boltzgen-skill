#!/usr/bin/env bash
# setup.sh — boltzgen-skill 의존성 설치 스크립트
# 지원 환경: macOS, Linux (Python 3.9+)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUIET=${1:-""}

log() {
  [ "$QUIET" = "--quiet" ] || echo "$@"
}

log "=== boltzgen-skill setup ==="

# 1. Python 확인
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3를 찾을 수 없습니다. Python 3.9+ 설치 후 다시 실행하세요." >&2
  exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log "Python: $PY_VER"

# 2. 의존성 설치
log "의존성 설치 중..."

install_deps() {
  # uv가 있으면 uv로 설치 (빠름)
  if command -v uv &>/dev/null; then
    log "  uv 사용"
    uv pip install --system --break-system-packages -r "$SCRIPT_DIR/requirements.txt" 2>&1
    return $?
  fi

  # pip3 시도
  if command -v pip3 &>/dev/null; then
    log "  pip3 사용"
    pip3 install -r "$SCRIPT_DIR/requirements.txt" 2>&1
    return $?
  fi

  # python3 -m pip 시도
  python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" 2>&1
}

# 첫 시도
if ! install_deps; then
  # PEP 668 (externally-managed-environment) 오류 시 --break-system-packages 재시도
  log "  --break-system-packages 옵션으로 재시도..."
  pip3 install -r "$SCRIPT_DIR/requirements.txt" --break-system-packages 2>&1 || \
  python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" --break-system-packages 2>&1
fi

# 3. 설치 검증
if python3 -c "import httpx, yaml; print('  ✓ httpx, pyyaml 설치 확인')" 2>&1; then
  log "의존성 설치 완료"
else
  echo "ERROR: 의존성 설치 실패. 수동으로 설치해 주세요:" >&2
  echo "  pip3 install httpx pyyaml" >&2
  exit 1
fi

# 4. .env 설정 안내
if [ ! -f "$SCRIPT_DIR/.env" ]; then
  if [ -f "$SCRIPT_DIR/.env.example" ]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    log ""
    log "⚠ .env 파일이 생성되었습니다. API 설정을 입력해 주세요:"
    log "  파일: $SCRIPT_DIR/.env"
    log "  항목: API_BASE_URL, API_KEY"
  fi
else
  log ".env: 이미 존재함"
fi

log ""
log "✓ 설정 완료. 사용 방법:"
log "  python3 $SCRIPT_DIR/generate_yaml.py --help"
log "  python3 $SCRIPT_DIR/submit.py --help"
