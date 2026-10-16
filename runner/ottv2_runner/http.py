from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class HttpResponse:
    status_code: int


class HttpTransport(Protocol):
    def post(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> HttpResponse: ...


class UrllibTransport:
    def post(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> HttpResponse:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return HttpResponse(response.status)
        except urllib.error.HTTPError as exc:
            return HttpResponse(exc.code)
