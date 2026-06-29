export type ToolPackDefinition = {
  id: string;
  label: string;
  description: string;
};

export type ToolPackLockSession = {
  id: string;
  name?: string | null;
};

export const TOOL_PACK_DEFINITIONS: ToolPackDefinition[] = [
  {
    id: 'interactive_desktop',
    label: 'Interactive Desktop',
    description: 'Vision, OCR, clicking, typing, windows, and browser-extension actions.',
  },
  {
    id: 'browser_isolated',
    label: 'Isolated Browser',
    description: 'Selenium-style browser automation without using the live desktop.',
  },
  {
    id: 'workspace_write',
    label: 'Workspace Write',
    description: 'Editing files and running mutating workspace commands.',
  },
  {
    id: 'workspace_read',
    label: 'Workspace Read',
    description: 'Reading files, searching code, tests, diffs, and safe shell reads.',
  },
  {
    id: 'web_research',
    label: 'Web Research',
    description: 'Search and fetch external documentation or websites.',
  },
  {
    id: 'scheduler',
    label: 'Scheduler',
    description: 'Automations, recurring tasks, run-now, and event inspection.',
  },
  {
    id: 'app_runtime',
    label: 'App Runtime',
    description: 'Session and runtime controls that are safe for this chat.',
  },
];

const DEFAULT_TOOL_PACK_IDS = TOOL_PACK_DEFINITIONS.map((item) => item.id);

export function defaultToolPackIds() {
  return [...DEFAULT_TOOL_PACK_IDS];
}

export function toolPackLabel(packId: string) {
  return TOOL_PACK_DEFINITIONS.find((item) => item.id === packId)?.label || packId;
}

export function toggleToolPackId(enabledPackIds: string[] | null | undefined, packId: string) {
  const current = Array.isArray(enabledPackIds) ? enabledPackIds : DEFAULT_TOOL_PACK_IDS;
  return current.includes(packId)
    ? current.filter((item) => item !== packId)
    : [...current, packId];
}

export function enabledToolPackIdsFrom(...candidates: Array<string[] | null | undefined>) {
  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length > 0) {
      return [...candidate];
    }
  }
  return defaultToolPackIds();
}

export function availableToolPackIdsFrom(...candidates: Array<string[] | null | undefined>) {
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      return [...candidate];
    }
  }
  return defaultToolPackIds();
}

export function formatToolPackLockReason(reason: string | null | undefined, sessions: ToolPackLockSession[] = []) {
  const text = String(reason || '').trim();
  if (!text) {
    return null;
  }
  return text.replace(/\bchat\s+([A-Za-z0-9_-]{4,})\b/g, (match, ownerSessionId: string) => {
    const owner = sessions.find((item) => item.id === ownerSessionId);
    const ownerName = String(owner?.name || '').trim();
    return ownerName ? `chat "${ownerName}"` : match;
  });
}
