const PAIRING_SCHEMES = new Set(['emploai:', 'kraitos:']);
const TOKEN_QUERY_KEYS = ['token', 'pairing_token', 'pairingToken'];

export function buildPairingUri(pairingToken: string) {
  const token = pairingToken.trim();
  return token ? `emploai://pair?token=${encodeURIComponent(token)}` : '';
}

export function buildPairingQrValue(pairingUri?: string | null, pairingToken?: string | null) {
  const uri = String(pairingUri || '').trim();
  if (uri) {
    return uri;
  }
  return buildPairingUri(String(pairingToken || ''));
}

function tokenFromSearchParams(params: URLSearchParams) {
  for (const key of TOKEN_QUERY_KEYS) {
    const value = String(params.get(key) || '').trim();
    if (value) {
      return value;
    }
  }
  return '';
}

function looksLikePairingToken(value: string) {
  return /^[A-Za-z0-9_-]{24,}$/.test(value);
}

function tokenFromPairingUri(candidate: string) {
  const queryIndex = candidate.indexOf('?');
  if (queryIndex < 0) {
    return '';
  }

  const prefix = candidate.slice(0, queryIndex).toLowerCase();
  const query = candidate.slice(queryIndex + 1).split('#', 1)[0] || '';
  const schemeMatch = /^([a-z][a-z0-9+.-]*):/i.exec(prefix);
  const scheme = schemeMatch ? `${schemeMatch[1].toLowerCase()}:` : '';
  const pairPath = scheme
    ? prefix.slice(scheme.length).replace(/^\/+/, '').split('/', 1)[0]
    : prefix.replace(/^\/+/, '').split('/', 1)[0];
  const pathLooksLikePairing = pairPath === 'pair' || prefix.endsWith('/pair');
  if (!PAIRING_SCHEMES.has(scheme) && !pathLooksLikePairing) {
    return '';
  }
  return tokenFromSearchParams(new URLSearchParams(query));
}

export function extractPairingTokenFromInput(input: string, options?: { allowRawToken?: boolean }) {
  const allowRawToken = options?.allowRawToken !== false;
  const cleanInput = String(input || '').trim();
  if (!cleanInput) {
    return '';
  }

  const candidates = [cleanInput];
  try {
    const decoded = decodeURIComponent(cleanInput);
    if (decoded && decoded !== cleanInput) {
      candidates.push(decoded);
    }
  } catch {
    // Not URL encoded. Keep the original candidate.
  }

  for (const candidate of candidates) {
    const uriToken = tokenFromPairingUri(candidate);
    if (uriToken) {
      return uriToken;
    }
    const queryPrefix = candidate.startsWith('?') ? candidate.slice(1) : candidate;
    const queryToken = tokenFromSearchParams(new URLSearchParams(queryPrefix));
    if (queryToken) {
      return queryToken;
    }
  }

  return allowRawToken && looksLikePairingToken(cleanInput) ? cleanInput : '';
}
