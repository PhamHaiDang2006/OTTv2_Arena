# web/p1-participant — Cổng thí sinh

## Implementation 1.0.0

Mã P1 ở `../src/participant.tsx`, routing/layout/auth ở `../src/main.tsx` và client
dùng chung ở `../src/api.ts`. Đã có login, trang đội/lịch đóng băng, upload ZIP có
progress, build log, lịch sử/chọn bot, scrimmage/quota, trận/replay, bảng/nhánh và tài liệu.
Nguồn bot được xem qua endpoint own-source. Không gọi admin API từ luồng P1.

Chạy/build/test từ `web/` theo [README workspace](../README.md).
Kết quả thực tế và giới hạn nghiệm thu ở [CHECKS.md](../CHECKS.md).
Checklist ngày công bên dưới giữ làm kế hoạch gốc, không phải kết quả test trình duyệt.

## Hợp đồng tích hợp và hướng dẫn cho AI

Đọc [AGENTS.md](../../AGENTS.md), [hợp đồng tích hợp](../../integration.md) mục 2, 3, 6–9 và README backend/replay-viewer/P2.

- D sở hữu workspace `web/`, shared UI/API client và lockfile chung. Không tạo lockfile riêng cho P1/P2/viewer.
- Dùng [generated types](../../contracts/generated/types.ts), [client](../../contracts/client.ts) và [mock API](../../contracts/README.md). Lệnh sinh là node contracts/build.mjs; không tự viết lại wire DTO hoặc sửa output sinh tự động.
- Mock lấy fixture hợp đồng. OpenAPI đã có opponents/quota/auth/me/docs; tra operationId trong contracts/operations.json, không tự chọn URL.
- Auth, refresh một lần, error envelope, phân trang và reconnect theo integration mục 3. P1 chỉ chọn active bot ready của đội hiện tại.
- Build log: build.updated báo trạng thái để refetch log; nếu cần stream từng dòng phải thêm hợp đồng riêng với C, không giả định event chứa toàn bộ log.
- Trang replay tải/validate JSON rồi truyền object vào package viewer; không sao chép logic bàn cờ hay tải stderr admin.
- Hiển thị đầy đủ loading/empty/error/403/409/429 và hết hạn URL replay; khi hết hạn lấy URL mới qua API có quyền, không sửa chữ ký.
- POST upload/scrimmage không tự retry khi mất mạng; báo trạng thái chưa xác định và refetch. Chỉ dùng cơ chế idempotency nếu được OpenAPI quy định.

### Ánh xạ dữ liệu màn hình

| Màn hình | Nguồn chuẩn | Sự kiện để refetch |
| --- | --- | --- |
| Đội / active bot | /teams/me, /teams/me/active-bot | build.updated khi cần cập nhật lựa chọn |
| Nộp / lịch sử | /submissions, /submissions/{id}/build-log | build.updated |
| Đánh tập / trận | /scrimmages, /matches/{id} | game.finished, match.finished |
| Replay | /games/{id}/replay | game.finished |
| Bảng / nhánh | /standings, /bracket | standings.updated, match.finished |
| Thông báo | /announcements | announcement.published |

Đường dẫn trong bảng tương đối với /api/v1; method/response lấy từ OpenAPI. Không cộng điểm hoặc suy ra winner ở frontend.

### Chạy độc lập và bàn giao

Workspace đã có `npm ci`, `npm run dev`, `npm run typecheck`, `npm test`, `npm run build`. Cấu hình mock/dev API thật ở README workspace. Dùng VITE_API_BASE_URL/VITE_WS_URL theo integration, không nhúng secret.

Trước merge: mock và HTTP thật cùng schema, refresh đồng thời, WS mất kết nối, upload lỗi, submission failed, hết quota, replay 0 nước/hỏng; build và kiểm tra màn hình nhỏ. C review API usage, A đối chiếu viewer props. PR ghi fixture và commit OpenAPI được dùng.


**Phụ trách:** D · **Dự phòng:** C · **Công nghệ:** React 18, Vite, TypeScript, TanStack Query, React Router

Mục tiêu của P1 là rút ngắn vòng lặp *sửa code → biết bot mạnh hơn hay yếu đi*. Mọi màn hình khác là phụ.

## Màn hình

| Đường dẫn | Màn hình | Nội dung chính |
| --- | --- | --- |
| `/login` | Đăng nhập | Email, mật khẩu |
| `/` | Trang chủ đội | Bot đang dùng, trận sắp đấu, kết quả gần nhất, thông báo mới |
| `/submit` | Nộp bài | Kéo thả zip, chọn ngôn ngữ, nhật ký build chạy trực tiếp |
| `/submissions` | Lịch sử nộp | Danh sách bản nộp, trạng thái, đặt làm bot đánh tập hoặc bot thi đấu |
| `/scrimmage` | Đánh tập | Chọn đội đối thủ, hạn mức còn lại, danh sách trận đã đánh |
| `/games/:id` | Xem replay | Nhúng `replay-viewer` |
| `/standings` | Bảng đấu | 4 bảng, điểm, hiệu số |
| `/bracket` | Nhánh đấu | Sơ đồ tứ kết đến chung kết |
| `/docs` | Tài liệu | Luật, giao thức, tải bộ khởi động, câu hỏi thường gặp |

## Nhiệm vụ

### Ngày 1
- [ ] Khung Vite + React + TypeScript, cấu trúc dùng chung với P2 (thư viện component, client API)
- [ ] Bố cục chung, thanh điều hướng, trang đăng nhập
- [ ] Client API sinh từ OpenAPI của backend; dùng dữ liệu giả khi backend chưa sẵn

### Ngày 2
- [ ] Trang chủ đội
- [ ] Trang nộp bài: kéo thả, kiểm tra kích thước phía trình duyệt, thanh tiến trình tải lên

### Ngày 3
- [ ] Lịch sử nộp, nút đặt làm bot đang dùng (chỉ đội trưởng thấy)
- [ ] Nhật ký build cập nhật trực tiếp qua WebSocket `build.updated`

### Ngày 4 — M2
- [ ] Trang đánh tập: chọn đối thủ, tạo trận, danh sách trận cập nhật trực tiếp
- [ ] Trang replay nhúng `replay-viewer`

### Ngày 7
- [ ] Bảng đấu và nhánh đấu, cập nhật qua kênh `public`
- [ ] Hiển thị thông báo, có huy hiệu khi có thông báo mới
- [ ] Trang tài liệu
- [ ] Hiển thị tốt trên điện thoại, đủ để xem kết quả và replay

## Yêu cầu trải nghiệm

- Mọi lỗi từ backend hiện bằng tiếng Việt rõ ràng, không hiện mã lỗi thô.
- Trạng thái build có 4 màu cố định: chờ, đang build, sẵn sàng, lỗi.
- Khi bản nộp lỗi, hiện ngay dòng nhật ký gây lỗi, không bắt thí sinh cuộn tìm.
- Thời gian đóng băng nộp bài hiện đếm ngược trên trang chủ.

## Tiêu chí hoàn thành

- Một đội đi trọn luồng: đăng nhập → nộp → xem build → đặt bot → đánh tập → xem replay, không cần tải lại trang.
- Chạy được trên Chrome, Firefox, Safari và trình duyệt điện thoại.

## Đăng ký người chơi

Mở cổng thí sinh → **Chưa có tài khoản? Đăng ký** → nhập tên đội, email, mật khẩu (ít nhất 8 ký tự), nhập lại mật khẩu → **Đăng ký và vào đấu trường**. Hệ thống đăng nhập luôn và tạo đội riêng. Sau khi nộp bot và build thành công, chọn bot đánh tập để thi đấu. Đội chưa được duyệt vẫn được đánh tập; giải chính thức cần admin duyệt. Không có đăng ký admin, xác minh email, quên mật khẩu hoặc mã mời gia nhập đội trong đợt này.

Yêu cầu backend + contracts 1.1.0 cùng checkout. Form dùng `register` trong client generated, không lưu mật khẩu/token vào localStorage. Nếu mất kết nối sau đăng ký, thử đăng nhập bằng tài khoản vừa nhập.
