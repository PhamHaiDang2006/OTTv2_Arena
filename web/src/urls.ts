export const participantUrl = import.meta.env.DEV ? `${location.protocol}//${location.hostname}:5173/` : '/';
export const adminUrl = import.meta.env.DEV
  ? `${location.protocol}//${location.hostname}:5174/admin/`
  : '/admin/';
