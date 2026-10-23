# Khôi phục branch game — 2026-10-23

Commit `0e8406d` đã ghi cả dấu conflict từ stash trong web, trên nền contract
1.2.0 còn thiếu commit `abddf6a` của backend. Bản sửa giữ lịch sử hiện tại,
khôi phục nội dung nền tảng từ `backend` và các file tài nguyên/UI từ stash
`On backend: cap nhap UI/QOL`. Không tạo merge commit, không push, không xóa stash.

Phạm vi: backend/contracts/engine/starter-kits và phần web liên quan được đưa về
nền 1.3.0; infra/runner giữ cách ly tài nguyên; UI/QOL được khôi phục đầy đủ.
Generated contracts lấy nguyên từ commit nguồn, không chỉnh tay. Không đổi
engine 1.0.0, job/callback/replay v1 hoặc luật dev-v1.

Kiểm tra đã chạy:

- Web: 127 tests, TypeScript và build cả P1/P2 đạt.
- `node contracts/build.mjs --check`: đạt.
- Validator: 88 definitions, 66 operations, 141 fixture cases đạt.
- Mock HTTP: 5 tests đạt (chạy ngoài sandbox để truy cập localhost).
- Infra: 6 tests đạt; runner build resources: 2 tests đạt.
- Engine local CLI: 5 tests đạt.
- Compose local (dev + play) và VPS2: config --quiet đạt.
- Không còn dấu conflict; git diff --check đạt.

Không chạy lại toàn bộ backend integration cần PostgreSQL/Redis test riêng;
không khởi động lại dịch vụ đang chạy hoặc thay dữ liệu người dùng. UI phục hồi
đúng nội dung đã kiểm tra trình duyệt ở UI_POLISH_CHECKS.md, không thiết kế mới.

Khi commit phải đứng ở repo root và dùng `git add -A` để bao gồm file mới và
việc gỡ API Casual cũ; chỉ add trong web sẽ thiếu nền tảng. Bản sửa chưa commit.
