# runner — Sandbox, build worker, match worker

> **Implementation status (contract v1.0.0):** `ottv2_runner` now provides
> strict job validation, ZIP screening, Redis leases, durable callback outbox,
> S3-compatible storage adapters, system-owned Docker build/run specifications,
> and injectable engine/smoke-test interfaces. This is development/integration
> ready, not a certified production deployment. No real Docker daemon, Redis,
> MinIO, backend, registry, or OTTv2 engine was exercised by its unit tests.
> In particular, builds are not reported `ready` unless an injected smoke-game
> verifier succeeds; matches explicitly report `INFRA_ERROR` when the engine
> adapter is absent. Worker code never creates attempts.

## Implemented package

Engine thật hiện có trong `engine/`. Cài `python -m pip install -e engine -e runner`
từ repo root, dùng `OTTv2_ENGINE_FACTORY=ottv2.adapter:make_engine` và
`OTTv2_BUILD_VERIFIER=ottv2_runner.engine_verifier:make_build_verifier`.
Build image chứa cả hai bằng `docker build -f runner/Dockerfile.engine -t ottv2-worker:local .`
từ repo root. Python bot base cần `engine/Dockerfile.bot` để có package ottv2.
Adapter devkit cũ vẫn chỉ dùng kiểm tra plumbing, không phải trọng tài.

The Python 3.12+ distribution lives in this folder:

```powershell
Set-Location runner
python -m pip install -e .
python -m pip install --target ../contracts/.deps -r ../contracts/requirements.txt
python -m unittest discover -s tests -v
docker build -t ottv2-worker:local .
ottv2-runner validate-build path\to\build-job.json
ottv2-runner validate-match path\to\match-job.json
ottv2-runner-worker --queue build
ottv2-runner-worker --queue match:tournament --queue match:scrimmage
ottv2-runner flush-outbox
```

From contract 1.3.0 production runs separate pools: tournament workers listen
only on `match:tournament` and scrimmage workers only on `match:scrimmage`, so
the scrimmage worker count caps concurrent scrimmage games and official games
never wait behind a scrimmage (`infra/docker-compose.vps2.yml`). One process may
still list both queues for local development (`docker-compose.play.yml`); RQ
then takes tournament jobs first. Set `RUNNER_WORKER_ID` to show the pool in
the admin worker view. The worker code, job and callback payloads are unchanged.

Public RQ callables are `ottv2_runner.jobs.build_submission(payload)` and
`ottv2_runner.jobs.run_match(payload)`. CLI validation uses the strict v1 DTO
shape; contract schemas remain the source of truth. The worker requires these
environment variables: `INTERNAL_API_BASE_URL` (base URL including `/api/v1`),
`WORKER_API_TOKEN`, `REDIS_URL`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`,
`S3_SECRET_ACCESS_KEY`, and `S3_BUCKET`, matching `infra/vps2.env.example`.
Optional settings include
`RUNNER_OUTBOX_DIR` (must be a persistent volume), `RUNNER_WORK_DIR`,
`RUNNER_WORKER_ID`, and `RUNNER_CPUSET_BLUE`/`RUNNER_CPUSET_RED`.

Contract regression tests validate failed smoke-build callbacks and startup
CRASH/TIMEOUT results against the shared v1.0.0 schemas. Bot stdout is limited
to 4096 bytes per line including LF; debug capture is truncated at 64 KiB per
bot, as specified by `dev-v1`. Oversized lines raise the public engine
`BotProtocolError`, including when a bot never terminates the line.

The worker image can be built with the included Dockerfile. Deployment images
must be published and referenced by immutable digest. The worker also requires
the system-owned `OTTv2_ENGINE_FACTORY=module:factory` and
`OTTv2_BUILD_VERIFIER=module:factory` adapters to be included in its image;
the VPS2 Compose configuration refuses to start without both settings.

Configure `RUNNER_IMAGE_PYTHON` and `RUNNER_IMAGE_CPP` as trusted, digest-pinned
images; C++ also needs `RUNNER_BUILD_IMAGE_CPP`. Java and Node remain disabled
until explicitly enabled with `RUNNER_ENABLE_JAVA=true` /
`RUNNER_ENABLE_NODE=true` and certified runtime/compiler images are configured.
Docker builds and containers use runner-generated Dockerfiles/argv only. The
runner never runs a participant Dockerfile, shell command, install script, or
network-connected build.

`OTTv2_ENGINE_FACTORY=module:factory` must resolve to a system-owned callable
returning an object with async `run_game(blue_io, red_io, config)`. It is a
narrow adapter around the public engine API; the runner implements no game
rules. `OTTv2_BUILD_VERIFIER=module:factory` may resolve to a verifier with
`verify(image, job, timeout_seconds=150)`; without it, the build result is an
explicit `INFRA_ERROR`, not `ready`. When `REGISTRY_URL` is set, a verified image is
pushed to that registry (`ottv2_runner.registry`) and the build callback's
`image_tag` is the immutable `REGISTRY_URL/ottv2-bot@sha256:…` reference; match
workers pull missing digest references before starting a bot. The push is done by
the host Docker daemon, so on VPS2 the daemon must trust the loopback registry.

Terminal callback payload/token pairs are fsync-written to the file outbox
before HTTP delivery. Transport retries resend that exact payload and never
rerun a completed build/game; preserve the outbox volume across restarts. S3
artifacts use unique staging keys containing resource, job, and lease token;
backend callback receipt/finalization remains backend-owned. Redis leases use
compare-token Lua for renewal and release. Worker heartbeat is sent to
`/api/v1/internal/workers/heartbeat`; callback requests use the worker bearer
token plus `X-Worker-Lease`.

Docker isolation options are specified in `ottv2_runner/sandbox.py`; the code
has not been security-certified. Staging ownership is aligned with backend:
`staging/{job_id}/{lease_token}/{builds|games}/{resource_id}/...`.
Game logs use `blue.stderr.log` / `red.stderr.log` for both success and infra errors.
The real engine adapter and build verifier ship in `runner/Dockerfile.engine`;
backend integration tests exercise their callbacks and replay promotion (Docker
processes and the S3 server are substituted). See backend/README.md.
Contract profile `dev-v1` remains development-only and is not an official ruleset.

### Live development acceptance run

`ottv2_runner.devkit` provides a **development-only** stand-in engine and build
verifier that speak the bot line protocol but implement no game rules
(`OTTv2_ENGINE_FACTORY=ottv2_runner.devkit:make_engine`,
`OTTv2_BUILD_VERIFIER=ottv2_runner.devkit:make_build_verifier`). With the dev
Compose stack and a registry on `127.0.0.1:5000` running:

```powershell
python scripts\dev_e2e.py
```

it exercises real RQ, Redis leases, MinIO, Docker builds, registry push/pull,
duplicate-job dedupe, crash/syntax-error bots, a full match, and callback outage
recovery through the outbox against a fake backend. Never use `devkit` in a
tournament.

## Hợp đồng tích hợp và hướng dẫn cho AI

Đọc [AGENTS.md](../AGENTS.md), [hợp đồng tích hợp](../integration.md) mục 2, 4, 5, 7–9 và README của engine/backend/infra/starter-kits.

- **Sở hữu:** build/match worker, Docker sandbox, adapter BotIO, upload artifact và callback. Không tự cập nhật DB, tính điểm hoặc tạo game attempt.
- **Nhận:** job v1 đã được C validate; **gọi:** public API ottv2; **trả:** callback v1 theo mục 4. Không tự thêm field hoặc đổi `plies` thành `total_plies` trên wire.
- Dùng schema/fixture trong [contracts](../contracts/README.md). Entry points cố định: `ottv2_runner.jobs.build_submission(payload)` và `ottv2_runner.jobs.run_match(payload)`; nhận một dict đúng schema. C enqueue cùng tên, không tự đặt hàm khác.
- Runner ghi started_at_ns khi khởi động bot, thu stderr độc lập, luôn dọn container trong finally. Engine sở hữu stdout giao thức và quyết định lỗi bot.
- Claim/lease và redelivery phải chống hai worker chạy cùng job. Backend sở hữu tạo attempt mới. HTTP callback timeout chỉ gửi lại payload đã lưu; không tự chạy lại ván.
- Upload xong replay/log rồi callback finished. Artifact và image của submission/game bất biến; không ghi đè replay của attempt trước.
- Callback dùng INTERNAL_API_BASE_URL có sẵn /api/v1 và token worker; không dùng token người chơi hoặc credential DB.

### Build và starter kit phải khớp

B dùng bảng ngôn ngữ/file chính/lệnh build/run trong [behavior.md](../contracts/behavior.md); chọn image digest khi triển khai Dockerfile. Python/C++ bắt buộc, Java/Node chỉ bật sau khi image và kit qua pipeline thật. Không tự đặt cách đóng gói khác kit.

Kiểm tra ZIP trước/sau giải nén, traversal, symlink, số file/kích thước theo giới hạn đã chốt trong behavior. Dockerfile do hệ thống cung cấp; không chạy Dockerfile hoặc shell command tùy ý từ metadata của thí sinh.

### Chạy độc lập và bàn giao

Package worker và lệnh chạy/test bằng fake đã được bổ sung trong `pyproject.toml`,
`ottv2_runner/` và `tests/`. Compose/production service wiring, Docker/MinIO/
Redis/backend acceptance testing và registry publication chưa được chạy trong
môi trường này; liệt kê biến môi trường cần triển khai ở phần Implemented
package phía trên, không commit secret.

Trước merge: bot mẫu kit build thành công; timeout/crash/illegal move giữ đúng lý do; container sạch sau engine exception; callback gửi lặp chỉ tạo một kết quả; storage/API mất kết nối và worker chết có cách phục hồi. Ghi rõ test nào cần Linux/Docker và test nào đã thực sự chạy. A review engine adapter; C review job/callback.


**Phụ trách:** B · **Dự phòng:** A · **Chạy ở:** VPS 2

Thư mục này chứa mọi thứ chạm vào code của thí sinh. Đây là phần nhạy cảm nhất của hệ thống: một lỗ hổng ở đây có thể làm sai kết quả hoặc cho bot chiếm máy chủ.

## Cấu trúc dự kiến

```
runner/
├── images/
│   ├── python/Dockerfile   # ottv2/py:1    — Python 3.12 + numpy
│   ├── cpp/Dockerfile      # ottv2/cpp:1   — g++ C++20
│   ├── java/Dockerfile     # ottv2/java:1  — Java 21
│   └── node/Dockerfile     # ottv2/node:1  — Node 22
├── sandbox.py              # Dựng lệnh docker run với đầy đủ giới hạn
├── build_worker.py         # Lấy việc từ hàng đợi build
├── match_worker.py         # Lấy việc từ hàng đợi match
├── backend_client.py       # Gọi /internal/* của backend
└── tests/
    └── malicious/          # Bộ bot phá hoại
```

## Nhiệm vụ

### Ngày 1–2
- [ ] `images/python`: image nền, người dùng không phải root (`10001`), có sẵn gói `ottv2`
- [ ] `sandbox.py`: dựng lệnh `docker run -i --rm` với toàn bộ giới hạn ở `architecture.md` mục 6
- [ ] Chạy một bot Python trong container, nói chuyện qua stdin/stdout, đo độ trễ khứ hồi một dòng
- [ ] Chốt với C định dạng kết quả gửi về `/internal/builds/{id}` và `/internal/games/{id}`

### Ngày 3 — Build worker
- [ ] Tải mã nguồn từ MinIO, giải nén vào thư mục tạm, kiểm tra lại kích thước và số tệp
- [ ] `docker build --network none`, gắn thẻ `ottv2-bot:{submission_id}`, đẩy vào registry nội bộ
- [ ] Chạy thử một ván với bot ngẫu nhiên, thất bại thì đánh dấu `failed`
- [ ] Đẩy nhật ký build lên MinIO, gửi kết quả về backend
- [ ] Phát hiện lỗi thường gặp và ghi thông báo dễ hiểu vào nhật ký: quên flush, không gửi `READY`, sai tên tệp chính

### Ngày 4 — Match worker
- [ ] Lấy việc từ `match:tournament` trước, `match:scrimmage` sau
- [ ] Khởi động 2 container bot, nối ống dẫn vào engine, chạy ván
- [ ] Ghim mỗi container vào một lõi riêng theo số thứ tự worker
- [ ] Dừng và xóa container khi ván kết thúc, kể cả khi engine lỗi
- [ ] Đẩy replay và stderr lên MinIO, gửi kết quả về backend
- [ ] Phân biệt lỗi của bot với `INFRA_ERROR`; với lỗi hạ tầng thì đẩy lại tối đa 3 lần

### Ngày 5–6
- [ ] Image C++ (bắt buộc), Java và Node (nếu kịp)
- [ ] Benchmark: cùng một cặp bot chạy 100 lần, độ lệch thời gian tiêu thụ dưới 2%
- [ ] Nhịp tim worker gửi endpoint nội bộ `/api/v1/internal/workers/heartbeat` mỗi 30 giây

### Ngày 7 — Gia cố
- [ ] Viết cùng A bộ 10 bot phá hoại và xác nhận tất cả bị chặn:
    - Fork bomb
    - Mở kết nối mạng ra ngoài
    - Kết nối sang container đối thủ
    - Ghi đầy đĩa
    - Cấp phát vượt bộ nhớ
    - Đọc `/etc/passwd`, biến môi trường, Docker socket
    - In vô hạn ra stdout và stderr
    - Treo không trả lời
    - Ngủ đến sát hết giờ rồi mới trả lời mỗi nước
    - Tạo tiến trình con tiếp tục chạy sau khi tiến trình chính thoát
- [ ] Giới hạn kích thước nhật ký stderr mỗi bot (1 MB), phần thừa cắt bỏ

## Giao diện với phần khác

| Nhận từ | Thứ nhận |
| --- | --- |
| `backend/` | Việc trong Redis theo định dạng `architecture.md` mục 5.4 |
| `engine/` | Hàm `run_game` |

| Cung cấp cho | Thứ được cung cấp |
| --- | --- |
| `backend/` | Kết quả build và kết quả ván qua `/internal/*` |
| MinIO | Nhật ký build, replay, stderr |

## Tiêu chí hoàn thành

- Bot Python mẫu build xong dưới 60 giây.
- Bộ 10 bot phá hoại đều bị chặn, máy chủ không bị ảnh hưởng.
- Độ lệch đồng hồ dưới 2% qua 100 lần chạy.
- Tắt đột ngột một worker giữa trận thì trận đó tự chạy lại ở worker khác.

### Cách ly CPU build và giới hạn tài nguyên (2026-10-22)

`RUNNER_CPUSET_BUILD` áp dụng cho cả container compiler và bot chạy thử trong `EngineBuildVerifier`; không lấy CPU của bot Xanh giải. CLI/test cũ chưa cấu hình vẫn fallback CPU 0 để tương thích, **không dùng fallback khi triển khai giải**. Cả Compose VPS2/local đều truyền giá trị rõ ràng; `infra/check_resources.py` từ chối thiếu giá trị hoặc trùng CPU giải. Có thể truyền `build_cpu` vào verifier khi nhúng trong test.

Compiler/smoke vẫn giới hạn 1 CPU, 512 MiB, không thêm swap; container bot trận giữ cùng giới hạn. Giới hạn worker Compose chỉ áp dụng tiến trình điều phối, không tự truyền xuống container con do host Docker daemon tạo. Vì vậy preflight cộng riêng 2×512 MiB cho mỗi match worker và 512 MiB cho compiler/smoke tuần tự. Registry/worker có giới hạn CPU, RAM, PID và cùng nằm trên CPU phụ trợ. Không thay HTTP 1.3.0, job/callback v1 hay luật/clock.
