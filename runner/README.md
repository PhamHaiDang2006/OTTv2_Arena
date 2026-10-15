# runner — Sandbox, build worker, match worker

## Hợp đồng tích hợp và hướng dẫn cho AI

Đọc [AGENTS.md](../AGENTS.md), [hợp đồng tích hợp](../integration.md) mục 2, 4, 5, 7–9 và README của engine/backend/infra/starter-kits.

- **Sở hữu:** build/match worker, Docker sandbox, adapter BotIO, upload artifact và callback. Không tự cập nhật DB, tính điểm hoặc tạo game attempt.
- **Nhận:** job v1 đã được C validate; **gọi:** public API ottv2; **trả:** callback v1 theo mục 4. Không tự thêm field hoặc đổi `plies` thành `total_plies` trên wire.
- Dùng schema/fixture trong [contracts](../contracts/README.md). Entry points cố định: `ottv2_runner.jobs.build_submission(payload)` và `ottv2_runner.jobs.run_match(payload)`; nhận một dict đúng schema. C enqueue cùng tên, không tự đặt hàm khác.
- Runner ghi started_at_ns khi khởi động bot, thu stderr độc lập, luôn dọn container trong finally. Engine sở hữu stdout giao thức và quyết định lỗi bot.
- Claim/lease và redelivery phải chống hai worker chạy cùng job. Backend sở hữu tạo attempt mới. HTTP callback timeout chỉ gửi lại payload đã lưu; không tự chạy lại ván.
- Upload xong replay/log rồi callback finished. Artifact và image của submission/game bất biến; không ghi đè replay của attempt trước.
- Callback dùng INTERNAL_API_BASE_URL có sẵn /api/v1 và token worker; không dùng token người chơi hoặc credential DB.

### Build và starter kit phải khớp

B dùng bảng ngôn ngữ/file chính/lệnh build/run trong [behavior.md](../contracts/behavior.md); chọn image digest khi triển khai Dockerfile. Python/C++ bắt buộc, Java/Node chỉ bật sau khi image và kit qua pipeline thật. Không tự đặt cách đóng gói khác kit.

Kiểm tra ZIP trước/sau giải nén, traversal, symlink, số file/kích thước theo giới hạn đã chốt trong behavior. Dockerfile do hệ thống cung cấp; không chạy Dockerfile hoặc shell command tùy ý từ metadata của thí sinh.

### Chạy độc lập và bàn giao

Chưa có worker/Compose thực thi trong repo hiện tại. PR đầu tiên bổ sung lệnh cài, chạy từng worker, chạy test với fake backend/storage và test Docker thật; liệt kê biến môi trường theo mục 7, không commit secret.

Trước merge: bot mẫu kit build thành công; timeout/crash/illegal move giữ đúng lý do; container sạch sau engine exception; callback gửi lặp chỉ tạo một kết quả; storage/API mất kết nối và worker chết có cách phục hồi. Ghi rõ test nào cần Linux/Docker và test nào đã thực sự chạy. A review engine adapter; C review job/callback.


**Phụ trách:** B · **Dự phòng:** A · **Chạy ở:** VPS 2

Thư mục này chứa mọi thứ chạm vào code của thí sinh. Đây là phần nhạy cảm nhất của hệ thống: một lỗ hổng ở đây có thể làm sai kết quả hoặc cho bot chiếm máy chủ.

## Cấu trúc dự kiến

```
runner/
├── images/
│   ├── python/Dockerfile   # ottv2/py:1    — Python 3.12 + numpy
│   ├── cpp/Dockerfile      # ottv2/cpp:1   — g++ C++20
│   ├── java/Dockerfile     # ottv2/java:1  — Java 21
│   └── node/Dockerfile     # ottv2/node:1  — Node 22
├── sandbox.py              # Dựng lệnh docker run với đầy đủ giới hạn
├── build_worker.py         # Lấy việc từ hàng đợi build
├── match_worker.py         # Lấy việc từ hàng đợi match
├── backend_client.py       # Gọi /internal/* của backend
└── tests/
    └── malicious/          # Bộ bot phá hoại
```

## Nhiệm vụ

### Ngày 1–2
- [ ] `images/python`: image nền, người dùng không phải root (`10001`), có sẵn gói `ottv2`
- [ ] `sandbox.py`: dựng lệnh `docker run -i --rm` với toàn bộ giới hạn ở `architecture.md` mục 6
- [ ] Chạy một bot Python trong container, nói chuyện qua stdin/stdout, đo độ trễ khứ hồi một dòng
- [ ] Chốt với C định dạng kết quả gửi về `/internal/builds/{id}` và `/internal/games/{id}`

### Ngày 3 — Build worker
- [ ] Tải mã nguồn từ MinIO, giải nén vào thư mục tạm, kiểm tra lại kích thước và số tệp
- [ ] `docker build --network none`, gắn thẻ `ottv2-bot:{submission_id}`, đẩy vào registry nội bộ
- [ ] Chạy thử một ván với bot ngẫu nhiên, thất bại thì đánh dấu `failed`
- [ ] Đẩy nhật ký build lên MinIO, gửi kết quả về backend
- [ ] Phát hiện lỗi thường gặp và ghi thông báo dễ hiểu vào nhật ký: quên flush, không gửi `READY`, sai tên tệp chính

### Ngày 4 — Match worker
- [ ] Lấy việc từ `match:tournament` trước, `match:scrimmage` sau
- [ ] Khởi động 2 container bot, nối ống dẫn vào engine, chạy ván
- [ ] Ghim mỗi container vào một lõi riêng theo số thứ tự worker
- [ ] Dừng và xóa container khi ván kết thúc, kể cả khi engine lỗi
- [ ] Đẩy replay và stderr lên MinIO, gửi kết quả về backend
- [ ] Phân biệt lỗi của bot với `INFRA_ERROR`; với lỗi hạ tầng thì đẩy lại tối đa 3 lần

### Ngày 5–6
- [ ] Image C++ (bắt buộc), Java và Node (nếu kịp)
- [ ] Benchmark: cùng một cặp bot chạy 100 lần, độ lệch thời gian tiêu thụ dưới 2%
- [ ] Nhịp tim worker gửi về Redis mỗi 30 giây

### Ngày 7 — Gia cố
- [ ] Viết cùng A bộ 10 bot phá hoại và xác nhận tất cả bị chặn:
    - Fork bomb
    - Mở kết nối mạng ra ngoài
    - Kết nối sang container đối thủ
    - Ghi đầy đĩa
    - Cấp phát vượt bộ nhớ
    - Đọc `/etc/passwd`, biến môi trường, Docker socket
    - In vô hạn ra stdout và stderr
    - Treo không trả lời
    - Ngủ đến sát hết giờ rồi mới trả lời mỗi nước
    - Tạo tiến trình con tiếp tục chạy sau khi tiến trình chính thoát
- [ ] Giới hạn kích thước nhật ký stderr mỗi bot (1 MB), phần thừa cắt bỏ

## Giao diện với phần khác

| Nhận từ | Thứ nhận |
| --- | --- |
| `backend/` | Việc trong Redis theo định dạng `architecture.md` mục 5.4 |
| `engine/` | Hàm `run_game` |

| Cung cấp cho | Thứ được cung cấp |
| --- | --- |
| `backend/` | Kết quả build và kết quả ván qua `/internal/*` |
| MinIO | Nhật ký build, replay, stderr |

## Tiêu chí hoàn thành

- Bot Python mẫu build xong dưới 60 giây.
- Bộ 10 bot phá hoại đều bị chặn, máy chủ không bị ảnh hưởng.
- Độ lệch đồng hồ dưới 2% qua 100 lần chạy.
- Tắt đột ngột một worker giữa trận thì trận đó tự chạy lại ở worker khác.
