# C++ kit 1.0.0

Engine 1.0.0, protocol `OTTV2 1`, luật **dev-v1 (phát triển)**. Cần compiler C++20, không cần thư viện ngoài standard library.

## Bắt đầu

Từ repo root:

```sh
g++ -std=c++20 -O2 -pipe starter-kits/cpp/main.cpp -o starter-kits/cpp/main
python -m pip install -e engine
python -m ottv2 play starter-kits/python starter-kits/cpp --replay starter-kits/dist/mixed-match.json
python starter-kits/tools/package.py
```

Trên Windows dùng `-o starter-kits/cpp/main.exe` và đặt thư mục runtime MinGW trong PATH. Build worker dùng cùng chuẩn C++20 và file gốc `main.cpp`.

Sửa `choose_move(board, blue, remaining_ms)` trong `main.cpp`; `blue = true` nghĩa là bên Xanh. `GREEDY = false` chọn ngẫu nhiên với seed 1, `true` ưu tiên đích, ăn quân, rồi khoảng cách tới đích.

## API

`ottv2.hpp` cung cấp `Board::parse`, `fen`, `pieces`, `legal_moves`, `apply` (trả bản sao), `push`/`pop` (hoàn tác LIFO), `debug` và `serve`. Ô trống trong `cells` là ký tự 0; a1 = 0, i9 = 80. Danh sách nước đã được sort. Bot random C++ và Python có thể chọn nước khác nhau, nhưng tập nước hợp lệ phải giống hệt nhau.

`serve` luôn flush bằng `std::endl`. Debug dùng `ottv2::debug`, không trộn văn bản khác vào dòng `MOVE`.

## Nộp bài

ZIP chứa `main.cpp` và `ottv2.hpp` ngay tại gốc, không chứa `main`/`main.exe` hay thư mục bọc ngoài. `package.py` tạo sẵn hai ZIP random/greedy.

## Ví dụ giao thức

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

Luật và giới hạn: [contracts/rules.md](../../contracts/rules.md).
