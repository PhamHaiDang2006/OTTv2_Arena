# Bàn giao tự đăng ký tài khoản

## Sửa môi trường local sau bàn giao

Web 5173/5174 đang chạy nhưng không có API 8000 hoặc PostgreSQL/Redis; gọi
`/api/v1/health` qua Vite trả 500. Đã thêm `infra/start-local-api.ps1` để tạo cấu hình
local nếu chưa có, bật database/Redis dev bền, migrate và khởi động API nền.
Script chạy lại thành công và dùng lại API khỏe, không tạo thêm tiến trình API.
Secret, PID và log không được commit. Web giải thích rõ hơn lỗi backend 500/502/503/504.

Đã kiểm tra HTTP qua proxy thật `http://127.0.0.1:5173/api/v1` với tài khoản kiểm tra
tự sinh (tên đội `Kiem tra dang ky tu dong`): health ok, register 201, team pending
với một thành viên, refresh 200, logout 204, login lại 200, logout 204. Tài khoản kiểm
tra còn trong database dev, không có bot. Để API/PostgreSQL/Redis chạy phục vụ người dùng.
Không bật MinIO/registry/scheduler/runner trong lần sửa kết nối đăng ký này.

## Thay đổi

- Contract 1.1.0: Register/email/password/team_name, POST /auth/register, Auth 201,
  fixture hợp lệ và lỗi, OpenAPI/type/client operation tái sinh bằng Node 24.
- Backend: tạo captain + đội pending + membership + refresh session + audit trong
  một transaction; unique email không phân biệt hoa thường xử lý đăng ký đồng thời.
  Hash Argon2id, Origin allowlist, hạn mức IP, lỗi schema không phản chiếu mật khẩu.
- Đội pending được nộp bot, chọn bot và đánh tập; đối thủ vẫn phải có bot ready,
  không bị khóa/loại. Giải chỉ lấy đội approved. Không cần migration.
- Web: form đăng ký, xác nhận mật khẩu, tự đăng nhập khi thành công; P2 không có
  nút đăng ký. Login tách sang src/auth-page.tsx. Không lưu token/password vào storage.
- Tài liệu architecture/integration/README/backend/web và behavior cập nhật.
  Engine/runner/starter kits không sửa implementation. Không push/merge.

## Kết quả kiểm tra

- `node contracts/build.mjs --check`: đạt (86 definitions, 66 operations, 138 cases).
- `backend/.venv/Scripts/python.exe contracts/validate.py`: đạt.
- `backend/.venv/Scripts/python.exe contracts/test_mock.py`: 5 tests đạt, bao gồm 66 operations.
- Từ backend với PostgreSQL/Redis test riêng:
  `python -m pytest -q tests/test_registration.py tests/test_auth.py tests/test_teams_idempotency.py tests/test_contract_surface.py`
  đạt 35 tests; sau khi thêm ca race/Redis lỗi, chạy
  `python -m pytest -q tests/test_registration.py -k "concurrent or unavailable"`: 2 tests đạt.
  Tổng 37 tests backend liên quan đạt, mọi response được kiểm theo contract.
- `npm test`: 97 tests / 7 files đạt. `npm run build`: P1/P2 + typecheck đạt.
- `npm run format:check`, Ruff cho backend/app + test_registration.py,
  `git diff --check`: đạt.
- Trình duyệt Chromium: mở login → Đăng ký, đủ bốn trường và nút chuyển về login;
  ảnh tại evidence/registration.png. Luồng submit/session được kiểm qua UI test và
  API với PostgreSQL/Redis thật; chưa submit đăng ký từ browser tới API thật trong lượt này.

Sandbox Windows chặn socket localhost/cache test; các kiểm tra mock, Vitest và
backend thành công dùng quyền chạy ngoài sandbox. Docker dùng compose.test với
DB tạm và Redis DB 15, không dùng database phát triển của người dùng.

## Giới hạn và tích hợp

Chưa có xác minh email, quên mật khẩu, hoặc mã mời gia nhập đội. Mỗi tài khoản mới
có một đội riêng. Chưa chạy lại toàn bộ suite backend hoặc pipeline Docker bot/replay
trong lượt này. Đây không phải nghiệm thu toàn bộ hệ thống thi đấu.

Merge backend + web + contracts 1.1.0 cùng nhau, khởi động lại backend và build/restart
web. `REGISTRATION_RATE_PER_HOUR` mặc định 5/IP/giờ, Redis lỗi trả 503. Sau mất response
đăng ký, người dùng thử đăng nhập; không tự retry tạo tài khoản. Admin vẫn dùng CLI.
