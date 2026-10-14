# infra — Hạ tầng và triển khai

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
- Quét cổng từ bên ngoài chỉ thấy 22, 80, 443 trên VPS 1 và 22 trên VPS 2.
