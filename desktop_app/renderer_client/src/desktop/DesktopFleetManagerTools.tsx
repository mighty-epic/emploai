import { useEffect, useMemo, useState } from 'react';
import ChevronDown from 'lucide-react-native/icons/chevron-down';
import ChevronUp from 'lucide-react-native/icons/chevron-up';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { DesktopFleetRemoteTarget } from '@/lib/desktopBridge';
import { TOOL_PACK_DEFINITIONS } from './desktopToolPacks';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';
import { DESKTOP_UI as UI } from './desktopUiTokens';

const MANAGER_CORE = 'manager_core';

function optionalPacks(target: DesktopFleetRemoteTarget | null): string[] {
  return (target?.enabled_tool_packs || []).filter((packId) => packId !== MANAGER_CORE);
}

export function DesktopFleetManagerTools({
  desktopId,
  desktopName,
  manager,
  allowed,
  online,
  busy,
  onSave,
}: {
  desktopId: string;
  desktopName: string;
  manager: DesktopFleetRemoteTarget | null;
  allowed: boolean;
  online: boolean;
  busy: boolean;
  onSave: (enabledToolPacks: string[]) => Promise<boolean>;
}) {
  const configured = optionalPacks(manager);
  const signature = configured.slice().sort().join('|');
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState<string[]>(configured);

  useEffect(() => {
    setExpanded(false);
    setDraft(optionalPacks(manager));
  }, [desktopId]);

  useEffect(() => {
    setDraft(optionalPacks(manager));
  }, [signature]);

  const changed = useMemo(() => {
    const current = new Set(configured);
    return draft.length !== current.size || draft.some((packId) => !current.has(packId));
  }, [draft, signature]);
  const unsupported = !manager || !Array.isArray(manager.enabled_tool_packs);
  const saveDisabled = busy || !online || !allowed || unsupported || !changed;

  const toggle = (packId: string) => {
    setDraft((current) => current.includes(packId)
      ? current.filter((item) => item !== packId)
      : [...current, packId]);
  };

  const save = async () => {
    if (saveDisabled) return;
    const saved = await onSave([MANAGER_CORE, ...draft]);
    if (saved) setExpanded(false);
  };

  const summary = unsupported
    ? 'Update required'
    : configured.length
      ? `${configured.length} optional pack${configured.length === 1 ? '' : 's'}`
      : 'Delegates execution by default';

  return (
    <View style={styles.container}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Manager tools on ${desktopName}, ${summary}`}
        accessibilityState={{ expanded }}
        onPress={() => setExpanded((current) => !current)}
        style={styles.summary}
      >
        <View style={styles.summaryCopy}>
          <Text style={styles.title}>Manager tools</Text>
          <Text style={[styles.meta, !allowed ? styles.metaBlocked : null]}>
            {allowed ? summary : 'Remote configuration blocked'}
          </Text>
        </View>
        <View style={styles.disclosure}>
          <Text style={styles.disclosureLabel}>{expanded ? 'Close' : 'Change'}</Text>
          {expanded
            ? <ChevronUp size={16} color={UI.color.accentStrong} strokeWidth={2} />
            : <ChevronDown size={16} color={UI.color.accentStrong} strokeWidth={2} />}
        </View>
      </Pressable>

      {expanded ? (
        <View style={styles.editor}>
          <View style={styles.coreRow}>
            <View style={styles.coreCopy}>
              <Text style={styles.packLabel}>Manager Core</Text>
              <Text style={styles.packDetail}>Orchestration, memory, automations, and scheduling</Text>
            </View>
            <Text style={styles.required}>REQUIRED</Text>
          </View>

          {TOOL_PACK_DEFINITIONS.map((pack) => {
            const enabled = draft.includes(pack.id);
            return (
              <Pressable
                key={pack.id}
                accessibilityRole="switch"
                accessibilityLabel={pack.label}
                accessibilityState={{ checked: enabled, disabled: busy || !allowed || unsupported }}
                disabled={busy || !allowed || unsupported}
                onPress={() => toggle(pack.id)}
                style={styles.packRow}
              >
                <View style={styles.packCopy}>
                  <Text style={[styles.packLabel, enabled ? styles.packLabelEnabled : null]}>{pack.label}</Text>
                  <Text style={styles.packDetail} numberOfLines={1}>{pack.description}</Text>
                </View>
                <View style={[styles.switchTrack, enabled ? styles.switchTrackEnabled : null]}>
                  <View style={[styles.switchKnob, enabled ? styles.switchKnobEnabled : null]} />
                </View>
              </Pressable>
            );
          })}

          <View style={styles.footer}>
            <Text style={styles.note}>
              {!allowed
                ? `Allow “Configure manager tools” in Connection access first.`
                : unsupported
                  ? `Update ${desktopName} before changing its manager profile.`
                  : 'Disabled capabilities continue to route to that computer’s default worker.'}
            </Text>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: saveDisabled }}
              disabled={saveDisabled}
              onPress={() => void save()}
              style={[styles.saveButton, saveDisabled ? styles.disabled : null]}
            >
              <Text style={styles.saveButtonText}>{busy ? 'Saving…' : 'Save tools'}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { overflow: 'hidden', borderRadius: UI.radius.panel, backgroundColor: UI.color.surfaceMuted },
  summary: { minHeight: 60, paddingHorizontal: 14, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', gap: 12 },
  summaryCopy: { flex: 1, minWidth: 0, gap: 5 },
  title: { color: UI.color.text, fontSize: TYPE.control, fontWeight: '800' },
  meta: { color: UI.color.textMuted, fontSize: TYPE.meta, fontWeight: '700' },
  metaBlocked: { color: UI.color.warning },
  disclosure: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  disclosureLabel: { color: UI.color.accentStrong, fontSize: TYPE.body, fontWeight: '800' },
  editor: { paddingHorizontal: 14, paddingTop: 4, paddingBottom: 14 },
  coreRow: { minHeight: 50, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 12 },
  coreCopy: { flex: 1, minWidth: 0 },
  required: { color: UI.color.success, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  packRow: { minHeight: 50, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 12 },
  packCopy: { flex: 1, minWidth: 0 },
  packLabel: { color: UI.color.textMuted, fontSize: TYPE.body, fontWeight: '800' },
  packLabelEnabled: { color: UI.color.text },
  packDetail: { marginTop: 2, color: UI.color.textSubtle, fontSize: TYPE.meta },
  switchTrack: { width: 36, height: 20, padding: 2, borderRadius: UI.radius.pill, backgroundColor: UI.color.surfaceRaised },
  switchTrackEnabled: { backgroundColor: UI.color.accentSoft },
  switchKnob: { width: 16, height: 16, borderRadius: UI.radius.pill, backgroundColor: UI.color.textSubtle },
  switchKnobEnabled: { marginLeft: 16, backgroundColor: UI.color.accentStrong },
  footer: { paddingTop: 12, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  note: { flexGrow: 1, flexShrink: 1, color: UI.color.textSubtle, fontSize: TYPE.meta },
  saveButton: { minHeight: 38, paddingHorizontal: 12, borderRadius: UI.radius.control, backgroundColor: UI.color.accentSoft, alignItems: 'center', justifyContent: 'center' },
  saveButtonText: { color: UI.color.accentStrong, fontSize: TYPE.body, fontWeight: '900' },
  disabled: { opacity: 0.4 },
});
