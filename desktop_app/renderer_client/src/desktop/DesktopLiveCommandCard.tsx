import { useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { MonoIcon } from './DesktopConversationView.components';
import { DESKTOP_UI as UI } from './desktopUiTokens';

type LiveCommandCardProps = {
  entry: any;
  formatAbsoluteTime: (value: string) => string;
  openToolContextMenu: (event: any, content: string) => void;
  killLiveCommand?: (metadata: Record<string, any>) => void | Promise<void>;
};

const RUNNING_STATUSES = new Set([
  'waiting_on_process',
  'waiting_on_ready_signal',
  'process_running',
  'process_output',
  'process_ready',
  'process_meaningful_output',
  'process_still_running',
]);

function statusLabel(status: string, exitCode: unknown) {
  if (status === 'process_completed') {
    return 'completed';
  }
  if (status === 'process_failed') {
    return exitCode === undefined || exitCode === null ? 'failed' : `failed ${exitCode}`;
  }
  if (status === 'process_ready') {
    return 'ready';
  }
  if (status === 'process_meaningful_output' || status === 'process_output') {
    return 'output';
  }
  if (RUNNING_STATUSES.has(status)) {
    return 'running';
  }
  return status.replace(/^process_/, '').replace(/_/g, ' ') || 'running';
}

export function DesktopLiveCommandCard({
  entry,
  formatAbsoluteTime,
  openToolContextMenu,
  killLiveCommand,
}: LiveCommandCardProps) {
  const [expanded, setExpanded] = useState(false);
  const metadata = (entry?.metadata || {}) as Record<string, any>;
  const status = String(metadata.status || '').toLowerCase();
  const command = String(metadata.command || entry?.body || '').trim();
  const commandId = String(metadata.command_id || '').trim();
  const output = String(metadata.output || '').trim();
  const exitCode = metadata.exit_code;
  const running = RUNNING_STATUSES.has(status) && !metadata.completed_at;
  const contextText = [
    command ? `Command\n${command}` : '',
    output ? `Output\n${output}` : '',
  ].filter(Boolean).join('\n\n');

  return (
    <View
      {...(Platform.OS === 'web'
        ? ({ onContextMenu: (event: any) => openToolContextMenu(event, contextText || command || commandId) } as any)
        : {})}
      style={[
        localStyles.card,
        running ? localStyles.cardRunning : null,
        entry?.tone === 'error' ? localStyles.cardError : null,
      ]}
    >
      <View style={localStyles.header}>
        <View style={localStyles.headerCopy}>
          <Text style={localStyles.eyebrow}>Command</Text>
          <Text style={localStyles.time}>{entry?.timestamp ? formatAbsoluteTime(entry.timestamp) : 'running'}</Text>
        </View>
        <View style={[localStyles.statusPill, running ? localStyles.statusPillRunning : null]}>
          <Text style={[localStyles.statusText, running ? localStyles.statusTextRunning : null]}>{statusLabel(status, exitCode)}</Text>
        </View>
      </View>
      <Text style={localStyles.commandText}>{command || commandId || 'Command running'}</Text>
      <View style={localStyles.metaRow}>
        {commandId ? <Text style={localStyles.metaText}>{commandId}</Text> : null}
        {metadata.pid ? <Text style={localStyles.metaText}>pid {String(metadata.pid)}</Text> : null}
        {metadata.shell ? <Text style={localStyles.metaText}>{String(metadata.shell)}</Text> : null}
      </View>
      <View style={localStyles.actionRow}>
        <Pressable
          style={[localStyles.actionButton, !output ? localStyles.actionButtonDisabled : null]}
          disabled={!output}
          onPress={() => setExpanded((current) => !current)}
        >
          <Text style={localStyles.actionText}>{expanded ? 'Hide output' : 'Output'}</Text>
        </Pressable>
        {running && metadata.process_wait_id && killLiveCommand ? (
          <Pressable
            style={[localStyles.actionButton, localStyles.killButton]}
            onPress={() => { void killLiveCommand(metadata); }}
          >
            <MonoIcon name="stop" style={localStyles.killIcon} />
            <Text style={localStyles.killText}>Kill</Text>
          </Pressable>
        ) : null}
      </View>
      {expanded && output ? (
        <View style={localStyles.outputBlock}>
          <Text style={localStyles.outputLabel}>Live output</Text>
          <Text style={localStyles.outputText}>{output}</Text>
        </View>
      ) : null}
    </View>
  );
}

const localStyles = StyleSheet.create({
  card: {
    borderRadius: UI.radius.panel,
    borderWidth: 1,
    borderColor: UI.color.border,
    backgroundColor: UI.color.surface,
    padding: 12,
    gap: 10,
  },
  cardRunning: {
    borderColor: 'rgba(117, 198, 154, 0.36)',
    backgroundColor: UI.color.successSoft,
  },
  cardError: {
    borderColor: 'rgba(224, 120, 132, 0.38)',
    backgroundColor: UI.color.dangerSoft,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
    alignItems: 'center',
  },
  headerCopy: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minWidth: 0,
  },
  eyebrow: {
    color: UI.color.textSubtle,
    fontSize: 11,
    fontWeight: '600',
    textTransform: 'none',
  },
  time: {
    color: UI.color.textSubtle,
    fontSize: 11,
  },
  statusPill: {
    borderRadius: UI.radius.small,
    paddingHorizontal: 8,
    paddingVertical: 3,
    backgroundColor: UI.color.surfaceMuted,
  },
  statusPillRunning: {
    backgroundColor: UI.color.successSoft,
    borderWidth: 1,
    borderColor: 'rgba(117, 198, 154, 0.34)',
  },
  statusText: {
    color: UI.color.textMuted,
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'none',
  },
  statusTextRunning: {
    color: UI.color.success,
  },
  commandText: {
    color: UI.color.text,
    fontSize: 13,
    lineHeight: 19,
    fontFamily: Platform.OS === 'web' ? UI.type.mono : undefined,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  metaText: {
    color: UI.color.textSubtle,
    fontSize: 11,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
  },
  actionButton: {
    minHeight: 30,
    borderRadius: UI.radius.control,
    paddingHorizontal: 10,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 6,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 1,
    borderColor: UI.color.border,
  },
  actionButtonDisabled: {
    opacity: 0.45,
  },
  actionText: {
    color: UI.color.textMuted,
    fontSize: 12,
    fontWeight: '700',
  },
  killButton: {
    backgroundColor: UI.color.dangerSoft,
    borderColor: 'rgba(224, 120, 132, 0.36)',
  },
  killIcon: {
    color: UI.color.danger,
    fontSize: 10,
  },
  killText: {
    color: '#f3b5bd',
    fontSize: 12,
    fontWeight: '800',
  },
  outputBlock: {
    borderRadius: UI.radius.control,
    borderWidth: 1,
    borderColor: UI.color.border,
    backgroundColor: UI.color.canvas,
    padding: 10,
    gap: 6,
  },
  outputLabel: {
    color: UI.color.textSubtle,
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  outputText: {
    color: UI.color.textMuted,
    fontSize: 12,
    lineHeight: 18,
    fontFamily: Platform.OS === 'web' ? UI.type.mono : undefined,
  },
});
