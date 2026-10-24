import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ReplayViewer } from '@ottv2/replay-viewer';
import type { Replay } from '../../contracts/generated/types';
import { validate } from '../shared/schema';
import { ErrorBox, Heading } from './ui';
import { Crest } from './casual-presentation';

const MAX_REPLAY_BYTES = 5 * 1024 * 1024;
const readText = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('Không đọc được file replay.'));
    reader.readAsText(file);
  });
/** Tự luyện runs on the contestant's machine; this page only explains it and opens local replay files. */
export function Practice() {
  const [replay, setReplay] = useState<{ name: string; data: Replay }>(),
    [error, setError] = useState<unknown>();
  return (
    <>
      <div className="training-intro">
        <div className="training-emblem" aria-hidden="true">
          <Crest kind="bot" />
        </div>
        <Heading
          eyebrow="OTT v2 / TỰ LUYỆN"
          title="Tự luyện · Chạy trên máy của bạn"
          description="Cho bot của bạn đấu bot mẫu hoặc một bot khác có sẵn trên máy. Không tốn lượt đánh tập trên máy chủ."
        />
      </div>
      <div className="two-col">
        <section className="card">
          <h2>1. Chuẩn bị</h2>
          <p>
            Tải bộ khởi động ở <Link to="/docs">Tài liệu</Link>, rồi cài Python 3.12 và gói engine{' '}
            <code>ottv2</code> theo README của kit. Bot C++ cần biên dịch trước.
          </p>
          <h2>2. Đấu với bot mẫu</h2>
          <pre>python -m ottv2 practice duong/dan/bot-cua-ban --vs greedy --games 10</pre>
          <p>
            <code>--vs random</code> là bot ngẫu nhiên, <code>--vs greedy</code> là bot ưu tiên ăn quân. Hai
            bên đổi màu sau mỗi ván; dòng cuối in tổng số ván thắng.
          </p>
          <h2>3. Đấu với một bot khác trên máy</h2>
          <pre>python -m ottv2 practice duong/dan/bot-moi --vs duong/dan/bot-cu --games 10</pre>
          <p>
            Bot là thư mục có <code>main.py</code> (hoặc file chạy <code>main</code>) hay đường dẫn tới chính
            file đó. Replay được ghi vào <code>practice/replay-1.json</code>,{' '}
            <code>practice/replay-2.json</code>…
          </p>
          <p className="muted">
            Engine trên máy dùng cùng luật dev-v1 và cùng cách tính giờ với máy chủ, nhưng không có sandbox:
            chỉ chạy bot bạn tin tưởng. Thời gian đo trên máy bạn có thể khác máy chủ.
          </p>
        </section>
        <section className="card">
          <h2>4. Xem replay</h2>
          <p>Chọn một file replay vừa tạo. File được đọc ngay trên trình duyệt, không gửi lên máy chủ.</p>
          <input
            type="file"
            accept="application/json,.json"
            aria-label="Chọn file replay"
            onChange={async (e) => {
              const file = e.currentTarget.files?.[0];
              setError(undefined);
              if (!file) return;
              try {
                if (file.size > MAX_REPLAY_BYTES) throw new Error('File replay quá lớn.');
                const data = validate<Replay>('Replay', JSON.parse(await readText(file)));
                setReplay({ name: file.name, data });
              } catch (err) {
                setReplay(undefined);
                // A TypeError here is not a network failure; errorText would say so.
                setError(
                  err instanceof SyntaxError
                    ? new Error('File không phải JSON hợp lệ.')
                    : err instanceof TypeError
                      ? new Error('Không đọc được file replay.')
                      : err,
                );
              }
            }}
          />
          <ErrorBox error={error} />
        </section>
      </div>
      {replay && (
        <section className="card">
          <h2>{replay.name}</h2>
          <ReplayViewer replay={replay.data} mode="participant" />
        </section>
      )}
    </>
  );
}
