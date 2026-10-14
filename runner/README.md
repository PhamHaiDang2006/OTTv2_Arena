# runner — Sandbox, build worker, match worker

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
