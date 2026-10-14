# starter-kits — Bộ khởi động cho thí sinh

**Phụ trách:** B · **Dự phòng:** A

Bộ khởi động giúp thí sinh tập trung vào thuật toán thay vì tự viết bộ đọc giao thức. Mỗi ngôn ngữ có cùng một bộ chức năng, để đội nào chọn ngôn ngữ nào cũng không bị thiệt.

## Cấu trúc dự kiến

```
starter-kits/
├── python/
├── cpp/
├── java/
├── node/
└── tools/
    └── local-runner/   # Chạy 2 bot đấu nhau trên máy cá nhân (dùng gói engine)
```

## Mỗi bộ khởi động phải có

| Thành phần | Mô tả |
| --- | --- |
| Lớp giao thức | Đọc `INIT`, `STATE`, `GO`, `END`; ghi `READY`, `OK`, `MOVE`; tự flush sau mỗi dòng |
| Cấu trúc bàn cờ | Đọc FEN, truy vấn quân tại ô, liệt kê quân theo bên và loại |
| Sinh nước đi | Trả về toàn bộ nước hợp lệ, đúng y luật của engine |
| Áp và hoàn tác nước đi | Để thí sinh viết tìm kiếm minimax, alpha–beta, MCTS |
| Hàm gỡ lỗi | `debug("...")` in ra dòng bắt đầu bằng `#` |
| Bot ngẫu nhiên | Mốc thấp nhất |
| Bot tham lam | Ưu tiên ăn quân và tiến về ô mục tiêu, mốc để thí sinh so sánh |
| Hướng dẫn | Cách build, cách chạy cục bộ, cách đóng gói zip để nộp |

Thí sinh chỉ cần viết một hàm, ví dụ với Python:

```python
def chon_nuoc_di(ban_co, ms_con_lai):
    ...
    return nuoc_di
```

## Nhiệm vụ

### Ngày 5
- [ ] Bộ khởi động Python: dùng trực tiếp gói `ottv2` của engine
- [ ] Bộ khởi động C++: viết lại sinh nước đi, kiểm thử chéo với engine
- [ ] Bot ngẫu nhiên và bot tham lam cho cả hai ngôn ngữ
- [ ] `tools/local-runner`: `python -m local_runner bot_a/ bot_b/ --games 10`

### Ngày 6
- [ ] Java và Node nếu image đã sẵn
- [ ] **Kiểm thử chéo bắt buộc**: với 1.000 thế trận ngẫu nhiên, danh sách nước hợp lệ của mỗi bộ khởi động phải trùng khớp tuyệt đối với engine

### Ngày 8
- [ ] Đóng gói từng bộ thành zip, đặt link tải trên trang tài liệu của P1
- [ ] Ghi số phiên bản khớp với `engine_version`

## Tiêu chí hoàn thành

- Bot mẫu của mỗi ngôn ngữ build và chạy được trên hệ thống thật, không sửa gì.
- Kiểm thử chéo sinh nước đi đạt 100%.
- Một người chưa biết dự án, theo hướng dẫn, nộp được bot đầu tiên trong vòng 15 phút.
