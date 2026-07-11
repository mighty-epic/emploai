import type { ModelProviderGroup } from '@/lib/appApi';

export const MODEL_PROVIDER_PRIORITY = ['openai', 'openai-codex', 'anthropic', 'google', 'xai', 'deepseek', 'nvidia', 'openrouter'];

export type ModelVariantOption = {
  id: string;
  label: string;
};

const STANDARD_VARIANT = 'standard';

const MODEL_VARIANTS: Record<string, { variants: string[]; default: string }> = {
  'claude-sonnet-4.5': { variants: ['standard', 'thinking'], default: 'standard' },
  'claude-opus-4.5': { variants: ['standard', 'thinking'], default: 'standard' },
  'claude-sonnet-4.6': { variants: ['standard', 'thinking'], default: 'standard' },
  'claude-opus-4.6': { variants: ['standard', 'thinking'], default: 'standard' },
  'claude-opus-4.7': { variants: ['standard'], default: 'standard' },
  'claude-haiku-4.5': { variants: ['standard'], default: 'standard' },
  'claude-sonnet-4': { variants: ['standard', 'thinking'], default: 'standard' },
  'claude-opus-4': { variants: ['standard', 'thinking'], default: 'standard' },
  'claude-haiku-4': { variants: ['standard'], default: 'standard' },
  'gpt-5': { variants: ['low', 'medium', 'high'], default: 'medium' },
  'gpt-5.1': { variants: ['low', 'medium', 'high'], default: 'medium' },
  'gpt-5.2': { variants: ['low', 'medium', 'high', 'xhigh'], default: 'medium' },
  'gpt-5.5': { variants: ['low', 'medium', 'high', 'xhigh'], default: 'medium' },
  'gpt-5.4': { variants: ['low', 'medium', 'high', 'xhigh'], default: 'medium' },
  'gpt-5.4-mini': { variants: ['low', 'medium', 'high', 'xhigh'], default: 'medium' },
  'chatgpt/gpt-5.5': { variants: ['low', 'medium', 'high', 'xhigh'], default: 'medium' },
  'chatgpt/gpt-5.4': { variants: ['low', 'medium', 'high', 'xhigh'], default: 'medium' },
  'chatgpt/gpt-5.4-mini': { variants: ['low', 'medium', 'high', 'xhigh'], default: 'medium' },
  'gpt-5.1-codex-max': { variants: ['low', 'medium', 'high', 'xhigh'], default: 'medium' },
  'gpt-5.2-codex': { variants: ['low', 'medium', 'high', 'xhigh'], default: 'medium' },
  'gpt-4.1': { variants: ['standard'], default: 'standard' },
  'gpt-4o': { variants: ['standard'], default: 'standard' },
  'gpt-4o-mini': { variants: ['standard'], default: 'standard' },
  'gemini-3.5-flash': { variants: ['standard', 'low', 'medium', 'high'], default: 'standard' },
  'gemini-3.1-pro-preview': { variants: ['standard', 'low', 'medium', 'high'], default: 'standard' },
  'gemini-3.1-pro-preview-customtools': { variants: ['standard', 'low', 'medium', 'high'], default: 'standard' },
  'gemini-3-flash-preview': { variants: ['standard', 'low', 'medium', 'high'], default: 'standard' },
  'gemini-3.1-flash-lite': { variants: ['standard', 'low', 'medium', 'high'], default: 'standard' },
  'gemini-2.5-pro': { variants: ['standard', 'low', 'medium', 'high'], default: 'standard' },
  'gemini-2.5-flash': { variants: ['standard', 'low', 'medium', 'high'], default: 'standard' },
  'gemini-2.5-flash-lite': { variants: ['standard', 'low', 'medium', 'high'], default: 'standard' },
  'grok-4.1-fast-reasoning': { variants: ['low', 'medium', 'high'], default: 'medium' },
  'grok-4.1-fast-non-reasoning': { variants: ['standard'], default: 'standard' },
  'grok-code-fast-1': { variants: ['standard'], default: 'standard' },
  'grok-4-fast-reasoning': { variants: ['low', 'medium', 'high'], default: 'medium' },
  'grok-4-fast-non-reasoning': { variants: ['standard'], default: 'standard' },
  'grok-4-0709': { variants: ['standard'], default: 'standard' },
  'grok-3-mini': { variants: ['standard'], default: 'standard' },
  'grok-3': { variants: ['standard'], default: 'standard' },
  'grok-2-vision-1212': { variants: ['standard'], default: 'standard' },
  'grok-2': { variants: ['standard'], default: 'standard' },
  'grok-beta': { variants: ['standard'], default: 'standard' },
  'deepseek-chat': { variants: ['standard'], default: 'standard' },
  'deepseek-reasoner': { variants: ['standard'], default: 'standard' },
  'orb-gpt-4o': { variants: ['standard'], default: 'standard' },
  'orb-claude-3.5-sonnet': { variants: ['standard'], default: 'standard' },
};

const VARIANT_ALIASES: Record<string, string> = {
  light: 'low',
};

const VARIANT_LABELS: Record<string, string> = {
  standard: 'Standard',
  low: 'Light',
  medium: 'Medium',
  high: 'High',
  xhigh: 'XHigh',
  thinking: 'Thinking',
};

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

function modelVariantInfo(model: string | null | undefined) {
  const normalized = String(model || '').trim();
  return MODEL_VARIANTS[normalized] || { variants: [STANDARD_VARIANT], default: STANDARD_VARIANT };
}

function normalizeVariantId(variant: string | null | undefined) {
  const normalized = String(variant || '').trim().toLowerCase();
  return VARIANT_ALIASES[normalized] || normalized;
}

export function modelVariantIdsForModel(model: string | null | undefined) {
  const variants = modelVariantInfo(model).variants;
  return variants.length ? variants : [STANDARD_VARIANT];
}

export function defaultVariantForModel(model: string | null | undefined) {
  const info = modelVariantInfo(model);
  return info.default || info.variants[0] || STANDARD_VARIANT;
}

export function normalizeModelVariantForModel(
  model: string | null | undefined,
  variant: string | null | undefined,
) {
  const normalized = normalizeVariantId(variant);
  if (!normalized) {
    return null;
  }
  return modelVariantIdsForModel(model).includes(normalized) ? normalized : null;
}

export function modelVariantDisplayLabel(variant: string | null | undefined) {
  const normalized = normalizeVariantId(variant);
  return VARIANT_LABELS[normalized] || String(variant || '').trim() || 'Standard';
}

export function modelVariantOptionsForModel(model: string | null | undefined): ModelVariantOption[] {
  return modelVariantIdsForModel(model).map((variant) => ({
    id: variant,
    label: modelVariantDisplayLabel(variant),
  }));
}

export function shouldShowModelVariantControls(model: string | null | undefined) {
  const variants = modelVariantIdsForModel(model);
  return variants.length > 1 || variants[0] !== STANDARD_VARIANT;
}

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
  const configuredByProvider = new Map<string, { provider: string; models: string[]; modelSet: Set<string> }>();
  for (const group of configuredGroups || []) {
    const providerKey = modelProviderKey(group.provider);
    const models = uniqueModels(Array.isArray(group.models) ? group.models : []);
    if (!providerKey || models.length === 0) {
      continue;
    }
    configuredByProvider.set(providerKey, {
      provider: group.provider,
      models,
      modelSet: new Set(models),
    });
  }
  if (configuredByProvider.size === 0) {
    return [];
  }

  const seenProviderKeys = new Set<string>();
  const filtered: ModelProviderGroup[] = [];
  for (const group of candidateGroups || []) {
    const providerKey = modelProviderKey(group.provider);
    const configured = configuredByProvider.get(providerKey);
    if (!configured) {
      continue;
    }
    const models = uniqueModels(Array.isArray(group.models) ? group.models : [])
      .filter((model) => configured.modelSet.has(model));
    if (models.length === 0) {
      continue;
    }
    seenProviderKeys.add(providerKey);
    filtered.push({ provider: group.provider, models });
  }
  for (const [providerKey, configured] of configuredByProvider.entries()) {
    if (seenProviderKeys.has(providerKey)) {
      continue;
    }
    filtered.push({ provider: configured.provider, models: configured.models });
  }
  return filtered;
}

export function filterModelsByConfiguredList(
  candidateModels: string[],
  configuredModels: string[],
) {
  const configured = uniqueModels(configuredModels || []);
  const configuredSet = new Set(configured);
  if (configuredSet.size === 0) {
    return [];
  }
  const filtered = uniqueModels(candidateModels || []).filter((model) => configuredSet.has(model));
  const seen = new Set(filtered);
  for (const model of configured) {
    if (!seen.has(model)) {
      filtered.push(model);
    }
  }
  return filtered;
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
