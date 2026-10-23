import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { CasualPlay } from '../src/casual';
import { newGame, playMove, resign, saveGame, loadGames } from '../src/casual-engine';
import { initializeTheme, ThemeSwitch, useGameSound } from '../src/preferences';
import { historyFrame } from '../src/casual-presentation';
import type { User } from '../../contracts/generated/types';

const user: User = {
  id: 'polish-user',
  email: 'polish@example.test',
  role: 'member',
  team_id: null,
  is_active: true,
};
beforeEach(() => {
  localStorage.clear();
  document.documentElement.dataset.theme = 'light';
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function open(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/casual/${id}`]}>
      <Routes>
        <Route path="/casual/:id" element={<CasualPlay user={user} />} />
        <Route path="/casual" element={<p>Sảnh Casual</p>} />
      </Routes>
    </MemoryRouter>,
  );
}
it('persists theme and synchronizes a change from another tab', () => {
  localStorage.setItem('ottv2.theme', 'dark');
  initializeTheme();
  render(<ThemeSwitch />);
  expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('true');
  fireEvent.click(screen.getByRole('switch'));
  expect(document.documentElement.dataset.theme).toBe('light');
  expect(localStorage.getItem('ottv2.theme')).toBe('light');
  localStorage.setItem('ottv2.theme', 'dark');
  fireEvent(window, new StorageEvent('storage', { key: 'ottv2.theme', newValue: 'dark' }));
  expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('true');
});
it('shows the intermediate human move, locks interaction, then shows the bot reply', async () => {
  const game = newGame('BLUE', 'random');
  saveGame(user.id, game);
  open(game.id);
  fireEvent.click(screen.getByRole('button', { name: /^c3:/ }));
  fireEvent.click(screen.getByRole('button', { name: /^d4:/ }));
  await screen.findByText('Máy đang đi…');
  expect(loadGames(user.id)[0].ply).toBe(2); // atomic save already finished, animation is presentation only
  expect((screen.getByRole('button', { name: /^d4:/ }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('button', { name: /^d4:/ }).querySelector('.piece-moving')).toBeTruthy();
  await waitFor(() => expect(screen.getByRole('status').textContent).toBe('Đến lượt của bạn'), {
    timeout: 2500,
  });
});
it('skips delayed animation with reduced motion', async () => {
  vi.stubGlobal('matchMedia', () => ({
    matches: true,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  const game = newGame('BLUE', 'random');
  saveGame(user.id, game);
  open(game.id);
  fireEvent.click(screen.getByRole('button', { name: /^c3:/ }));
  fireEvent.click(screen.getByRole('button', { name: /^d4:/ }));
  await waitFor(() => expect(loadGames(user.id)[0].ply).toBe(2));
  expect(screen.queryByText('Máy đang đi…')).toBeNull();
  expect(screen.getByRole('status').textContent).toBe('Đến lượt của bạn');
});
it('reviews a finished game without changing storage then replays with the same settings', async () => {
  const finished = resign(playMove(newGame('RED', 'greedy'), 'a7a6'));
  saveGame(user.id, finished);
  open(finished.id);
  expect(screen.getByRole('dialog')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Xem lại ván' }));
  fireEvent.change(screen.getByLabelText('Nước xem lại'), { target: { value: '0' } });
  expect(screen.getByRole('status').textContent).toContain('Nước 0/');
  expect(loadGames(user.id)[0]).toEqual(finished);
  expect(historyFrame(finished, 0).moves).toHaveLength(0);
  fireEvent.click(screen.getByText('Xem kết quả'));
  fireEvent.click(screen.getByRole('button', { name: 'Chơi lại' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  await screen.findByText('Đến lượt của bạn');
  const next = loadGames(user.id).find((g) => g.id !== finished.id)!;
  expect([next.bot, next.human_side, next.ply]).toEqual(['greedy', 'RED', 1]);
});
it('shows victory celebration and exits to lobby', () => {
  const game = { ...resign(newGame('BLUE', 'random')), winner: 'BLUE' as const, reason: 'GOAL' as const };
  saveGame(user.id, game);
  open(game.id);
  expect(screen.getByRole('heading', { name: 'Chiến thắng!' })).toBeTruthy();
  expect(screen.getByRole('dialog').querySelector('.confetti')).toBeTruthy();
  fireEvent.click(screen.getByRole('dialog').querySelectorAll('button')[2]);
  expect(screen.getByText('Sảnh Casual')).toBeTruthy();
});
it('uses different sounds for capture and move and respects mute', () => {
  const frequency = vi.fn();
  class FakeAudio {
    state = 'running';
    currentTime = 0;
    destination = {};
    resume = () => Promise.resolve();
    createOscillator() {
      return {
        type: '',
        frequency: {
          set value(value: number) {
            frequency(value);
          },
        },
        connect: vi.fn(),
        disconnect: vi.fn(),
        start: vi.fn(),
        stop: vi.fn(),
      };
    }
    createGain() {
      return {
        gain: {
          setValueAtTime: vi.fn(),
          linearRampToValueAtTime: vi.fn(),
          exponentialRampToValueAtTime: vi.fn(),
        },
        connect: vi.fn(),
        disconnect: vi.fn(),
      };
    }
  }
  vi.stubGlobal('AudioContext', FakeAudio);
  function Sound() {
    const sound = useGameSound();
    return (
      <>
        <button onClick={sound.toggle}>Toggle</button>
        <button onClick={() => sound.play(false)}>Move</button>
        <button onClick={() => sound.play(true)}>Capture</button>
      </>
    );
  }
  render(<Sound />);
  fireEvent.click(screen.getByText('Move'));
  expect(frequency).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('Toggle'));
  fireEvent.click(screen.getByText('Move'));
  expect(frequency).toHaveBeenCalledWith(520);
  frequency.mockClear();
  fireEvent.click(screen.getByText('Capture'));
  expect(frequency.mock.calls.flat()).toEqual([440, 660, 880]);
  fireEvent.click(screen.getByText('Toggle'));
  frequency.mockClear();
  fireEvent.click(screen.getByText('Capture'));
  expect(frequency).not.toHaveBeenCalled();
});
