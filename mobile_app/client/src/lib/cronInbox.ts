import * as SecureStore from 'expo-secure-store';

import type { CronFeedItem } from '@/lib/appApi';

const CRON_LAST_SEEN_ID_KEY = 'emploai.cron.lastSeenId';
const CRON_LAST_SEEN_TIMESTAMP_KEY = 'emploai.cron.lastSeenTimestamp';

type CronSeenMarker = {
  id: string;
  timestamp: string;
};

export async function loadCronSeenMarker(): Promise<CronSeenMarker | null> {
  const [id, timestamp] = await Promise.all([
    SecureStore.getItemAsync(CRON_LAST_SEEN_ID_KEY),
    SecureStore.getItemAsync(CRON_LAST_SEEN_TIMESTAMP_KEY),
  ]);

  if (!id && !timestamp) {
    return null;
  }

  return {
    id: (id || '').trim(),
    timestamp: (timestamp || '').trim(),
  };
}

export async function markCronFeedSeen(feed: CronFeedItem[]): Promise<void> {
  const latest = feed[0];
  if (!latest) {
    return;
  }

  await Promise.all([
    SecureStore.setItemAsync(CRON_LAST_SEEN_ID_KEY, String(latest.id || '')),
    SecureStore.setItemAsync(CRON_LAST_SEEN_TIMESTAMP_KEY, String(latest.timestamp || '')),
  ]);
}

export async function getUnreadCronCount(feed: CronFeedItem[]): Promise<number> {
  if (!feed.length) {
    return 0;
  }

  const marker = await loadCronSeenMarker();
  if (!marker) {
    return feed.length;
  }

  if (marker.id) {
    const seenIndex = feed.findIndex((item) => item.id === marker.id);
    if (seenIndex >= 0) {
      return seenIndex;
    }
  }

  if (marker.timestamp) {
    const seenTime = Date.parse(marker.timestamp);
    if (!Number.isNaN(seenTime)) {
      return feed.filter((item) => {
        const itemTime = Date.parse(String(item.timestamp || ''));
        return !Number.isNaN(itemTime) && itemTime > seenTime;
      }).length;
    }
  }

  return feed.length;
}
