# Phòng hai người (Rooms)

Rooms tách khỏi Arena, không tạo match/job, không gọi runner hoặc bot search.
Ba map: `standard` (luật engine dev-v1), `hexagon` và `circular` (Annulus, special-v1).
Schema và client dùng chung được sinh từ `build.mjs`, các operation mới nằm trong `openapi.yaml`.

## Luồng HTTP

- `POST /rooms` `{map}` → 201 Room; người tạo cầm BLUE, tối đa 5 phòng waiting/playing do một tài khoản tạo.
- `GET /rooms` → tối đa 50 phòng gần nhất của người gọi, mới nhất trước.
- `POST /rooms/join` `{code}` → Room. Mã 8 ký tự viết hoa. Tài khoản thứ hai nhận RED; người thứ ba nhận 409. Người đã có ghế vào lại không đổi trạng thái.
- `GET /rooms/{room_id}` → snapshot mới nhất; chỉ hai người có ghế được đọc. Người ngoài nhận 404, kể cả admin.
- `POST /rooms/{room_id}/commands` `{revision,action,move?}` → Room.
  Các mutation cần bearer và `Idempotency-Key` UUID theo quy tắc chung 24h.

## Trạng thái và lệnh

`waiting` → cả hai `ready` → `playing` → thắng theo luật hoặc `resign` → `finished`.
`unready` chỉ áp dụng trong waiting. Có thể sẵn sàng trước khi đối thủ vào.
`move` chỉ hợp lệ với chủ lượt, kiểm tra hoàn toàn trên server; `move` là `{from,to}`.
Bàn vuông dùng `a1`…`i9`; hex dùng axial `q,r`; Annulus dùng `sector,ring` (24 × 4).
Mỗi lệnh dùng revision hiện tại; revision cũ trả 409, client tải lại và yêu cầu người chơi thử lại.
Transaction khóa hàng phòng nên hai join hoặc hai nước đi đồng thời không ghi đè nhau.

Hai người `rematch` trong finished → đổi màu, tăng round, reset bàn/lịch sử, BLUE đi trước.
`leave` đóng phòng cho cả hai; khi đang chơi người rời bị tính thua. UI hỏi xác nhận.
Đóng tab, mất mạng hoặc chuyển sang danh sách không gửi leave, không tự động xử thua.
Phòng đã đóng không mở lại; tạo phòng mới để chơi tiếp. Mã không có hạn tự hết ở bản này.

## Kết nối lại và tải server

Snapshot lưu PostgreSQL, không dựa vào bộ nhớ API hay localStorage. Cùng tài khoản có thể mở lại phòng
sau refresh, mất mạng hoặc restart API. Hai người phải dùng cùng backend/database.
Client GET snapshot mỗi 2 giây khi tab phòng hoạt động, ngừng polling nền khi tab bị ẩn,
đồng bộ lại khi focus/online; không chạy vòng lặp bot hoặc RQ worker.
Đây là HTTP polling, chưa phải push WebSocket; nước đối thủ có thể xuất hiện chậm khoảng 2 giây.
Mất mạng khóa điều khiển. Khi phản hồi mutation bị mất, lần tải snapshot tiếp theo khôi phục kết quả;
revision ngăn cùng thao tác trên trạng thái cũ được áp dụng thêm lần nữa.
Không công bố email trong snapshot; hai ghế dùng UUID và màu quân.
