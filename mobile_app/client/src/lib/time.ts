export function formatRelativeTime(value?: string | null) {
  if (!value) return 'unknown';

  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;

  const diffMs = timestamp - Date.now();
  const absMs = Math.abs(diffMs);
  const future = diffMs >= 0;

  if (absMs < 45_000) {
    return future ? 'in a moment' : 'just now';
  }

  const units: Array<[number, string]> = [
    [1000 * 60 * 60 * 24, 'd'],
    [1000 * 60 * 60, 'h'],
    [1000 * 60, 'm'],
  ];

  for (const [unitMs, label] of units) {
    if (absMs >= unitMs) {
      const amount = Math.round(absMs / unitMs);
      return future ? `in ${amount}${label}` : `${amount}${label} ago`;
    }
  }

  const seconds = Math.max(1, Math.round(absMs / 1000));
  return future ? `in ${seconds}s` : `${seconds}s ago`;
}

export function formatAbsoluteTime(value?: string | null) {
  if (!value) return 'unknown';

  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;

  const date = new Date(timestamp);
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  const hours = `${date.getHours()}`.padStart(2, '0');
  const minutes = `${date.getMinutes()}`.padStart(2, '0');
  return `${month}/${day} ${hours}:${minutes}`;
}
