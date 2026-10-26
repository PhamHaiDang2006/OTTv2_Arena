# engine — Trọng tài OTTv2

Package Python `ottv2` 1.0.0, không phụ thuộc thư viện ngoài, luật `dev-v1`. Engine là nguồn sự thật duy nhất về luật: giữ trạng thái thật của ván, gửi thế trận cho bot, đo đồng hồ, kiểm tra nước đi, phân định thắng thua và ghi replay. Engine không tin dữ liệu từ bot và không gọi Docker, HTTP, Redis hay storage.

Cùng package này chạy ở ba nơi: match worker, ván chạy thử của build worker và starter kit Python trên máy thí sinh.

## Cài đặt và kiểm thử

Từ repo root, Python 3.12+:

```sh
python -m pip install -e engine
python -m pip install --target contracts/.deps -r contracts/requirements.txt   # test dùng validator hợp đồng
python -m unittest discover -s engine/tests -v
python engine/scripts/generate_fixtures.py     # sinh lại engine/fixtures/
python engine/scripts/stress.py --games 10000  # 10.000 ván ngẫu nhiên, chạy hai lần để so tất định
```

## CLI

```sh
python -m ottv2 play starter-kits/python starter-kits/python --games 4 --replay engine/dist/local.json
python -m ottv2 practice path/to/my_bot --vs greedy --games 10   # random | greedy | đường dẫn bot khác
python -m ottv2.bot greedy                                      # chạy riêng bot mẫu theo giao thức
```

Bot là thư mục, file `.py` hoặc file thực thi. Hai bên đổi màu mỗi ván; dòng cuối in `Total: <bot> x - y <đối thủ>`. `random`/`greedy` chỉ là bot mẫu khi không có thư mục hay file trùng tên. Local runner chạy bot bằng quyền người dùng, không phải sandbox, nên chỉ dùng cho bot tin cậy.

## API công khai

- `run_game(blue_io, red_io, config) -> GameResult`, `GameConfig`, `GameResult`, `BotIO`, `BotProtocolError`, `InfrastructureError`, theo [contracts/engine_api.py](../contracts/engine_api.py).
- `Board`: kit Python dùng trực tiếp; `apply` trả bản sao, `push`/`pop` sửa tại chỗ và hoàn tác theo LIFO.
- `outcome(board, mover, plies, max_turns=300)`: trả `(winner, reason)` hoặc `None` sau mỗi nước hợp lệ; `run_game` dùng cùng hàm.

Lỗi của bot là kết quả ván (`TIMEOUT`, `ILLEGAL_MOVE`, `CRASH`...); lỗi hạ tầng raise `InfrastructureError`. `GameConfig` trên wire theo giá trị cố định trong schema; API cho phép giảm clock hoặc `max_turns` để test cục bộ, nhưng không đưa các override đó vào job. Protocol v1 không gửi seed tới bot.

## Ghép với runner

Runner nạp engine qua hai biến môi trường:

- `OTTv2_ENGINE_FACTORY=ottv2.adapter:make_engine`: chuyển dict cấu hình của job thành `GameConfig`.
- `OTTv2_BUILD_VERIFIER=ottv2_runner.engine_verifier:make_build_verifier`: chạy trọn một ván với bot random tin cậy. Bot nộp thua bình thường vẫn build thành công; bot bị `CRASH`, `TIMEOUT` hay `ILLEGAL_MOVE` thì build thất bại.

Image, build từ repo root:

```sh
docker build -f runner/Dockerfile.engine -t ottv2-worker:local .   # worker có engine + runner
docker build -f engine/Dockerfile.bot -t ottv2-python:local .      # image nền bot Python, có sẵn ottv2
```

## Cấu trúc

```
engine/
├── ottv2/
│   ├── board.py     # Bàn cờ, FEN, sinh nước, apply/push/pop (a1=0, i9=80)
│   ├── rules.py     # Phân định kết thúc ván và tiebreak
│   ├── clock.py     # Đồng hồ
│   ├── game.py      # Giao thức và vòng lặp một ván với hai BotIO, ghi replay
│   ├── api.py       # Kiểu public
│   ├── adapter.py   # Adapter cho runner
│   ├── local.py     # Chạy bot bằng tiến trình cục bộ (không sandbox)
│   ├── bot.py       # Bot mẫu random/greedy, debug(), serve()
│   └── cli.py       # play, practice
├── fixtures/        # Replay thật, thế trận, ca kết thúc, báo cáo stress
├── scripts/         # generate_fixtures.py, stress.py
└── tests/
```

## Fixture và giới hạn

[fixtures/README.md](fixtures/README.md) mô tả từng file. Đổi luật phải sinh lại fixture và sửa bản TypeScript `web/replay-viewer/src/rules.ts` trong cùng một lần thay đổi. Test tích hợp runner dùng engine thật với Docker và storage giả lập; sandbox Docker và độ cân bằng của luật chưa được chứng nhận.
