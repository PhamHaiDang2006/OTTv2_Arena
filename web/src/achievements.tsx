import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { collectCasualTraining, loadGames } from './casual-engine';
import { collectSpecialTraining, listSpecial } from './special-engine';
import {
  readTraining,
  trainingAwards,
  trainingMaps,
  trainingNames,
  difficulties,
  difficultyNames,
  mapCells,
  progressEvent,
  progressPrefix,
  type TrainingProgress,
} from './training-progress';
import { ErrorBox, Heading } from './ui';
import './achievements.css';

export function Achievements({ userId }: { userId: string }) {
  const [progress, setProgress] = useState<TrainingProgress>(),
    [error, setError] = useState<unknown>();
  useEffect(() => {
    const refresh = () => {
      try {
        setProgress(readTraining(userId));
      } catch (e) {
        setError(e);
      }
    };
    // Existing games still on this device can contribute; deleted histories cannot be recovered.
    setError(undefined);
    try {
      for (const game of loadGames(userId)) collectCasualTraining(userId, game);
      for (const game of listSpecial(userId)) collectSpecialTraining(userId, game);
    } catch {
      setError(new Error('Không đọc được toàn bộ lịch sử luyện tập trên trình duyệt này.'));
    }
    refresh();
    const storage = (e: StorageEvent) => {
      if (e.key === null || e.key.startsWith(progressPrefix(userId))) refresh();
    };
    const local = (e: Event) => {
      if ((e as CustomEvent).detail === userId) refresh();
    };
    window.addEventListener('storage', storage);
    window.addEventListener(progressEvent, local);
    return () => {
      window.removeEventListener('storage', storage);
      window.removeEventListener(progressEvent, local);
    };
  }, [userId]);
  const awards = progress ? trainingAwards(progress) : [];
  return (
    <section className="achievements">
      <Heading
        eyebrow="OTT v2 / BỘ SƯU TẬP"
        title="Thành tích luyện tập"
        description="7 thử thách dành cho hành trình đấu máy của bạn."
      />
      <p className="card">
        Tiến độ cá nhân lưu trên trình duyệt này, riêng theo tài khoản. Chưa đồng bộ lên server hoặc công khai
        trên hồ sơ. Xóa dữ liệu trình duyệt sẽ xóa tiến độ.
      </p>
      <ErrorBox error={error} />
      {progress && (
        <>
          <p role="status">Đã mở {awards.filter((a) => a.value === a.total).length}/7 thành tích</p>
          <div className="achievement-grid">
            {awards.map((a) => (
              <article key={a.id} className={`card achievement ${a.value === a.total ? 'unlocked' : ''}`}>
                <span className="achievement-medal" aria-hidden="true">
                  {a.value === a.total ? '★' : '◇'}
                </span>
                <h2>{a.title}</h2>
                <p>{a.description}</p>
                <strong>
                  {a.value === a.total ? 'Đã mở khóa' : 'Đang khám phá'} · {a.value}/{a.total}
                </strong>
                <progress aria-label={a.title} value={a.value} max={a.total} />
              </article>
            ))}
          </div>
          <section className="card">
            <h2>Đánh bại bot · 9 mốc</h2>
            <table>
              <thead>
                <tr>
                  <th>Bản đồ</th>
                  {difficulties.map((bot) => (
                    <th key={bot}>{difficultyNames[bot]}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trainingMaps.map((map) => (
                  <tr key={map}>
                    <th>{trainingNames[map]}</th>
                    {difficulties.map((bot) => (
                      <td key={bot}>{progress[map].wins.includes(bot) ? '✓ Đã thắng' : 'Chưa thắng'}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="card">
            <h2>Nhật ký khám phá</h2>
            <p>
              Chỉ tính ô đích của nước người chơi đi, không tính vị trí xuất phát hoặc nước của máy. Hãy chơi
              cả Xanh và Đỏ để ghé đủ hai ô đích. Xem replay không tăng tiến độ.
            </p>
            {trainingMaps.map((map) => (
              <details key={map}>
                <summary>
                  {trainingNames[map]} · {progress[map].visited.length}/{mapCells(map).length} ô
                </summary>
                <div className={`exploration-map map-${map}`}>
                  {mapCells(map).map((cell) => (
                    <span
                      key={cell}
                      className={progress[map].visited.includes(cell) ? 'visited' : ''}
                      title={`${cell}: ${progress[map].visited.includes(cell) ? 'đã tới' : 'chưa tới'}`}
                    >
                      {cell}
                    </span>
                  ))}
                </div>
                <small>
                  {map === 'standard'
                    ? 'Tọa độ a1–i9.'
                    : map === 'hexagon'
                      ? 'Tọa độ axial q,r của Hexagon.'
                      : 'Tọa độ sector,vòng; sector 0–23 và vòng 0–3.'}
                </small>
              </details>
            ))}
          </section>
          <div className="achievement-actions">
            <Link className="primary" to="/casual">
              Chơi Casual
            </Link>
            <Link className="primary" to="/special">
              Khám phá bản đồ
            </Link>
            <Link to="/profile">Hồ sơ của tôi</Link>
          </div>
        </>
      )}
    </section>
  );
}
