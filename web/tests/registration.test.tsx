import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { Login } from '../src/auth-page';
import { session } from '../src/api';
import auth from '../../contracts/examples/http/register.response.json';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  session.set(null);
});
function openRegistration() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Login />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByText('Chưa có tài khoản? Đăng ký'));
  for (const [label, value] of [
    ['Tên đội', 'Đội mới'],
    ['Email', 'new@example.test'],
    ['Mật khẩu', 'password123'],
    ['Nhập lại mật khẩu', 'password123'],
  ]) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
}
it('registers with the canonical endpoint and starts a session', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(auth), { status: 201 }));
  vi.stubGlobal('fetch', fetch);
  openRegistration();
  fireEvent.click(screen.getByText('Đăng ký và vào đấu trường →'));
  await waitFor(() => expect(session.user()?.id).toBe(auth.user.id));
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).toBe('/api/v1/auth/register');
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
    email: 'new@example.test',
    password: 'password123',
    team_name: 'Đội mới',
  });
});
it('blocks mismatched passwords before sending', async () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  openRegistration();
  fireEvent.change(screen.getByLabelText('Nhập lại mật khẩu'), { target: { value: 'different123' } });
  fireEvent.click(screen.getByText('Đăng ký và vào đấu trường →'));
  expect(await screen.findByText('Hai mật khẩu chưa khớp nhau.')).toBeTruthy();
  expect(fetch).not.toHaveBeenCalled();
});
it('shows duplicate email errors without a session or automatic retries', async () => {
  const fetch = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        error: { code: 'STATE_CONFLICT', message: 'Email đã được sử dụng.', details: {} },
        request_id: 'test',
      }),
      { status: 409 },
    ),
  );
  vi.stubGlobal('fetch', fetch);
  openRegistration();
  fireEvent.click(screen.getByText('Đăng ký và vào đấu trường →'));
  expect(await screen.findByText(/Email đã được sử dụng/)).toBeTruthy();
  expect(session.user()).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(1);
});
it('does not offer self-registration in the admin portal', () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Login admin />
    </QueryClientProvider>,
  );
  expect(screen.queryByText('Chưa có tài khoản? Đăng ký')).toBeNull();
});
