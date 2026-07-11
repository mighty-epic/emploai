import { Platform, Pressable, Text, View } from 'react-native';

import { renameSession } from '@/lib/appApi';
import { copyDesktopText, openDesktopPath } from '@/lib/desktopBridge';
import type { DesktopConversationScope } from './DesktopConversationScope';
import { styles } from './DesktopConversationView.styles';

const ASK_ABOUT_PREFIX = 'elaborate on what you did here';
const CONTEXT_MENU_WIDTH = 224;
const CONTEXT_MENU_MARGIN = 8;

export type DesktopConversationContextMenuTarget =
  | { kind: 'chat'; session: any; projectPath?: string | null }
  | { kind: 'project'; project: any }
  | { kind: 'userMessage'; content: string }
  | { kind: 'toolCall'; content: string }
  | { kind: 'assistantFinal'; content: string };

export type DesktopConversationContextMenuState = {
  x: number;
  y: number;
  target: DesktopConversationContextMenuTarget;
} | null;

type ContextMenuItem = {
  label: string;
  destructive?: boolean;
  disabled?: boolean;
  onPress: () => void | Promise<void>;
};

export function openDesktopConversationContextMenu(
  setContextMenu: (menu: DesktopConversationContextMenuState) => void,
  event: any,
  target: DesktopConversationContextMenuTarget,
) {
  event?.preventDefault?.();
  event?.stopPropagation?.();
  event?.nativeEvent?.preventDefault?.();
  event?.nativeEvent?.stopPropagation?.();
  const nativeEvent = event?.nativeEvent || event || {};
  const x = Number(nativeEvent.clientX ?? nativeEvent.pageX ?? 24);
  const y = Number(nativeEvent.clientY ?? nativeEvent.pageY ?? 24);
  setContextMenu({ x, y, target });
}

function textFromTarget(target: DesktopConversationContextMenuTarget) {
  return String((target as any).content || '').trim();
}

function projectPathFor(project: any) {
  return String(project?.path || '').trim();
}

function chatPathFor(target: Extract<DesktopConversationContextMenuTarget, { kind: 'chat' }>) {
  return String(target.session?.workspace || target.projectPath || '').trim();
}

function normalizePath(scope: DesktopConversationScope, value: string) {
  return scope.normalizeWorkspacePath ? scope.normalizeWorkspacePath(value) : value;
}

function sessionsForProject(scope: DesktopConversationScope, project: any) {
  if (Array.isArray(project?.sessions) && project.sessions.length > 0) {
    return project.sessions;
  }
  const projectPath = normalizePath(scope, projectPathFor(project));
  return (scope.sessions || []).filter((session: any) => (
    normalizePath(scope, String(session?.workspace || '')) === projectPath
  ));
}

async function copyText(scope: DesktopConversationScope, text: string, statusText: string) {
  const cleanText = String(text || '');
  if (!cleanText) {
    scope.setStatus?.('nothing to copy');
    return;
  }
  await copyDesktopText(cleanText);
  scope.setStatus?.(statusText);
}

async function openPath(scope: DesktopConversationScope, targetPath: string) {
  const cleanPath = String(targetPath || '').trim();
  if (!cleanPath) {
    scope.setStatus?.('no folder path is available');
    return;
  }
  await openDesktopPath(cleanPath);
  scope.setStatus?.('opened in Explorer');
}

function addTextToComposer(scope: DesktopConversationScope, text: string) {
  const cleanText = String(text || '').trim();
  if (!cleanText) {
    scope.setStatus?.('nothing to add');
    return;
  }
  const currentInput = String(scope.input || '');
  const nextInput = currentInput.trim()
    ? `${currentInput.replace(/\s+$/, '')}\n\n${cleanText}`
    : cleanText;
  scope.setComposerInputValue?.(nextInput, { origin: 'manual' });
  scope.setStatus?.('added to chat draft');
  setTimeout(() => {
    scope.composerTextRegionRef?.current?.focus?.();
  }, 0);
}

function askAboutFinalMessage(scope: DesktopConversationScope, text: string) {
  const cleanText = String(text || '').trim();
  if (!cleanText) {
    scope.setStatus?.('nothing to ask about');
    return;
  }
  const prompt = `${ASK_ABOUT_PREFIX}:\n\n${cleanText}`;
  addTextToComposer(scope, prompt);
  scope.setStatus?.('ask-about draft added');
}

async function renameChat(scope: DesktopConversationScope, session: any) {
  const sessionId = String(session?.id || '').trim();
  if (!sessionId) {
    scope.setStatus?.('chat is missing an id');
    return;
  }
  const currentName = String(session?.name || 'Untitled chat');
  const promptValue = (globalThis as any).prompt?.('Rename chat', currentName);
  if (typeof promptValue !== 'string') {
    return;
  }
  const nextName = promptValue.trim();
  if (!nextName || nextName === currentName) {
    return;
  }
  if (!scope.apiBaseUrl || !scope.token) {
    scope.setStatus?.('local API is not ready');
    return;
  }
  scope.setStatus?.('renaming chat');
  const detail = await renameSession(scope.apiBaseUrl, scope.token, sessionId, nextName);
  scope.setSessions?.((current: any[]) => current.map((item: any) => (
    item.id === detail.id
      ? { ...item, name: detail.name, updated_at: detail.updated_at }
      : item
  )));
  if ((scope.sessionIdRef?.current || scope.sessionId) === detail.id) {
    scope.setSessionName?.(detail.name);
  }
  await scope.refreshSidebarState?.(detail.id, true);
  await scope.refreshOverviewState?.(detail.id, { quiet: true });
  scope.pushActivity?.(`Renamed chat: ${detail.name}`, 'accent');
  scope.setStatus?.('chat renamed');
}

async function openChatInFleet(scope: DesktopConversationScope, target: Extract<DesktopConversationContextMenuTarget, { kind: 'chat' }>) {
  const sessionId = String(target.session?.id || '').trim();
  if (!sessionId) {
    scope.setStatus?.('chat is missing an id');
    return;
  }
  scope.setConversationMode?.('fleet');
  scope.setFleetChatPanelCollapsed?.(false);
  await scope.openSession?.(sessionId, { projectPath: target.projectPath || target.session?.workspace || null });
  await scope.refreshFleetSnapshot?.({ quiet: true });
  scope.setStatus?.('opened in Fleet');
}

async function archiveProjectChats(scope: DesktopConversationScope, project: any) {
  const sessions = sessionsForProject(scope, project);
  if (!sessions.length) {
    scope.setStatus?.('no chats to archive in this project');
    return;
  }
  const label = project?.label || scope.projectPathBasename?.(projectPathFor(project)) || 'this project';
  const confirmed = scope.confirmAction
    ? await scope.confirmAction({
        title: `Archive ${sessions.length} chats?`,
        message: `This archives every chat currently listed in ${label}.`,
        confirmLabel: 'Archive chats',
        cancelLabel: 'Cancel',
        tone: 'danger',
      })
    : ((globalThis as any).confirm?.(`Archive ${sessions.length} chats in ${label}?`) ?? true);
  if (!confirmed) {
    return;
  }
  for (const session of sessions) {
    await scope.deleteSidebarSession?.(session);
  }
  scope.setStatus?.(`archived ${sessions.length} chats`);
}

function buildContextMenuItems(scope: DesktopConversationScope, target: DesktopConversationContextMenuTarget): ContextMenuItem[] {
  if (target.kind === 'chat') {
    const chatPath = chatPathFor(target);
    const pinned = Boolean(scope.sidebarState?.sessionMeta?.[target.session?.id]?.pinned);
    return [
      { label: 'Rename', onPress: () => renameChat(scope, target.session) },
      { label: 'Archive Chat', destructive: true, onPress: () => scope.deleteSidebarSession?.(target.session) },
      { label: pinned ? 'Unpin' : 'Pin', onPress: () => scope.toggleSessionPin?.(target.session) },
      { label: 'Open path in Explorer', disabled: !chatPath, onPress: () => openPath(scope, chatPath) },
      { label: 'Copy path', disabled: !chatPath, onPress: () => copyText(scope, chatPath, 'path copied') },
      { label: 'Open in Fleet', onPress: () => openChatInFleet(scope, target) },
    ];
  }

  if (target.kind === 'project') {
    const projectPath = projectPathFor(target.project);
    const pinned = Boolean(target.project?.pinned);
    return [
      { label: pinned ? 'Unpin' : 'Pin', onPress: () => scope.toggleProjectPin?.(projectPath) },
      { label: 'Open in Explorer', disabled: !projectPath, onPress: () => openPath(scope, projectPath) },
      { label: 'Rename', onPress: () => scope.renameProject?.(projectPath) },
      { label: 'Remove', destructive: true, onPress: () => scope.removeProjectFromSidebar?.(projectPath) },
      { label: 'Archive chats', destructive: true, onPress: () => archiveProjectChats(scope, target.project) },
    ];
  }

  if (target.kind === 'assistantFinal') {
    const content = textFromTarget(target);
    return [
      { label: 'Ask about', disabled: !content, onPress: () => askAboutFinalMessage(scope, content) },
    ];
  }

  const content = textFromTarget(target);
  return [
    { label: 'Copy', disabled: !content, onPress: () => copyText(scope, content, 'copied') },
    { label: 'Add to chat', disabled: !content, onPress: () => addTextToComposer(scope, content) },
  ];
}

function menuPosition(menu: NonNullable<DesktopConversationContextMenuState>, itemCount: number) {
  const viewport = (globalThis as any).window || {};
  const viewportWidth = Number(viewport.innerWidth || 0);
  const viewportHeight = Number(viewport.innerHeight || 0);
  const estimatedHeight = Math.min(360, itemCount * 34 + 8);
  const maxLeft = viewportWidth > 0 ? viewportWidth - CONTEXT_MENU_WIDTH - CONTEXT_MENU_MARGIN : menu.x;
  const maxTop = viewportHeight > 0 ? viewportHeight - estimatedHeight - CONTEXT_MENU_MARGIN : menu.y;
  return {
    left: Math.max(CONTEXT_MENU_MARGIN, Math.min(menu.x, maxLeft)),
    top: Math.max(CONTEXT_MENU_MARGIN, Math.min(menu.y, maxTop)),
  };
}

export function DesktopConversationContextMenu({ scope }: { scope: DesktopConversationScope }) {
  const menu = scope.contextMenu as DesktopConversationContextMenuState;
  if (Platform.OS !== 'web' || !menu) {
    return null;
  }

  const items = buildContextMenuItems(scope, menu.target);
  const position = menuPosition(menu, items.length);

  const runItem = (item: ContextMenuItem) => {
    if (item.disabled) {
      return;
    }
    scope.closeContextMenu?.();
    Promise.resolve(item.onPress()).catch((error: unknown) => {
      const message = scope.userFacingError?.(error, 'Context menu action failed.')
        || scope.describeError?.(error)
        || 'Context menu action failed.';
      scope.setStatus?.(message);
    });
  };

  return (
    <Pressable
      style={styles.contextMenuOverlay}
      onPress={() => scope.closeContextMenu?.()}
      {...({ onContextMenu: (event: any) => event?.preventDefault?.() } as any)}
    >
      <View
        style={[styles.contextMenuCard, position]}
        onStartShouldSetResponder={() => true}
        {...({ onContextMenu: (event: any) => event?.preventDefault?.() } as any)}
      >
        {items.map((item) => (
          <Pressable
            key={item.label}
            disabled={item.disabled}
            style={({ hovered }: any) => [
              styles.contextMenuItem,
              hovered && !item.disabled ? styles.contextMenuItemHovered : null,
              item.disabled ? styles.contextMenuItemDisabled : null,
            ]}
            onPress={() => runItem(item)}
          >
            <Text
              style={[
                styles.contextMenuItemText,
                item.destructive ? styles.contextMenuItemTextWarn : null,
                item.disabled ? styles.contextMenuItemTextDisabled : null,
              ]}
              numberOfLines={1}
            >
              {item.label}
            </Text>
          </Pressable>
        ))}
      </View>
    </Pressable>
  );
}
