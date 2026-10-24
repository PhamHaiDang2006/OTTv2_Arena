# Chơi hai người

## Sau khi cập nhật code

Giữ PostgreSQL và Redis đang chạy như khi chạy backend bình thường. Dừng API cũ và chạy migration
trong terminal đã cấu hình `DATABASE_URL` của môi trường muốn dùng:

```powershell
cd C:\Users\huymu\BT01-G6-OTTv2\OTTv2_Arena\backend
.venv\Scripts\python.exe -m app.cli migrate
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Migration 0003 thêm bảng `play_rooms`, giữ nguyên tài khoản và dữ liệu hiện có.
Nếu dùng các script khởi động trong infra, chạy lại script theo hướng dẫn repo;
đảm bảo migration đã chạy trước API. Không trỏ migration vào database test nếu muốn chơi thật.

Terminal thứ hai:

```powershell
cd C:\Users\huymu\BT01-G6-OTTv2\OTTv2_Arena\web
npm.cmd run dev
```

## Mời bạn

1. Mở web, đăng nhập, chọn **Chơi với bạn · Hai người** trên thanh điều hướng.
2. Chọn **Casual 9×9 / Hexagon / Annulus**, bấm **Tạo phòng hai người**.
3. Gửi mã 8 ký tự hoặc **Sao chép lời mời** cho người thứ hai.
4. Người thứ hai dùng tài khoản riêng trên cùng website, nhập mã hoặc mở link và bấm **Vào phòng**.
5. Cả hai bấm **Sẵn sàng**. Xanh đi trước. Sau ván, cả hai bấm **Chơi lại** để đổi màu và chơi tiếp.

Dùng hai trình duyệt hoặc cửa sổ riêng tư để thử hai tài khoản trên cùng máy.
Để bạn ở máy khác vào bằng link, cả hai mở cùng URL tunnel/deployment kết nối cùng backend và database.
Link `127.0.0.1` chỉ dùng trên chính máy đó. Tạo/copy lời mời từ URL công khai nếu mời qua internet.

Đóng tab không xử thua. Đăng nhập lại cùng tài khoản, mở **Phòng gần đây** để tiếp tục.
**Rời và đóng phòng** đóng phòng cho cả hai; nếu đang chơi, người rời thua.
Nước đối thủ cập nhật khoảng 2 giây; khi mạng trở lại, bàn tự tải trạng thái đã lưu.
Không cần chạy runner cho các phòng này. Chế độ đấu máy vẫn chạy ở client.

Chi tiết kỹ thuật và trạng thái: [contracts/rooms.md](contracts/rooms.md).
