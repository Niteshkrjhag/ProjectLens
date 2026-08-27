"""Small operator CLI used by the documented offline dry run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .storage import Storage
from .workflow import ProjectLensWorkflow


def demo(args: argparse.Namespace) -> int:
    storage = Storage(data_dir=args.state_dir)
    workflow = ProjectLensWorkflow(storage)
    project = storage.create_project(args.name, str(Path(args.source).resolve()))
    run = storage.create_run(project["id"], mode=args.mode, source_path=str(Path(args.source).resolve()))
    workflow.execute(run["id"], stop_after_stage=args.stop_after_stage)
    if args.approve_all:
        for item in storage.pending_review_items(run["id"]):
            workflow.approve_item(run["id"], item["id"], decided_by="dry-run")
    payload = {
        "project": project,
        "run": storage.get_run(run["id"]),
        "stages": storage.list_stages(run["id"]),
        "documents": storage.list_run_documents(run["id"]),
        "review_items": storage.list_review_items(run["id"]),
        "deliverable": storage.get_deliverable(run["id"]),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["run"]["status"] in {"awaiting_review", "committed", "paused"} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="projectlens", description="Run the ProjectLens offline proof of concept")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo_parser = subparsers.add_parser("demo", help="run a folder through the durable analysis workflow")
    demo_parser.add_argument("--source", required=True, help="folder containing supported documents")
    demo_parser.add_argument("--state-dir", default="data", help="folder for the local POC database")
    demo_parser.add_argument("--name", default="ProjectLens demo")
    demo_parser.add_argument("--mode", choices=("initial", "incremental"), default="initial")
    demo_parser.add_argument("--stop-after-stage", choices=("discover", "extract", "reconcile", "draft", "examine", "human_gate", "commit"))
    demo_parser.add_argument("--approve-all", action="store_true")
    demo_parser.set_defaults(handler=demo)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
