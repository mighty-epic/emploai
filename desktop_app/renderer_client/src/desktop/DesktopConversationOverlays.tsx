import { Image, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';

import { FoldSection, MonoIcon } from './DesktopConversationView.components';
import { DesktopConversationContextMenu } from './DesktopConversationContextMenu';
import { styles } from './DesktopConversationView.styles';
import type { DesktopConversationScope } from './DesktopConversationScope';

type DesktopConversationOverlaysProps = {
  scope: DesktopConversationScope;
};

export function DesktopConversationOverlays({ scope }: DesktopConversationOverlaysProps) {
    const { chooseFolderFromChoice, closeFolderChoice, closeSidebarSearchModal, createAutomaticFolderFromChoice, folderChoiceBusy, folderChoiceOpen, id, mergedSidebarSearchResults, openSearchResult, projectPath, projectPathBasename, recentSearchSessions, sessionId, setSidebarSearch, shortStatusText, sidebarChatTooltip, sidebarSearch, sidebarSearchError, sidebarSearchInputRef, sidebarSearchLoading, sidebarSearchModalRef, sidebarSearchOpen, sidebarSearchQuery, title } = scope;

  return (
    <>
      {Platform.OS === 'web' && sidebarChatTooltip ? (
        <View pointerEvents="none" style={styles.sidebarChatTooltipLayer}>
          <View
            style={[
              styles.sidebarChatTooltipCard,
              {
                top: sidebarChatTooltip.top,
                left: sidebarChatTooltip.left,
              },
            ]}
          >
            <Text style={styles.sidebarChatTooltipTitle} numberOfLines={1}>
              {sidebarChatTooltip.title}
            </Text>
            <Text style={styles.sidebarChatTooltipMeta} numberOfLines={1}>
              {sidebarChatTooltip.projectPath}
            </Text>
            <Text style={styles.sidebarChatTooltipMetaSecondary} numberOfLines={1}>
              {sidebarChatTooltip.botLabel}
            </Text>
          </View>
        </View>
      ) : null}

      {folderChoiceOpen ? (
        <Pressable style={styles.folderChoiceOverlay} onPress={() => closeFolderChoice(null)}>
          <Pressable
            style={styles.folderChoiceCard}
            onPress={(event: any) => event?.stopPropagation?.()}
          >
            <View style={styles.folderChoiceHeader}>
              <Text style={styles.folderChoiceTitle}>Choose a folder</Text>
              <Pressable style={styles.folderChoiceCloseButton} onPress={() => closeFolderChoice(null)}>
                <Text style={styles.folderChoiceCloseText}>X</Text>
              </Pressable>
            </View>
            <Text style={styles.folderChoiceText}>
              This chat needs a folder so the agent knows where to read and write files.
            </Text>
            <View style={styles.folderChoiceActions}>
              <Pressable
                style={[
                  styles.folderChoiceAction,
                  styles.folderChoiceActionPrimary,
                  folderChoiceBusy ? styles.folderChoiceActionDisabled : null,
                ]}
                disabled={Boolean(folderChoiceBusy)}
                onPress={() => void createAutomaticFolderFromChoice()}
              >
                <Text style={[styles.folderChoiceActionText, styles.folderChoiceActionTextPrimary]}>
                  {folderChoiceBusy === 'auto' ? 'Creating…' : 'Automatic folder'}
                </Text>
                <Text style={styles.folderChoiceActionHint}>
                  Create a new chat folder in the default location.
                </Text>
              </Pressable>
              <Pressable
                style={[
                  styles.folderChoiceAction,
                  folderChoiceBusy ? styles.folderChoiceActionDisabled : null,
                ]}
                disabled={Boolean(folderChoiceBusy)}
                onPress={() => void chooseFolderFromChoice()}
              >
                <Text style={styles.folderChoiceActionText}>
                  {folderChoiceBusy === 'choose' ? 'Opening…' : 'Choose location'}
                </Text>
                <Text style={styles.folderChoiceActionHint}>
                  Pick an existing folder or create one wherever you want.
                </Text>
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      ) : null}

      {sidebarSearchOpen ? (
        <Pressable style={styles.sidebarSearchModalOverlay} onPress={closeSidebarSearchModal}>
          <Pressable
            ref={sidebarSearchModalRef}
            style={styles.sidebarSearchModalCard}
            onPress={(event: any) => event?.stopPropagation?.()}
          >
            <View style={styles.sidebarSearchModalInputShell}>
              <MonoIcon name="search" style={styles.sidebarSearchModalInputGlyph} />
              <TextInput
                ref={sidebarSearchInputRef}
                style={styles.sidebarSearchModalInput}
                value={sidebarSearch}
                onChangeText={setSidebarSearch}
                placeholder="Search chats"
                placeholderTextColor="#8f8f8f"
              />
            </View>

            {!sidebarSearchQuery ? (
              <>
                <Text style={styles.sidebarSearchSectionLabel}>Recent chats</Text>
                <ScrollView style={styles.sidebarSearchResultsScroll} contentContainerStyle={styles.sidebarSearchResultsList}>
                  {recentSearchSessions.map((item: any) => (
                    <Pressable
                      key={`recent-chat-${item.id}`}
                      style={styles.sidebarSearchResultRow}
                      onPress={() => void openSearchResult({
                        kind: 'session',
                        sessionId: item.id,
                        projectPath: item.workspace || '',
                      })}
                    >
                      <View style={styles.sidebarSearchResultLine}>
                        <Text style={styles.sidebarSearchResultPrimary} numberOfLines={1}>{item.name}</Text>
                        <Text style={styles.sidebarSearchResultSecondary} numberOfLines={1}>
                          {projectPathBasename(item.workspace || '') || 'chat'}
                        </Text>
                      </View>
                    </Pressable>
                  ))}
                </ScrollView>
              </>
            ) : sidebarSearchLoading ? (
              <View style={styles.sidebarSearchEmptyState}>
                <Text style={styles.sidebarSearchEmptyTitle}>Searching…</Text>
                <Text style={styles.sidebarSearchEmptyText}>Scanning folders, chats, and saved message history.</Text>
              </View>
            ) : sidebarSearchError ? (
              <View style={styles.sidebarSearchEmptyState}>
                <Text style={styles.sidebarSearchEmptyTitle}>Search unavailable</Text>
                <Text style={styles.sidebarSearchEmptyText}>{shortStatusText(sidebarSearchError)}</Text>
              </View>
            ) : mergedSidebarSearchResults.length === 0 ? (
              <View style={styles.sidebarSearchEmptyState}>
                <Text style={styles.sidebarSearchEmptyTitle}>No matches</Text>
                <Text style={styles.sidebarSearchEmptyText}>Try a shorter phrase or one of the key words from the chat.</Text>
              </View>
            ) : (
              <ScrollView style={styles.sidebarSearchResultsScroll} contentContainerStyle={styles.sidebarSearchResultsList}>
                {mergedSidebarSearchResults.map((result: any, index: any) => {
                  const searchTarget: any = result.kind === 'message'
                    ? {
                        kind: 'message',
                        sessionId: result.session_id || '',
                        projectPath: result.project_path,
                        messageIndex: Number(result.message_index ?? -1),
                      }
                    : {
                        kind: 'session',
                        sessionId: result.session_id || '',
                        projectPath: result.project_path,
                      };
                  const primaryText = result.kind === 'session'
                    ? result.session_name || 'Untitled chat'
                    : result.snippet || result.session_name || 'Message match';
                  const secondaryText = result.kind === 'session'
                    ? projectPathBasename(result.project_path) || 'chat'
                    : result.session_name || projectPathBasename(result.project_path) || 'chat';
                  return (
                    <Pressable
                      key={`${result.kind}-${result.session_id || 'session'}-${result.message_index ?? index}`}
                      style={styles.sidebarSearchResultRow}
                      onPress={() => void openSearchResult(searchTarget)}
                    >
                      <View style={styles.sidebarSearchResultLine}>
                        <Text style={styles.sidebarSearchResultPrimary} numberOfLines={1}>
                          {primaryText}
                        </Text>
                        <Text style={styles.sidebarSearchResultSecondary} numberOfLines={1}>
                          {secondaryText}
                        </Text>
                      </View>
                    </Pressable>
                  );
                })}
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      ) : null}

      <DesktopConversationContextMenu scope={scope} />

    </>
  );
}
