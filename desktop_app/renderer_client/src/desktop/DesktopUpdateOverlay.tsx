import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { DESKTOP_UI as UI } from "./desktopUiTokens";
import { useReducedMotion } from "./useReducedMotion";

export type DesktopUpdatePhase =
  | "preparing"
  | "stopping"
  | "checking"
  | "preserving"
  | "pulling"
  | "dependencies"
  | "building"
  | "restarting";

export type DesktopUpdateProgress = {
  phase: DesktopUpdatePhase;
  message: string;
  updatedAt?: string | null;
};

const UPDATE_STEPS: DesktopUpdatePhase[] = [
  "preparing",
  "stopping",
  "checking",
  "preserving",
  "pulling",
  "dependencies",
  "building",
  "restarting",
];

function phaseLabel(phase: DesktopUpdatePhase) {
  if (phase === "stopping") return "Securing active work";
  if (phase === "checking") return "Checking update";
  if (phase === "preserving") return "Preserving local changes";
  if (phase === "pulling") return "Downloading changes";
  if (phase === "dependencies") return "Updating dependencies";
  if (phase === "building") return "Building desktop";
  if (phase === "restarting") return "Restarting";
  return "Preparing";
}

export function desktopUpdatePhaseForMessage(
  message: string | null | undefined,
): DesktopUpdatePhase {
  const value = String(message || "").toLowerCase();
  if (value.includes("restart")) return "restarting";
  if (value.includes("build")) return "building";
  if (value.includes("dependenc")) return "dependencies";
  if (value.includes("download") || value.includes("pull")) return "pulling";
  if (value.includes("backing up") || value.includes("preserv"))
    return "preserving";
  if (value.includes("check")) return "checking";
  if (value.includes("stopping") || value.includes("securing"))
    return "stopping";
  return "preparing";
}

export function DesktopUpdateOverlay({
  progress,
}: {
  progress: DesktopUpdateProgress;
}) {
  const reducedMotion = useReducedMotion();
  const phaseIndex = Math.max(0, UPDATE_STEPS.indexOf(progress.phase));
  const completion = Math.max(
    8,
    Math.round(((phaseIndex + 1) / UPDATE_STEPS.length) * 100),
  );

  return (
    <View
      accessibilityRole="alert"
      accessibilityViewIsModal
      accessibilityLiveRegion="polite"
      style={styles.overlay}
      pointerEvents="auto"
    >
      <View style={styles.card}>
        <View style={styles.statusRow}>
          <View style={styles.spinnerFrame}>
            {reducedMotion ? (
              <Text style={styles.staticGlyph}>↑</Text>
            ) : (
              <ActivityIndicator color={UI.color.accentStrong} size="small" />
            )}
          </View>
          <View style={styles.copy}>
            <Text style={styles.eyebrow}>DESKTOP UPDATE IN PROGRESS</Text>
            <Text style={styles.title}>{phaseLabel(progress.phase)}</Text>
          </View>
        </View>

        <Text style={styles.message}>{progress.message}</Text>

        <View
          style={styles.track}
          accessibilityLabel={`Update progress: ${completion} percent`}
        >
          <View style={[styles.fill, { width: `${completion}%` }]} />
        </View>

        <View style={styles.safetyNote}>
          <Text style={styles.safetyTitle}>Please leave EmploAI open</Text>
          <Text style={styles.safetyText}>
            Controls are paused while the project is updated. The desktop app
            will close and reopen automatically when it is ready.
          </Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 100000,
    elevation: 100000,
    padding: 24,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(2, 7, 14, 0.94)",
  },
  card: {
    width: "100%",
    maxWidth: 560,
    padding: 26,
    gap: 20,
    borderRadius: UI.radius.large,
    backgroundColor: UI.color.surfaceRaised,
    ...UI.elevation.high,
  },
  statusRow: { flexDirection: "row", alignItems: "center", gap: 15 },
  spinnerFrame: {
    width: 48,
    height: 48,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accentSoft,
  },
  staticGlyph: {
    color: UI.color.accentStrong,
    fontSize: 20,
    fontWeight: "900",
  },
  copy: { flex: 1, gap: 5 },
  eyebrow: {
    color: UI.color.accentStrong,
    fontFamily: UI.type.mono,
    fontSize: 11,
    fontWeight: "900",
    letterSpacing: 1.1,
  },
  title: {
    color: UI.color.text,
    fontSize: 24,
    lineHeight: 30,
    fontWeight: "900",
  },
  message: { color: UI.color.textMuted, fontSize: 15, lineHeight: 23 },
  track: {
    height: 7,
    overflow: "hidden",
    borderRadius: UI.radius.pill,
    backgroundColor: UI.color.surfaceRaised,
  },
  fill: {
    height: "100%",
    borderRadius: UI.radius.pill,
    backgroundColor: UI.color.accentStrong,
  },
  safetyNote: {
    padding: 14,
    gap: 4,
    borderLeftWidth: 3,
    borderLeftColor: UI.color.accentStrong,
    backgroundColor: UI.color.surface,
  },
  safetyTitle: { color: UI.color.text, fontSize: 14, fontWeight: "800" },
  safetyText: { color: UI.color.textSubtle, fontSize: 13, lineHeight: 20 },
});
