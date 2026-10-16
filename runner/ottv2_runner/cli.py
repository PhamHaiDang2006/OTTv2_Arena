from __future__ import annotations

import argparse
import json
from pathlib import Path

from .jobs import _get_runtime
from .validation import validate_build_job, validate_match_job


def main() -> None:
    parser = argparse.ArgumentParser(prog="ottv2-runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("validate-build", "validate-match"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("payload", type=Path, help="JSON file containing one contract v1 job")
    subparsers.add_parser("flush-outbox", help="Retry durable callbacks without rerunning jobs")
    args = parser.parse_args()
    if args.command.startswith("validate-"):
        payload = json.loads(args.payload.read_text(encoding="utf-8"))
        validator = validate_build_job if args.command == "validate-build" else validate_match_job
        validator(payload)
        print("valid contract v1 payload")
        return
    runtime = _get_runtime()
    assert runtime.callback_sender and runtime.outbox
    for pending in runtime.outbox.pending():
        runtime._terminal_callback(pending)


if __name__ == "__main__":
    main()
