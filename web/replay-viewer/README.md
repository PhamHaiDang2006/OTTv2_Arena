# web/replay-viewer — Trình phát replay

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
