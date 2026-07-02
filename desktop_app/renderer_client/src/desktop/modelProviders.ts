import type { ModelProviderGroup } from '@/lib/appApi';

export const MODEL_PROVIDER_PRIORITY = ['openai', 'openai-codex', 'anthropic', 'google', 'xai', 'deepseek', 'nvidia', 'openrouter'];

export const MODEL_PROVIDER_DEFAULTS: Record<string, string[]> = {
  openai: ['gpt-5.4-mini'],
  'openai-codex': ['chatgpt/gpt-5.5', 'chatgpt/gpt-5.4-mini'],
  anthropic: ['claude-sonnet-4.5'],
  google: ['gemini-3.5-flash'],
  nvidia: ['mistralai/ministral-14b-instruct-2512'],
};

const NVIDIA_MODEL_PREFIXES = [
  '01-ai/',
  'abacusai/',
  'ai21labs/',
  'aisingapore/',
  'bigcode/',
  'bytedance/',
  'databricks/',
  'deepseek-ai/',
  'google/codegemma',
  'google/diffusiongemma',
  'google/gemma',
  'google/recurrentgemma',
  'ibm/granite',
  'meta/codellama',
  'meta/llama',
  'microsoft/phi',
  'minimaxai/',
  'mistralai/',
  'moonshotai/',
  'nv-mistralai/',
  'nvidia/',
  'openai/gpt-oss',
  'qwen/',
  'sarvamai/',
  'stepfun-ai/',
  'stockmark/',
  'upstage/',
  'writer/palmyra-creative',
  'z-ai/',
  'zyphra/',
];

export function preferredModelFromGroups(groups: ModelProviderGroup[]) {
  for (const provider of MODEL_PROVIDER_PRIORITY) {
    const group = groups.find((item) => item.provider.toLowerCase() === provider);
    if (!group?.models?.length) {
      continue;
    }
    const preferred = MODEL_PROVIDER_DEFAULTS[provider]?.find((model) => group.models.includes(model));
    return preferred || group.models[0] || null;
  }
  return groups.find((group) => group.models.length > 0)?.models[0] || null;
}

export function modelProviderKey(provider: string | null | undefined) {
  return String(provider || '').trim().toLowerCase();
}

function uniqueModels(models: string[]) {
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const model of models) {
    const normalized = String(model || '').trim();
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    unique.push(normalized);
  }
  return unique;
}

export function filterModelGroupsByConfiguredProviders(
  candidateGroups: ModelProviderGroup[],
  configuredGroups: ModelProviderGroup[],
) {
  const configuredByProvider = new Map<string, Set<string>>();
  for (const group of configuredGroups || []) {
    const providerKey = modelProviderKey(group.provider);
    const models = uniqueModels(Array.isArray(group.models) ? group.models : []);
    if (!providerKey || models.length === 0) {
      continue;
    }
    configuredByProvider.set(providerKey, new Set(models));
  }
  if (configuredByProvider.size === 0) {
    return [];
  }

  const filtered: ModelProviderGroup[] = [];
  for (const group of candidateGroups || []) {
    const providerKey = modelProviderKey(group.provider);
    const configuredModels = configuredByProvider.get(providerKey);
    if (!configuredModels) {
      continue;
    }
    const models = uniqueModels(Array.isArray(group.models) ? group.models : [])
      .filter((model) => configuredModels.has(model));
    if (models.length === 0) {
      continue;
    }
    filtered.push({ provider: group.provider, models });
  }
  return filtered;
}

export function filterModelsByConfiguredList(
  candidateModels: string[],
  configuredModels: string[],
) {
  const configured = new Set(uniqueModels(configuredModels || []));
  if (configured.size === 0) {
    return [];
  }
  return uniqueModels(candidateModels || []).filter((model) => configured.has(model));
}

export function modelExistsInGroups(
  model: string | null | undefined,
  groups: ModelProviderGroup[],
) {
  const normalized = String(model || '').trim();
  if (!normalized) {
    return false;
  }
  return (groups || []).some((group) => (
    Array.isArray(group.models) && group.models.includes(normalized)
  ));
}

export function providerForModelName(model: string, modelGroups: ModelProviderGroup[]) {
  const exactGroup = modelGroups.find((group) => group.models.includes(model));
  if (exactGroup?.provider) {
    return exactGroup.provider;
  }

  const lower = model.toLowerCase();
  if (lower.includes('claude')) return 'anthropic';
  if (lower.startsWith('chatgpt/')) return 'openai-codex';
  if (lower.includes('gemini')) return 'google';
  if (lower.includes('grok')) return 'xai';
  if (
    lower.includes('nvidia')
    || lower.includes('nemotron')
    || lower.includes('minimax')
    || lower.includes('gpt-oss')
    || NVIDIA_MODEL_PREFIXES.some((prefix) => lower.startsWith(prefix))
  ) return 'nvidia';
  if (lower.includes('deepseek')) return 'deepseek';
  if (lower.startsWith('gpt') || /^o\d/.test(lower) || lower.includes('openai')) return 'openai';
  if (lower.includes('/')) return model.split('/')[0] || 'other';
  return 'other';
}

export function groupPlannerModelsByProvider(models: string[], modelGroups: ModelProviderGroup[]) {
  const grouped = new Map<string, ModelProviderGroup>();
  for (const model of models) {
    const provider = providerForModelName(model, modelGroups);
    const key = modelProviderKey(provider);
    const existing = grouped.get(key);
    if (existing) {
      existing.models.push(model);
    } else {
      grouped.set(key, { provider, models: [model] });
    }
  }
  return Array.from(grouped.values()).sort((left, right) => {
    const leftIndex = MODEL_PROVIDER_PRIORITY.indexOf(modelProviderKey(left.provider));
    const rightIndex = MODEL_PROVIDER_PRIORITY.indexOf(modelProviderKey(right.provider));
    const normalizedLeft = leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex;
    const normalizedRight = rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex;
    if (normalizedLeft !== normalizedRight) {
      return normalizedLeft - normalizedRight;
    }
    return left.provider.localeCompare(right.provider);
  });
}
