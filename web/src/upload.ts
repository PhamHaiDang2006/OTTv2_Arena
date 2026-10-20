/** Fetch adapter: canonical client still owns the URL, body and headers. */
export function uploadFetch(onProgress: (percent: number) => void): typeof fetch {
  return (input, init) =>
    new Promise<Response>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open(init?.method ?? 'POST', String(input));
      xhr.withCredentials = true;
      new Headers(init?.headers).forEach((value, key) => xhr.setRequestHeader(key, value));
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
      };
      const abort = () => xhr.abort();
      const clean = () => init?.signal?.removeEventListener('abort', abort);
      xhr.onload = () => {
        clean();
        resolve(new Response(xhr.status === 204 ? null : xhr.responseText, { status: xhr.status }));
      };
      xhr.onerror = () => {
        clean();
        reject(new TypeError('Upload network failure'));
      };
      xhr.onabort = () => {
        clean();
        reject(new DOMException('Aborted', 'AbortError'));
      };
      if (init?.signal?.aborted) {
        reject(new DOMException('Aborted', 'AbortError'));
        return;
      }
      init?.signal?.addEventListener('abort', abort);
      onProgress(0);
      xhr.send(init?.body as XMLHttpRequestBodyInit);
    });
}
