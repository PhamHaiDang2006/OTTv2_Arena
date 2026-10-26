import { useEffect, useRef, useState } from 'react';

function stored(key: string, fallback: string) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}
function persist(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* Preferences still work for this visit. */
  }
}
export function initializeTheme() {
  document.documentElement.dataset.boardSkin =
    stored('ottv2.board-skin', 'wood') === 'classic' ? 'classic' : 'wood';
  const theme = stored(
    'ottv2.theme',
    window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
  );
  document.documentElement.dataset.theme = theme === 'dark' ? 'dark' : 'light';
}
export function BoardSkinSwitch() {
  const [skin, setSkin] = useState(() => document.documentElement.dataset.boardSkin ?? 'wood');
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === 'ottv2.board-skin' || event.key === null) {
        const next = stored('ottv2.board-skin', 'wood') === 'classic' ? 'classic' : 'wood';
        document.documentElement.dataset.boardSkin = next;
        setSkin(next);
      }
    };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);
  return (
    <label className="board-skin-control">
      Bàn & quân{' '}
      <select
        aria-label="Giao diện bàn và quân"
        value={skin}
        onChange={(event) => {
          const next = event.target.value;
          setSkin(next);
          document.documentElement.dataset.boardSkin = next;
          persist('ottv2.board-skin', next);
        }}
      >
        <option value="wood">Gỗ</option>
        <option value="classic">Nguyên bản</option>
      </select>
    </label>
  );
}
export function ThemeSwitch() {
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === 'dark');
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === 'ottv2.theme' || event.key === null) {
        initializeTheme();
        setDark(document.documentElement.dataset.theme === 'dark');
      }
    };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);
  return (
    <button
      type="button"
      role="switch"
      aria-label="Nền tối"
      aria-checked={dark}
      className="theme-switch"
      onClick={() => {
        const next = !dark;
        setDark(next);
        document.documentElement.dataset.theme = next ? 'dark' : 'light';
        persist('ottv2.theme', next ? 'dark' : 'light');
      }}
    >
      <span aria-hidden="true">{dark ? '☾' : '☀'}</span> {dark ? 'Nền tối' : 'Nền sáng'}
    </button>
  );
}
export function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
  );
  useEffect(() => {
    const media = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!media) return;
    const sync = () => setReduced(media.matches);
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);
  return reduced;
}
let context: AudioContext | undefined;
export function useGameSound() {
  const [enabled, setEnabled] = useState(() => stored('ottv2.sound', 'off') === 'on');
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  function unlock() {
    try {
      context ??= new AudioContext();
      void context.resume().catch(() => {});
    } catch {
      /* Audio optional. */
    }
  }
  return {
    enabled,
    toggle() {
      const next = !enabled;
      setEnabled(next);
      persist('ottv2.sound', next ? 'on' : 'off');
      if (next) unlock();
    },
    unlock() {
      if (enabled) unlock();
    },
    play(capture: boolean) {
      if (!enabledRef.current || !context || context.state !== 'running') return;
      try {
        const audio = context;
        (capture ? [440, 660, 880] : [520]).forEach((frequency, i) => {
          const oscillator = audio.createOscillator(),
            gain = audio.createGain();
          const start = audio.currentTime + i * 0.055;
          oscillator.type = 'sine';
          oscillator.frequency.value = frequency;
          gain.gain.setValueAtTime(0, start);
          gain.gain.linearRampToValueAtTime(0.055, start + 0.01);
          gain.gain.exponentialRampToValueAtTime(0.001, start + 0.12);
          oscillator.connect(gain);
          gain.connect(audio.destination);
          oscillator.onended = () => {
            oscillator.disconnect();
            gain.disconnect();
          };
          oscillator.start(start);
          oscillator.stop(start + 0.14);
        });
      } catch {
        /* A sound failure must never block a move. */
      }
    },
  };
}
