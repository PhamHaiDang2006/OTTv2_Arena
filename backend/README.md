# backend — API, dữ liệu, logic giải đấu

FastAPI triển khai contract v1.3.0, luật `dev-v1`. Backend là trung tâm điều phối: xác thực, đội, bản nộp, đẩy việc cho worker, nhận callback, bảng xếp hạng, nhánh đấu, phòng hai người và hồ sơ người chơi. Cùng một code chạy hai tiến trình: API (uvicorn) và scheduler.

Hợp đồng HTTP là [contracts/openapi.yaml](../contracts/openapi.yaml); OpenAPI tự sinh của FastAPI bị tắt. Request và response được validate bằng chính JSON Schema trong `contracts/`. Quyết định đã chọn và câu hỏi còn mở: [DECISIONS.md](DECISIONS.md).

## Chạy local

Cần Python 3.12 qua [uv](https://docs.astral.sh/uv/), PostgreSQL 16, Redis 7 và MinIO; dịch vụ dữ liệu dev có sẵn trong `infra/docker-compose.dev.yml` ([infra/README.md](../infra/README.md)). Từ `backend/`:

```bash
uv sync
export DATABASE_URL=postgresql+psycopg://ottv2:<mật-khẩu>@127.0.0.1:5432/ottv2
export REDIS_URL=redis://:<mật-khẩu>@127.0.0.1:6379/0
export S3_ENDPOINT_URL=http://127.0.0.1:9000 S3_PUBLIC_ENDPOINT_URL=http://127.0.0.1:9000 S3_BUCKET=ottv2
export S3_ACCESS_KEY_ID=... S3_SECRET_ACCESS_KEY=...
export JWT_SECRET=... WORKER_API_TOKEN=...
export FRONTEND_ORIGINS=http://127.0.0.1:5173,http://127.0.0.1:5174
export COOKIE_SECURE=false                # chỉ khi dev qua HTTP

uv run python -m app.cli migrate          # alembic upgrade head (head hiện tại: 0004)
uv run python -m app.cli ensure-bucket    # dev: tạo bucket nếu chưa có
OTTV2_PASSWORD=... uv run python -m app.cli seed-dev   # admin@example.test + 2 đội approved (doi-a, doi-b)
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
uv run python -m app.cli scheduler        # tiến trình riêng
```

Scheduler đẩy outbox sang RQ và WebSocket, gỡ job của hàng đợi đang tạm dừng, canh lease hết hạn để tạo attempt mới, đóng băng vòng theo giờ và tính độ trùng mã. Luôn chạy `migrate` trước API và scheduler.

Trên Windows, `infra/start-local-api.ps1` tự tạo `infra/.env`, bật PostgreSQL/Redis, migrate và chạy API nền.

## Tài khoản

- Người chơi tự đăng ký qua `POST /api/v1/auth/register` (email, mật khẩu, tên đội): tạo đội trưởng và đội `pending` trong một transaction. Chưa có xác minh email hay quên mật khẩu.
- Admin chỉ tạo bằng CLI: `OTTV2_PASSWORD=... uv run python -m app.cli create-admin --email ...`.
- Đặt mật khẩu: `app.cli set-password --email ...`; thêm thành viên: `app.cli add-member --team <slug> --email ...`. Đội tạo qua `POST /admin/teams` hoặc import CSV không có mật khẩu.

Giới hạn tần suất đăng ký và đăng nhập tính theo IP client. Khi chạy sau Caddy, đặt `FORWARDED_ALLOW_IPS` cho uvicorn để lấy IP thật từ header; nếu không, mọi request đều mang IP của Caddy và giới hạn đăng ký thành giới hạn chung của cả site.

## Kiểm thử

Từ repo root:

```sh
uv sync --project backend --frozen
uv pip install --python backend/.venv/bin/python -e engine -e runner
uv pip install --python backend/.venv/bin/python --target contracts/.deps -r contracts/requirements.txt
docker compose -f infra/docker-compose.test.yml up -d --wait
export DATABASE_URL='postgresql+psycopg://ottv2_test:local-test-only@127.0.0.1:55432/ottv2_test'
export REDIS_URL='redis://127.0.0.1:56379/15'
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app tests migrations scripts
```

- Test **TRUNCATE mọi bảng và FLUSHDB**: tên DB phải chứa `test` và Redis phải dùng DB khác 0, conftest từ chối nếu sai. `docker-compose.test.yml` chỉ chứa dữ liệu tạm.
- Gọi thẳng `.venv/bin/python` (Windows: `.venv/Scripts/python.exe`) thay vì `uv run`, để uv không gỡ engine/runner khi đồng bộ môi trường.
- Suite dùng PostgreSQL, Redis, RQ và engine thật; S3 giả lập bằng moto, Docker và HTTP của worker thay bằng adapter test. Kết quả liên thông backend → runner → engine: [INTEGRATION_CHECK.md](INTEGRATION_CHECK.md).
- Smoke với tiến trình thật: chạy API và scheduler, `seed-dev`, rồi `OTTV2_PASSWORD=... uv run python scripts/smoke.py --api http://127.0.0.1:8000 --origin http://127.0.0.1:5173`. Script đóng vai worker (lease, upload S3, callback), không build hay chạy bot thật.

## Image

```sh
docker build -f backend/Dockerfile -t ottv2-backend:local .   # từ repo root
```

Image chứa `contracts/`, `architecture.md` (nguồn mục giao thức cho `GET /docs`), migration và CLI. Compose chạy API và scheduler thành hai service từ cùng image.

## Biến môi trường

Bắt buộc: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `WORKER_API_TOKEN`. Cần cho tính năng nộp bài và replay: `S3_ENDPOINT_URL`, `S3_PUBLIC_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`. `FRONTEND_ORIGINS` là danh sách origin được phép, ngăn bằng dấu phẩy.

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `ALLOW_DEVELOPMENT_TOURNAMENTS` | `false` | Cho phép tạo giải với ruleset development; chỉ bật để demo |
| `RULESET_ID`, `ENGINE_VERSION` | `dev-v1`, `1.0.0` | Ghi vào submission, job và giải |
| `ENABLED_LANGUAGES` | `python,cpp` | Ngôn ngữ nhận upload |
| `COOKIE_SECURE` | `true` | Cờ Secure của cookie refresh; chỉ tắt khi dev qua HTTP |
| `SCRIMMAGE_MAX_ACTIVE_PER_TEAM` | `2` | Số trận đánh tập chưa xong mỗi đội (`429 SCRIMMAGE_LIMIT`) |
| `SCRIMMAGE_MAX_PENDING_GAMES` | `12` | Tồn đọng đánh tập tối đa trước khi tạm dừng nhận (`503 SCRIMMAGE_PAUSED`) |
| `SCRIMMAGE_PAUSE_TOURNAMENT_JOBS` | `1` | Tạm dừng nhận đánh tập khi giải có việc; `0` là tắt |
| `SUBMISSION_RATE_PER_HOUR` | `10` | Số lần nộp mỗi đội mỗi giờ |
| `LOGIN_RATE_PER_MINUTE` | `10` | Số lần đăng nhập mỗi IP + email mỗi phút |
| `REGISTRATION_RATE_PER_HOUR` | `5` | Số lần đăng ký mỗi IP mỗi giờ; Redis lỗi thì trả 503 |
| `REPLAY_URL_TTL_SECONDS` | `300` | Hạn URL ký sẵn của replay |
| `RQ_BUILD_TIMEOUT_SECONDS`, `RQ_MATCH_TIMEOUT_SECONDS` | `600`, `1800` | `job_timeout` khi enqueue RQ |
| `STARTER_KITS_JSON` | `[]` | Danh sách starter kit hiện ở `GET /docs` |
| `S3_REGION` | `us-east-1` | Region ký S3 |
| `CONTRACTS_DIR`, `ARCHITECTURE_PATH` | `../contracts`, `../architecture.md` | Nơi đọc schema, rules và mục giao thức lúc chạy |

## Cấu trúc

```
backend/
├── app/
│   ├── main.py, config.py, cli.py
│   ├── contract.py        # Nạp schema/operations từ contracts/, validate request
│   ├── models.py          # Lược đồ SQL
│   ├── auth/ teams/ submissions/ matches/ tournament/ admin/ internal/ public/ ws/
│   ├── rooms.py, room_rules.py   # Phòng hai người, kiểm tra nước trên server
│   ├── profiles.py        # Hồ sơ và thống kê phòng, không lộ email
│   ├── queue.py           # Outbox giao dịch → RQ (job id = RQ id), Redis pub/sub cho WS
│   ├── scheduler.py, similarity.py
│   └── deps.py, idempotency.py, errors.py, security.py, ratelimit.py, audit.py, serializers.py, storage.py
├── migrations/            # Alembic 0001–0004
├── scripts/smoke.py
└── tests/                 # pytest; mọi response được validate với contracts/
```

## Quy tắc nghiệp vụ

- Đội của thí sinh lấy từ phiên đăng nhập đã kiểm tra membership; ID đội khác trong request (đối thủ, thao tác admin) phải kiểm tra quyền riêng.
- Mã nguồn chỉ đội sở hữu và admin đọc được.
- Submission đi `queued → building → ready/failed`; chỉ bot `ready` của chính đội mới được chọn.
- Không xóa, không ghi đè `games`; kết quả hiện hành là attempt lớn nhất. Callback lặp lại giống hệt trả 200, khác payload trả 409, callback của attempt cũ không thay kết quả hiện hành.
- WebSocket chỉ phát sau commit để frontend tải lại; không phát mã nguồn hay debug ra kênh public.
- Casual chạy trên trình duyệt từ contract 1.3.0: các route `/casual/games` trả 404, bảng `casual_games` được giữ nhưng không đọc/ghi.

Chi tiết chuyển trạng thái, lease và idempotency: [contracts/behavior.md](../contracts/behavior.md).
