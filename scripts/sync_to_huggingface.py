#!/usr/bin/env python3
"""Mirror the local Parquet partition tree to a Hugging Face Datasets repo.

Reads `HF_TOKEN` from the environment. The HF repo id can be overridden
with `HF_REPO_ID` (default: `afhubbard/gpu-prices`).

Usage:
    # Default — sync everything under data/parquet/prices/ to <repo>:prices/
    python3 scripts/sync_to_huggingface.py

    # CI: sync just whatever the cron run produced this iteration
    python3 scripts/sync_to_huggingface.py --src data/parquet/prices

    # One-time bootstrap from a fully-converted local tree
    python3 scripts/sync_to_huggingface.py --src data/parquet/prices --bootstrap

`upload_folder` is content-addressable on the HF Hub: re-uploading files
already present is a no-op, so this script is idempotent and safe to run
from CI on every collection.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--src",
        default="data/parquet/prices",
        help="Local directory holding the partitioned Parquet tree.",
    )
    ap.add_argument(
        "--repo-id",
        default=os.environ.get("HF_REPO_ID", "afhubbard/gpu-prices"),
        help="Hugging Face dataset repo id (org/name).",
    )
    ap.add_argument(
        "--path-in-repo",
        default="prices",
        help="Where in the HF repo to place the tree (default: prices).",
    )
    ap.add_argument(
        "--bootstrap",
        action="store_true",
        help="If set, also upload the dataset card (dataset_card.md as README).",
    )
    args = ap.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("ERROR: HF_TOKEN env var is required.", file=sys.stderr)
        sys.exit(2)

    src = Path(args.src)
    if not src.is_dir():
        print(f"ERROR: --src {src} does not exist or is not a directory.", file=sys.stderr)
        sys.exit(2)

    # Lazy import so the rest of the codebase doesn't require huggingface_hub.
    from huggingface_hub import HfApi

    api = HfApi(token=token)

    # Ensure the repo exists. `exist_ok=True` makes this idempotent.
    api.create_repo(
        repo_id=args.repo_id,
        repo_type="dataset",
        exist_ok=True,
        private=False,
    )

    print(f"Syncing {src} -> hf://datasets/{args.repo_id}/{args.path_in_repo}")
    api.upload_folder(
        folder_path=str(src),
        path_in_repo=args.path_in_repo,
        repo_id=args.repo_id,
        repo_type="dataset",
        commit_message=f"Sync snapshots from {src}",
    )

    if args.bootstrap:
        card = Path(__file__).resolve().parent.parent / "dataset_card.md"
        if card.exists():
            print(f"Uploading dataset card from {card}")
            api.upload_file(
                path_or_fileobj=str(card),
                path_in_repo="README.md",
                repo_id=args.repo_id,
                repo_type="dataset",
                commit_message="Update dataset card",
            )
        else:
            print(f"WARN: --bootstrap set but {card} not found; skipping card upload.", file=sys.stderr)

    print("Done.")


if __name__ == "__main__":
    main()
