# web/replay-viewer — Trình phát replay

Package `@ottv2/replay-viewer` là công cụ gỡ lỗi chính của thí sinh: xem lại từng nước để biết bot thua vì sao. Component được nhúng ở cả P1 (`/games/:id`) và P2 (`/admin/games/:id`); các chế độ chơi trên trình duyệt dùng lại bản luật TypeScript của package.

## Export

- `ReplayViewer`: component React vẽ bàn 9×9 bằng SVG. Props lấy từ [contracts/viewer-api.ts](../../contracts/viewer-api.ts).
- `parseFen`, `applyMove`, `toFen` (`src/board.ts`): đọc/ghi FEN, áp nước đã ghi trong replay; `applyMove` trả bàn mới.
- `legalMoves`, `isLegal`, `outcome`, `tiebreak`... (`src/rules.ts`): bản TypeScript của luật dev-v1 cho các bàn chơi trên trình duyệt như Casual.

```tsx
<ReplayViewer replay={replay} mode="participant" />            // P1
<ReplayViewer replay={replay} mode="admin" stderr={stderr} />   // P2
```

Viewer nhận replay đã parse; trang chứa nó lo tải file, URL ký sẵn, giải nén HTTP và nút tải về. Viewer không biết router, đăng nhập hay HTTP client. Schema được validate bằng `web/shared/schema.ts`.

## Chức năng

- Bàn có nhãn cột a–i, hàng 1–9; ô đích a1 và i9; đánh dấu ô nguồn, ô đích và quân vừa bị ăn.
- Về đầu, lùi, phát, tiến, về cuối, thanh tua, chọn tốc độ; phím mũi tên và phím cách.
- Danh sách nước bấm để nhảy tới; đồng hồ còn lại và thời gian suy nghĩ; dòng debug `#` của nước đang xem; số quân còn lại; lý do kết thúc bằng câu dễ hiểu.
- Chế độ admin thêm stderr hai bên; P1 không bao giờ nhận stderr.

## Quy tắc

- Board index a1 = 0, i1 = 8, a9 = 72, theo hợp đồng chung; không dùng vị trí CSS làm tọa độ luật.
- Chỉ áp nước hợp lệ đã ghi; timeout hay illegal move không di chuyển quân. Replay 0 nước vẫn hiện bàn ban đầu và kết quả.
- Tua tính lại trạng thái từ `initial_fen` qua timeline bất biến, không sửa object replay do trang cha truyền vào. Replay hỏng hoặc sai format không làm sập trang.
- Đổi luật thì sửa `src/rules.ts` cùng lúc với engine và sinh lại fixture.

## Kiểm thử

Chạy trong workspace web (`npm test`, xem [README workspace](../README.md#kiểm-thử)): round-trip 1.000 FEN, 6 replay cố định từ engine kèm `expected_final_fen`, 600 ca kết thúc và 100 ván thật khi đã chạy generator. Harness chính ở `web/tests/replay.test.tsx` và `web/tests/rules.test.ts`.
