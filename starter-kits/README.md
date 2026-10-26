# starter-kits — Bộ khởi động cho thí sinh

Giúp thí sinh tập trung vào thuật toán thay vì tự viết phần giao thức. Mọi kit dùng protocol `OTTV2 1`, engine 1.0.0 và luật phát triển `dev-v1`.

| Kit | Yêu cầu | Nội dung |
| --- | --- | --- |
| [python/](python/README.md) | Python 3.12+ | Dùng trực tiếp `ottv2.Board` của engine, không sao chép luật |
| [cpp/](cpp/README.md) | Compiler C++20 | Header `ottv2.hpp` cài lại luật, kiểm chéo với engine bằng 1.000 thế trận |
| [python-demo/](python-demo/README.md) | Python 3.12+ | Bot alpha-beta + iterative deepening, ví dụ tìm kiếm thật dùng API kit Python |

Kit Python và C++ có cùng bộ chức năng: lớp giao thức tự flush, đọc FEN, sinh nước hợp lệ đúng như engine, apply/undo cho thuật toán tìm kiếm, `debug()` in dòng `#`, bot mẫu `random` (mốc thấp nhất) và `greedy` (ưu tiên đích, ăn quân rồi tiến lên). Java và Node chưa bật vì chưa có image runner đã kiểm chứng.

## Nộp bài

ZIP chỉ chứa source, file chính nằm ngay tại gốc ZIP (`main.py`, hoặc `main.cpp` + `ottv2.hpp`), không có thư mục bọc ngoài, venv hay file thực thi. Lệnh build và chạy phía máy chủ theo bảng ngôn ngữ trong [contracts/behavior.md](../contracts/behavior.md).

```sh
python starter-kits/tools/package.py
```

Lệnh trên tạo trong `dist/` năm ZIP (random/greedy cho hai ngôn ngữ và bot demo) kèm `manifest.json` ghi version và SHA-256. Không sửa ZIP bằng tay.

## Tự luyện trên máy

```sh
python -m pip install -e engine
python -m ottv2 practice starter-kits/python --vs greedy --games 10
python -m ottv2 practice path/to/new_bot --vs path/to/old_bot --games 10
python -m ottv2 play starter-kits/python starter-kits/cpp --games 10 --replay starter-kits/dist/game.json
```

Hai bên đổi màu mỗi ván. Mở file replay bằng trang Tự luyện của P1 để xem trên trình duyệt. Bot C++ phải compile trước (xem [cpp/README.md](cpp/README.md)). `tools/local_runner.py` nhận đúng các tham số này, chỉ là lối tắt tới CLI của engine. Bot chạy bằng quyền người dùng, không có sandbox.

## Kiểm thử kit

```sh
python -m pip install -e engine
python -m pip install --target contracts/.deps -r contracts/requirements.txt
python starter-kits/tests/check_kits.py   # 1.000 thế trận, cả hai màu, apply/undo, so với engine
python starter-kits/tests/play_kits.py    # kiểm tra ZIP bằng runner, compile C++, 8 cặp Python/C++ đổi màu
```

Hai script nhận `--cxx /path/to/g++`. Khi engine đổi, chạy lại kiểm thử chéo và sinh lại ZIP trước khi phát hành kit mới. Image Python của runner phải cài sẵn đúng phiên bản `ottv2` (`engine/Dockerfile.bot`).
