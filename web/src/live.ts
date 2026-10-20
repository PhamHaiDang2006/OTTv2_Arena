import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { refresh, session } from './api';
import type { User, WsServer } from '../../contracts/generated/types';
import { validate } from '../shared/schema';
export function useLive(user: User | null) {
  const cache = useQueryClient();
  const [online, setOnline] = useState(false);
  useEffect(() => {
    let stopped = false,
      timer: ReturnType<typeof setTimeout>,
      heartbeat: ReturnType<typeof setInterval>;
    let socket: WebSocket | undefined,
      attempts = 0;
    const seen = new Set<string>();
    const connect = () => {
      if (stopped) return;
      const url =
        import.meta.env.VITE_WS_URL ||
        `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`;
      socket = new WebSocket(url);
      const send = (message: object) =>
        socket?.readyState === WebSocket.OPEN && socket.send(JSON.stringify(message));
      socket.onopen = () => {
        attempts = 0;
        setOnline(true);
        void cache.invalidateQueries();
        send({ type: 'subscribe', channel: 'public' });
        if (session.token()) send({ type: 'auth', access_token: session.token() });
        heartbeat = setInterval(() => send({ type: 'ping' }), 25000);
      };
      socket.onmessage = (event) => {
        let frame: WsServer;
        try {
          frame = validate('WsServer', JSON.parse(event.data));
        } catch {
          return;
        }
        if (frame.type === 'auth.ok' && user?.team_id)
          send({ type: 'subscribe', channel: `team:${user.team_id}` });
        if ('event_id' in frame && !seen.has(frame.event_id)) {
          seen.add(frame.event_id);
          if (seen.size > 500) seen.delete(seen.values().next().value!);
          void cache.invalidateQueries();
        }
      };
      socket.onclose = async (event) => {
        clearInterval(heartbeat);
        setOnline(false);
        if (stopped) return;
        if (event.code === 4401) {
          try {
            await refresh();
          } catch {
            return;
          }
        }
        if (!stopped)
          timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** attempts++) + Math.random() * 500);
      };
      socket.onerror = () => socket?.close();
    };
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      clearInterval(heartbeat);
      socket?.close();
    };
  }, [user?.id, cache]);
  return online;
}
