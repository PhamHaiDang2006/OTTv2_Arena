/** Local, unverified training progress. Independent marker keys make cross-tab unions lossless. */
export type TrainingMap = 'standard' | 'hexagon' | 'circular';
export type Difficulty = 'random' | 'greedy' | 'hard';
export const trainingMaps: TrainingMap[] = ['standard', 'hexagon', 'circular'];
export const difficulties: Difficulty[] = ['random', 'greedy', 'hard'];
export const trainingNames = { standard: 'Casual 9×9', hexagon: 'Hexagon', circular: 'Annulus' };
export const difficultyNames = { random: 'Dễ', greedy: 'Trung bình', hard: 'Khó' };
export const progressEvent = 'ottv2-training-progress';
export const progressPrefix = (user: string) => `ottv2.training.v1:${user}:`;
export function mapCells(map: TrainingMap): string[] {
  if (map === 'standard')
    return Array.from({ length: 81 }, (_, i) => String.fromCharCode(97 + (i % 9)) + (Math.floor(i / 9) + 1));
  if (map === 'circular') return Array.from({ length: 96 }, (_, i) => `${Math.floor(i / 4)},${i % 4}`);
  const ids: string[] = [];
  for (let q = -5; q <= 5; q++)
    for (let r = -5; r <= 5; r++)
      if (Math.max(Math.abs(q), Math.abs(r), Math.abs(q + r)) <= 5) ids.push(`${q},${r}`);
  return ids;
}
export type TrainingProgress = Record<TrainingMap, { visited: string[]; wins: Difficulty[] }>;
export function readTraining(user: string): TrainingProgress {
  const prefix = progressPrefix(user);
  return Object.fromEntries(
    trainingMaps.map((map) => [
      map,
      {
        visited: mapCells(map).filter(
          (cell) => localStorage.getItem(`${prefix}${map}:visit:${cell}`) === '1',
        ),
        wins: difficulties.filter((bot) => localStorage.getItem(`${prefix}${map}:win:${bot}`) === '1'),
      },
    ]),
  ) as TrainingProgress;
}
export function recordTraining(user: string, map: TrainingMap, visits: string[], won?: Difficulty) {
  const prefix = `${progressPrefix(user)}${map}:`,
    allowed = new Set(mapCells(map));
  let changed = false;
  for (const key of [...new Set(visits)]
    .filter((cell) => allowed.has(cell))
    .map((cell) => `visit:${cell}`)
    .concat(won && difficulties.includes(won) ? [`win:${won}`] : [])) {
    if (localStorage.getItem(prefix + key) !== '1') {
      localStorage.setItem(prefix + key, '1');
      changed = true;
    }
  }
  if (changed) window.dispatchEvent(new CustomEvent(progressEvent, { detail: user }));
}
export function trainingAwards(progress: TrainingProgress) {
  const awards = trainingMaps.flatMap((map) => [
    {
      id: `explore-${map}`,
      title: `Nhà thám hiểm ${trainingNames[map]}`,
      value: progress[map].visited.length,
      total: mapCells(map).length,
      description: 'Đưa quân của bạn đi tới mọi ô, cộng dồn qua nhiều ván và cả hai màu quân.',
    },
    {
      id: `master-${map}`,
      title: `Chinh phục ${trainingNames[map]}`,
      value: progress[map].wins.length,
      total: 3,
      description: 'Thắng bot Dễ, Trung bình và Khó trên bản đồ này.',
    },
  ]);
  awards.push({
    id: 'master-all',
    title: 'Bậc thầy ba bản đồ',
    value: trainingMaps.reduce((n, map) => n + progress[map].wins.length, 0),
    total: 9,
    description: 'Hoàn thành cả 9 tổ hợp bản đồ × độ khó.',
  });
  return awards;
}
