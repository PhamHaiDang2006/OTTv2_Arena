from __future__ import annotations

from typing import Any

from .runtime import RunnerRuntime

_runtime: RunnerRuntime | None = None


def configure_runtime(runtime: RunnerRuntime | None) -> None:
    """Inject adapters in tests or a hosting process; passing None restores env setup."""
    global _runtime
    _runtime = runtime


def _get_runtime() -> RunnerRuntime:
    global _runtime
    if _runtime is None:
        _runtime = RunnerRuntime.from_env()
    return _runtime


def build_submission(payload: dict[str, Any]) -> dict[str, Any] | None:
    """RQ import entrypoint. Build once; callback retries only resend the saved payload."""
    return _get_runtime().build(payload)


def run_match(payload: dict[str, Any]) -> dict[str, Any] | None:
    """RQ import entrypoint. The backend, not this worker, owns attempt creation."""
    return _get_runtime().match(payload)
