import { useEffect, useState } from 'react';
export function Countdown({ until }: { until: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.floor((Date.parse(until) - now) / 1000));
  return (
    <strong>
      {seconds
        ? `${Math.floor(seconds / 3600)} giờ ${Math.floor((seconds % 3600) / 60)} phút ${seconds % 60} giây`
        : 'Đã đến giờ đóng băng'}
    </strong>
  );
}
