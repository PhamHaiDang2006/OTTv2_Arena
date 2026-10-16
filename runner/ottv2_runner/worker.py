from __future__ import annotations

import argparse

from .config import Settings
from .errors import InfrastructureError
from .http import UrllibTransport
from .runtime import HeartbeatReporter


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OTTv2 RQ worker queues")
    parser.add_argument("--queue", choices=("build", "match:tournament", "match:scrimmage"), action="append")
    args = parser.parse_args()
    try:
        import redis
        from rq import Queue, Worker
    except ImportError as exc:
        raise InfrastructureError("Install redis and rq worker dependencies") from exc
    settings = Settings.from_env()
    connection = redis.Redis.from_url(settings.redis_url)
    queue_names = args.queue or ["build"]
    if "build" in queue_names and any(name.startswith("match:") for name in queue_names):
        parser.error("Run build and match queues in separate worker processes")
    queues = [Queue(name, connection=connection) for name in queue_names]
    kind = "build" if all(name == "build" for name in queue_names) else "match"
    heartbeat = HeartbeatReporter(settings, UrllibTransport(), kind)
    heartbeat.start()
    try:
        Worker(queues, connection=connection).work(with_scheduler=False)
    finally:
        heartbeat.close()


if __name__ == "__main__":
    main()
