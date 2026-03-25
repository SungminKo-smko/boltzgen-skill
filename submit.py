#!/usr/bin/env python3
"""
BoltzGen MSA API CLI — submit, track, cancel, and list design jobs.

Subcommands:
  (default)          Upload → validate → submit → poll → artifacts
  status  <job_id>   Get job status
  list               List design jobs
  cancel  <job_id>   Cancel a running job
  templates          List available spec templates
  render             Render a spec from template (nanobody_targeted_binder)

Environment (or .env file):
  API_KEY            x-api-key authentication header value
  API_BASE_URL       Override default API server URL (optional)
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

DEFAULT_API_BASE_URL = "https://nanobody-aca-api.politebay-55ff119b.westus3.azurecontainerapps.io"

SCRIPT_DIR = Path(__file__).parent


def load_env():
    """Load .env from script directory or cwd."""
    for env_path in [SCRIPT_DIR / ".env", Path(".env")]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            break


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
        except httpx.HTTPStatusError:
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
# Upload
# ---------------------------------------------------------------------------

def upload_file(client: httpx.Client, base_url: str, file_path: Path) -> str:
    """Upload a structure file and return asset_id."""
    print(f"Uploading {file_path.name}…")

    content_type = "chemical/x-cif" if file_path.suffix == ".cif" else "chemical/x-pdb"
    relative_path = f"targets/{file_path.name}"

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

    with httpx.Client(timeout=httpx.Timeout(CONNECT_TIMEOUT, read=300.0)) as raw_client:
        with file_path.open("rb") as f:
            put_resp = raw_client.put(
                upload_url,
                content=f.read(),
                headers={"x-ms-blob-type": "BlockBlob", "content-type": content_type},
            )
        put_resp.raise_for_status()

    print(f"  ✓ Uploaded → asset_id: {asset_id}")
    return asset_id


# ---------------------------------------------------------------------------
# Spec: validate
# ---------------------------------------------------------------------------

def validate_spec(
    client: httpx.Client,
    base_url: str,
    yaml_content: str,
    asset_ids: list[str],
) -> str:
    """Validate raw YAML via the API and return validated spec_id."""
    print("Validating spec…")
    resp = _request_with_retry(
        client, "POST", f"{base_url}/v1/specs/validate",
        content=json.dumps({"raw_yaml": yaml_content, "asset_ids": asset_ids})
    )
    data = resp.json()

    if not data.get("valid"):
        errors = data.get("errors", [])
        print("ERROR: Spec validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print("\nHint: Check chain IDs (case-sensitive, 1-based residue indices).", file=sys.stderr)
        print("      Visualize the structure in Mol* (https://molstar.org/viewer/)", file=sys.stderr)
        sys.exit(1)

    for w in data.get("warnings", []):
        print(f"  ⚠ {w}")

    spec_id = data["spec_id"]
    print(f"  ✓ Valid → spec_id: {spec_id}")
    return spec_id


# ---------------------------------------------------------------------------
# Spec: render template
# ---------------------------------------------------------------------------

def render_template(
    client: httpx.Client,
    base_url: str,
    asset_id: str,
    include: list[str],
    design: list[dict] | None,
    binding_types: list[dict] | None,
    additional_entities: list[dict] | None,
) -> str:
    """Render nanobody_targeted_binder template and return spec_id."""
    print("Rendering spec from template…")

    target: dict = {"target_asset_id": asset_id}
    if include:
        target["include"] = [{"id": c} for c in include]
    if design:
        target["design"] = design
    if binding_types:
        target["binding_types"] = binding_types

    payload: dict = {
        "template_name": "nanobody_targeted_binder",
        "target": target,
    }
    if additional_entities:
        payload["additional_entities"] = additional_entities

    resp = _request_with_retry(
        client, "POST", f"{base_url}/v1/spec-templates/render",
        content=json.dumps(payload)
    )
    data = resp.json()
    spec_id = data["spec_id"]
    print(f"  ✓ Rendered → spec_id: {spec_id}")
    if data.get("canonical_yaml"):
        print("\n--- canonical YAML ---")
        print(data["canonical_yaml"])
        print("--- end ---")
    return spec_id


# ---------------------------------------------------------------------------
# Job: submit
# ---------------------------------------------------------------------------

def submit_job(
    client: httpx.Client,
    base_url: str,
    spec_id: str,
    runtime_options: dict,
    client_request_id: str | None = None,
) -> str:
    """Submit a design job and return job_id."""
    print("Submitting design job…")
    payload: dict = {
        "validated_spec_id": spec_id,
        "runtime_options": runtime_options,
    }
    if client_request_id:
        payload["client_request_id"] = client_request_id

    resp = _request_with_retry(
        client, "POST", f"{base_url}/v1/design-jobs",
        content=json.dumps(payload)
    )
    data = resp.json()
    job_id = data["job_id"]
    replay = data.get("idempotent_replay", False)
    suffix = " (idempotent replay)" if replay else ""
    print(f"  ✓ Submitted → job_id: {job_id} (status: {data['status']}){suffix}")
    return job_id


# ---------------------------------------------------------------------------
# Job: poll
# ---------------------------------------------------------------------------

TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}
POLL_INTERVAL = 5
POLL_TIMEOUT = 3600


def poll_job(client: httpx.Client, base_url: str, job_id: str) -> dict:
    """Poll until job reaches a terminal state."""
    print("Waiting for job to complete…")
    start = time.time()
    last_stage = None

    while True:
        elapsed = time.time() - start
        if elapsed > POLL_TIMEOUT:
            print(f"ERROR: Polling timed out after {POLL_TIMEOUT}s. job_id: {job_id}", file=sys.stderr)
            print(f"  Re-check later: python3 submit.py status {job_id}", file=sys.stderr)
            sys.exit(1)

        resp = _request_with_retry(client, "GET", f"{base_url}/v1/design-jobs/{job_id}")
        data = resp.json()
        status = data.get("status", "unknown")
        stage = data.get("current_stage")
        progress = data.get("progress_percent")

        stage_line = stage or status
        if stage_line != last_stage:
            prog_str = f" ({progress}%)" if progress is not None else ""
            print(f"  [{int(elapsed):>4}s] {stage_line}{prog_str}")
            last_stage = stage_line

        if status in TERMINAL_STATUSES:
            return data

        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Job: artifacts
# ---------------------------------------------------------------------------

def fetch_artifacts(client: httpx.Client, base_url: str, job_id: str) -> dict[str, str]:
    resp = _request_with_retry(client, "GET", f"{base_url}/v1/design-jobs/{job_id}/artifacts")
    return resp.json().get("artifacts", {})


def save_and_print_artifacts(artifacts: dict, job_id: str, output_dir: str) -> None:
    if artifacts:
        print("\nArtifacts:")
        for name, url in artifacts.items():
            print(f"  {name}: {url}")
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{job_id}_artifacts.json"
        out_file.write_text(json.dumps({"job_id": job_id, "artifacts": artifacts}, indent=2))
        print(f"\nSaved: {out_file}")
    else:
        print("No artifacts available.")


# ---------------------------------------------------------------------------
# Subcommand: status
# ---------------------------------------------------------------------------

def cmd_status(base_url: str, api_key: str, job_id: str) -> None:
    with make_client(api_key) as client:
        resp = _request_with_retry(client, "GET", f"{base_url}/v1/design-jobs/{job_id}")
        d = resp.json()

    print(f"job_id:    {d['job_id']}")
    print(f"status:    {d['status']}")
    print(f"protocol:  {d.get('protocol', '-')}")
    if d.get("current_stage"):
        progress = d.get("progress_percent")
        prog_str = f" ({progress}%)" if progress is not None else ""
        print(f"stage:     {d['current_stage']}{prog_str}")
    if d.get("status_message"):
        print(f"message:   {d['status_message']}")
    if d.get("failure_message"):
        print(f"error:     {d['failure_message']}")
    print(f"created:   {d.get('created_at', '-')}")
    if d.get("started_at"):
        print(f"started:   {d['started_at']}")
    if d.get("finished_at"):
        print(f"finished:  {d['finished_at']}")
    opts = d.get("runtime_options", {})
    if opts:
        print(f"options:   num_designs={opts.get('num_designs')} budget={opts.get('budget')}")


# ---------------------------------------------------------------------------
# Subcommand: list
# ---------------------------------------------------------------------------

def cmd_list(base_url: str, api_key: str, status_filter: str | None, limit: int, offset: int) -> None:
    params: dict = {"limit": limit, "offset": offset}
    if status_filter:
        params["status"] = status_filter

    with make_client(api_key) as client:
        resp = _request_with_retry(
            client, "GET", f"{base_url}/v1/design-jobs",
            params=params
        )
        data = resp.json()

    jobs = data.get("jobs", [])
    total = data.get("total", len(jobs))
    print(f"Jobs ({len(jobs)}/{total}):")
    print(f"  {'JOB ID':<38} {'STATUS':<12} {'STAGE':<20} {'PROGRESS'}")
    print("  " + "-" * 80)
    for j in jobs:
        stage = j.get("current_stage") or "-"
        progress = j.get("progress_percent")
        prog_str = f"{progress}%" if progress is not None else "-"
        print(f"  {j['job_id']:<38} {j['status']:<12} {stage:<20} {prog_str}")


# ---------------------------------------------------------------------------
# Subcommand: cancel
# ---------------------------------------------------------------------------

def cmd_cancel(base_url: str, api_key: str, job_id: str) -> None:
    print(f"Canceling job {job_id}…")
    with make_client(api_key) as client:
        resp = client.post(f"{base_url}/v1/design-jobs/{job_id}:cancel")
        if resp.status_code in (200, 201, 204):
            data = resp.json() if resp.content else {}
            status = data.get("status", "canceled")
            print(f"✓ Canceled → job_id: {job_id} (status: {status})")
        else:
            print(f"ERROR: Cancel failed (HTTP {resp.status_code}): {resp.text}", file=sys.stderr)
            sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommand: templates
# ---------------------------------------------------------------------------

def cmd_templates(base_url: str, api_key: str) -> None:
    with make_client(api_key) as client:
        resp = _request_with_retry(client, "GET", f"{base_url}/v1/spec-templates")
        data = resp.json()

    templates = data.get("templates", [])
    for t in templates:
        print(f"\n{'='*60}")
        print(f"  name:     {t['name']}")
        print(f"  protocol: {t.get('protocol', '-')}")
        print(f"  desc:     {t.get('description', '-')}")
        fields = t.get("fields", [])
        if fields:
            print("  fields:")
            for f in fields:
                req = "required" if f.get("required") else "optional"
                print(f"    - {f['name']} ({f['type']}, {req}): {f.get('description', '')}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_runtime_options(args) -> dict:
    opts: dict = {
        "num_designs": args.num_designs,
        "budget": args.budget,
    }
    if hasattr(args, "alpha") and args.alpha is not None:
        opts["alpha"] = args.alpha
    if hasattr(args, "no_filter_biased") and args.no_filter_biased:
        opts["filter_biased"] = False
    if hasattr(args, "additional_filters") and args.additional_filters:
        opts["additional_filters"] = args.additional_filters
    if hasattr(args, "inverse_fold_num_sequences") and args.inverse_fold_num_sequences is not None:
        opts["inverse_fold_num_sequences"] = args.inverse_fold_num_sequences
    if hasattr(args, "reuse") and args.reuse:
        opts["reuse"] = True
    if hasattr(args, "diffusion_batch_size") and args.diffusion_batch_size is not None:
        opts["diffusion_batch_size"] = args.diffusion_batch_size
    return opts


def add_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--num-designs", type=int, default=5, help="Number of designs (default: 5).")
    parser.add_argument("--budget", type=int, default=1, help="Budget — final designs to keep (default: 1).")
    parser.add_argument("--alpha", type=float, default=None, help="Filtering weight (0.0–1.0).")
    parser.add_argument("--no-filter-biased", action="store_true", help="Disable biased design filtering.")
    parser.add_argument("--additional-filters", nargs="+", metavar="EXPR", help="Extra filter expressions (e.g. ALA_fraction<0.3).")
    parser.add_argument("--inverse-fold-num-sequences", type=int, default=None, help="Inverse folding sequences per backbone.")
    parser.add_argument("--reuse", action="store_true", help="Allow reuse of existing worker resources.")
    parser.add_argument("--diffusion-batch-size", type=int, default=None, help="Diffusion batch size override.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="BoltzGen MSA API CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
subcommands:
  (none)      upload + validate + submit + poll  [requires --spec --structure]
  render      render template → spec_id + submit [requires --structure --include]
  status      get job status
  list        list jobs
  cancel      cancel a running job
  templates   list available spec templates
        """
    )
    subparsers = parser.add_subparsers(dest="command")

    # ── default (submit via raw YAML) ──────────────────────────────────────
    parser.add_argument("--spec", help="Spec YAML file path.")
    parser.add_argument(
        "--structure", action="append", dest="structures", metavar="FILE",
        help="Structure file(s) to upload."
    )
    parser.add_argument("--output-dir", default=".", help="Output directory for artifact JSON (default: cwd).")
    parser.add_argument("--client-request-id", default=None, help="Idempotency key for job submission.")
    add_runtime_args(parser)

    # ── render (template → spec_id → submit) ──────────────────────────────
    render_p = subparsers.add_parser("render", help="Render spec from template and submit job.")
    render_p.add_argument("--structure", required=True, dest="structure", metavar="FILE",
                          help="Structure file to upload.")
    render_p.add_argument("--include", nargs="+", metavar="CHAIN_ID", required=True,
                          help="Chain IDs to include (e.g. A B).")
    render_p.add_argument("--design", nargs="+", metavar="CHAIN:RES",
                          help="Chains to redesign (format: 'A:97..114' or 'A').")
    render_p.add_argument("--binding", nargs="+", metavar="CHAIN:RESIDUES",
                          help="Binding residues (format: 'B:317,321,324').")
    render_p.add_argument("--output-dir", default=".", help="Output directory for artifact JSON.")
    render_p.add_argument("--client-request-id", default=None)
    add_runtime_args(render_p)

    # ── status ──────────────────────────────────────────────────────────────
    status_p = subparsers.add_parser("status", help="Get job status.")
    status_p.add_argument("job_id", help="Job ID.")

    # ── list ────────────────────────────────────────────────────────────────
    list_p = subparsers.add_parser("list", help="List design jobs.")
    list_p.add_argument("--status", default=None,
                        choices=["queued", "validating", "running", "uploading", "succeeded", "failed", "canceled"],
                        help="Filter by status.")
    list_p.add_argument("--limit", type=int, default=20, help="Max results (default: 20).")
    list_p.add_argument("--offset", type=int, default=0, help="Pagination offset (default: 0).")

    # ── cancel ──────────────────────────────────────────────────────────────
    cancel_p = subparsers.add_parser("cancel", help="Cancel a running job.")
    cancel_p.add_argument("job_id", help="Job ID to cancel.")

    # ── templates ───────────────────────────────────────────────────────────
    subparsers.add_parser("templates", help="List available spec templates.")

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    base_url, api_key = get_config()

    if args.command == "status":
        cmd_status(base_url, api_key, args.job_id)
        return

    if args.command == "list":
        cmd_list(base_url, api_key, args.status, args.limit, args.offset)
        return

    if args.command == "cancel":
        cmd_cancel(base_url, api_key, args.job_id)
        return

    if args.command == "templates":
        cmd_templates(base_url, api_key)
        return

    if args.command == "render":
        # Parse --design and --binding arguments
        design_list = None
        if args.design:
            design_list = []
            for d in args.design:
                if ":" in d:
                    chain_id, res = d.split(":", 1)
                    design_list.append({"id": chain_id.strip(), "res_index": res.strip()})
                else:
                    design_list.append({"id": d.strip()})

        binding_list = None
        if args.binding:
            binding_list = []
            for b in args.binding:
                if ":" in b:
                    chain_id, residues = b.split(":", 1)
                    binding_list.append({"id": chain_id.strip(), "binding": residues.strip()})
                else:
                    binding_list.append({"id": b.strip()})

        with make_client(api_key) as client:
            struct_path = Path(args.structure)
            if not struct_path.exists():
                print(f"ERROR: File not found: {struct_path}", file=sys.stderr)
                sys.exit(1)
            asset_id = upload_file(client, base_url, struct_path)
            spec_id = render_template(client, base_url, asset_id, args.include, design_list, binding_list, None)
            job_id = submit_job(client, base_url, spec_id, build_runtime_options(args), args.client_request_id)
            final = poll_job(client, base_url, job_id)
            status = final["status"]
            if status == "failed":
                print(f"\n✗ Job failed: {final.get('failure_message', 'no message')}", file=sys.stderr)
                sys.exit(1)
            elif status == "canceled":
                print("\n✗ Job was canceled.", file=sys.stderr)
                sys.exit(1)
            artifacts = fetch_artifacts(client, base_url, job_id)

        print(f"\n✓ Job succeeded: {job_id}")
        save_and_print_artifacts(artifacts, job_id, args.output_dir)
        return

    # ── default: raw YAML submit ────────────────────────────────────────────
    if not args.spec:
        print("ERROR: --spec is required (or use a subcommand: render, status, list, cancel, templates)", file=sys.stderr)
        sys.exit(1)

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"ERROR: Spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    yaml_content = spec_path.read_text()

    with make_client(api_key) as client:
        asset_ids = []
        for struct_str in (args.structures or []):
            struct_path = Path(struct_str)
            if not struct_path.exists():
                print(f"ERROR: Structure file not found: {struct_path}", file=sys.stderr)
                sys.exit(1)
            asset_ids.append(upload_file(client, base_url, struct_path))

        spec_id = validate_spec(client, base_url, yaml_content, asset_ids)
        job_id = submit_job(client, base_url, spec_id, build_runtime_options(args), args.client_request_id)
        final = poll_job(client, base_url, job_id)
        status = final["status"]

        if status == "failed":
            print(f"\n✗ Job failed: {final.get('failure_message', 'no message')}", file=sys.stderr)
            sys.exit(1)
        elif status == "canceled":
            print("\n✗ Job was canceled.", file=sys.stderr)
            sys.exit(1)

        artifacts = fetch_artifacts(client, base_url, job_id)

    print(f"\n✓ Job succeeded: {job_id}")
    save_and_print_artifacts(artifacts, job_id, args.output_dir)


if __name__ == "__main__":
    main()
