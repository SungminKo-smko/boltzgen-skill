#!/usr/bin/env python3
"""
Submit a BoltzGen design job to the nanobody-designer MSA API.

Full workflow:
  1. Upload structure file(s)
  2. Validate spec YAML via API
  3. Submit design job
  4. Poll job status until complete
  5. Print artifact download URLs

Usage:
    python submit.py \\
        --spec spec.yaml \\
        --structure targets/input.cif \\
        [--num-designs 5] \\
        [--budget 1] \\
        [--output-dir ./results]

Environment:
    API_BASE_URL   Base URL of the MSA API server
    API_KEY        x-api-key authentication header value

    Both can also be set in a .env file in the same directory.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_env():
    """Load .env file from cwd if present."""
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


DEFAULT_API_BASE_URL = "https://nanobody-aca-api.politebay-55ff119b.westus3.azurecontainerapps.io"


def get_config() -> tuple[str, str]:
    load_env()
    base_url = os.environ.get("API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")
    api_key = os.environ.get("API_KEY", "")
    if not api_key:
        print("ERROR: API_KEY is not set (env var or .env file)", file=sys.stderr)
        sys.exit(1)
    return base_url, api_key


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

RETRY_ATTEMPTS = 3
CONNECT_TIMEOUT = 30.0


def make_client(api_key: str) -> httpx.Client:
    return httpx.Client(
        headers={"x-api-key": api_key, "content-type": "application/json"},
        timeout=httpx.Timeout(CONNECT_TIMEOUT, read=120.0),
    )


def _request_with_retry(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    last_exc = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = client.request(method, url, **kwargs)
            if resp.status_code >= 500:
                wait = 2 ** attempt
                print(f"  [retry {attempt}/{RETRY_ATTEMPTS}] HTTP {resp.status_code}, retrying in {wait}s…")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            raise
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_exc = e
            wait = 2 ** attempt
            print(f"  [retry {attempt}/{RETRY_ATTEMPTS}] Network error: {e}, retrying in {wait}s…")
            time.sleep(wait)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Request to {url} failed after {RETRY_ATTEMPTS} attempts.")


# ---------------------------------------------------------------------------
# Step 1: Upload structure file
# ---------------------------------------------------------------------------

def upload_file(client: httpx.Client, base_url: str, file_path: Path) -> str:
    """Upload a structure file and return asset_id."""
    print(f"[1/4] Uploading {file_path.name}…")

    content_type = "chemical/x-cif" if file_path.suffix == ".cif" else "chemical/x-pdb"
    relative_path = f"targets/{file_path.name}"

    # Create signed upload target
    resp = _request_with_retry(
        client, "POST", f"{base_url}/v1/uploads",
        content=json.dumps({
            "filename": file_path.name,
            "content_type": content_type,
            "kind": "structure",
            "relative_path": relative_path,
        })
    )
    data = resp.json()
    asset_id = data["asset_id"]
    upload_url = data["upload_url"]

    # Upload file bytes to the signed URL (no auth header)
    with httpx.Client(timeout=httpx.Timeout(CONNECT_TIMEOUT, read=300.0)) as raw_client:
        with file_path.open("rb") as f:
            put_resp = raw_client.put(
                upload_url,
                content=f.read(),
                headers={
                    "x-ms-blob-type": "BlockBlob",
                    "content-type": content_type,
                },
            )
        put_resp.raise_for_status()

    print(f"  ✓ Uploaded → asset_id: {asset_id}")
    return asset_id


# ---------------------------------------------------------------------------
# Step 2: Validate spec
# ---------------------------------------------------------------------------

def validate_spec(
    client: httpx.Client,
    base_url: str,
    yaml_content: str,
    asset_ids: list[str],
) -> str:
    """Validate raw YAML via the API and return validated spec_id."""
    print("[2/4] Validating spec via API…")
    resp = _request_with_retry(
        client, "POST", f"{base_url}/v1/specs/validate",
        content=json.dumps({
            "raw_yaml": yaml_content,
            "asset_ids": asset_ids,
        })
    )
    data = resp.json()

    if not data.get("valid"):
        errors = data.get("errors", [])
        print("ERROR: Spec validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print("\nHint: Check chain IDs (case-sensitive, 1-based residue indices).", file=sys.stderr)
        print("      Visualize the structure in Mol* (https://molstar.org/viewer/) to verify.", file=sys.stderr)
        sys.exit(1)

    warnings = data.get("warnings", [])
    if warnings:
        for w in warnings:
            print(f"  ⚠ {w}")

    spec_id = data["spec_id"]
    print(f"  ✓ Valid → spec_id: {spec_id}")
    return spec_id


# ---------------------------------------------------------------------------
# Step 3: Submit job
# ---------------------------------------------------------------------------

def submit_job(
    client: httpx.Client,
    base_url: str,
    spec_id: str,
    num_designs: int,
    budget: int,
) -> str:
    """Submit a design job and return job_id."""
    print("[3/4] Submitting design job…")
    resp = _request_with_retry(
        client, "POST", f"{base_url}/v1/design-jobs",
        content=json.dumps({
            "validated_spec_id": spec_id,
            "runtime_options": {
                "num_designs": num_designs,
                "budget": budget,
            },
        })
    )
    data = resp.json()
    job_id = data["job_id"]
    print(f"  ✓ Submitted → job_id: {job_id} (status: {data['status']})")
    return job_id


# ---------------------------------------------------------------------------
# Step 4: Poll job status
# ---------------------------------------------------------------------------

TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}
POLL_INTERVAL = 5      # seconds between polls
POLL_TIMEOUT = 3600    # maximum total wait time in seconds


def poll_job(client: httpx.Client, base_url: str, job_id: str) -> dict:
    """Poll until job reaches a terminal state. Returns final status dict."""
    print("[4/4] Waiting for job to complete…")
    start = time.time()
    last_stage = None

    while True:
        elapsed = time.time() - start
        if elapsed > POLL_TIMEOUT:
            print(f"ERROR: Job polling timed out after {POLL_TIMEOUT}s.", file=sys.stderr)
            sys.exit(1)

        resp = _request_with_retry(client, "GET", f"{base_url}/v1/design-jobs/{job_id}")
        data = resp.json()
        status = data.get("status", "unknown")
        stage = data.get("current_stage")
        progress = data.get("progress_percent")

        # Print progress only when stage changes
        stage_line = stage or status
        if stage_line != last_stage:
            prog_str = f" ({progress}%)" if progress is not None else ""
            print(f"  [{int(elapsed):>4}s] {stage_line}{prog_str}")
            last_stage = stage_line

        if status in TERMINAL_STATUSES:
            return data

        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Step 5: Fetch artifacts
# ---------------------------------------------------------------------------

def fetch_artifacts(client: httpx.Client, base_url: str, job_id: str) -> dict[str, str]:
    resp = _request_with_retry(client, "GET", f"{base_url}/v1/design-jobs/{job_id}/artifacts")
    return resp.json().get("artifacts", {})


# ---------------------------------------------------------------------------
# Cancel job
# ---------------------------------------------------------------------------

def cancel_job(base_url: str, api_key: str, job_id: str) -> None:
    """Cancel a running design job."""
    print(f"Canceling job {job_id}…")
    with make_client(api_key) as client:
        resp = client.post(f"{base_url}/v1/design-jobs/{job_id}:cancel")
        if resp.status_code in (200, 201, 204):
            print(f"✓ Job canceled: {job_id}")
        else:
            print(f"ERROR: Cancel failed (HTTP {resp.status_code}): {resp.text}", file=sys.stderr)
            sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Submit a BoltzGen design job to the MSA API.")

    subparsers = parser.add_subparsers(dest="command")

    # Default: submit (no subcommand, for backwards compatibility)
    parser.add_argument("--spec", help="Path to the spec YAML file.")
    parser.add_argument(
        "--structure", action="append", dest="structures", metavar="FILE",
        help="Structure file(s) to upload. Can be specified multiple times."
    )
    parser.add_argument("--num-designs", type=int, default=5, help="Number of designs (default: 5).")
    parser.add_argument("--budget", type=int, default=1, help="Budget (default: 1).")
    parser.add_argument("--output-dir", default=".", help="Directory to save artifact list (default: cwd).")

    # cancel subcommand
    cancel_parser = subparsers.add_parser("cancel", help="Cancel a running design job.")
    cancel_parser.add_argument("job_id", help="Job ID to cancel.")

    return parser.parse_args()


def main():
    args = parse_args()
    base_url, api_key = get_config()

    # cancel subcommand
    if args.command == "cancel":
        cancel_job(base_url, api_key, args.job_id)
        return

    if not args.spec:
        print("ERROR: --spec is required.", file=sys.stderr)
        sys.exit(1)

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"ERROR: Spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    yaml_content = spec_path.read_text()

    with make_client(api_key) as client:
        # 1. Upload all structure files
        asset_ids = []
        for struct_path_str in (args.structures or []):
            struct_path = Path(struct_path_str)
            if not struct_path.exists():
                print(f"ERROR: Structure file not found: {struct_path}", file=sys.stderr)
                sys.exit(1)
            asset_id = upload_file(client, base_url, struct_path)
            asset_ids.append(asset_id)

        # 2. Validate spec
        spec_id = validate_spec(client, base_url, yaml_content, asset_ids)

        # 3. Submit job
        job_id = submit_job(client, base_url, spec_id, args.num_designs, args.budget)

        # 4. Poll
        final = poll_job(client, base_url, job_id)
        status = final["status"]

        if status == "failed":
            print(f"\n✗ Job failed: {final.get('failure_message', 'no message')}", file=sys.stderr)
            sys.exit(1)
        elif status == "canceled":
            print("\n✗ Job was canceled.", file=sys.stderr)
            sys.exit(1)

        # 5. Fetch artifacts
        artifacts = fetch_artifacts(client, base_url, job_id)

    print(f"\n✓ Job succeeded: {job_id}")
    if artifacts:
        print("\nArtifacts:")
        for name, url in artifacts.items():
            print(f"  {name}: {url}")

        # Save artifact list
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{job_id}_artifacts.json"
        out_file.write_text(json.dumps({"job_id": job_id, "artifacts": artifacts}, indent=2))
        print(f"\nArtifact list saved to: {out_file}")
    else:
        print("No artifacts available yet.")


if __name__ == "__main__":
    main()
