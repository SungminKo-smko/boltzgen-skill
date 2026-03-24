#!/usr/bin/env python3
"""
Generate a BoltzGen spec YAML from minimal user inputs.

Usage:
    python generate_yaml.py \\
        --structure targets/input.cif \\
        --target-chain A \\
        --design-chain B \\
        --design-length 80..140 \\
        [--binding-residues "317,321,324,325,326"] \\
        [--num-designs 5] \\
        [--budget 1] \\
        [--output spec.yaml]
"""

import argparse
import sys
from pathlib import Path

import yaml


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a BoltzGen spec YAML from minimal inputs."
    )
    parser.add_argument(
        "--structure", required=True,
        help="Path to the target structure file (.cif or .pdb), relative to YAML location."
    )
    parser.add_argument(
        "--target-chain", required=True,
        help="Chain ID(s) to use as binding target. Comma-separated for multiple (e.g. A,B)."
    )
    parser.add_argument(
        "--design-chain", default="B",
        help="Chain ID for the designed nanobody (default: B)."
    )
    parser.add_argument(
        "--design-length", required=True,
        help="Design length range as 'MIN..MAX' (e.g. 80..140) or fixed integer (e.g. 110)."
    )
    parser.add_argument(
        "--binding-residues", default=None,
        help="Residue indices on the target chain that should be bound (e.g. '317,321,324')."
    )
    parser.add_argument(
        "--num-designs", type=int, default=5,
        help="Number of designs to generate (default: 5)."
    )
    parser.add_argument(
        "--budget", type=int, default=1,
        help="Budget (must be <= num_designs, default: 1)."
    )
    parser.add_argument(
        "--output", default="spec.yaml",
        help="Output YAML file path (default: spec.yaml)."
    )
    return parser.parse_args()


def parse_length(length_str: str) -> str:
    """Parse design length: '80..140' or '110' → boltzgen sequence string."""
    length_str = length_str.strip()
    if ".." in length_str:
        parts = length_str.split("..")
        if len(parts) != 2:
            print(f"ERROR: Invalid length format '{length_str}'. Use 'MIN..MAX' or a fixed integer.", file=sys.stderr)
            sys.exit(1)
        try:
            lo, hi = int(parts[0]), int(parts[1])
        except ValueError:
            print(f"ERROR: Length values must be integers in '{length_str}'.", file=sys.stderr)
            sys.exit(1)
        if lo >= hi:
            print(f"ERROR: MIN must be less than MAX in '{length_str}'.", file=sys.stderr)
            sys.exit(1)
        return f"{lo}..{hi}"
    else:
        try:
            n = int(length_str)
        except ValueError:
            print(f"ERROR: Invalid length '{length_str}'. Use 'MIN..MAX' or a fixed integer.", file=sys.stderr)
            sys.exit(1)
        return str(n)


def build_spec(
    structure: str,
    target_chains: list[str],
    design_chain: str,
    design_length: str,
    binding_residues: str | None,
) -> dict:
    """Build the BoltzGen spec as a Python dict."""
    # File entity: target structure
    file_entity: dict = {
        "file": {
            "path": structure,
            "include": [{"chain": {"id": c}} for c in target_chains],
        }
    }

    # Add binding_types if specified
    if binding_residues:
        file_entity["file"]["binding_types"] = [
            {
                "chain": {
                    "id": target_chains[0],
                    "binding": binding_residues,
                }
            }
        ]

    # Protein entity: designed nanobody
    protein_entity = {
        "protein": {
            "id": design_chain,
            "sequence": design_length,
        }
    }

    spec = {
        "entities": [file_entity, protein_entity]
    }
    return spec


def main():
    args = parse_args()

    # Validate budget <= num_designs
    if args.budget > args.num_designs:
        print(
            f"ERROR: --budget ({args.budget}) must be <= --num-designs ({args.num_designs}).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Parse target chains
    target_chains = [c.strip() for c in args.target_chain.split(",") if c.strip()]
    if not target_chains:
        print("ERROR: --target-chain must not be empty.", file=sys.stderr)
        sys.exit(1)

    # Parse design length
    design_length = parse_length(args.design_length)

    # Build spec
    spec = build_spec(
        structure=args.structure,
        target_chains=target_chains,
        design_chain=args.design_chain,
        design_length=design_length,
        binding_residues=args.binding_residues,
    )

    # Write YAML
    out_path = Path(args.output)
    with out_path.open("w") as f:
        yaml.dump(spec, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"✓ Spec YAML written to: {out_path}")
    print(f"  Target chain(s): {', '.join(target_chains)}")
    print(f"  Design chain: {args.design_chain} ({design_length} residues)")
    if args.binding_residues:
        print(f"  Binding residues: {args.binding_residues}")
    print(f"  Runtime: num_designs={args.num_designs}, budget={args.budget}")

    # Print runtime options as JSON comment for submit.py to pick up
    import json
    runtime = {"num_designs": args.num_designs, "budget": args.budget}
    print(f"__RUNTIME__:{json.dumps(runtime)}")


if __name__ == "__main__":
    main()
