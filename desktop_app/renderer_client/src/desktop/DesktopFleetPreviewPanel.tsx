import React from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import type { DesktopFleetPreviewResult } from '../lib/desktopBridge';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';
import { DESKTOP_UI as UI } from './desktopUiTokens';


type DesktopFleetPreviewPanelProps = {
  preview: DesktopFleetPreviewResult | null;
  workerId: string;
  workerName: string;
  onClose: () => void;
};


export function DesktopFleetPreviewPanel({ preview, workerId, workerName, onClose }: DesktopFleetPreviewPanelProps) {
  if (!preview || preview.worker_id !== workerId) {
    return null;
  }

  const capture = preview.capture;
  const imageUri = capture?.image_base64
    ? `data:${capture.mime_type || 'image/jpeg'};base64,${capture.image_base64}`
    : null;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>{workerName} preview</Text>
          <Text style={styles.meta}>
            {capture ? `${capture.width} × ${capture.height} · ${capture.backend}` : preview.dispatch_status}
          </Text>
        </View>
        <Pressable accessibilityRole="button" accessibilityLabel="Close worker preview" onPress={onClose} style={styles.closeButton}>
          <Text style={styles.closeText}>Close</Text>
        </Pressable>
      </View>
      {imageUri ? (
        <Image source={{ uri: imageUri }} resizeMode="contain" style={styles.image} />
      ) : (
        <Text style={styles.detail}>{preview.detail || 'No preview image was returned.'}</Text>
      )}
      {imageUri && preview.detail ? <Text style={styles.detail}>{preview.detail}</Text> : null}
    </View>
  );
}


const styles = StyleSheet.create({
  container: {
    marginTop: 12,
    overflow: 'hidden',
    borderWidth: 0,
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceMuted,
  },
  header: {
    minHeight: 44,
    paddingHorizontal: 12,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  headerCopy: {
    flex: 1,
  },
  title: {
    color: UI.color.text,
    fontSize: TYPE.sectionTitle,
    fontWeight: '700',
  },
  meta: {
    marginTop: 2,
    color: UI.color.textSubtle,
    fontSize: TYPE.meta,
  },
  closeButton: {
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  closeText: {
    color: UI.color.textMuted,
    fontSize: TYPE.body,
    fontWeight: '700',
  },
  image: {
    width: '100%',
    aspectRatio: 16 / 9,
    backgroundColor: UI.color.canvas,
  },
  detail: {
    paddingHorizontal: 12,
    paddingVertical: 9,
    color: UI.color.textMuted,
    fontSize: TYPE.body,
    lineHeight: TYPE.bodyLine,
  },
});
