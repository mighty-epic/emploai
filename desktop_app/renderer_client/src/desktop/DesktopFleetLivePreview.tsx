import { useCallback, useEffect, useRef, useState } from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";

import {
  requestDesktopFleetComputerPreview,
  type DesktopFleetPreviewResult,
} from "@/lib/desktopBridge";
import { userFacingError } from "../../lib/diagnostics";
import { DesktopFleetInfoButton } from "./DesktopFleetInfoButton";
import { FLEET_TYPE as TYPE } from "./desktopFleetUi";
import { DESKTOP_UI as UI } from "./desktopUiTokens";

type PreviewRate = 0 | 1 | 2 | 4;

const RATE_OPTIONS: Array<{ value: PreviewRate; label: string }> = [
  { value: 0, label: "Manual" },
  { value: 1, label: "1/min" },
  { value: 2, label: "2/min" },
  { value: 4, label: "4/min" },
];

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
}: {
  desktopId: string;
  desktopName: string;
  online: boolean;
}) {
  const [rate, setRate] = useState<PreviewRate>(0);
  const [preview, setPreview] = useState<DesktopFleetPreviewResult | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const requestInFlightRef = useRef(false);
  const requestSequenceRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestSequenceRef.current += 1;
    };
  }, []);

  useEffect(() => {
    requestSequenceRef.current += 1;
    requestInFlightRef.current = false;
    setRate(0);
    setPreview(null);
    setError(null);
  }, [desktopId]);

  const capture = useCallback(async () => {
    if (!online || requestInFlightRef.current) return;
    const requestSequence = ++requestSequenceRef.current;
    requestInFlightRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const result = await requestDesktopFleetComputerPreview(desktopId);
      if (!mountedRef.current || requestSequence !== requestSequenceRef.current)
        return;
      if (!result)
        throw new Error(
          "Desktop preview controls are unavailable in this shell.",
        );
      if (
        result.dispatch_status !== "captured" ||
        !result.capture?.image_base64
      ) {
        throw new Error(
          result.detail || "This computer did not return a preview.",
        );
      }
      setPreview(result);
    } catch (captureError) {
      if (
        mountedRef.current &&
        requestSequence === requestSequenceRef.current
      ) {
        setError(
          userFacingError(captureError, `Could not capture ${desktopName}.`),
        );
      }
    } finally {
      requestInFlightRef.current = false;
      if (mountedRef.current && requestSequence === requestSequenceRef.current)
        setLoading(false);
    }
  }, [desktopId, desktopName, online]);

  useEffect(() => {
    if (!online || rate === 0) return undefined;
    void capture();
    const timer = globalThis.setInterval(() => void capture(), 60_000 / rate);
    return () => globalThis.clearInterval(timer);
  }, [capture, online, rate]);

  const captureUri = preview?.capture
    ? `data:${preview.capture.mime_type || "image/jpeg"};base64,${preview.capture.image_base64}`
    : null;

  return (
    <View style={styles.section}>
      <View style={styles.headingRow}>
        <View style={styles.headingCopy}>
          <Text style={styles.eyebrow}>VIEW-ONLY PREVIEW</Text>
          <Text style={styles.title}>Current screen</Text>
        </View>
        <DesktopFleetInfoButton
          label="Live preview privacy"
          text="Preview captures bounded screenshots only at the rate you choose. Frames stay in this open panel's memory and are discarded when you close it. There is no mouse, keyboard, or continuous video access."
        />
      </View>

      <View style={styles.rateRow} accessibilityRole="radiogroup">
        {RATE_OPTIONS.map((option) => (
          <Pressable
            key={option.value}
            accessibilityRole="radio"
            accessibilityLabel={
              option.value
                ? `${option.value} screenshots per minute`
                : "Manual screenshots only"
            }
            accessibilityState={{
              checked: rate === option.value,
              disabled: !online,
            }}
            disabled={!online}
            onPress={() => setRate(option.value)}
            style={[
              styles.rateButton,
              rate === option.value ? styles.rateButtonSelected : null,
              !online ? styles.disabled : null,
            ]}
          >
            <Text
              style={[
                styles.rateText,
                rate === option.value ? styles.rateTextSelected : null,
              ]}
            >
              {option.label}
            </Text>
          </Pressable>
        ))}
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: !online || loading }}
          disabled={!online || loading}
          onPress={() => void capture()}
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
              {online ? "No screenshot yet" : "Computer offline"}
            </Text>
            <Text style={styles.emptyText}>
              {online
                ? "Capture once or choose a screenshots-per-minute rate."
                : "Preview resumes only after this computer reconnects."}
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
        {rate > 0 ? (
          <Text style={styles.liveBadge}>● {rate}/MIN ACTIVE</Text>
        ) : (
          <Text style={styles.manualBadge}>MANUAL</Text>
        )}
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
  rateRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  rateButton: {
    minHeight: 42,
    minWidth: 64,
    paddingHorizontal: 11,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surface,
  },
  rateButtonSelected: {
    borderColor: UI.color.accentBorder,
    backgroundColor: UI.color.accentSoft,
  },
  rateText: {
    color: UI.color.textMuted,
    fontSize: TYPE.body,
    fontWeight: "800",
  },
  rateTextSelected: { color: UI.color.accentStrong },
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
  manualBadge: {
    marginLeft: "auto",
    color: UI.color.textSubtle,
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
