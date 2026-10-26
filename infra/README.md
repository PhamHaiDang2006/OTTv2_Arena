# infra — Triển khai và vận hành

Docker Compose cho máy dev và VPS, cấu hình Caddy, sao lưu và kiểm tra tài nguyên. Hệ thống chạy trên **một VPS**; lý do, phân bổ CPU và RAM ở [architecture.md mục 8](../architecture.md#8-triển-khai). Quy trình vận hành chi tiết (sao lưu, khôi phục, nâng cấp, sự cố): [RUNBOOK.md](RUNBOOK.md).

## File

| File | Dùng cho |
| --- | --- |
| `docker-compose.dev.yml` | PostgreSQL, Redis, MinIO cho dev, bind `127.0.0.1` |
| `docker-compose.play.yml` | Ghép với dev: registry, build worker, worker giải, worker đánh tập trên máy local |
| `docker-compose.test.yml` | PostgreSQL/Redis tạm cho test backend (cổng 55432/56379, không có volume bền) |
| `docker-compose.vps1.yml` | Nhóm ứng dụng: `caddy`, `web-p1`, `web-p2`, `backend`, `scheduler`, `postgres`, `redis`, `minio`, `minio-backup` (profile `backup`) |
| `docker-compose.vps2.yml` | Nhóm thi đấu: `registry`, `build-worker`, `match-tournament-1..3`, `match-scrimmage-1` |
| `docker-compose.tunnel.yml`, `Caddyfile.tunnel` | Phục vụ web local qua Cloudflare Tunnel, API chạy trên host |
| `Caddyfile` | Định tuyến công khai của VPS |
| `.env.example`, `vps1.env.example`, `vps2.env.example` | Mẫu biến môi trường cho dev và hai nhóm Compose |
| `check_resources.py` | Kiểm tra CPU/RAM của worker trước khi bật |
| `backup/` | Sao lưu, khôi phục PostgreSQL; mirror MinIO ra kho ngoài |
| `minio/Dockerfile` | Build MinIO community từ source ở commit cố định |
| `start-local-api.ps1`, `start-local-play.ps1`, `demo_match.py` | Khởi động nhanh trên Windows và tạo một trận demo |
| `wireguard/` | Mẫu WireGuard, chỉ cần nếu tách nhóm thi đấu sang máy thứ hai |

## Dev trên máy cá nhân

Từ `infra/`:

```sh
cp .env.example .env        # thay giá trị mẫu, không commit .env
docker compose --env-file .env -f docker-compose.dev.yml up --build -d
docker compose --env-file .env -f docker-compose.dev.yml ps
docker compose --env-file .env -f docker-compose.dev.yml down   # giữ nguyên volume
```

- Cổng mặc định: PostgreSQL 5432, Redis 6379, MinIO 9000 (console 9001); đổi bằng `POSTGRES_PORT`, `REDIS_PORT`, `MINIO_PORT`, `MINIO_CONSOLE_PORT`. Chỉ dùng `down -v` khi thật sự muốn xóa dữ liệu.
- Khi chạy backend trực tiếp trên host, đổi hostname Docker trong `DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT_URL` thành `localhost`. Tạo bucket bằng `app.cli ensure-bucket` hoặc console MinIO.
- MinIO không còn phát hành image community nên `minio/Dockerfile` build từ source ở commit cố định. Đây là tiện ích cho dev, không phải bản phân phối được bảo trì.

Trên Windows với Docker Desktop:

- `start-local-api.ps1` tạo `infra/.env` với secret ngẫu nhiên nếu chưa có, bật PostgreSQL/Redis, migrate và chạy API nền ở `127.0.0.1:8000` (log `infra/.local-api.error.log`). Cần `backend/.venv`.
- `start-local-play.ps1` build image worker và bot, đẩy bot vào registry local để lấy digest, chạy `check_resources.py` rồi bật worker. Thêm `-SkipBuild` để bỏ qua bước build.
- `demo_match.py` tạo hai người chơi demo, nộp kit Python thật và yêu cầu một trận qua HTTP.

`docker-compose.play.yml` gọi API trên host qua `host.docker.internal` mà không khai báo `extra_hosts`, nên chỉ chạy sẵn trên Docker Desktop; trên Linux cần thêm `host.docker.internal:host-gateway`. Bố trí CPU local: bot giải CPU 0–1, phụ trợ 2–3; nên có từ 8 GiB RAM.

`docker-compose.tunnel.yml` phục vụ P1/P2 ở `127.0.0.1:8088` và proxy `/api/v1`, `/ws` tới API trên host, để mở ra Internet qua Cloudflare Tunnel (TLS kết thúc ở Cloudflare). Cần build trước image `ottv2-web-p1:local` và `ottv2-web-p2:local`.

## Triển khai một VPS

Gộp `docker-compose.vps1.yml` và `docker-compose.vps2.yml` thành một project, thêm override `docker-compose.single.yml`. Mọi service chung một mạng Docker nên worker gọi `backend`, `redis`, `minio` bằng tên service; không cần WireGuard.

### 1. Chuẩn bị máy

- Ubuntu 24.04, Docker Engine và Compose v2. Ở cả firewall của máy lẫn của nhà cung cấp, chỉ mở TCP 22 (giới hạn IP nếu được), 80 và 443.
- `DOMAIN` và `STORAGE_DOMAIN` trỏ về IP của VPS. Không có domain thì dùng `<ip-nối-bằng-gạch>.sslip.io` cho `DOMAIN` và một tên con như `s3.<ip-nối-bằng-gạch>.sslip.io` cho `STORAGE_DOMAIN`; Caddy tự lấy chứng chỉ Let's Encrypt. Vẫn cần HTTPS vì cookie refresh mặc định có cờ `Secure`.
- Đặt code ở `/srv/ottv2`. Registry chạy HTTP ở `127.0.0.1:5000`; Docker mặc định cho phép registry không TLS trên loopback.

### 2. Override `docker-compose.single.yml`

File này chưa có trong repo; tạo ở `infra/` với nội dung:

```yaml
# Gộp vps1 + vps2 trên một máy; image được build ngay trên VPS.
services:
  backend:
    pull_policy: never
    environment:
      FORWARDED_ALLOW_IPS: "*"   # để giới hạn đăng ký/đăng nhập thấy IP thật thay vì IP của Caddy
  scheduler: {pull_policy: never}
  web-p1: {pull_policy: never}
  web-p2: {pull_policy: never}
  build-worker: {pull_policy: never}
  match-tournament-1: {pull_policy: never}
  match-scrimmage-1: {pull_policy: never}
  match-tournament-2: {pull_policy: never, profiles: ["8cpu"]}
  match-tournament-3: {pull_policy: never, profiles: ["8cpu"]}
```

`FORWARDED_ALLOW_IPS: "*"` an toàn ở đây vì cổng 8000 của backend chỉ bind loopback và mạng Docker. Máy 4 vCPU chạy một worker giải và một worker đánh tập; máy 8 vCPU bật thêm profile `8cpu`.

### 3. File môi trường

Tạo `infra/.env` (mode 600) bằng cách ghép `vps1.env.example` với `vps2.env.example` (bỏ dòng trùng `WORKER_API_TOKEN`, `S3_BUCKET`), rồi sửa:

| Biến | Giá trị cho một VPS |
| --- | --- |
| `COMPOSE_PROJECT_NAME` | `ottv2` (thêm mới), để `backup/postgres-backup.sh` vốn chỉ truyền `vps1.yml` vẫn tìm đúng project |
| `VPS1_WG_IP` | `127.0.0.1`: backend, Redis, MinIO chỉ bind loopback |
| `VPS2_REDIS_URL` | `redis://:<REDIS_PASSWORD>@redis:6379/0` |
| `VPS2_INTERNAL_API_BASE_URL` | `http://backend:8000/api/v1` |
| `VPS2_S3_ENDPOINT_URL` | `http://minio:9000` |
| `VPS1_BACKEND_IMAGE`, `VPS1_P1_IMAGE`, `VPS1_P2_IMAGE`, `VPS1_MINIO_IMAGE`, `VPS2_WORKER_IMAGE` | Tag image build ở bước 4 |
| `RUNNER_IMAGE_PYTHON`, `RUNNER_IMAGE_CPP`, `RUNNER_BUILD_IMAGE_CPP` | Digest image bot trong registry `127.0.0.1:5000` (bước 4) và image compiler C++ đã kiểm chứng |
| `VPS2_AUX_CPUSET`, `VPS2_BUILD_CPUSET` | `2-3` (máy 4 vCPU) |
| `VPS2_TOURNAMENT_1_BLUE`, `VPS2_TOURNAMENT_1_RED` | `0`, `1` |
| `VPS2_SCRIMMAGE_BLUE`, `VPS2_SCRIMMAGE_RED` | `2`, `3` |
| `ALLOW_DEVELOPMENT_TOURNAMENTS` | `true` chỉ khi muốn demo giải với luật `dev-v1` |
| `VPS1_MC_IMAGE`, `MINIO_MIRROR_*`, `MINIO_BACKUP_*` | Phải khác rỗng kể cả khi không dùng profile `backup`, nếu không Compose từ chối nội suy |

Secret: đặt giá trị ngẫu nhiên chỉ gồm chữ và số (khỏi phải URL-encode) cho `POSTGRES_PASSWORD` (khớp `DATABASE_URL`), `REDIS_PASSWORD` (khớp `VPS2_REDIS_URL`), `MINIO_ROOT_*`, `JWT_SECRET`, `WORKER_API_TOKEN`. Cách đơn giản là dùng tài khoản root MinIO cho cả `S3_*` của backend và `WORKER_S3_*` của worker; an toàn hơn là tạo hai tài khoản S3 riêng chỉ có quyền trên bucket. Không đưa secret vào biến `VITE_*`.

### 4. Build image

Từ `/srv/ottv2`:

```sh
docker build -f backend/Dockerfile -t ottv2-backend:local .
docker build --target p1 -f web/Dockerfile -t ottv2-web-p1:local .
docker build --target p2 -f web/Dockerfile -t ottv2-web-p2:local .
docker build -f runner/Dockerfile.engine -t ottv2-worker:local .
docker build -f engine/Dockerfile.bot -t ottv2-python:local .
docker build -t ottv2-minio:local infra/minio
```

Image bot phải được tham chiếu bằng digest. Từ `infra/`, đặt tạm `RUNNER_IMAGE_*` một giá trị bất kỳ để Compose nội suy được, rồi:

```sh
alias dc='docker compose --env-file .env -f docker-compose.vps1.yml -f docker-compose.vps2.yml -f docker-compose.single.yml'
dc up -d registry
docker tag ottv2-python:local 127.0.0.1:5000/ottv2-python:local
docker push 127.0.0.1:5000/ottv2-python:local
docker image inspect --format '{{index .RepoDigests 0}}' 127.0.0.1:5000/ottv2-python:local
```

Ghi digest vào `.env`. Mỗi lần build lại image bot, digest đổi (kể cả khi mọi layer đều cache), nên phải cập nhật `.env` và tạo lại worker.

### 5. Khởi động

```sh
dc config --quiet
python3 check_resources.py --env-file .env -f docker-compose.vps1.yml -f docker-compose.vps2.yml -f docker-compose.single.yml
dc up -d postgres redis minio
# Tạo bucket S3_BUCKET (và tài khoản S3 riêng nếu dùng) trước khi chạy API
dc run --rm --no-deps backend python -m app.cli migrate < /dev/null
dc up -d
dc ps
```

`check_resources.py` chỉ tính worker, bot, compiler và registry (bố trí trên cần khoảng 6.25 GiB gồm 2 GiB dự phòng), không tính PostgreSQL, MinIO hay backend. `< /dev/null` cần khi chạy lệnh qua `ssh ... 'bash -s'`, nếu không `docker compose run` nuốt phần còn lại của script từ stdin. Tạo admin: `dc exec backend python -m app.cli create-admin --email ...` rồi nhập mật khẩu khi được hỏi.

Kiểm tra sau khi bật: trang P1 và `/admin/` mở được kể cả deep link; `/api/v1` và `/ws` hoạt động; `/api/v1/internal/*` trả 404 từ ngoài; URL replay ký sẵn tải được trong trình duyệt; quét cổng từ ngoài chỉ thấy 22, 80, 443.

### Cập nhật phiên bản

1. `bash backup/postgres-backup.sh` và chép bản sao ra ngoài VPS.
2. Tạm dừng các hàng đợi trong P2 → Hàng đợi, đợi việc đang chạy xong và callback đã gửi.
3. Cập nhật code trong `/srv/ottv2`, build lại image (bước 4), cập nhật digest bot.
4. `dc run --rm --no-deps backend python -m app.cli migrate < /dev/null`, rồi `dc up -d`.
5. Kiểm tra nhịp tim worker trong P2, mở lại hàng đợi.

Sao lưu PostgreSQL mỗi giờ khi có giải, ví dụ cron `0 * * * * cd /srv/ottv2/infra && bash backup/postgres-backup.sh`. Khôi phục luôn vào database mới, xem [RUNBOOK.md](RUNBOOK.md) mục 4.

## Định tuyến và lưu ý an toàn

- Caddy lấy TLS cho `DOMAIN` và `STORAGE_DOMAIN`. `/` tới P1, `/admin/` tới P2, `/api/v1/*` và `/ws` tới backend (khớp trước catch-all nên lỗi 404 của API không bị đổi thành trang SPA). `STORAGE_DOMAIN` proxy tới MinIO để trình duyệt tải URL ký sẵn; `S3_PUBLIC_ENDPOINT_URL` phải là `https://STORAGE_DOMAIN`.
- `/internal`, `/api/v1/internal` và mọi đường dẫn con trả 404 ở Caddy; worker gọi backend trực tiếp trong mạng Docker bằng `WORKER_API_TOKEN`.
- Caddy giới hạn body 2 MiB; backend vẫn là nơi kiểm tra ZIP (1 MiB) và giới hạn tần suất. Caddy không có rate limit.
- Bucket cần CORS cho đúng origin của web. Replay nén phải có `Content-Type: application/json` và `Content-Encoding: gzip`.
- Worker mount `/var/run/docker.sock`, tương đương quyền root trên VPS, và trên một VPS máy này cũng giữ dữ liệu. Chỉ chạy image worker build từ repo, không cho bot có mạng; xem [architecture.md mục 6](../architecture.md#6-sandbox).
- Build worker bind-mount `/var/lib/ottv2/work` cùng đường dẫn trên host và trong container; không chuyển sang tmpfs.
- Script shell phải giữ kết dòng LF (`.gitattributes` đã ép).

## Kiểm tra cấu hình

```sh
docker compose --env-file .env.example -f docker-compose.dev.yml config --quiet
docker compose --env-file vps1.env.example -f docker-compose.vps1.yml config --quiet
docker compose --env-file vps2.env.example -f docker-compose.vps2.yml config --quiet
python -m unittest discover -s infra/tests -v   # từ repo root
```

Các lệnh này chỉ kiểm cú pháp và nội suy Compose, không chứng minh service khởi động được hay đúng hành vi.
