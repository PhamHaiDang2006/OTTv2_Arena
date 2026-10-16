from __future__ import annotations

import time
from typing import Callable

from .config import Settings
from .errors import InfrastructureError
from .http import HttpTransport
from .outbox import CallbackOutbox, PendingCallback


class CallbackSender:
    def __init__(
        self,
        settings: Settings,
        outbox: CallbackOutbox,
        transport: HttpTransport,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings
        self.outbox = outbox
        self.transport = transport
        self.sleep = sleep

    def enqueue(self, item: PendingCallback) -> None:
        self.outbox.put(item)

    def send(self, item: PendingCallback) -> int:
        delay_index = 0
        while True:
            try:
                response = self.transport.post(
                    item.url, item.payload,
                    {
                        "Authorization": f"Bearer {self.settings.worker_token}",
                        "X-Worker-Lease": item.lease_token,
                    },
                    self.settings.callback_timeout_seconds,
                )
                if 200 <= response.status_code < 300 or response.status_code == 409:
                    self.outbox.mark_completed(item)
                    return response.status_code
                # 4xx other than 409 are not transport failures and need operator attention.
                if 400 <= response.status_code < 500:
                    raise InfrastructureError(f"Callback rejected with HTTP {response.status_code}")
            except InfrastructureError:
                raise
            except Exception:
                pass
            delays = self.settings.callback_backoff_seconds
            self.sleep(delays[min(delay_index, len(delays) - 1)])
            delay_index += 1
