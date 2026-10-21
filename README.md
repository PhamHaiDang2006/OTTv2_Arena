# OTTv2 Arena

## Làm việc với bốn người dùng AI

Mỗi phiên AI đọc [AGENTS.md](AGENTS.md), [architecture.md](architecture.md), [integration.md](integration.md), [project_plan.md](project_plan.md) và README của folder phụ trách. Không giả định AI biết cuộc trao đổi của người khác.

Phân công A/B/C/D hiện hành được giữ: A làm engine + viewer; B làm runner + starter kits + infra; C làm backend; D làm P1/P2 và workspace web. Nếu đổi phân công, cập nhật đồng thời các README và lịch trước khi giao việc.

Nền tảng dùng ngay nằm ở [contracts/README.md](contracts/README.md): OpenAPI, JSON Schema, dữ liệu mẫu, type Python/TypeScript, mock HTTP và kiểm tra tự động. `integration.md` là bản đồ tích hợp. Backend/engine/worker/web và Compose bên dưới vẫn cần triển khai. Profile `dev-v1` thống nhất luật tạm để làm thử, chưa phải luật thi đấu chính thức.

Mẫu giao việc:

```text
Đọc AGENTS.md, contracts/README.md và các tài liệu được yêu cầu. Tôi phụ trách <folder>.
Thực hiện <nhiệm vụ> theo contract v1.1.0, profile dev-v1 và commit <commit>.
Đối chiếu với <folder liên quan>; không tự đoán quyết định còn mở.
Bàn giao thay đổi, lệnh kiểm tra đã chạy, kết quả và phụ thuộc còn thiếu.
```

Nền tảng thi đấu lập trình kiểu Battlecode cho trò chơi **OTTv2** (Búa – Bao – Kéo trên bàn 9x9). Các đội nộp bot, hệ thống chạy trận tự động trong sandbox, và ban tổ chức điều hành một giải 20 đội thể thức World Cup.

- **P1 – Cổng thí sinh**: đăng nhập, nộp bot, đánh tập, xem replay, xem bảng đấu.
- **P2 – Cổng quản trị**: quản lý đội, kiểm tra code, bốc thăm, điều hành giải, chạy lại trận.

## Tài liệu chính

| Tệp | Nội dung |
| --- | --- |
| [project_plan.md](project_plan.md) | Mục tiêu, phạm vi, mốc, phân công 4 người trong 8 ngày |
| [architecture.md](architecture.md) | Kiến trúc đầu cuối, mô hình dữ liệu, các quyết định thiết kế |

## Cấu trúc thư mục

```
ottv2-arena/
├── README.md
├── project_plan.md
├── architecture.md
├── engine/              # Trọng tài OTTv2: luật chơi, đồng hồ, ghi replay      (A)
├── runner/              # Sandbox, build worker, match worker                  (B)
├── starter-kits/        # Bộ khởi động cho thí sinh: Python, C++, Java, JS      (B)
├── backend/             # API REST + WebSocket, DB, hàng đợi, logic giải đấu    (C)
├── web/
│   ├── p1-participant/  # Cổng thí sinh                                       (D)
│   ├── p2-admin/        # Cổng quản trị                                       (D)
│   └── replay-viewer/   # Trình phát replay dùng chung cho P1 và P2           (A)
└── infra/               # Docker Compose, Caddy, triển khai VPS, backup        (B)
```

Mỗi thư mục có một `README.md` mô tả nhiệm vụ, người phụ trách, giao diện với các phần khác và tiêu chí hoàn thành.

## Công nghệ

| Lớp | Lựa chọn |
| --- | --- |
| Engine, worker, backend | Python 3.12, FastAPI, SQLAlchemy, Alembic |
| Hàng đợi | Redis 7 (RQ) |
| Cơ sở dữ liệu | PostgreSQL 16 |
| Lưu trữ tệp | MinIO (tương thích S3) |
| Giao diện | React 18 + Vite + TypeScript |
| Hạ tầng | 2 VPS, Docker Compose, Caddy |

## Quy ước làm việc

- Nhánh chính `main` luôn chạy được. Mỗi việc làm trên nhánh `ten-nguoi/mo-ta-ngan`, mở Pull Request, ít nhất một người khác duyệt.
- Commit theo dạng `engine: thêm luật ăn quân`, tiền tố là tên thư mục.
- Đứng máy 15 phút lúc 9:00 mỗi ngày: hôm qua xong gì, hôm nay làm gì, đang vướng gì.
- Hợp đồng giao tiếp giữa các phần (giao thức bot, định dạng replay, API) nằm trong `architecture.md`. Muốn đổi thì sửa tài liệu trước, báo cả nhóm, rồi mới sửa code.

## Chạy môi trường phát triển

```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.dev.yml up -d   # PostgreSQL, Redis, MinIO
```

Hướng dẫn chi tiết cho từng phần nằm trong README của thư mục tương ứng.
