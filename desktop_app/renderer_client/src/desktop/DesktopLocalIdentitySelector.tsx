import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { ReactNode } from 'react';

import type { DesktopFleetIdentity } from '@/lib/desktopBridge';
import { DESKTOP_UI as UI } from './desktopUiTokens';

type Props = {
  identities: DesktopFleetIdentity[];
  activeIdentity?: DesktopFleetIdentity | null;
  busy?: boolean;
  compact?: boolean;
  title?: string;
  hint?: string;
  trailingControl?: ReactNode;
  onSelect: (identity: DesktopFleetIdentity) => void | Promise<void>;
};

function identityRoleLabel(identity: DesktopFleetIdentity) {
  if (identity.role === 'manager') return 'Manager';
  if (identity.is_default) return 'Default worker';
  return 'Worker';
}

export function DesktopLocalIdentitySelector({
  identities,
  activeIdentity,
  busy = false,
  compact = false,
  title = 'Local identity',
  hint = 'Chat and Jarvis use this identity on this computer',
  trailingControl,
  onSelect,
}: Props) {
  return (
    <View style={[styles.shell, compact ? styles.shellCompact : null]}>
      <View style={styles.headerRow}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>{title}</Text>
          {!compact ? <Text style={styles.hint} numberOfLines={1}>{hint}</Text> : null}
        </View>
        {trailingControl}
      </View>
      {identities.length ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.identityList}
        >
          {identities.map((identity) => {
            const active = activeIdentity?.identity_id === identity.identity_id;
            return (
              <Pressable
                key={identity.identity_id}
                accessibilityRole="radio"
                accessibilityState={{ checked: active, disabled: busy }}
                accessibilityLabel={`${identity.display_name}, ${identityRoleLabel(identity)}`}
                disabled={busy}
                style={({ hovered }: any) => [
                  styles.identityChip,
                  active ? styles.identityChipActive : null,
                  hovered && !active ? styles.identityChipHovered : null,
                  busy ? styles.identityChipDisabled : null,
                ]}
                onPress={() => void onSelect(identity)}
              >
                <View style={[styles.statusDot, identity.status === 'active' || identity.status === 'idle' ? styles.statusDotOnline : null]} />
                <View style={styles.identityCopy}>
                  <Text style={[styles.identityName, active ? styles.identityNameActive : null]} numberOfLines={1}>
                    {identity.display_name}
                  </Text>
                  <Text style={[styles.identityMeta, active ? styles.identityMetaActive : null]} numberOfLines={1}>
                    {identityRoleLabel(identity)}{identity.status ? ` · ${identity.status}` : ''}
                  </Text>
                </View>
              </Pressable>
            );
          })}
        </ScrollView>
      ) : (
        <Text style={styles.empty}>Local identities will appear when Fleet is ready.</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  shell: {
    borderWidth: 0,
    borderBottomWidth: 1,
    borderBottomColor: UI.color.border,
    backgroundColor: 'transparent',
    paddingHorizontal: 0,
    paddingVertical: 10,
    gap: 9,
  },
  shellCompact: {
    borderWidth: 0,
    borderBottomWidth: 1,
    borderBottomColor: UI.color.border,
    paddingHorizontal: 12,
  },
  headerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  headerCopy: { flex: 1, minWidth: 0 },
  eyebrow: { color: UI.color.textSubtle, fontSize: 10, fontWeight: '600', letterSpacing: 0.65, textTransform: 'uppercase' },
  hint: { color: UI.color.textSubtle, fontSize: 11, marginTop: 2 },
  identityList: { flexDirection: 'row', gap: 8, paddingRight: 4 },
  identityChip: {
    minWidth: 144,
    maxWidth: 230,
    minHeight: 42,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 0,
    borderRadius: UI.radius.control,
    backgroundColor: 'transparent',
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  identityChipActive: { backgroundColor: UI.color.accentSoft },
  identityChipHovered: { backgroundColor: UI.color.surfaceHover },
  identityChipDisabled: { opacity: 0.55 },
  statusDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: UI.color.textSubtle },
  statusDotOnline: { backgroundColor: UI.color.success },
  identityCopy: { flex: 1, minWidth: 0 },
  identityName: { color: UI.color.textMuted, fontSize: 12, fontWeight: '600' },
  identityNameActive: { color: UI.color.text },
  identityMeta: { color: UI.color.textSubtle, fontSize: 10, marginTop: 2, textTransform: 'capitalize' },
  identityMetaActive: { color: UI.color.accentStrong },
  empty: { color: UI.color.textSubtle, fontSize: 11 },
});
