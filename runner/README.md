# runner — Build worker, match worker và sandbox

Package `ottv2_runner` (Python 3.12+) chứa mọi thứ chạm vào code thí sinh: nhận job từ Redis RQ, kiểm tra ZIP, build image bot không mạng, chạy ván trong container sandbox, đẩy artifact lên MinIO rồi gọi callback backend. Runner không chứa luật (engine lo), không đụng DB và không tự tạo attempt.

## Cài đặt và kiểm thử

Từ repo root:

```sh
python -m pip install -e engine -e runner
python -m pip install --target contracts/.deps -r contracts/requirements.txt
python -m unittest discover -s runner/tests -v
docker build -f runner/Dockerfile.engine -t ottv2-worker:local .
```

Triển khai dùng `Dockerfile.engine` (có cả engine). `runner/Dockerfile` không kèm engine, chỉ dành cho adapter tự cung cấp.

## CLI

```sh
ottv2-runner validate-build path/to/build-job.json
ottv2-runner validate-match path/to/match-job.json
ottv2-runner-worker --queue build        # hoặc match:tournament, match:scrimmage
ottv2-runner flush-outbox                # gửi lại callback đang chờ, không chạy lại job
```

Mỗi worker nghe đúng một hàng đợi: worker giải chỉ nghe `match:tournament`, worker đánh tập chỉ nghe `match:scrimmage`. `infra/check_resources.py` từ chối cấu hình trộn hai hàng đợi.

## Biến môi trường

| Biến | Ý nghĩa |
| --- | --- |
| `INTERNAL_API_BASE_URL` | Bắt buộc. Base URL nội bộ của backend, phải kết thúc bằng `/api/v1` (một VPS: `http://backend:8000/api/v1`) |
| `WORKER_API_TOKEN` | Bắt buộc. Token callback, trùng với backend |
| `REDIS_URL` | Bắt buộc |
| `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET` | Bắt buộc. MinIO |
| `OTTv2_ENGINE_FACTORY`, `OTTv2_BUILD_VERIFIER` | Adapter engine, xem [engine/README.md](../engine/README.md). Thiếu verifier thì build báo `INFRA_ERROR`, không bao giờ `ready`; thiếu engine thì ván báo `INFRA_ERROR` |
| `RUNNER_IMAGE_PYTHON`, `RUNNER_IMAGE_CPP`, `RUNNER_BUILD_IMAGE_CPP` | Image chạy bot và compiler C++, ghim theo digest. Image Python phải cài sẵn `ottv2` (`engine/Dockerfile.bot`) |
| `REGISTRY_URL` | Dạng `host:port`. Image đã kiểm tra được push lên đây và `image_tag` trong callback là `REGISTRY_URL/ottv2-bot@sha256:…`; Docker daemon của host phải tin registry này |
| `RUNNER_CPUSET_BLUE`, `RUNNER_CPUSET_RED` | CPU ghim cho hai bot của match worker |
| `RUNNER_CPUSET_BUILD` | CPU cho compiler và ván thử của build. Thiếu thì rơi về CPU 0, không dùng khi triển khai |
| `RUNNER_OUTBOX_DIR` | Thư mục outbox callback, phải là volume bền |
| `RUNNER_WORK_DIR`, `RUNNER_WORKER_ID` | Thư mục làm việc; tên worker hiện ở P2 → Hàng đợi |
| `RUNNER_ENABLE_JAVA`, `RUNNER_ENABLE_NODE` | Mặc định `false`; chỉ bật khi có image và kit đã kiểm chứng |

## Hành vi chính

- **Job**: theo schema v1 trong [contracts](../contracts/README.md). Hàm RQ là `ottv2_runner.jobs.build_submission(payload)` và `ottv2_runner.jobs.run_match(payload)`; RQ job id bằng `payload.job_id`.
- **Lease**: Redis `ottv2:lease:{job_id}` SET NX, gia hạn và giải phóng bằng Lua so token. Nhịp tim gửi tới `/api/v1/internal/workers/heartbeat`.
- **Callback**: kết quả cuối được fsync vào outbox trước khi gửi. Retry gửi lại đúng payload đó, không chạy lại build hay ván. Request kèm token worker và `X-Worker-Lease`.
- **Artifact**: upload vào `staging/{job_id}/{lease_token}/{builds|games}/{resource_id}/...`; backend chuyển sang khóa chính thức. Log ván là `blue.stderr.log`, `red.stderr.log`.
- **Build**: kiểm tra ZIP trước và sau giải nén (traversal, symlink, số file, kích thước). Dockerfile và argv do runner sinh; không bao giờ chạy Dockerfile, script cài đặt hay lệnh shell của thí sinh; build không có mạng. Tên file chính và lệnh build/run theo bảng trong [behavior.md](../contracts/behavior.md).
- **Giao thức**: stdout của bot tối đa 4096 byte mỗi dòng (gồm LF); debug lưu tối đa 64 KiB mỗi bot; dòng quá dài raise `BotProtocolError`.
- **Tài nguyên**: giới hạn container ở [architecture.md mục 6](../architecture.md#6-sandbox) và `ottv2_runner/sandbox.py`. Compiler và bot chạy thử cũng 1 CPU, 512 MiB, không swap. Giới hạn Compose của worker chỉ áp cho tiến trình điều phối, không truyền xuống container con do Docker daemon của host tạo.
- **Thư mục build**: build worker bind-mount `/var/lib/ottv2/work` ở cùng đường dẫn trên host và trong container, vì compiler chạy qua Docker daemon của host. Đổi sang đường dẫn chỉ có trong container (ví dụ tmpfs) thì build C++ lỗi `main.cpp: No such file or directory`.

## Chạy thử không cần engine thật

`ottv2_runner.devkit` là engine và verifier giả: nói đúng giao thức nhưng không có luật (`OTTv2_ENGINE_FACTORY=ottv2_runner.devkit:make_engine`, `OTTv2_BUILD_VERIFIER=ottv2_runner.devkit:make_build_verifier`). Khi đã bật dịch vụ dev (`infra/docker-compose.dev.yml`) và registry ở `127.0.0.1:5000`:

```sh
python runner/scripts/dev_e2e.py
```

Script chạy RQ, lease, MinIO, Docker build, registry, chống job trùng, bot crash và bot lỗi cú pháp, một ván đầy đủ, phục hồi callback qua outbox với backend giả. Không dùng devkit cho giải.

## Cấu trúc

```
ottv2_runner/
├── jobs.py, worker.py, cli.py           # Entry point RQ và CLI
├── runtime.py                           # Điều phối job, nhịp tim, callback cuối
├── validation.py                        # Kiểm tra job theo schema v1
├── archive.py                           # Kiểm tra và giải nén ZIP
├── sandbox.py, registry.py              # Docker build/run, push/pull image
├── engine.py, engine_verifier.py        # Nạp engine, ván chạy thử khi build
├── lease.py                             # Lease Redis
├── callbacks.py, outbox.py, http.py     # Callback bền
├── storage.py                           # S3/MinIO
├── config.py, errors.py
└── devkit.py                            # Engine giả chỉ dùng khi phát triển
```

## Giới hạn

Unit test thay Docker, Redis, MinIO và backend bằng fake; `dev_e2e.py` và Compose thi đấu đã chạy với dịch vụ dev thật (build Python, C++ rồi chạy một ván). Sandbox chưa được audit bảo mật và chưa benchmark độ lệch đồng hồ.
