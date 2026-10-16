from __future__ import annotations

import os
import re
from typing import Any, Protocol

from .errors import InfrastructureError

_DIGEST = re.compile(r"sha256:[a-f0-9]{64}")
_REGISTRY = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*(:[0-9]{1,5})?")


class ImagePublisher(Protocol):
    def publish(self, image_id: str, submission_id: str) -> str:
        """Push a verified local image and return an immutable registry reference."""


class DockerRegistryPublisher:
    """Pushes a verified bot image to the worker-local registry and returns repo@sha256:digest."""

    def __init__(self, client: Any, registry_url: str, repository: str = "ottv2-bot"):
        if not _REGISTRY.fullmatch(registry_url):
            raise InfrastructureError("REGISTRY_URL must be host[:port] without a scheme or path")
        self.client = client
        self.registry_url = registry_url
        self.repository = f"{registry_url}/{repository}"

    @classmethod
    def from_env(cls, client: Any) -> "DockerRegistryPublisher | None":
        registry_url = os.environ.get("REGISTRY_URL", "").strip()
        return cls(client, registry_url) if registry_url else None

    def publish(self, image_id: str, submission_id: str) -> str:
        tag = submission_id
        try:
            self.client.images.get(image_id).tag(self.repository, tag=tag)
            digest: str | None = None
            for record in self.client.images.push(self.repository, tag=tag, stream=True, decode=True):
                if not isinstance(record, dict):
                    continue
                if record.get("error"):
                    raise InfrastructureError("Registry push was rejected")
                aux = record.get("aux")
                if isinstance(aux, dict) and _DIGEST.fullmatch(str(aux.get("Digest", ""))):
                    digest = aux["Digest"]
                found = re.search(rf": digest: ({_DIGEST.pattern}) size: \d+", str(record.get("status", "")))
                if found:
                    digest = found.group(1)
        except InfrastructureError:
            raise
        except Exception as exc:
            raise InfrastructureError("Could not push the bot image to the registry") from exc
        if digest is None:
            raise InfrastructureError("Registry push did not report an image digest")
        return f"{self.repository}@{digest}"
