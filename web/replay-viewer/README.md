# web/replay-viewer — Trình phát replay

## Hợp đồng tích hợp và hướng dẫn cho AI

Đọc [AGENTS.md](../../AGENTS.md), [hợp đồng tích hợp](../../integration.md) mục 5, 6, 7, 9 và README engine/P1/P2. A sở hữu viewer theo phân công hiện hành; D sở hữu workspace web và tích hợp trang.

- Export package @ottv2/replay-viewer theo [viewer-api.ts](../../contracts/viewer-api.ts) và [types.ts](../../contracts/generated/types.ts). Dùng fixture board/replay trong contracts; không import router, auth hay API client của P1/P2.
- Nhận Replay đã parse; container page chịu fetch, signed URL, giải mã HTTP và download callback. Viewer kiểm tra format/dữ liệu để không crash trang.
- A tạo fixture từ engine cùng expected_final_fen; D dùng chính fixture đó trên hai trang. Không tạo replay giả có result.plies khác moves.length.
- Board index và ký hiệu quân theo hợp đồng chung; applyMove trả board mới. Không dùng vị trí ô theo CSS làm tọa độ luật.
- Chỉ áp nước hợp lệ đã ghi; timeout/illegal move không di chuyển quân. 0 nước vẫn có bàn ban đầu và kết quả.
- Debug của nước hiện tại và stderr là dữ liệu khác nhau. Admin mode không thay thế kiểm tra quyền backend; participant không được nhận stderr riêng.
- Điều khiển tua phải tính lại trạng thái từ initial_fen hoặc snapshot cache nhất quán; không mutate object replay do parent cung cấp.
- Dùng profile dev-v1 đã ghi trong contracts/rules.md; không tự sửa RULE-01..08 để làm fixture pass. Nếu fixture và engine khác, đối chiếu profile trước.

### Chạy độc lập và bàn giao

Khi tạo package, A/D bổ sung trang demo hoặc harness dùng fixture, lệnh test/typecheck/build qua workspace web chung. Không thêm lockfile con; dependency và scripts root phối hợp D.

Trước merge: FEN round-trip, board cuối khớp fixture engine, tua đầu/cuối/lùi sau ăn quân, 0 nước, format lạ/dữ liệu hỏng; participant/admin props; keyboard/mobile và replay dài. Replay dài 600 ply là ca hiệu năng, không tự xác nhận max_turns có nghĩa 600 ply. Bàn giao public exports, fixture version và kết quả kiểm tra cho D.


**Phụ trách:** A · **Dự phòng:** D · **Công nghệ:** React component bằng TypeScript, vẽ bàn cờ bằng SVG

Trình phát replay là công cụ gỡ lỗi chính của thí sinh. Thiếu nó, thí sinh không biết bot thua vì sao. Component này được nhúng vào cả P1 và P2.

## Đầu vào

Tệp replay theo định dạng `architecture.md` mục 5.2. Component tự dựng thế trận từng nước bằng cách áp dần `moves` lên `initial_fen`, nên cần một bản TypeScript của phần áp nước đi.

```tsx
<ReplayViewer replay={replayJson} mode="participant" />   // P1
<ReplayViewer replay={replayJson} mode="admin" stderr={...} />  // P2
```

## Chức năng

| Chức năng | Ngày |
| --- | --- |
| Bàn 9x9 có nhãn cột a–i, hàng 1–9; Búa tròn, Bao vuông, Kéo tam giác; Xanh và Đỏ | 4 |
| Tô ô mục tiêu `a1` và `i9` | 4 |
| Nút về đầu, lùi, phát, tiến, về cuối; thanh tua; chọn tốc độ | 4 |
| Phím tắt: mũi tên trái phải, phím cách | 4 |
| Đánh dấu ô nguồn, ô đích của nước vừa đi và quân vừa bị ăn | 4 |
| Danh sách nước đi dạng ký hiệu, bấm để nhảy tới | 5 |
| Đồng hồ còn lại của hai bên và thời gian suy nghĩ của nước hiện tại | 5 |
| Khung gỡ lỗi: dòng `#` mà bot in ra ở đúng nước đang xem | 5 |
| Số quân còn lại mỗi loại của mỗi bên | 5 |
| Lý do kết thúc bằng câu dễ hiểu, ví dụ "Đỏ thua vì hết giờ ở nước 214" | 5 |
| Nút tải tệp replay | 5 |
| Chế độ admin: thêm stderr hai bên | 6 |

## Nhiệm vụ

### Ngày 4
- [ ] Viết `applyMove` và `parseFen` bằng TypeScript
- [ ] Kiểm thử chéo: với 100 tệp replay sinh từ engine, thế trận cuối do viewer dựng phải khớp thế trận cuối của engine
- [ ] Bàn cờ, điều khiển phát, đánh dấu nước đi

### Ngày 5
- [ ] Danh sách nước, đồng hồ, khung gỡ lỗi, đếm quân, lý do kết thúc

### Ngày 6
- [ ] Chế độ admin
- [ ] Xử lý replay hỏng hoặc thiếu trường mà không làm sập trang

## Tiêu chí hoàn thành

- Kiểm thử chéo với engine đạt 100%.
- Replay 600 nước tua mượt, không giật.
- Dùng được trên điện thoại.
