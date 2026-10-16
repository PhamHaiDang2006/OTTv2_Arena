from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any, Protocol

from .errors import InfrastructureError


class MatchEngine(Protocol):
    async def run_game(self, blue_io: Any, red_io: Any, config: Mapping[str, Any]) -> Any:
        """Run one match and return the engine's GameResult without implementing rules here."""


class EngineFactory(Protocol):
    def __call__(self) -> MatchEngine: ...


class BuildVerifier(Protocol):
    def verify(self, image: str, job: Mapping[str, Any], timeout_seconds: int) -> None:
        """Smoke-run the built bot against a system-owned test opponent using the engine."""


def load_engine_factory(import_path: str | None = None) -> EngineFactory:
    """Load an explicitly configured system-owned engine adapter.

    The contract's engine package is not present in this repository baseline; no
    rules or fallback result are synthesized when the configured factory is absent.
    """
    target = import_path or __import__("os").environ.get("OTTv2_ENGINE_FACTORY")
    if not target:
        raise InfrastructureError(
            "OTTv2 engine integration is missing; configure OTTv2_ENGINE_FACTORY"
        )
    module_name, separator, attribute = target.partition(":")
    if not separator or not module_name or not attribute:
        raise InfrastructureError("OTTv2_ENGINE_FACTORY must be module:factory")
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
    except Exception as exc:
        raise InfrastructureError("Could not load the configured OTTv2 engine factory") from exc
    if not callable(factory):
        raise InfrastructureError("Configured OTTv2 engine factory is not callable")
    return factory


def load_build_verifier(import_path: str | None = None) -> BuildVerifier | None:
    target = import_path or __import__("os").environ.get("OTTv2_BUILD_VERIFIER")
    if not target:
        return None
    module_name, separator, attribute = target.partition(":")
    if not separator or not module_name or not attribute:
        raise InfrastructureError("OTTv2_BUILD_VERIFIER must be module:factory")
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
        verifier = factory()
    except Exception as exc:
        raise InfrastructureError("Could not load the configured build smoke-test verifier") from exc
    if not callable(getattr(verifier, "verify", None)):
        raise InfrastructureError("Configured build verifier does not implement verify()")
    return verifier
