# infra — Hạ tầng và triển khai

## Hợp đồng tích hợp và hướng dẫn cho AI

Đọc [AGENTS.md](../AGENTS.md), [hợp đồng tích hợp](../integration.md) mục 7–9 và README backend/runner/web. B sở hữu Compose, env mẫu, CI và điều phối smoke test.

- Không tự đổi cổng/tên biến/endpoint mà không cập nhật consumer. [.env.example](.env.example) đã có biến chuẩn; [contracts](../contracts/README.md) có validator/mock và CI trong .github/workflows/contracts.yml. Compose vẫn cần triển khai.
- Khi tạo Compose, ghi bảng service → hostname nội bộ → container port → host port → healthcheck → volume. Tách URL trình duyệt với URL DNS Docker.
- Public gateway route /api/v1 đến backend, /ws nâng cấp WebSocket; chặn /api/v1/internal/*. Internal API chỉ mở qua WireGuard và vẫn kiểm tra token.
- P2 phục vụ dưới /admin, P1 ở /; cấu hình SPA fallback không nuốt /api/v1 hoặc /ws. D phải đối chiếu Vite base/router basename với reverse proxy.
- C chạy migration một lần trước backend; healthcheck liveness không đồng nghĩa readiness DB/Redis/storage. Không khởi động worker khi dependency chưa sẵn.
- Storage gzip phải có đúng Content-Type/Content-Encoding và CORS để browser dùng URL ký sẵn. S3 public endpoint không được là hostname chỉ container hiểu.
- Secret chỉ trên backend/worker phù hợp; không đưa vào VITE_* hoặc log CI. VPS2 không có DATABASE_URL/JWT_SECRET.
- Kiểm tra cấu hình rate limit thực tế của bản Caddy được chọn; nếu cần module phải ghi cách build, hoặc đặt enforcement ở backend. Không giả định directive có sẵn.
- Mở UDP WireGuard trên máy làm endpoint theo cấu hình tunnel; tiêu chí quét cổng phải phân biệt TCP/UDP. Không dùng “chỉ cổng 22” để vô tình chặn tunnel.

### Chạy và tích hợp

Khi tạo file Compose, thêm lệnh dev up/down không xóa dữ liệu, migrate/seed, start worker, xem log và smoke test; nêu cwd và env file rõ ràng. Hiện các đường dẫn Compose trong kế hoạch chưa phải file đã có.

CI tối thiểu: validate hợp đồng/fixture; unit test package bị ảnh hưởng; typecheck/build web; kiểm tra producer/consumer cho thay đổi ranh giới. Smoke test có 2 đội + admin: login → upload ZIP → ready → active bot → scrimmage 2 game → replay. Chạy test lỗi worker/callback riêng; không dùng database thật của giải.

Trước merge: compose config hợp lệ, startup từ môi trường sạch, healthcheck, URL ký sẵn trong browser, P1/P2 deep link, WS và internal route isolation. Ghi lệnh/kết quả thật cùng giới hạn môi trường; backup phải có lần restore thử được xác nhận. B điều phối, chủ phần chịu trách nhiệm sửa lỗi phần mình.


**Phụ trách:** B · **Dự phòng:** C

## Cấu trúc dự kiến

```
infra/
├── docker-compose.dev.yml     # PostgreSQL, Redis, MinIO cho máy phát triển
├── docker-compose.vps1.yml    # Caddy, web, backend, PostgreSQL, Redis, MinIO
├── docker-compose.vps2.yml    # build worker, match worker ×4, registry
├── Caddyfile
├── wireguard/                 # Mẫu cấu hình đường hầm giữa hai VPS
├── backup/                    # Script sao lưu và khôi phục
├── .env.example
└── RUNBOOK.md                 # Xử lý sự cố trong ngày thi
```

## Máy chủ

| Máy | Cấu hình | Mở ra Internet |
| --- | --- | --- |
| VPS 1 | 2 vCPU, 4 GB RAM, 80 GB SSD | Cổng 80, 443 (Caddy), 22 (SSH chỉ bằng khóa) |
| VPS 2 | 8 vCPU, 8 GB RAM, 100 GB SSD | Chỉ cổng 22 và WireGuard |

## Nhiệm vụ

### Ngày 1
- [ ] Khởi tạo repo, nhánh bảo vệ `main`, CI chạy kiểm thử của `engine/` và `backend/` mỗi Pull Request
- [ ] `docker-compose.dev.yml` và `.env.example`
- [ ] Thuê 2 VPS, tạo người dùng triển khai, tắt đăng nhập SSH bằng mật khẩu, bật tường lửa

### Ngày 2
- [ ] WireGuard giữa hai VPS; Redis, MinIO, endpoint `/internal/*` chỉ nghe trên địa chỉ WireGuard
- [ ] Trỏ tên miền về VPS 1

### Ngày 7
- [ ] `docker-compose.vps1.yml`, `docker-compose.vps2.yml`, triển khai lần đầu
- [ ] Caddy: TLS tự động, giới hạn tần suất (10 lần nộp mỗi đội mỗi giờ, 100 yêu cầu đọc mỗi phút mỗi IP), giới hạn kích thước tải lên 2 MB
- [ ] Sao lưu PostgreSQL mỗi giờ, giữ 48 bản; đồng bộ MinIO ra kho ngoài mỗi ngày
- [ ] Giám sát và cảnh báo qua Telegram hoặc Discord:
    - Hàng đợi dài quá 50 việc
    - Tỷ lệ `INFRA_ERROR` quá 2%
    - Đĩa còn dưới 20%
    - Worker mất nhịp tim quá 5 phút
    - Backend trả lỗi 5xx liên tục
- [ ] Dọn image bot cũ: giữ image của bản nộp chính thức và 5 bản mới nhất mỗi đội

### Ngày 8
- [ ] **Diễn tập khôi phục**: xóa DB trên máy thử, khôi phục từ bản sao lưu, đo thời gian
- [ ] Viết `RUNBOOK.md`: VPS 2 chết, đĩa đầy, hàng đợi kẹt, cần chạy lại một vòng

## Tiêu chí hoàn thành

- Triển khai lại toàn bộ hệ thống từ đầu bằng một lệnh cho mỗi máy, trong dưới 30 phút.
- Khôi phục từ bản sao lưu thành công và mất dữ liệu không quá 1 giờ.
- Quét TCP từ bên ngoài chỉ thấy 22, 80, 443 trên VPS 1 và 22 trên VPS 2; UDP WireGuard mở trên endpoint theo cấu hình tunnel, dịch vụ nội bộ không lộ ra Internet.
