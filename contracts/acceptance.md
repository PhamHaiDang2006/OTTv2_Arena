# Kiểm tra implementation trước khi ghép

Các test hợp đồng đã chạy không thay thế các test dưới đây. Chủ phần bổ sung test vào implementation và báo kết quả thật; chưa có code sản phẩm thì các mục này là chưa chạy.

| Bên | Tình huống bắt buộc |
| --- | --- |
| A ↔ B | Cùng GameConfig/seed qua BotIO giả và pipe; handshake, EOF, timeout, overflow, invalid UTF-8; mất hạ tầng phải raise InfrastructureError |
| A ↔ B kit | Fixture FEN/áp nước, undo, legal moves theo ruleset; cross-check 1.000 thế trận; ZIP main.py/main.cpp chạy được nguyên trạng |
| A ↔ D | Fixture replay 0 nước/ăn quân và replay thật, tua qua lại khớp expected_final_fen; ruleset/format lạ bị từ chối rõ ràng |
| B ↔ C | Job schema; claim trùng; lease hết hạn; callback lặp cùng token sau release; payload terminal khác; attempt cũ; storage lỗi; worker chết; không tính điểm hai lần |
| C ↔ D | Tất cả response thật validate OpenAPI; 401 refresh chỉ một lần; 403/404 chéo đội; 409 trạng thái; 429 quota; signed URL hết hạn |
| C ↔ D admin | Freeze snapshot bất biến; run cùng key không nhân đôi match; rerun bị khóa khi downstream frozen; override lưu audit; CSRF/Origin sai bị chặn |
| C ↔ D WS | Auth trước team subscribe, token hết hạn, reconnect/refetch, event trùng, public không thấy private data, invalid frame/rate limit |
| A ↔ D Casual | Luật TypeScript trong trình duyệt khớp positions.json, outcomes.json và replay engine thật từng nước; Casual không gọi API ván |
| C ↔ D tài nguyên | 503 SCRIMMAGE_PAUSED theo từng lý do, 429 SCRIMMAGE_LIMIT, trận đã nhận không bị hủy; quota/queue trả admission đúng schema |
| B infra | /admin deep link, /api/v1 và /ws routing, chặn internal API ngoài VPN, gzip/CORS signed URL; migrate từ DB sạch và restore |

## Luồng smoke thật (cần implementation)

1. Seed hai đội approved và tài khoản captain/admin; chưa có bot active.
2. Login captain A, upload ZIP Python với Idempotency-Key; lặp lại cùng key phải trả cùng submission_id.
3. Chờ ready, xem log, đặt bot scrimmage; làm tương tự đội B.
4. Tạo scrimmage A–B, chụp hai submission; thay active bot sau đó không thay game đã tạo.
5. Hoàn thành hai ván đổi màu, validate callback/replay, xem cả hai trên P1.
6. Gửi lại callback: số ván/điểm/event không tăng thêm. Xem stderr ở admin; member không đọc được.
7. Kill worker trong một ván thử mới; current attempt mới có ID khác, kết quả cũ không được lấy thay.

Chạy smoke với ruleset dev-v1 chỉ chứng minh tích hợp trong môi trường phát triển. Luật và bảo mật sandbox cần test riêng trước dùng thi đấu thật.
