import { useEffect, useState } from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";

import type { DesktopFleetPreviewResult } from "@/lib/desktopBridge";
import { DesktopFleetInfoButton } from "./DesktopFleetInfoButton";
import {
  captureDesktopFleetPreview,
  getDesktopFleetPreviewState,
  subscribeDesktopFleetPreview,
} from "./desktopFleetPreviewScheduler";
import { FLEET_TYPE as TYPE } from "./desktopFleetUi";
import { DESKTOP_UI as UI } from "./desktopUiTokens";

function previewTimestamp(preview: DesktopFleetPreviewResult | null) {
  const raw = Number(preview?.capture?.captured_at || 0);
  if (!raw) return "No preview captured";
  const milliseconds = raw < 10_000_000_000 ? raw * 1000 : raw;
  return `Captured ${new Date(milliseconds).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
}

export function DesktopFleetLivePreview({
  desktopId,
  desktopName,
  online,
  automatic,
}: {
  desktopId: string;
  desktopName: string;
  online: boolean;
  automatic: boolean;
}) {
  const [previewState, setPreviewState] = useState(() => getDesktopFleetPreviewState(desktopId));

  useEffect(() => {
    const sync = () => setPreviewState(getDesktopFleetPreviewState(desktopId));
    const unsubscribe = subscribeDesktopFleetPreview(desktopId, sync);
    sync();
    return unsubscribe;
  }, [desktopId]);

  const { preview, latestResult, loading, error } = previewState;

  const captureUri = preview?.capture
    ? `data:${preview.capture.mime_type || "image/jpeg"};base64,${preview.capture.image_base64}`
    : null;
  const captureUnavailable = latestResult?.capture_capability?.available === false;
  const recovery = String(latestResult?.capture_capability?.recovery || "").trim();

  return (
    <View style={styles.section}>
      <View style={styles.headingRow}>
        <View style={styles.headingCopy}>
          <Text style={styles.eyebrow}>VIEW-ONLY PREVIEW</Text>
          <Text style={styles.title}>Current screen</Text>
        </View>
        <DesktopFleetInfoButton
          label="Live preview privacy"
          text="While this Yggdrasil computer is online, EmploAI captures one bounded screenshot every 10 seconds on Fleet and every 2 minutes elsewhere. Frames remain only in this app's renderer memory. There is no mouse, keyboard, continuous video, or cloud storage."
        />
      </View>

      <View style={styles.captureRow}>
        <View style={[styles.autoBadge, !online || !automatic ? styles.autoBadgePaused : null]}>
          <Text style={[styles.autoBadgeText, !online || !automatic ? styles.autoBadgeTextPaused : null]}>
            {!automatic
              ? "○ AUTO UNAVAILABLE · UPDATE REQUIRED"
              : online
                ? "● AUTO · EVERY 10 SEC"
                : "○ AUTO PAUSED · OFFLINE"}
          </Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Capture ${desktopName} screen now`}
          accessibilityState={{ disabled: !online || loading }}
          disabled={!online || loading}
          onPress={() => void captureDesktopFleetPreview(desktopId, desktopName)}
          style={[
            styles.captureButton,
            !online || loading ? styles.disabled : null,
          ]}
        >
          <Text style={styles.captureButtonText}>
            {loading ? "Capturing…" : "Capture now"}
          </Text>
        </Pressable>
      </View>

      <View style={styles.previewFrame}>
        {captureUri ? (
          <Image
            accessibilityLabel={`Latest view-only screenshot from ${desktopName}`}
            source={{ uri: captureUri }}
            resizeMode="contain"
            style={styles.image}
          />
        ) : (
          <View style={styles.emptyPreview}>
            <Text style={styles.emptyGlyph}>▣</Text>
            <Text style={styles.emptyTitle}>
              {!online
                ? "Computer offline"
                : captureUnavailable
                  ? "Screen unavailable"
                  : "No screenshot yet"}
            </Text>
            <Text style={styles.emptyText}>
              {!online
                ? "Preview resumes only after this computer reconnects."
                : captureUnavailable
                  ? recovery || "The computer is connected, but Windows is not exposing a desktop frame."
                  : automatic
                    ? "The first screenshot appears automatically while this Yggdrasil computer is online."
                    : "Update EmploAI on this computer to enable automatic previews. You can still try Capture now."}
            </Text>
          </View>
        )}
      </View>

      <View style={styles.footer} accessibilityLiveRegion="polite">
        <Text style={styles.freshness}>{previewTimestamp(preview)}</Text>
        {preview?.capture ? (
          <Text style={styles.captureMeta}>
            {preview.capture.width}×{preview.capture.height} ·{" "}
            {preview.capture.backend}
          </Text>
        ) : null}
        {captureUnavailable ? (
          <Text style={styles.unavailableBadge}>DISPLAY UNAVAILABLE</Text>
        ) : automatic ? (
          <Text style={styles.liveBadge}>{loading ? "UPDATING…" : "AUTO ACTIVE"}</Text>
        ) : null}
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    flex: 1,
    minWidth: 300,
    padding: 14,
    gap: 12,
    borderWidth: 1,
    borderColor: UI.color.accentBorder,
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.canvas,
  },
  headingRow: {
    position: "relative",
    zIndex: 10,
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 10,
  },
  headingCopy: { flex: 1, gap: 4 },
  eyebrow: {
    color: UI.color.accentStrong,
    fontFamily: UI.type.mono,
    fontSize: TYPE.eyebrow,
    fontWeight: "900",
    letterSpacing: 0.8,
  },
  title: {
    color: UI.color.text,
    fontSize: TYPE.sectionTitle,
    fontWeight: "900",
  },
  captureRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  autoBadge: {
    minHeight: 42,
    paddingHorizontal: 12,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: UI.color.accentBorder,
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accentSoft,
  },
  autoBadgePaused: {
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surface,
  },
  autoBadgeText: {
    color: UI.color.success,
    fontFamily: UI.type.mono,
    fontSize: TYPE.micro,
    fontWeight: "900",
  },
  autoBadgeTextPaused: { color: UI.color.textSubtle },
  captureButton: {
    minHeight: 42,
    paddingHorizontal: 15,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accentStrong,
  },
  captureButtonText: {
    color: UI.color.accentInk,
    fontSize: TYPE.body,
    fontWeight: "900",
  },
  disabled: { opacity: 0.42 },
  previewFrame: {
    minHeight: 220,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: UI.color.border,
    borderRadius: UI.radius.control,
    backgroundColor: "#02050a",
  },
  image: {
    width: "100%",
    minHeight: 220,
    aspectRatio: 16 / 9,
    backgroundColor: "#02050a",
  },
  emptyPreview: {
    minHeight: 220,
    padding: 24,
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
  },
  emptyGlyph: { color: UI.color.textSubtle, fontSize: 28 },
  emptyTitle: {
    color: UI.color.text,
    fontSize: TYPE.sectionTitle,
    fontWeight: "900",
  },
  emptyText: {
    maxWidth: 360,
    color: UI.color.textSubtle,
    fontSize: TYPE.body,
    lineHeight: TYPE.bodyLine,
    textAlign: "center",
  },
  footer: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 8,
  },
  freshness: { color: UI.color.text, fontSize: TYPE.body, fontWeight: "800" },
  captureMeta: {
    color: UI.color.textSubtle,
    fontFamily: UI.type.mono,
    fontSize: TYPE.micro,
  },
  liveBadge: {
    marginLeft: "auto",
    color: UI.color.success,
    fontFamily: UI.type.mono,
    fontSize: TYPE.micro,
    fontWeight: "900",
  },
  unavailableBadge: {
    marginLeft: "auto",
    color: UI.color.warning,
    fontFamily: UI.type.mono,
    fontSize: TYPE.micro,
    fontWeight: "900",
  },
  error: {
    color: UI.color.danger,
    fontSize: TYPE.body,
    lineHeight: TYPE.bodyLine,
    fontWeight: "700",
  },
});
