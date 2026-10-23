# backend — API, dữ liệu, logic giải đấu

## Hợp đồng tích hợp và hướng dẫn cho AI

Đọc [AGENTS.md](../AGENTS.md), [hợp đồng tích hợp](../integration.md) mục 2–4, 7–9 và README runner/P1/P2. C là chủ schema DB, migration và hợp đồng HTTP.

### API trước giao diện

- [contracts/openapi.yaml](../contracts/openapi.yaml) đã có operationId, quyền, request/response/error, fixture và phân trang. C triển khai đúng hợp đồng này; không tạo lại API theo suy đoán. Nguồn sinh là contracts/build.mjs.
- OpenAPI đã review là hợp đồng consumer. Code FastAPI phải khớp; kiểm tra diff OpenAPI sinh từ code trong CI, không âm thầm lấy code mới ghi đè hợp đồng.
- D sinh TypeScript client từ bản này. Không bắt D tự khai báo DTO hoặc suy kiểu từ bảng SQL.
- API-01 đã được đặc tả: opponents/quota, auth/me, freeze/snapshot, nguồn/log, thông báo và queue. Dùng operationId và fixture trong contracts/operations.json để phối hợp D.
- Mọi tài nguyên submission/match/game phải có schema detail và list rõ ràng. Login/refresh, error envelope, response list theo integration mục 3.
- Thực hiện cookie/CSRF/Origin, đăng ký WS và hết hạn token theo contracts/behavior.md. WebSocket chỉ là thông báo refetch sau commit; không phát mã nguồn/debug lên public.

### Trạng thái và dữ liệu

- Submission queued → building → ready/failed; không cho đặt active bot chưa ready hoặc của đội khác.
- Snapshot bot theo vòng cần dữ liệu bền riêng (round và frozen submission mapping); bổ sung migration/architecture trước code, không chỉ đọc lại active_bots khi enqueue.
- Dùng enum trong schema và bảng chuyển trạng thái/điều kiện trong contracts/behavior.md; trả 409 khi không hợp lệ, frontend không tự điều hành tiến trình.
- Team hiện tại lấy từ user/token được kiểm tra với membership. Admin thao tác đội khác và opponent_team_id được phép là tham số nhưng phải validate quyền/nghiệp vụ; không diễn giải quy tắc team_id thành cấm mọi ID đội trong API.
- Callback tuân mục 4: xác thực job, transaction, dedup, attempt cũ và chống cộng điểm lặp. Chốt cơ chế enqueue sau commit và phục hồi khi DB thành công nhưng Redis lỗi.
- DB result dùng BLUE/RED khi finished; callback result là object, adapter phải map rõ. Không trộn kết quả game với điểm cặp đấu.
- Giữ lịch sử rerun/override, không xóa games. Tính lại đúng một lần; khóa thao tác khi downstream đã frozen hoặc giải finished theo contracts/behavior.md.

### Chạy độc lập và bàn giao

Lệnh chạy ở mục [Chạy backend](#chạy-backend) bên dưới. Quyết định đã chọn và câu hỏi còn mở: [DECISIONS.md](DECISIONS.md).

Trước merge: response thật khớp OpenAPI/fixture, phân quyền chéo đội, refresh/logout, callback lặp và sai job, snapshot bất biến, retry attempt, bảng điểm và nhánh; WS reconnect refetch được với D. Migration kiểm tra từ DB trống và từ revision trước. Chỉ C tạo migration, ghi head/revision và thứ tự merge để tránh hai head. D review API, B review queue/callback.


**Phụ trách:** C · **Dự phòng:** D · **Công nghệ:** FastAPI, SQLAlchemy 2, Alembic, RQ, PostgreSQL 16, MinIO

Backend là trung tâm điều phối: xác thực người dùng, giữ dữ liệu đội và bản nộp, đẩy việc cho worker, nhận kết quả, tính bảng xếp hạng và dựng nhánh đấu.

## Chạy backend

Triển khai contract **v1.3.0**, profile **dev-v1** (development). Công cụ: Python 3.12 qua [uv](https://docs.astral.sh/uv/) (đã dùng uv 0.13.1), PostgreSQL 16, Redis 7, S3/MinIO. Mọi lệnh chạy từ `backend/`.

```bash
uv sync                                   # tạo .venv từ uv.lock (Python 3.12)

# Biến môi trường: tên theo infra/.env.example, cộng thêm các biến backend ở bảng dưới
export DATABASE_URL=postgresql+psycopg://ottv2:ottv2@127.0.0.1:5432/ottv2
export REDIS_URL=redis://127.0.0.1:6379/0
export S3_ENDPOINT_URL=http://127.0.0.1:9000 S3_PUBLIC_ENDPOINT_URL=http://127.0.0.1:9000 S3_BUCKET=ottv2
export S3_ACCESS_KEY_ID=... S3_SECRET_ACCESS_KEY=...
export JWT_SECRET=... WORKER_API_TOKEN=...
export FRONTEND_ORIGINS=http://localhost:5173,http://localhost:5174
export COOKIE_SECURE=false                # chỉ dev loopback; production để mặc định true

uv run python -m app.cli migrate          # alembic upgrade head (head hiện tại: 0002)
uv run python -m app.cli ensure-bucket    # dev: tạo bucket nếu chưa có
OTTV2_PASSWORD=... uv run python -m app.cli seed-dev   # admin@example.test + 2 đội approved (doi-a, doi-b)
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
uv run python -m app.cli scheduler        # tiến trình riêng: outbox → RQ/WS, gỡ job queue đang dừng, watchdog lease, freeze theo giờ, similarity
```

Người chơi tự đăng ký qua `POST /api/v1/auth/register` (email, password, team_name), nhận phiên đăng nhập và đội pending để nộp bot/đánh tập. API quản trị đội không nhận mật khẩu. Đội trưởng tạo bằng `POST /admin/teams` hoặc import CSV chưa có mật khẩu; đặt bằng `OTTV2_PASSWORD=... uv run python -m app.cli set-password --email ...`. Thêm thành viên: `app.cli add-member --team <slug> --email ...`. Admin: `app.cli create-admin --email ...`.

### Test

Kiểm tra liên thông backend → runner → engine nằm trong
`tests/test_runner_engine_integration.py`. Cài cả hai package local trước khi
chạy suite backend. Kết quả và giới hạn nghiệm thu tại
[INTEGRATION_CHECK.md](INTEGRATION_CHECK.md). Từ repo root:

```sh
uv sync --project backend --frozen
uv pip install --python backend/.venv/bin/python -e engine -e runner
uv pip install --python backend/.venv/bin/python --target contracts/.deps -r contracts/requirements.txt
docker compose -f infra/docker-compose.test.yml up -d --wait
export DATABASE_URL='postgresql+psycopg://ottv2_test:local-test-only@127.0.0.1:55432/ottv2_test'
export REDIS_URL='redis://127.0.0.1:56379/15'
cd backend
.venv/bin/python -m pytest -q
```

Windows dùng `.venv/Scripts/python.exe` thay `.venv/bin/python` và đặt biến bằng
`$env:DATABASE_URL=...`, `$env:REDIS_URL=...`. Sau cài runner/engine, gọi Python
trực tiếp như trên để `uv run` không gỡ package tích hợp khi đồng bộ môi trường.
Compose test chỉ dùng dữ liệu tạm, tách khỏi dev/production. Suite dùng PostgreSQL,
Redis và RQ thật, adapter S3 thật với moto, engine thật; Docker và transport HTTP
được thay bằng test adapter. Đây chưa phải chứng nhận sandbox Docker/MinIO thật.

Image backend build từ repo root bằng
`docker build -f backend/Dockerfile -t ottv2-backend:local .`.
Image chứa contracts, architecture, migrations và CLI. Chạy
`python -m app.cli migrate` trước API/scheduler; Compose VPS1 có scheduler riêng.
Nguồn hợp đồng v1.0.0 được giữ; fixture callback được tái sinh bằng
`node contracts/build.mjs`, dùng staging theo `contracts/behavior.md`.

Test chạy trên PostgreSQL và Redis thật, S3 giả lập bằng moto. Test **TRUNCATE mọi bảng và FLUSHDB**, nên tên DB phải chứa `test` và Redis phải chọn DB khác 0 (conftest từ chối nếu sai).

```bash
# Sau thiết lập môi trường tích hợp ở trên, từ backend/:
.venv/bin/python -m pytest                              # toàn bộ
.venv/bin/python -m pytest tests/test_tournament_flow.py -k full
.venv/bin/python -m ruff check app tests migrations scripts
```

Smoke với tiến trình thật (`scripts/smoke.py` đóng vai worker: lease Redis, upload S3, callback; không build/chạy bot thật): chạy API + scheduler với cùng env, `seed-dev`, rồi `OTTV2_PASSWORD=... uv run python scripts/smoke.py --api http://127.0.0.1:8000 --origin http://localhost:5173`.

### Biến môi trường riêng của backend

Chưa có trong `infra/.env.example` (B sở hữu file đó); mặc định dùng được cho dev.

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `ENGINE_VERSION` | `1.0.0` | engine_version ghi vào submission/build job và scrimmage |
| `ENABLED_LANGUAGES` | `python,cpp` | Ngôn ngữ nhận upload; Java/Node chỉ bật sau khi sandbox đạt |
| `COOKIE_SECURE` | `true` | Cờ Secure của cookie refresh |
| `S3_REGION` | `us-east-1` | Region ký S3 |
| `CONTRACTS_DIR` | `../contracts` | Backend đọc schema/operations/version/rules từ đây lúc chạy; image phải chứa thư mục này |
| `ARCHITECTURE_PATH` | `../architecture.md` | Nguồn `protocol_markdown` cho `GET /docs` |
| `REPLAY_URL_TTL_SECONDS` | `300` | Hạn URL ký sẵn của replay |
| `STARTER_KITS_JSON` | `[]` | Danh sách starter kit cho `GET /docs` (B cung cấp) |
| `SUBMISSION_RATE_PER_HOUR` | `10` | Giới hạn nộp mỗi đội mỗi giờ (429 RATE_LIMITED) |
| `LOGIN_RATE_PER_MINUTE` | `10` | Giới hạn login mỗi IP+email mỗi phút |
| `RQ_BUILD_TIMEOUT_SECONDS`, `RQ_MATCH_TIMEOUT_SECONDS` | `600`, `1800` | job_timeout khi enqueue RQ |

## Cấu trúc

```
backend/
├── app/
│   ├── main.py          # ASGI app; tắt OpenAPI tự sinh, hợp đồng là contracts/openapi.yaml
│   ├── contract.py      # nạp schema/operations từ contracts/, validate request theo JSON Schema chung
│   ├── models.py        # lược đồ SQL (C sở hữu); migrations/versions/0001_initial_schema.py
│   ├── deps.py, idempotency.py, errors.py, security.py, ratelimit.py, audit.py, serializers.py
│   ├── auth/ teams/ submissions/ matches/ tournament/ admin/ internal/ ws/ public/
│   ├── queue.py         # outbox giao dịch → RQ (job_id = RQ id) và Redis pub/sub cho WS
│   ├── scheduler.py     # outbox, watchdog lease, freeze theo giờ, similarity, dọn dẹp
│   └── cli.py
├── migrations/
├── scripts/smoke.py
└── tests/               # pytest; mọi response được validate với contracts/
```

## Nhiệm vụ

### Ngày 1
- [ ] Lược đồ DB theo `architecture.md` mục 5.1, migration đầu tiên
- [ ] Đăng nhập, refresh, đăng xuất; ba vai trò `member`, `captain`, `admin`
- [ ] Liệt kê endpoint và kiểu dữ liệu trả về, xuất OpenAPI để D gọi API giả

### Ngày 2
- [ ] API đội và thành viên; script tạo sẵn 20 đội và tài khoản từ tệp CSV
- [ ] `POST /submissions`: kiểm tra zip (tối đa 1 MB, 50 tệp, không tệp nhị phân), lưu MinIO, tính `sha256`, đẩy build job
- [ ] Chốt định dạng build job và match job với B

### Ngày 3
- [ ] `POST /internal/builds/{id}`, `POST /internal/games/{id}`, xác thực bằng token worker
- [ ] `PUT /teams/me/active-bot`, tách `scrimmage` và `tournament`
- [ ] API đánh tập: mỗi lần tạo 1 cặp 2 ván đổi bên; hạn mức 60 trận mỗi đội mỗi ngày

### Ngày 4
- [ ] WebSocket với kênh `team:{id}` và `public`; phát `build.updated`, `game.finished`, `match.finished`
- [ ] API trận, ván; `GET /games/{id}/replay` trả URL ký sẵn từ MinIO

### Ngày 5 — Vòng bảng
- [ ] Bốc thăm 4 bảng × 5 đội theo 4 nhóm hạt giống; seed ghi vào `audit_log` trước khi bốc
- [ ] Đóng băng: chụp `active_bots` phạm vi `tournament` của mọi đội
- [ ] Sinh 10 cặp mỗi bảng, mỗi cặp 2 ván đổi bên
- [ ] Tính điểm 3–1–0 theo cặp; tiêu chí phụ: hiệu số ván → số ván thắng → đối đầu → tổng nước đi trong ván thắng → bốc thăm
- [ ] Kiểm thử tính bảng xếp hạng với ít nhất 10 kịch bản, kể cả 3 đội bằng điểm

### Ngày 6 — Loại trực tiếp và quản trị
- [ ] Điền nhánh: Nhất A–Nhì B, Nhất B–Nhì A, Nhất C–Nhì D, Nhất D–Nhì C
- [ ] Tứ kết, bán kết chạm 2 (3 ván); tranh ba, chung kết chạm 3 (5 ván); chỉ đẩy ván tiếp khi cặp chưa phân thắng bại
- [ ] Quy tắc chọn bên ở ván quyết định cho đội hạt giống cao hơn
- [ ] Chạy lại ván (`attempt + 1`), sửa kết quả bắt buộc có lý do
- [ ] Ghi mọi thao tác quản trị vào `audit_log`
- [ ] `GET /admin/queue`: số việc chờ, đang chạy, nhịp tim worker

### Ngày 7
- [ ] Giới hạn tần suất ở tầng ứng dụng bổ sung cho Caddy
- [ ] Rà trùng lặp mã: so khớp token giữa mọi cặp bản nộp chính thức (thư viện `copydetect` hoặc tương đương), lưu `code_similarity`
- [ ] Thông báo: tạo, công bố, phát qua WebSocket

## Quy tắc bắt buộc

- Đội sở hữu thao tác của thí sinh lấy từ phiên đăng nhập đã kiểm tra membership. ID đối thủ hoặc đội đích của thao tác admin nhận từ request phải được kiểm tra quyền/nghiệp vụ riêng.
- Mã nguồn chỉ đội sở hữu và admin đọc được.
- Không xóa, không ghi đè `games`; kết quả hiện hành là bản ghi có `attempt` lớn nhất.

## Tiêu chí hoàn thành

- Kiểm thử tự động cho phân quyền: mọi endpoint thử với 4 vai trò (khách, thành viên đội khác, thành viên, admin).
- Kiểm thử tự động cho tính bảng xếp hạng và dựng nhánh.
- Giải giả lập 8 đội chạy từ bốc thăm đến chung kết mà không phải sửa DB bằng tay.

### Đăng ký tài khoản (contract 1.1.0)

Không cần seed tài khoản người chơi. UI P1 có nút Đăng ký. API tạo captain + đội riêng trong một transaction; không cần migration vì dùng bảng/index hiện có. Admin vẫn được tạo bằng CLI. `REGISTRATION_RATE_PER_HOUR=5` mặc định; giới hạn theo IP, Redis lỗi trả 503. Chưa xác minh email/chưa có reset mật khẩu. Mật khẩu request không được phản chiếu trong lỗi schema.

Tái sinh: `node contracts/build.mjs` (Node 24); kiểm tra: `tests/test_registration.py` cùng suite backend. Thay đổi ảnh hưởng consumer web và mock; runner/engine giữ nguyên wire format.

### Casual và phân bổ tài nguyên (contract 1.3.0)

Casual chạy trên trình duyệt: `app/casual.py` và `tests/test_casual.py` đã được gỡ, 5 operation `/casual/games` trả 404. Model `CasualGame` và migration `0002` được giữ để không xóa ván cũ; backend không đọc/ghi bảng này. `ottv2` vẫn trong dependency (test tích hợp runner/engine dùng); runtime backend không import engine nữa. Chuyển nó sang nhóm dev cần chạy `uv lock`, chưa làm trong đợt này.

`app/matches/admission.py` quyết định nhận trận đánh tập mới: 503 `SCRIMMAGE_PAUSED` (`queue_paused`, `tournament_load`, `scrimmage_backlog`) và 429 `SCRIMMAGE_LIMIT`, theo `SCRIMMAGE_MAX_ACTIVE_PER_TEAM` (2), `SCRIMMAGE_MAX_PENDING_GAMES` (12), `SCRIMMAGE_PAUSE_TOURNAMENT_JOBS` (1, 0 là tắt). Trận đã nhận không bị hủy hay chuyển hàng đợi. `/scrimmages/quota` và `/admin/queue` trả trạng thái nhận trận. Kiểm tra: `tests/test_scrimmage_admission.py`.
