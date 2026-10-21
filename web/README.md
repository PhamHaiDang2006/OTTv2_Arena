# Web OTTv2 Arena

Implementation React 18 + TypeScript cho cổng thí sinh **P1**, cổng quản trị **P2** và package
`@ottv2/replay-viewer`. Hai bản build dùng chung session, API client, schema validator và UI.
Contract **1.1.0**, engine **1.0.0**, profile **dev-v1** chưa phải luật giải chính thức.

## Chạy

Yêu cầu Node 22+, npm. Từ `web/`:

```sh
npm ci
npm run dev          # http://127.0.0.1:5173/
npm run dev:admin    # terminal thứ hai: http://127.0.0.1:5174/admin/
npm run typecheck
npm test
npm run build        # dist/p1 và dist/p2
npm run format:check
```

Vite proxy HTTP `/api` và WebSocket `/ws` tới backend `127.0.0.1:8000`. Khởi động backend
theo README backend, đặt `FRONTEND_ORIGINS=http://127.0.0.1:5173,http://127.0.0.1:5174`.
Chỉ khi phát triển qua HTTP local, đặt backend `COOKIE_SECURE=false`. Production dùng HTTPS
và giữ cookie Secure. Dùng nhất quán `localhost` hoặc `127.0.0.1` giữa URL và allowlist.

Biến môi trường:

| Biến | Mặc định | Mục đích |
| --- | --- | --- |
| `API_PROXY_TARGET` | `http://127.0.0.1:8000` | Target HTTP của dev server; đặt trong shell trước npm |
| `WS_PROXY_TARGET` | `ws://127.0.0.1:8000` | Target WebSocket dev |
| `VITE_API_BASE_URL` | `/api/v1` | Base API được nhúng lúc build |
| `VITE_WS_URL` | `/ws` trên cùng host, ws/wss theo HTTP/HTTPS | URL socket nếu khác host |

Không đặt secret trong biến `VITE_*`. Production nên dùng cùng origin qua Caddy.
Signed URL storage cần trình duyệt truy cập được và CORS cho phép origin frontend.
Font có fallback system; không phụ thuộc font mạng để sử dụng giao diện.

## Chạy với mock

Từ repo root, chạy `python contracts/mock_server.py --port 4010` bằng interpreter đã cài
requirements hợp đồng. Trong PowerShell ở `web/`:

```powershell
$env:API_PROXY_TARGET = 'http://127.0.0.1:4010'
npm run dev
```

Login mock trả fixture captain và cookie, dùng email hợp lệ và mật khẩu đủ độ dài schema.
Mock **stateless**, mutation không thay đổi danh sách và không có WS. Vì vậy trạng thái
“đang kết nối lại” là bình thường. Mock login không hỗ trợ chọn admin; kiểm tra P2 với backend
dev đã `seed-dev`, không thêm backdoor/token nhập tay vào UI.

## Bố trí mã nguồn

- `src/participant.tsx`: P1, trang trận/replay và các màn hình public.
- `src/admin.tsx`: P2, điều hành đội/giải/vòng/trận/queue, source/similarity/audit/thông báo.
- `src/main.tsx`: routing, guard, layout và login dùng chung. P2 basename `/admin`.
- `src/api.ts`, `src/live.ts`, `src/upload.ts`: token trong memory, coalesced refresh, HTTP/WS/upload.
- `src/ui.tsx`: form mutation có xác nhận, bảng TanStack Table, pagination, lỗi/loading.
- `shared/schema.ts`: validate bằng chính JSON Schema generated trong `contracts/`.
- `replay-viewer/src`: package viewer độc lập với router/session/API.
- `tests`: fixture compatibility, transport, mutation, WS và kiểm thử engine/viewer.

Không sao chép DTO: tất cả dùng `contracts/generated/types.ts` và `contracts/client.ts`.
Không đổi API/schema. Khi cập nhật contract, chạy lại toàn bộ test web và generator contract.

## Quy tắc tích hợp

- Access token chỉ lưu trong memory; refresh cookie do backend quản lý. Một refresh dùng chung
  cho các request đồng thời. Sau 401 replay tối đa một lần và giữ nguyên Idempotency-Key.
- Mutation không retry do lỗi mạng. UI báo kết quả chưa xác định và refetch dữ liệu.
  CSV trả HTTP 201 kèm errors vẫn được hiển thị là thất bại.
- Đăng xuất/đổi người dùng xóa query cache. Admin guard chỉ là UX, quyền cuối cùng nằm ở backend.
- Socket gửi token bằng auth frame, chờ auth.ok trước khi subscribe team, ping 25s.
  Reconnect có backoff và refetch HTTP; sự kiện chỉ invalidate cache, không tính kết quả.
- Nộp ZIP dùng XHR adapter cho tiến trình tải lên nhưng vẫn dùng client chung cho request.
  Trình duyệt kiểm tra ZIP/1 MiB; backend chịu trách nhiệm kiểm tra archive đầy đủ.
- P2 giữ các attempt cũ, đánh dấu current; reason và xác nhận trước mutation.
  Queue poll 5s khi trang hoạt động. Nguồn/stderr chỉ lấy qua API được phân quyền.
- Replay tải signed URL qua API, tự xin URL mới một lần nếu storage trả 401/403.
  Browser giải mã Content-Encoding; không giải nén gzip hai lần. Viewer không nhận stderr ở P1.
- Tất cả Markdown không cho raw HTML. Mã nguồn được tokenize rồi render thành React text,
  không thực thi và không dùng `dangerouslySetInnerHTML`.

## Kiểm thử chéo engine

Từ repo root, với Python có package engine:

```sh
python -m pip install -e engine
python web/tests/generate_engine_replays.py
cd web
npm test
```

Generator dùng public `ottv2` API để tạo 100 ván, lưu dữ liệu tạm vào
`tests/generated/engine-replays.json` (gitignored). Test so sánh FEN cuối viewer với engine.
Nếu chưa chạy generator, chỉ test 100 ván được skip rõ ràng; 6 replay cố định và 1000 FEN vẫn chạy.
CI luôn sinh 100 replay trước test. Đây không phải bộ fixture hợp đồng mới.

## Container / infra

Từ repo root:

```sh
docker build --target p1 -f web/Dockerfile -t ottv2-web-p1:local .
docker build --target p2 -f web/Dockerfile -t ottv2-web-p2:local .
```

Hai target phục vụ port 8080 bằng nginx không root, hỗ trợ `read_only` + tmpfs `/tmp`.
P1 fallback `/index.html`, P2 fallback `/admin/index.html`; asset không tồn tại trả 404.
`/api/` và `/ws` không bị SPA nuốt. Các biến `VPS1_P1_IMAGE`/`VPS1_P2_IMAGE` của infra trỏ
tới digest image sau quy trình publish riêng. Không sửa Caddy vì routing hiện có đã khớp.

Xem [CHECKS.md](CHECKS.md) cho kết quả kiểm thử thực tế và các bước nghiệm thu còn lại.

## Đăng ký người chơi

Nếu web báo không thực hiện được yêu cầu, kiểm tra API đã chạy: từ repo root dùng
`powershell -ExecutionPolicy Bypass -File .\infra\start-local-api.ps1` (Docker Desktop
phải mở). Script giữ tài khoản trong database dev bền; chỉ chạy `npm run dev` chưa đủ.

Mở cổng thí sinh → **Chưa có tài khoản? Đăng ký** → nhập tên đội, email, mật khẩu (ít nhất 8 ký tự), nhập lại mật khẩu → **Đăng ký và vào đấu trường**. Hệ thống đăng nhập luôn và tạo đội riêng. Sau khi nộp bot và build thành công, chọn bot đánh tập để thi đấu. Đội chưa được duyệt vẫn được đánh tập; giải chính thức cần admin duyệt. Không có đăng ký admin, xác minh email, quên mật khẩu hoặc mã mời gia nhập đội trong đợt này.

Yêu cầu backend + contracts 1.1.0 cùng checkout. Form dùng `register` trong client generated, không lưu mật khẩu/token vào localStorage. Nếu mất kết nối sau đăng ký, thử đăng nhập bằng tài khoản vừa nhập.
