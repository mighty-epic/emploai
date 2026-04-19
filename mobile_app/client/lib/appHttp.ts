import { describeError, logDiagnostic } from './diagnostics';

type JsonRequestOptions = {
  scope: string;
  url: string;
  init?: RequestInit;
  timeoutMs?: number;
};

class AppRequestError extends Error {
  status?: number;
  url: string;

  constructor(message: string, url: string, status?: number) {
    super(message);
    this.name = 'AppRequestError';
    this.url = url;
    this.status = status;
  }
}

function maskHeaderValue(key: string, value: string) {
  if (key.toLowerCase() !== 'authorization') {
    return value;
  }
  if (!value.startsWith('Bearer ')) {
    return '***';
  }
  const token = value.slice('Bearer '.length);
  if (token.length <= 8) {
    return 'Bearer ***';
  }
  return `Bearer ${token.slice(0, 4)}...${token.slice(-4)}`;
}

function summarizeHeaders(headers?: HeadersInit) {
  if (!headers) return undefined;

  const summary: Record<string, string> = {};
  if (Array.isArray(headers)) {
    for (const [key, value] of headers) {
      summary[key] = maskHeaderValue(key, String(value));
    }
    return summary;
  }

  if (headers instanceof Headers) {
    headers.forEach((value, key) => {
      summary[key] = maskHeaderValue(key, value);
    });
    return summary;
  }

  for (const [key, value] of Object.entries(headers)) {
    if (typeof value === 'undefined') continue;
    summary[key] = maskHeaderValue(key, String(value));
  }
  return summary;
}

function summarizeBody(body?: BodyInit | null) {
  if (!body) return undefined;
  if (typeof body === 'string') {
    return body.length > 240 ? `${body.slice(0, 240)}...` : body;
  }
  if (typeof FormData !== 'undefined' && body instanceof FormData) {
    return 'FormData payload';
  }
  if (body instanceof URLSearchParams) {
    return body.toString();
  }
  return body.constructor?.name || typeof body;
}

function previewText(text: string, maxLength = 360) {
  const normalized = text.replace(/\s+/g, ' ').trim();
  if (!normalized) return '';
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength)}...`;
}

function parseJsonText(text: string) {
  if (!text.trim()) return null;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

function detailFromPayload(payload: any, fallback: string) {
  if (payload && typeof payload === 'object') {
    const detail = payload.detail || payload.message || payload.error;
    if (typeof detail === 'string' && detail.trim()) {
      return detail.trim();
    }
  }
  return fallback;
}

function tracebackFromPayload(payload: any) {
  if (payload && typeof payload === 'object' && typeof payload.traceback === 'string') {
    return previewText(payload.traceback, 1200);
  }
  return undefined;
}

function isAbortLikeError(error: unknown) {
  if (!(error instanceof Error)) {
    return false;
  }
  if (error.name === 'AbortError') {
    return true;
  }
  return /aborted/i.test(error.message);
}

export async function requestJson<T>({ scope, url, init, timeoutMs = 15000 }: JsonRequestOptions): Promise<T> {
  const method = (init?.method || 'GET').toUpperCase();
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : undefined;
  const timeout = controller
    ? setTimeout(() => controller.abort(), timeoutMs)
    : null;

  logDiagnostic(scope, `${method} ${url} started`, {
    headers: summarizeHeaders(init?.headers),
    body: summarizeBody(init?.body),
    timeoutMs,
  });

  try {
    const response = await fetch(url, {
      ...init,
      signal: controller?.signal,
    });
    const text = await response.text();
    const payload = parseJsonText(text);
    const responsePreview = previewText(text);
    const tracebackPreview = tracebackFromPayload(payload);

    logDiagnostic(scope, `${method} ${url} responded`, {
      status: response.status,
      ok: response.ok,
      body: responsePreview || '<empty>',
      traceback: tracebackPreview,
    });

    if (!response.ok) {
      const detail = detailFromPayload(payload, responsePreview || 'HTTP error');
      throw new AppRequestError(
        `${method} ${url} failed with ${response.status}: ${detail}${tracebackPreview ? ' (see Diagnostics for traceback)' : ''}`,
        url,
        response.status,
      );
    }

    if (payload === undefined) {
      throw new AppRequestError(
        `${method} ${url} returned a non-JSON response`,
        url,
        response.status,
      );
    }

    return payload as T;
  } catch (error) {
    const rawMessage = describeError(error);
    const timedOut = isAbortLikeError(error);
    const hint = timedOut
      ? `The request did not finish within ${timeoutMs}ms. The server may still be working, or the device may not be receiving the response.`
      : rawMessage.includes('Network request failed')
      ? 'Check phone-browser access to this URL, Windows firewall, same-network routing, and Android cleartext support for http:// URLs.'
      : undefined;
    const message = error instanceof AppRequestError
      ? error.message
      : timedOut
        ? `${method} ${url} timed out after ${timeoutMs}ms`
        : `${method} ${url} failed: ${rawMessage}`;
    logDiagnostic(scope, `${method} ${url} failed`, { message, hint }, 'error');
    throw new Error(hint ? `${message} ${hint}` : message);
  } finally {
    if (timeout) {
      clearTimeout(timeout);
    }
  }
}
