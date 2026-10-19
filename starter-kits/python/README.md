# Python kit 1.0.0

Engine `ottv2==1.0.0`, protocol `OTTV2 1`, luật **dev-v1 (phát triển)**. Cần Python 3.12+.

Từ repo root:

```sh
python -m pip install -e engine
python -m ottv2 play starter-kits/python starter-kits/python --replay starter-kits/dist/python-match.json
python starter-kits/tools/package.py
```

Sửa `choose_move(board, side, remaining_ms)` trong `main.py`. `STRATEGY="random"`
dùng seed 1; đổi thành `"greedy"` để ưu tiên đích, ăn quân, rồi tiến tới đích.
Kit Python dùng trực tiếp luật của engine, không sao chép bộ luật.

- `Board.from_fen(fen)`, `board.fen()`: đọc/ghi bàn; `cells[0]` là a1.
- `board.pieces(side, kind=None)`: chỉ số quân theo BLUE/RED và B/P/K.
- `board.legal_moves(side)`: các nước dạng `c3d4`.
- `board.apply(move, side)`: trả bàn mới, không sửa bàn cũ.
- `undo = board.push(move, side)` rồi `board.pop(undo)`: sửa/hoàn tác tại chỗ, theo LIFO.
- `ottv2.bot.debug(text)`: ghi dòng bắt đầu `#` và flush.

ZIP nộp bài phải chứa `main.py` **ngay tại gốc**, không chứa thư mục `python/`,
venv, package engine hay file thực thi. `package.py` tạo hai ZIP random/greedy
trong `starter-kits/dist/`. Image Python của hệ thống phải cài sẵn đúng phiên bản
`ottv2` và numpy; xem `engine/Dockerfile.bot`. Không tự pip install khi bot chạy.

Một lượt giao tiếp minh họa (engine E, bot B):

```text
E: OTTV2 1
B: READY PythonStarter
E: INIT side=BLUE budget_ms=60000 init_ms=10000 max_turns=300
B: OK
E: STATE 9/pbkpbkpbk/kpbkpbkpb/9/9/9/BPKBPKBPK/KBPKBPKBP/9 BLUE 0 60000 60000
E: GO
B: MOVE c3d4
... các lượt tiếp theo ...
E: END LOSS GOAL
```

`serve()` xử lý handshake và flush; chỉ gọi hàm chọn nước khi nhận GO. Không
in thêm vào stdout ngoài protocol/debug. Tài liệu luật: `contracts/rules.md`.
