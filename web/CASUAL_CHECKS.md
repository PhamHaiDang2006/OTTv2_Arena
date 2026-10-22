# Bàn giao Casual / Arena — 2026-10-22

## Phạm vi

- P1 `/`: chọn Casual hoặc Arena; tổng quan Arena chuyển `/arena`, giữ các route chức năng và P2.
- `web/src/casual.tsx`, `style.css`, `main.tsx`, `ui.tsx`: lobby, bàn tương tác, chọn bot/màu, lịch sử, tiếp tục ván, xác nhận đầu hàng.
- `backend/app/casual.py`, `models.py`, `main.py`, migration `0002`: API và lưu ván riêng, xác thực/quyền sở hữu, chống nước trùng/cạnh tranh. Không tạo trận/job/điểm Arena.
- `engine/ottv2/__init__.py`: public export outcome; backend pyproject/uv.lock/Dockerfile cài engine từ cùng checkout.
- `contracts/build.mjs` và artifacts sinh: HTTP 1.2.0, 91 definitions, 71 operations, 149 fixtures. Engine 1.0.0, job/callback/replay và dev-v1 giữ nguyên.
- README/architecture/integration/behavior cập nhật cách chạy và ranh giới A/C/D; infra/start-local-api.ps1 nhận version 1.2.0.

## Kiểm tra đã chạy

Windows, Python 3.12.14, Node 24.21, uv 0.13.1. Python đặt PYTHONUTF8=1.

| Lệnh | Kết quả |
| --- | --- |
| `node contracts/build.mjs --check` | Đạt, artifacts khớp nguồn |
| `backend/.venv/Scripts/python.exe contracts/validate.py` | Đạt 149 fixture cases, refs, board/draw |
| `backend/.venv/Scripts/python.exe contracts/test_mock.py` | 5 test đạt, gồm 71 operation |
| `backend/.venv/Scripts/python.exe -m ruff check backend/app backend/tests backend/migrations backend/scripts` | Đạt |
| `cd backend; .venv/Scripts/python.exe -m pytest -q` | **224 passed**, 7 deprecation warnings có sẵn từ Starlette/httpx/cookie |
| `backend/.venv/Scripts/python.exe -m unittest discover -s engine/tests -q` | 18 test đạt |
| `backend/.venv/Scripts/python.exe -m unittest discover -s runner/tests -q` | 23 test đạt |
| `cd web; npm.cmd test` | **107 passed** |
| `cd web; npm.cmd run build` | Typecheck + P1/P2 build đạt |
| `cd web; npm.cmd run format:check` | Đạt |
| `docker build -f backend/Dockerfile -t ottv2-backend:casual-check .` | Build thành công từ lockfile, gồm engine |
| `git diff --check` | Đạt |

Backend tests dùng PostgreSQL/Redis riêng trong docker-compose.test.yml (database ottv2_test, Redis DB15), không dùng dữ liệu người chơi. Mock HTTP ban đầu bị sandbox chặn socket WinError10013; chạy lại với quyền localhost đã đạt.

## Thử tích hợp thật

API local đã migrate 0001 → 0002 và khởi động với contract 1.2.0, giữ tài khoản admin hiện có. Qua trình duyệt đã chọn Casual, tạo ván Xanh/random, đi c3d4, nhận nước bot, tải lại vẫn giữ lịch sử, mở và hủy xác nhận đầu hàng; tạo ván Đỏ/greedy thấy bot Xanh đi trước và bàn xoay đúng hướng. Ảnh tại [evidence/casual.png](evidence/casual.png).

Backend tests kiểm tra hoàn thành ván theo engine, chiếm mục tiêu không cho bot đi tiếp, đầu hàng, quyền chủ ván, dữ liệu giả mạo, replay idempotency và hai request cùng lượt chỉ một request thành công. Test tích hợp cũ của Arena nằm trong bộ 224 test đã đạt.

## Phụ thuộc và giới hạn

Merge public engine export + contract + backend + web cùng nhau, cài lại dependencies rồi migrate trước khi chạy API mới. Chưa commit/push. Không chạy lại trận bot Arena bằng Docker trong lượt này; đã chạy bộ tích hợp backend/runner/engine và không thay đổi giao thức job/replay. Không có rank/matchmaking/PvP, đồng hồ Casual hay bot do người chơi tải lên; dev-v1 vẫn là luật phát triển. Bot random/greedy chỉ để làm quen. Đăng ký vẫn dùng form đội hiện có; đội pending được chơi Casual ngay.
