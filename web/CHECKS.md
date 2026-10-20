# Bàn giao web — 2026-10-20

## Phạm vi

P1, P2, replay viewer, shared auth/HTTP/WS/schema, upload progress, source highlighting,
test workspace, Docker targets và workflow CI. Mã mới nằm trong `web/`; workflow ở
`.github/workflows/web.yml`, `.gitignore` bỏ qua replay được sinh để test.
README ba phần đã trỏ về hướng dẫn workspace.

Contract **1.0.0**, engine **1.0.0**, **dev-v1**. Nguồn contract của checkout khi bắt đầu:
commit `c20d46a`. Không sửa machine contract, generated artifacts, backend, runner hoặc engine.
Consumer dùng các file generated có sẵn; không thêm wire DTO thứ hai.

## Kết quả đã chạy

| Kiểm tra | Kết quả |
| --- | --- |
| `npm run typecheck` | Đạt |
| `npm test` | 92 tests, 6 files đạt |
| `npm run build` | P1 và P2 đạt; base lần lượt `/` và `/admin/` |
| `npm run format:check` | Đạt |
| `npm audit` | 0 advisory tại thời điểm kiểm tra |
| `node contracts/build.mjs --check` | Đạt, 85 definitions / 65 operations / 133 cases |
| `python contracts/validate.py` | Đạt, OpenAPI/schema/fixtures/board/draw |
| `python contracts/test_mock.py` | 5 tests đạt |
| `python web/tests/generate_engine_replays.py` | 100 replay sinh bằng public engine API |
| Engine → viewer | FEN cuối khớp 100 ván sinh thêm và 6 fixture cố định; 1000 FEN round-trip |
| Timeline dài | Tua đầu/cuối fixture hiệu năng 600 ply đạt; không coi đây là luật cho phép 600 ply |
| Docker target `p1`, `p2` | Build đạt trên Linux Node 22/nginx unprivileged |
| Static containers `--read-only --tmpfs /tmp` | P1 `/games/test` và P2 `/admin/games/test` trả HTML 200; API và asset không tồn tại trả 404 |

Node local 24.21.0, npm 11.19.0, TypeScript 5.9.3, React 18.3.1, Vite 6.4.4,
Vitest 4.1.11. Các version cụ thể khác được pin bằng `package-lock.json`.
Windows sandbox chặn rename cache tạm Vitest và làm asyncio engine treo; các lần kiểm tra
thành công đã chạy ngoài sandbox. Đây là giới hạn môi trường công cụ, không phải test được bỏ qua.

Test đáng chú ý: 65 response fixtures validate bằng schema chung; refresh đồng thời chỉ gọi
một lần; giữ Idempotency-Key khi replay sau 401; không retry mutation khi mất mạng; refresh
thất bại xóa session; 409 không hiện thành công; CSV errors trong 201 báo lỗi; subscribe team
sau auth.ok; event dedup và refetch sau reconnect; xin lại signed URL sau 403; P1 không lấy
stderr admin; chặn ZIP quá cỡ; replay hỏng/0 nước/capture/tua ngược không mutate input.

## Kiểm tra qua trình duyệt

Đã dùng in-app Chromium, với cả giao diện hẹp khoảng 600px và desktop khoảng 1260px:

- Mock HTTP chuẩn: login captain → trang đội → chi tiết trận → tải replay qua signed URL,
  hiển thị ván 0 nước và kết quả; bố cục màn hình hẹp không làm mất chức năng.
- Backend FastAPI thật + PostgreSQL/Redis trong `infra/docker-compose.test.yml` riêng biệt:
  login admin → queue → xác nhận tạm dừng queue build → GET phản ánh trạng thái mới →
  audit hiển thị `queue.control`.
- Đăng xuất admin, login captain trên P2: bị chặn với thông báo không có quyền.
- P1 dùng API thật: khôi phục session bằng cookie, trang đội và quota/opponent/empty-state.
  Đội seed chưa có bot ready nên danh sách opponent rỗng và nút đánh tập bị disable.
- Router sau cập nhật dependency đã kiểm tra lại bằng login thật.

Ảnh kiểm chứng: [admin queue](evidence/admin-queue.png).
Dữ liệu dùng cho kiểm thử là tài khoản seed local, không dùng tài khoản hoặc dữ liệu thi thật.
Lệnh seed lần đầu ghi thành công nhưng print Unicode lỗi trên console Windows; dữ liệu đã
được xác nhận qua login và API. Không sửa CLI backend trong phạm vi web.

## Chưa nghiệm thu

- Chưa chạy xuyên suốt browser → upload → MinIO/registry → worker Docker → callback →
  replay và một giải 8 đội hoàn chỉnh trong lần làm web này. Browser đã kiểm tra API thật
  ở các luồng nêu trên; mock không chứng minh được pipeline đó.
- Chưa chạy Safari, Firefox và thiết bị điện thoại thật. Test 600 ply là kiểm tra tự động
  trong jsdom, chưa đo frame-time trên điện thoại cấu hình thấp.
- Chưa triển khai HTTPS/Caddy lên VPS, chưa kiểm tra CORS signed URL với domain production.
- Audit API hiện không có query khoảng ngày; UI chỉ cung cấp actor/action như contract.
- Workflow được thêm nhưng chưa được GitHub Actions chạy từ PR.

Không coi các test trên là chứng nhận sẵn sàng tổ chức giải chính thức. Profile dev-v1
vẫn cần ban tổ chức xác nhận.

## Phụ thuộc và review

Merge nền tảng contract/engine fixtures và backend/runner/infra tích hợp trước web.
C review request/response, Origin/cookie, quyền và workflow giải; A review viewer với engine;
B review image, static routing, Caddy và storage CORS. Không cần migration hay thay callback.
Không push, merge, publish image hoặc deploy trong lượt này.
