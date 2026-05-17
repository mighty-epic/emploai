import {
  actOnJob,
  activateAgentSkill,
  activateSession,
  appendAgentMemoryNote,
  configureAgent,
  controlAgentRun,
  createJob,
  createSession,
  compactAgentContext,
  fetchAgentConfig,
  fetchAgentOverview,
  fetchAgentSkills,
  fetchBridgeStatus,
  fetchJobs,
  fetchSessions,
  fetchTaskBoard,
  forceTaskBoardReassess,
  fetchSubAgents,
  forgetLastAgentMessage,
  resetAgentContext,
  searchAgentMemory,
  spawnSubAgent,
  updateAgentConfig,
  validateAgentSkill,
  type AgentOverview,
  type BridgeStatus,
  type ScheduledJob,
  type SessionSummary,
  type TaskBoard,
} from '@/lib/appApi';

type CommandContext = {
  apiBaseUrl: string;
  token: string;
  sessionId?: string;
  overview?: AgentOverview | null;
  sessions?: SessionSummary[];
  jobs?: ScheduledJob[];
  envFilePath?: string;
};

export type DesktopSlashCommandResult = {
  handled: boolean;
  output: string;
  status?: string;
  refresh?: boolean;
  nextSessionId?: string;
};

export const DESKTOP_COMMAND_PLACEHOLDER = 'Message EmploAI or use /help for Telegram-style slash commands';

const COMMAND_HELP: Record<string, string> = {
  start: 'Show the current desktop agent state and shared session info.',
  help: 'Show all slash commands or details for one command: `/help <command>`.',
  mode: 'Auto mode is always enabled. `/mode` is kept only as a compatibility stub.',
  continue: 'Disabled legacy command kept only for backwards compatibility.',
  model: 'Show or switch the current model: `/model` or `/model <model-id>`.',
  models: 'List available models grouped by provider.',
  planner: 'Show or switch the planner model: `/planner`, `/planner <model-id>`, or `/planner auto`.',
  variant: 'Show or switch the current variant: `/variant` or `/variant <variant>`.',
  settings: 'Show or set max turns: `/settings` or `/settings <10-1000>`.',
  workspace: 'Show or set the workspace path: `/workspace` or `/workspace <path>`.',
  session: 'List sessions or switch/create one: `/session`, `/session <id|name|index>`, `/session new`.',
  new: 'Create and activate a new shared session.',
  reset: 'Clear the current session context and pending files.',
  compact: 'Manually compact the current session context.',
  context: 'Show context token usage for the current session.',
  task: 'Show the active managed task board and current progress.',
  reassess: 'Force a reassessment of the active managed task board.',
  history: 'Show recent conversation history: `/history [count]`.',
  pause: 'Pause the current run if one is active.',
  stop: 'Stop the current run immediately.',
  restart: 'Restart the local runtime process in place.',
  spawn: 'Spawn a background sub-agent: `/spawn <prompt>`.',
  subagents: 'List spawned sub-agents.',
  schedule: 'Create a recurring job: `/schedule <name> <schedule> <prompt>`.',
  jobs: 'List scheduled jobs.',
  job_remove: 'Delete a scheduled job: `/job_remove <job_id>`.',
  headless: 'Toggle or set browser mode: `/headless`, `/headless status`, `/headless headless`, `/headless headed`.',
  monitor: 'Toggle or inspect auto-reply: `/monitor on|off|status`.',
  verbose: 'Toggle or inspect verbose tool logging: `/verbose on|off|toggle|status`.',
  bridge: 'Toggle or inspect the Chrome extension bridge: `/bridge on|off|status`.',
  heartbeat: 'Toggle or inspect the heartbeat: `/heartbeat on|off|status`.',
  skills: 'List skill availability.',
  skill: 'Activate a skill for the next messages: `/skill <name>`.',
  skilltest: 'Validate a skill: `/skilltest <name>`.',
  files: 'List pending uploaded files.',
  analytics: 'Show analytics summary: `/analytics [days]`.',
  setup: 'Show Telegram setup guidance and the env file path.',
  forget: 'Remove the last user message from the current session context.',
  security: 'Show security summary.',
  memory: 'Show memory summary or search memory: `/memory [query]`.',
  memory_update: 'Append a note to memory: `/memory_update <note>`.',
  config: 'View or edit config: `/config`, `/config <key>`, `/config <key> <value>`.',
};

export const DESKTOP_COMMAND_SUGGESTIONS = Object.entries(COMMAND_HELP).map(([name, description]) => ({
  name,
  command: `/${name}`,
  description,
}));

const HELP_SECTIONS = [
  {
    title: 'Agent Control',
    items: [
      '/variant - Set model variant',
      '/model - Switch model',
      '/models - List all models',
      '/planner - Set planner model',
      '/verbose - Toggle verbose tool logging',
    ],
  },
  {
    title: 'Automation & Control',
    items: [
      '/pause - Pause running task',
      '/stop - Stop running task',
      '/continue - Disabled legacy resume command',
      '/spawn <prompt> - Spawn parallel sub-agent',
      '/subagents - List running sub-agents',
    ],
  },
  {
    title: 'Scheduling',
    items: [
      '/schedule <name> <schedule> <prompt> - Schedule recurring task',
      '/jobs - List scheduled jobs',
      '/job_remove <id> - Remove a scheduled job',
    ],
  },
  {
    title: 'Session & Memory',
    items: [
      '/session - Manage sessions',
      '/new - Start a new session',
      '/reset - Clear chat history',
      '/compact - Compact the current context',
      '/context - Show token usage',
      '/task - Show the active task board',
      '/reassess - Force a task reassessment',
      '/memory [query] - Search memory',
      '/memory_update <note> - Add note to memory',
    ],
  },
  {
    title: 'Settings',
    items: [
      '/settings - Configure max turns',
      '/workspace - Set workspace path',
      '/headless - Toggle browser mode',
      '/config - View or edit configuration',
      '/heartbeat - Control heartbeat checks',
      '/restart - Restart the local runtime',
      '/bridge - Toggle the browser extension bridge',
    ],
  },
  {
    title: 'Skills',
    items: [
      '/skills - List available skills',
      '/skill <name> - Activate a specific skill',
      '/skilltest <name> - Validate a skill',
    ],
  },
  {
    title: 'Monitoring',
    items: [
      '/monitor - Toggle auto-reply',
      '/analytics - Usage summary',
      '/history - Conversation history',
      '/files - Pending files',
      '/setup - Guided setup guidance',
      '/forget - Remove last user message',
    ],
  },
  {
    title: 'Security',
    items: ['/security - Show security status and rate limits'],
  },
  {
    title: 'Basics',
    items: [
      '/start - Show the current agent state',
      '/help - Show available commands',
      '/mode - Auto mode compatibility stub',
    ],
  },
  {
    title: 'Chat Mode (Default)',
    items: [
      'Send any normal message to use the unified auto agent with:',
      '- File operations (read/write/edit)',
      '- Terminal commands',
      '- Web search',
      '- Codebase search',
      '- Browser and desktop automation',
      '- Persistent memory (auto-loaded and saved)',
    ],
  },
] as const;

function formatHelpOverview() {
  return [
    'Commands',
    '',
    ...HELP_SECTIONS.flatMap((section, index) => [
      `${section.title}:`,
      ...section.items,
      ...(index === HELP_SECTIONS.length - 1 ? [] : ['']),
    ]),
  ].join('\n');
}

function tokenizeArgs(raw: string) {
  const parts: string[] = [];
  const pattern = /"([^"]*)"|'([^']*)'|(\S+)/g;
  for (const match of raw.matchAll(pattern)) {
    parts.push(match[1] ?? match[2] ?? match[3] ?? '');
  }
  return parts;
}

function parseCommand(input: string) {
  const trimmed = input.trim();
  if (!trimmed.startsWith('/')) {
    return null;
  }
  const body = trimmed.slice(1);
  const firstSpace = body.search(/\s/);
  const name = (firstSpace >= 0 ? body.slice(0, firstSpace) : body).trim().toLowerCase();
  const rawArgs = firstSpace >= 0 ? body.slice(firstSpace + 1).trim() : '';
  return {
    name,
    rawArgs,
    args: rawArgs ? tokenizeArgs(rawArgs) : [],
  };
}

function normalize(value: string) {
  return value.trim().toLowerCase();
}

function coerceConfigValue(raw: string): unknown {
  const trimmed = raw.trim();
  if (!trimmed) {
    return '';
  }
  if (trimmed === 'true') return true;
  if (trimmed === 'false') return false;
  if (/^-?\d+$/.test(trimmed)) return Number.parseInt(trimmed, 10);
  if (/^-?\d+\.\d+$/.test(trimmed)) return Number.parseFloat(trimmed);
  if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return trimmed;
    }
  }
  return trimmed;
}

function formatModelGroups(overview: AgentOverview) {
  if (!overview.model_groups.length) {
    return 'No model providers are configured.';
  }

  const lines = [`Current model: ${overview.current_model}`];
  for (const group of overview.model_groups) {
    lines.push('');
    lines.push(`${group.provider}:`);
    for (const model of group.models) {
      lines.push(`- ${model}`);
    }
  }
  return lines.join('\n');
}

function formatPlannerModels(overview: AgentOverview) {
  const available = overview.available_planner_models || [];
  const plannerLabel = overview.planner_model || 'automatic cheapest supported planner';
  if (!available.length) {
    return [
      `Current planner: ${plannerLabel}`,
      'No supported planner models are currently available.',
    ].join('\n');
  }

  return [
    `Current planner: ${plannerLabel}`,
    '',
    'Supported planner models:',
    ...available.map((model) => `- ${model}`),
    '',
    'Use /planner <model-id> to pin one, or /planner auto to let the runtime choose the cheapest supported planner.',
  ].join('\n');
}

function resolvePlannerModel(overview: AgentOverview, raw: string) {
  const allModels = overview.available_planner_models || [];
  const target = normalize(raw);
  const exact = allModels.find((item) => normalize(item) === target);
  if (exact) return exact;
  const prefixMatches = allModels.filter((item) => normalize(item).startsWith(target));
  if (prefixMatches.length === 1) return prefixMatches[0];
  const containsMatches = allModels.filter((item) => normalize(item).includes(target));
  if (containsMatches.length === 1) return containsMatches[0];
  return null;
}

function resolveModel(overview: AgentOverview, raw: string) {
  const allModels = overview.model_groups.flatMap((group) => group.models);
  const target = normalize(raw);
  const exact = allModels.find((item) => normalize(item) === target);
  if (exact) return exact;
  const prefixMatches = allModels.filter((item) => normalize(item).startsWith(target));
  if (prefixMatches.length === 1) return prefixMatches[0];
  const containsMatches = allModels.filter((item) => normalize(item).includes(target));
  if (containsMatches.length === 1) return containsMatches[0];
  return null;
}

function resolveVariant(overview: AgentOverview, raw: string) {
  const target = normalize(raw);
  return overview.available_variants.find((item) => normalize(item) === target) || null;
}

function formatSessions(sessions: SessionSummary[], activeSessionId?: string) {
  if (!sessions.length) {
    return 'No shared sessions were found.';
  }
  return sessions
    .map((session, index) => {
      const marker = session.id === activeSessionId ? '*' : ' ';
      return `${marker} [${index + 1}] ${session.name} (${session.id}) · ${session.message_count} msgs`;
    })
    .join('\n');
}

function resolveSession(sessions: SessionSummary[], query: string) {
  if (!sessions.length) return null;
  const target = normalize(query);
  if (!target) return null;

  if (/^\d+$/.test(target)) {
    const index = Number.parseInt(target, 10) - 1;
    if (index >= 0 && index < sessions.length) {
      return sessions[index];
    }
  }

  const exactId = sessions.find((item) => normalize(item.id) === target);
  if (exactId) return exactId;
  const prefixIdMatches = sessions.filter((item) => normalize(item.id).startsWith(target));
  if (prefixIdMatches.length === 1) return prefixIdMatches[0];

  const exactName = sessions.find((item) => normalize(item.name) === target);
  if (exactName) return exactName;
  const nameMatches = sessions.filter((item) => normalize(item.name).includes(target));
  if (nameMatches.length === 1) return nameMatches[0];

  return null;
}

function formatJobs(jobs: ScheduledJob[]) {
  if (!jobs.length) {
    return 'No scheduled jobs exist.';
  }
  return jobs
    .map((job) => {
      const schedule = job.schedule || (job.interval_seconds ? `every ${job.interval_seconds}s` : 'manual');
      const nextRun = job.next_run_at ? ` · next ${job.next_run_at}` : '';
      return `- ${job.name} (${job.id}) · ${schedule}${nextRun}`;
    })
    .join('\n');
}

function formatBridgeStatus(status: BridgeStatus) {
  const extension = status.extension || {};
  const heartbeatAgeSeconds = typeof extension['heartbeat_age_seconds'] === 'number'
    ? extension['heartbeat_age_seconds']
    : null;
  const extensionConnected = Boolean(extension['connected']);
  const heartbeatAge = heartbeatAgeSeconds != null
    ? ` (${heartbeatAgeSeconds}s since heartbeat)`
    : '';
  const connection = status.desired_backend === 'extension'
    ? status.extension_ready
      ? `Online${heartbeatAge}`
      : extensionConnected
        ? 'Connected but unhealthy/stale'
        : 'Offline (waiting for extension)'
    : 'Disabled';

  return [
    `Desired backend: ${status.desired_backend || 'unknown'}`,
    `Connection: ${connection}`,
    `Task backend: ${status.task_backend || 'unassigned'}`,
    `Real Chrome available: ${status.real_browser_available ? 'Yes' : 'No'}`,
    `Task tab ready: ${status.task_tab_available ? 'Yes' : 'No'}`,
    `Primary task tab: ${String(status.primary_tab_id ?? 'none')}`,
    `Owned task tabs: ${Array.isArray(status.owned_tab_ids) ? status.owned_tab_ids.length : 0}`,
  ].join('\n');
}

function formatHistory(overview: AgentOverview) {
  if (!overview.history.length) {
    return 'No recent conversation history.';
  }
  return overview.history
    .map((entry) => {
      const timestamp = entry.timestamp || 'pending';
      const label = entry.display_label || entry.role;
      return `- [${timestamp}] ${label}: ${entry.preview}`;
    })
    .join('\n');
}

function formatPendingFiles(overview: AgentOverview) {
  if (!overview.pending_files.length) {
    return 'No pending files are attached.';
  }
  return overview.pending_files
    .map((file) => `- ${file.filename}${file.mime_type ? ` (${file.mime_type})` : ''}`)
    .join('\n');
}

function formatTaskBoard(board: TaskBoard | null | undefined) {
  if (!board) {
    return 'No active managed task.';
  }

  const lines = [
    `Goal: ${board.main_goal}`,
    `Status: ${board.status}`,
    `Progress: ${board.progress_summary || `${board.completed_sub_goals}/${board.total_sub_goals} sub-goals complete`}`,
  ];

  if (board.current_focus) {
    lines.push(`Current focus: ${board.current_focus}`);
  }

  lines.push('', 'Sub-goals:');
  for (const subGoal of board.sub_goals) {
    const marker = subGoal.status === 'done'
      ? '[x]'
      : subGoal.status === 'in_progress'
        ? '[>]'
        : subGoal.status === 'blocked'
          ? '[!]'
          : '[ ]';
    const suffix = subGoal.completion_reason ? ` - ${subGoal.completion_reason}` : '';
    lines.push(`${marker} ${subGoal.title}${suffix}`);
  }

  if (board.next_method) {
    lines.push('', `Next method: ${board.next_method}`);
  }
  if (board.pending_reassessment_reason) {
    lines.push('', `Pending reassessment: ${board.pending_reassessment_reason}`);
  }
  if (board.latest_summary) {
    lines.push('', `Latest update: ${board.latest_summary}`);
  }

  return lines.join('\n');
}

function formatSkills(items: Awaited<ReturnType<typeof fetchAgentSkills>>['items']) {
  if (!items.length) {
    return 'No skills are loaded.';
  }
  return items
    .map((item) => {
      const state = item.available ? (item.active ? 'active' : 'available') : `unavailable: ${item.unavailable_reason || 'gated'}`;
      return `- ${item.name} · ${state}`;
    })
    .join('\n');
}

function formatSubagents(status: Awaited<ReturnType<typeof fetchSubAgents>>) {
  if (!status.total_tasks) {
    return 'No sub-agents have been spawned yet.';
  }
  const lines = [
    `Total: ${status.total_tasks} · running ${status.running} · completed ${status.completed} · failed ${status.failed}`,
  ];
  for (const task of status.tasks) {
    lines.push(`- ${task.id} · ${task.status} · ${task.prompt.slice(0, 120)}`);
  }
  return lines.join('\n');
}

function formatAnalytics(overview: AgentOverview) {
  const analytics = overview.analytics;
  return [
    `Period: ${analytics.period_days} day(s)`,
    `Messages: ${analytics.total_messages}`,
    `Commands: ${analytics.total_commands}`,
    `Tokens: ${analytics.total_tokens}`,
    `Average tokens per message: ${analytics.avg_tokens_per_message.toFixed(1)}`,
  ].join('\n');
}

export function isDesktopSlashCommand(input: string) {
  return Boolean(parseCommand(input));
}

export async function runDesktopSlashCommand(input: string, context: CommandContext): Promise<DesktopSlashCommandResult> {
  const command = parseCommand(input);
  if (!command) {
    return { handled: false, output: '' };
  }

  const { apiBaseUrl, token, sessionId, envFilePath } = context;
  const currentOverview = async (params?: { historyCount?: number; analyticsDays?: number }) => (
    fetchAgentOverview(apiBaseUrl, token, {
      sessionId,
      historyCount: params?.historyCount,
      analyticsDays: params?.analyticsDays,
    })
  );

  switch (command.name) {
    case 'start': {
      const overview = await currentOverview();
      return {
        handled: true,
        output: [
          'EmploAI Agent Connected',
          '',
          `Model: ${overview.current_model}`,
          `Variant: ${overview.current_variant}`,
          `Planner: ${overview.planner_model || 'automatic'}`,
          'Mode: Auto',
          `Max Turns: ${overview.max_turns}`,
          `Workspace: ${overview.workspace}`,
          `Session: ${overview.session_id || 'none'}`,
          '',
          'Default Chat: Unified auto agent',
          'Send requests directly, including browser or desktop automation.',
          '',
          'Use /help to see available commands.',
        ].join('\n'),
        status: 'ready',
      };
    }

    case 'help': {
      const requested = command.args[0] ? normalize(command.args[0].replace(/^\//, '')) : '';
      if (requested) {
        return {
          handled: true,
          output: COMMAND_HELP[requested]
            ? `/${requested}\n\n${COMMAND_HELP[requested]}`
            : `Unknown command: /${requested}`,
        };
      }
      return {
        handled: true,
        output: formatHelpOverview(),
      };
    }

    case 'mode':
      return {
        handled: true,
        output: 'Agent mode: auto. Desktop uses the same unified auto agent flow as Telegram.',
      };

    case 'continue':
      return {
        handled: true,
        output: '`/continue` is disabled. Use a normal message to steer the active run, or `/pause` and `/stop` for run control.',
      };

    case 'models': {
      const overview = await currentOverview();
      return { handled: true, output: formatModelGroups(overview) };
    }

    case 'model': {
      const overview = await currentOverview();
      if (!command.args.length) {
        return {
          handled: true,
          output: `${formatModelGroups(overview)}\n\nUse /model <model-id> to switch.`,
        };
      }
      const resolved = resolveModel(overview, command.rawArgs);
      if (!resolved) {
        return {
          handled: true,
          output: `Could not resolve model "${command.rawArgs}".\n\n${formatModelGroups(overview)}`,
        };
      }
      await configureAgent(apiBaseUrl, token, { model: resolved }, sessionId);
      return {
        handled: true,
        output: `Model switched to ${resolved}.`,
        status: `model ${resolved}`,
        refresh: true,
      };
    }

    case 'planner': {
      const overview = await currentOverview();
      if (!command.args.length || normalize(command.args[0]) === 'status' || normalize(command.args[0]) === 'list') {
        return {
          handled: true,
          output: formatPlannerModels(overview),
        };
      }
      const arg = normalize(command.args[0]);
      if (['auto', 'none', 'default', 'clear', 'off'].includes(arg)) {
        await configureAgent(apiBaseUrl, token, { planner_model: null }, sessionId);
        return {
          handled: true,
          output: 'Planner model reset to automatic cheapest supported selection.',
          status: 'planner auto',
          refresh: true,
        };
      }
      const resolved = resolvePlannerModel(overview, command.rawArgs);
      if (!resolved) {
        return {
          handled: true,
          output: `Could not resolve planner model "${command.rawArgs}".\n\n${formatPlannerModels(overview)}`,
        };
      }
      await configureAgent(apiBaseUrl, token, { planner_model: resolved }, sessionId);
      return {
        handled: true,
        output: `Planner model pinned to ${resolved}.`,
        status: `planner ${resolved}`,
        refresh: true,
      };
    }

    case 'variant': {
      const overview = await currentOverview();
      if (!command.args.length) {
        return {
          handled: true,
          output: [
            `Current variant: ${overview.current_variant}`,
            `Available variants: ${overview.available_variants.join(', ') || 'none'}`,
            'Use /variant <name> to switch.',
          ].join('\n'),
        };
      }
      const resolved = resolveVariant(overview, command.args[0]);
      if (!resolved) {
        return {
          handled: true,
          output: `Unknown variant "${command.args[0]}". Available: ${overview.available_variants.join(', ') || 'none'}.`,
        };
      }
      await configureAgent(apiBaseUrl, token, { variant: resolved }, sessionId);
      return {
        handled: true,
        output: `Variant switched to ${resolved}.`,
        status: `variant ${resolved}`,
        refresh: true,
      };
    }

    case 'settings': {
      const overview = await currentOverview();
      if (!command.args.length) {
        return {
          handled: true,
          output: `Current max turns: ${overview.max_turns}\nUse /settings <10-1000> to change it.`,
        };
      }
      const value = Number.parseInt(command.args[0], 10);
      if (!Number.isFinite(value) || value < 10 || value > 1000) {
        return { handled: true, output: 'Max turns must be a number between 10 and 1000.' };
      }
      await configureAgent(apiBaseUrl, token, { max_turns: value }, sessionId);
      return {
        handled: true,
        output: `Max turns set to ${value}.`,
        status: `max turns ${value}`,
        refresh: true,
      };
    }

    case 'workspace': {
      if (!command.rawArgs) {
        const overview = await currentOverview();
        return {
          handled: true,
          output: `Current workspace: ${overview.workspace}\nUse /workspace <path> to change it.`,
        };
      }
      await configureAgent(apiBaseUrl, token, { workspace: command.rawArgs }, sessionId);
      return {
        handled: true,
        output: `Workspace set to ${command.rawArgs}.`,
        status: 'workspace updated',
        refresh: true,
      };
    }

    case 'session': {
      const sessions = await fetchSessions(apiBaseUrl, token);
      if (!command.args.length || normalize(command.args[0]) === 'list') {
        return {
          handled: true,
          output: formatSessions(sessions, sessionId),
        };
      }
      if (normalize(command.args[0]) === 'new') {
        const created = await createSession(apiBaseUrl, token);
        return {
          handled: true,
          output: `Created and activated session ${created.session.name} (${created.session.id}).`,
          status: 'session created',
          refresh: true,
          nextSessionId: created.session.id,
        };
      }
      if (normalize(command.args[0]) === 'current') {
        const active = sessions.find((item) => item.id === sessionId);
        return {
          handled: true,
          output: active
            ? `Current session: ${active.name} (${active.id})`
            : 'No active session is selected.',
        };
      }
      const selected = resolveSession(sessions, command.rawArgs);
      if (!selected) {
        return {
          handled: true,
          output: `Could not resolve session "${command.rawArgs}".\n\n${formatSessions(sessions, sessionId)}`,
        };
      }
      await activateSession(apiBaseUrl, token, selected.id);
      return {
        handled: true,
        output: `Switched to session ${selected.name} (${selected.id}).`,
        status: 'session switched',
        refresh: true,
        nextSessionId: selected.id,
      };
    }

    case 'new': {
      const created = await createSession(apiBaseUrl, token);
      return {
        handled: true,
        output: `Created and activated session ${created.session.name} (${created.session.id}).`,
        status: 'session created',
        refresh: true,
        nextSessionId: created.session.id,
      };
    }

    case 'reset':
      await resetAgentContext(apiBaseUrl, token, sessionId);
      return {
        handled: true,
        output: 'Current session context cleared.',
        status: 'context reset',
        refresh: true,
      };

    case 'compact': {
      const result = await compactAgentContext(apiBaseUrl, token, sessionId);
      return {
        handled: true,
        output: result.message || 'Context compacted.',
        status: 'context compacted',
        refresh: true,
      };
    }

    case 'context': {
      const overview = await currentOverview();
      const usage = overview.context_usage;
      return {
        handled: true,
        output: [
          `Model: ${usage.model}`,
          `Estimated tokens: ${usage.estimated_tokens} / ${usage.max_tokens}`,
          `Usage: ${usage.usage_percent.toFixed(1)}%`,
          `Messages: ${usage.message_count}`,
          `Compaction state: ${usage.compaction_state}`,
        ].join('\n'),
      };
    }

    case 'task': {
      const board = (await fetchTaskBoard(apiBaseUrl, token, sessionId)).task_board;
      return {
        handled: true,
        output: formatTaskBoard(board),
      };
    }

    case 'reassess': {
      const result = await forceTaskBoardReassess(apiBaseUrl, token, sessionId);
      return {
        handled: true,
        output: result.message || 'Manual reassessment requested.',
        status: 'task reassess',
        refresh: true,
      };
    }

    case 'history': {
      const count = command.args[0] ? Number.parseInt(command.args[0], 10) : 10;
      const boundedCount = Number.isFinite(count) ? Math.max(1, Math.min(50, count)) : 10;
      const overview = await currentOverview({ historyCount: boundedCount });
      return {
        handled: true,
        output: formatHistory(overview),
      };
    }

    case 'pause':
    case 'stop':
    case 'restart': {
      const result = await controlAgentRun(apiBaseUrl, token, command.name, sessionId);
      return {
        handled: true,
        output: result.message || `${command.name} requested.`,
        status: command.name,
        refresh: true,
      };
    }

    case 'spawn': {
      if (!command.rawArgs) {
        return { handled: true, output: 'Usage: /spawn <prompt>' };
      }
      const result = await spawnSubAgent(apiBaseUrl, token, { prompt: command.rawArgs, headless: true, max_turns: 30 }, sessionId);
      return {
        handled: true,
        output: result.message || 'Sub-agent started.',
        status: 'sub-agent started',
        refresh: true,
      };
    }

    case 'subagents': {
      const status = await fetchSubAgents(apiBaseUrl, token, sessionId);
      return { handled: true, output: formatSubagents(status) };
    }

    case 'schedule': {
      if (command.args.length < 3) {
        return { handled: true, output: 'Usage: /schedule <name> <schedule> <prompt>' };
      }
      let scheduleEnd = 1;
      for (let index = 1; index < Math.min(command.args.length, 6); index += 1) {
        if (['at', 'minutes', 'minute', 'hours', 'hour', 'days', 'day'].includes(normalize(command.args[index]))) {
          scheduleEnd = index + 1;
        }
      }
      const name = command.args[0];
      const schedule = command.args.slice(1, scheduleEnd).join(' ');
      const prompt = command.args.slice(scheduleEnd).join(' ');
      if (!prompt) {
        return { handled: true, output: 'Usage: /schedule <name> <schedule> <prompt>' };
      }
      const job = await createJob(apiBaseUrl, token, { name, prompt, schedule });
      return {
        handled: true,
        output: `Scheduled ${job.name} (${job.id}) with "${job.schedule || schedule}".`,
        status: 'job scheduled',
        refresh: true,
      };
    }

    case 'jobs': {
      const jobs = await fetchJobs(apiBaseUrl, token);
      return { handled: true, output: formatJobs(jobs) };
    }

    case 'job_remove': {
      if (!command.args.length) {
        return { handled: true, output: 'Usage: /job_remove <job_id>' };
      }
      await actOnJob(apiBaseUrl, token, command.args[0], 'delete');
      return {
        handled: true,
        output: `Deleted job ${command.args[0]}.`,
        status: 'job removed',
        refresh: true,
      };
    }

    case 'headless': {
      const overview = await currentOverview();
      const currentMode = overview.headless_mode;
      const desired = !command.args.length || normalize(command.args[0]) === 'toggle'
        ? currentMode === 'headless' ? 'headed' : 'headless'
        : ['on', 'headless', 'true'].includes(normalize(command.args[0]))
          ? 'headless'
          : ['off', 'headed', 'false'].includes(normalize(command.args[0]))
            ? 'headed'
            : normalize(command.args[0]) === 'status'
              ? currentMode
              : null;
      if (!desired) {
        return { handled: true, output: 'Usage: /headless, /headless status, /headless headless, or /headless headed.' };
      }
      if (desired === currentMode && normalize(command.args[0] || '') === 'status') {
        return { handled: true, output: `Current browser mode: ${currentMode}.` };
      }
      await configureAgent(apiBaseUrl, token, { headless_mode: desired as 'headless' | 'headed' }, sessionId);
      return {
        handled: true,
        output: `Browser mode set to ${desired}.`,
        status: `browser ${desired}`,
        refresh: true,
      };
    }

    case 'skills': {
      const skills = await fetchAgentSkills(apiBaseUrl, token, sessionId);
      return { handled: true, output: formatSkills(skills.items) };
    }

    case 'skill': {
      if (!command.args.length) {
        return { handled: true, output: 'Usage: /skill <name>' };
      }
      const result = await activateAgentSkill(apiBaseUrl, token, { name: command.args[0], active: true }, sessionId);
      return {
        handled: true,
        output: result.message || `${command.args[0]} will be active for your next messages.`,
        status: 'skill activated',
        refresh: true,
      };
    }

    case 'skilltest': {
      if (!command.args.length) {
        return { handled: true, output: 'Usage: /skilltest <name>' };
      }
      const result = await validateAgentSkill(apiBaseUrl, token, command.args[0], sessionId);
      if (!result.valid) {
        return {
          handled: true,
          output: [`Skill validation failed for ${result.name}.`, ...result.errors, ...result.warnings.map((item) => `Warning: ${item}`)].join('\n'),
        };
      }
      return {
        handled: true,
        output: [
          `Skill valid: ${result.name}`,
          `Scripts: ${result.scripts_count}`,
          `References: ${result.references_count}`,
          `Assets: ${result.assets_count}`,
          ...result.warnings.map((item) => `Warning: ${item}`),
        ].join('\n'),
      };
    }

    case 'files': {
      const overview = await currentOverview();
      return { handled: true, output: formatPendingFiles(overview) };
    }

    case 'monitor': {
      const current = await currentOverview();
      const arg = normalize(command.args[0] || 'status');
      if (arg === 'status') {
        return {
          handled: true,
          output: `Auto-reply is ${current.auto_reply_enabled ? 'ON' : 'OFF'}.`,
        };
      }
      if (!['on', 'off', 'enable', 'disable', 'start', 'stop'].includes(arg)) {
        return { handled: true, output: 'Usage: /monitor on|off|status' };
      }
      const enabled = ['on', 'enable', 'start'].includes(arg);
      await configureAgent(apiBaseUrl, token, { auto_reply_enabled: enabled }, sessionId);
      return {
        handled: true,
        output: `Auto-reply ${enabled ? 'enabled' : 'disabled'}.`,
        status: `auto-reply ${enabled ? 'on' : 'off'}`,
        refresh: true,
      };
    }

    case 'analytics': {
      const days = command.args[0] ? Number.parseInt(command.args[0], 10) : 7;
      const boundedDays = Number.isFinite(days) ? Math.max(1, Math.min(30, days)) : 7;
      const overview = await currentOverview({ analyticsDays: boundedDays });
      return { handled: true, output: formatAnalytics(overview) };
    }

    case 'setup':
      return {
        handled: true,
        output: [
          'Desktop is the default surface.',
          'Telegram setup:',
          '1. Open Telegram and talk to BotFather.',
          '2. Create a bot and copy the bot token.',
          '3. Get your numeric Telegram user ID from userinfobot.',
          '4. Put those values into TELEGRAM_BOT_TOKEN and ALLOWED_USER_IDS.',
          envFilePath ? `Env file: ${envFilePath}` : 'Env file path is not available in this desktop runtime.',
        ].join('\n'),
      };

    case 'forget':
      await forgetLastAgentMessage(apiBaseUrl, token, sessionId);
      return {
        handled: true,
        output: 'Removed the last user message from the current session context.',
        status: 'forgot last message',
        refresh: true,
      };

    case 'memory': {
      if (!command.rawArgs) {
        const overview = await currentOverview();
        const summary = overview.memory_summary;
        return {
          handled: true,
          output: [
            `Memory file exists: ${summary.memory_file_exists ? 'yes' : 'no'}`,
            `Daily logs: ${summary.daily_log_count}`,
            `Oldest log: ${summary.oldest_log || 'n/a'}`,
            `Newest log: ${summary.newest_log || 'n/a'}`,
          ].join('\n'),
        };
      }
      const result = await searchAgentMemory(apiBaseUrl, token, command.rawArgs, sessionId);
      if (!result.results.length) {
        return { handled: true, output: `No memory results found for "${command.rawArgs}".` };
      }
      return {
        handled: true,
        output: result.results.map((item) => `- ${item.source}${item.line ? `:${item.line}` : ''} · ${item.content}`).join('\n'),
      };
    }

    case 'memory_update':
      if (!command.rawArgs) {
        return { handled: true, output: 'Usage: /memory_update <note>' };
      }
      await appendAgentMemoryNote(apiBaseUrl, token, command.rawArgs, sessionId);
      return {
        handled: true,
        output: 'Memory note appended.',
        status: 'memory updated',
      };

    case 'config': {
      if (!command.args.length) {
        const config = await fetchAgentConfig(apiBaseUrl, token, undefined, sessionId);
        if (!config.items.length) {
          return { handled: true, output: 'No live config entries are available.' };
        }
        return {
          handled: true,
          output: config.items.slice(0, 20).map((item) => `${item.key} = ${JSON.stringify(item.value)}`).join('\n'),
        };
      }
      if (command.args.length === 1) {
        const config = await fetchAgentConfig(apiBaseUrl, token, command.args[0], sessionId);
        const item = config.items[0];
        return {
          handled: true,
          output: item ? `${item.key} = ${JSON.stringify(item.value)}` : `Config key ${command.args[0]} is not set.`,
        };
      }
      const key = command.args[0];
      const rawValue = command.rawArgs.slice(key.length).trim();
      await updateAgentConfig(apiBaseUrl, token, { key, value: coerceConfigValue(rawValue) }, sessionId);
      return {
        handled: true,
        output: `Updated ${key}.`,
        status: `config ${key} updated`,
        refresh: true,
      };
    }

    case 'heartbeat': {
      const overview = await currentOverview();
      const arg = normalize(command.args[0] || 'status');
      if (arg === 'status') {
        return {
          handled: true,
          output: [
            `Enabled: ${overview.heartbeat.enabled ? 'yes' : 'no'}`,
            `Running: ${overview.heartbeat.running ? 'yes' : 'no'}`,
            `Interval: ${overview.heartbeat.interval_seconds}s`,
            `Checks: ${overview.heartbeat.check_count}`,
            `Last: ${overview.heartbeat.last_heartbeat || 'n/a'}`,
          ].join('\n'),
        };
      }
      if (!['on', 'off'].includes(arg)) {
        return { handled: true, output: 'Usage: /heartbeat on|off|status' };
      }
      const enabled = arg === 'on';
      await configureAgent(apiBaseUrl, token, { heartbeat_enabled: enabled }, sessionId);
      return {
        handled: true,
        output: `Heartbeat ${enabled ? 'enabled' : 'disabled'}.`,
        status: `heartbeat ${arg}`,
        refresh: true,
      };
    }

    case 'bridge': {
      const arg = normalize(command.args[0] || 'status');
      if (arg === 'status') {
        const status = await fetchBridgeStatus(apiBaseUrl, token, sessionId);
        return {
          handled: true,
          output: formatBridgeStatus(status),
        };
      }
      if (!['on', 'off', 'enable', 'disable'].includes(arg)) {
        return { handled: true, output: 'Usage: /bridge on|off|status' };
      }
      const enabled = ['on', 'enable'].includes(arg);
      await configureAgent(apiBaseUrl, token, { bridge_enabled: enabled }, sessionId);
      return {
        handled: true,
        output: enabled ? 'Browser extension bridge enabled.' : 'Browser extension bridge disabled.',
        status: `bridge ${enabled ? 'on' : 'off'}`,
        refresh: true,
      };
    }

    case 'verbose': {
      const overview = await currentOverview();
      const arg = normalize(command.args[0] || 'status');
      if (arg === 'status') {
        return {
          handled: true,
          output: `Verbose tool logging is ${overview.verbose_mode ? 'ON' : 'OFF'}.`,
        };
      }
      let nextValue: boolean | null = null;
      if (['on', 'enable'].includes(arg)) nextValue = true;
      if (['off', 'disable'].includes(arg)) nextValue = false;
      if (arg === 'toggle') nextValue = !overview.verbose_mode;
      if (nextValue == null) {
        return { handled: true, output: 'Usage: /verbose on|off|toggle|status' };
      }
      await configureAgent(apiBaseUrl, token, { verbose_mode: nextValue }, sessionId);
      return {
        handled: true,
        output: `Verbose tool logging ${nextValue ? 'enabled' : 'disabled'}.`,
        status: `verbose ${nextValue ? 'on' : 'off'}`,
        refresh: true,
      };
    }

    case 'security': {
      const overview = await currentOverview();
      const security = overview.security;
      return {
        handled: true,
        output: [
          `Allowed users: ${security.allowed_users_count}`,
          `Rate-limited users: ${security.rate_limited_users}`,
          `Events 24h: ${security.security_events_24h}`,
          `Warnings 24h: ${security.warning_events_24h}`,
          `Errors 24h: ${security.error_events_24h}`,
          `Limits: ${security.max_requests_per_minute}/min, ${security.max_requests_per_hour}/hour`,
        ].join('\n'),
      };
    }

    default:
      return {
        handled: true,
        output: `Unknown command: /${command.name}\n\nUse /help to see available commands.`,
      };
  }
}
