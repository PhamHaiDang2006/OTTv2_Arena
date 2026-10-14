# engine — Trọng tài OTTv2

**Phụ trách:** A · **Dự phòng:** B · **Ngôn ngữ:** Python 3.12, không phụ thuộc thư viện ngoài

Engine là nguồn sự thật duy nhất về luật chơi. Nó giữ trạng thái thật của ván, gửi thế trận cho bot, đo đồng hồ, kiểm tra nước đi, quyết định thắng thua và ghi replay. Engine không bao giờ tin dữ liệu từ bot.

Cùng một gói Python này được dùng ở ba nơi: match worker trên VPS 2, build worker (ván chạy thử), và starter kit cho thí sinh chạy cục bộ.

## Cấu trúc dự kiến

```
engine/
├── ottv2/
│   ├── board.py       # Bàn cờ, quân, đọc ghi FEN
│   ├── rules.py       # Sinh nước đi hợp lệ, áp nước đi, kiểm tra kết thúc
│   ├── tiebreak.py    # Phân định khi chạm trần lượt
│   ├── protocol.py    # Đọc ghi các dòng giao thức
│   ├── clock.py       # Đồng hồ cờ vua
│   ├── game.py        # Vòng lặp một ván với hai kênh bot
│   ├── replay.py      # Ghi replay theo định dạng trong architecture.md
│   └── cli.py         # ottv2 play bot1 bot2 --replay out.json
└── tests/
```

## Nhiệm vụ

### Ngày 1
- [ ] Chốt 8 điểm luật với ban tổ chức (danh sách trong `project_plan.md`, mục 9)
- [ ] Viết đặc tả giao thức và định dạng replay vào `architecture.md`, cả nhóm duyệt
- [ ] `board.py`: biểu diễn bàn 9x9, chuyển đổi tọa độ `a1`–`i9`, đọc và ghi FEN

### Ngày 2
- [ ] `rules.py`: sinh nước đi 8 hướng, chặn quân cùng bên, chặn quân cùng loại đối phương, cấm tự sát, cấm vào ô mục tiêu đối phương
- [ ] Luật ăn: Búa ăn Kéo, Kéo ăn Bao, Bao ăn Búa
- [ ] Kiểm tra kết thúc theo đúng thứ tự: `GOAL`, `WIPEOUT`, `STALEMATE`
- [ ] Unit test cho từng luật, mỗi luật ít nhất một ca đúng và một ca sai

### Ngày 3
- [ ] `clock.py`: ngân sách khởi động 10 s, ngân sách ván 60 s, ân hạn 50 ms mỗi nước, giới hạn cứng
- [ ] `game.py`: vòng lặp ván, xử lý `TIMEOUT`, `ILLEGAL_MOVE`, `CRASH`, `MOVE_LIMIT`
- [ ] `tiebreak.py`: loại quân mỏng nhất → tổng quân → khoảng cách tới đích → Đỏ thắng
- [ ] `replay.py`: ghi replay, gồm cả dòng gỡ lỗi `#` của bot
- [ ] Chạy 10.000 ván bot ngẫu nhiên với bot ngẫu nhiên: không lỗi, chạy lại cho kết quả giống hệt, tỷ lệ thắng của Xanh nằm trong 48–52%

### Ngày 4–5
- [ ] Chuyển sang làm `web/replay-viewer/`
- [ ] Hỗ trợ B ghép engine vào match worker

### Ngày 6
- [ ] Kiểm thử biên: bot không gửi `READY`, gửi dòng rỗng, gửi nước sai định dạng, in 10 MB ra stdout, treo vĩnh viễn, thoát giữa ván
- [ ] Đóng phiên bản `1.0.0`, ghi vào `engine_version`

### Ngày 7
- [ ] Viết tài liệu luật chơi và giao thức cho thí sinh, kèm ví dụ minh họa từng luật

## Giao diện với phần khác

| Cung cấp cho | Thứ được cung cấp |
| --- | --- |
| `runner/` | Hàm `run_game(blue_io, red_io, config) -> GameResult` và tệp replay |
| `starter-kits/` | Gói `ottv2` để thí sinh chạy cục bộ |
| `web/replay-viewer/` | Định dạng replay và bộ ván mẫu để kiểm thử |

## Tiêu chí hoàn thành

- Độ phủ kiểm thử của `rules.py` và `clock.py` đạt 95%.
- 10.000 ván ngẫu nhiên không lỗi và tất định.
- `ottv2 play` chạy được hai bot mẫu trên máy cá nhân, không cần Docker.
