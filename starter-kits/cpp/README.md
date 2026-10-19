# C++ kit 1.0.0

Engine 1.0.0, protocol `OTTV2 1`, luật **dev-v1 (phát triển)**. Cần compiler C++20.

Từ repo root:

```sh
g++ -std=c++20 -O2 -pipe starter-kits/cpp/main.cpp -o starter-kits/cpp/main
python -m pip install -e engine
python -m ottv2 play starter-kits/python starter-kits/cpp --replay starter-kits/dist/mixed-match.json
python starter-kits/tools/package.py
```

Trên Windows dùng `-o starter-kits/cpp/main.exe`, đặt thư mục runtime MinGW
trong PATH. Compiler build worker dùng cùng C++20 và file gốc `main.cpp`.

Sửa `choose_move(board, blue, remaining_ms)` trong `main.cpp`. `blue=true`
là BLUE; `GREEDY=false` dùng random seed 1, `true` ưu tiên đích/ăn quân/khoảng
cách. Không cần thư viện ngoài standard library.

`ottv2.hpp` cung cấp `Board::parse`, `fen`, `pieces`, `legal_moves`,
`apply` (bản sao), `push`/`pop` (hoàn tác LIFO), `debug` và `serve`.
Ô trống trong `cells` là ký tự 0; a1=0, i9=80. Danh sách nước đã sort.
Random C++/Python có thể chọn nước khác nhau; tập nước hợp lệ phải giống nhau.

ZIP chứa `main.cpp` và `ottv2.hpp` ngay tại gốc, không chứa `main.exe` hay folder
bọc ngoài. `package.py` tạo ZIP random/greedy tương thích bộ kiểm tra ZIP của runner.

Ví dụ protocol đầy đủ một chu kỳ:

```text
engine: OTTV2 1
bot: READY CppStarter
engine: INIT side=BLUE budget_ms=60000 init_ms=10000 max_turns=300
bot: OK
engine: STATE 9/pbkpbkpbk/kpbkpbkpb/9/9/9/BPKBPKBPK/KBPKBPKBP/9 BLUE 0 60000 60000
engine: GO
bot: MOVE c3d4
... các lượt tiếp theo ...
engine: END WIN GOAL
```

`serve` luôn flush bằng `std::endl`. Debug dùng `ottv2::debug`, không trộn text
khác vào MOVE. Luật và giới hạn tại `contracts/rules.md`.
