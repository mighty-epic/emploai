import { StyleSheet, Text, View } from "react-native";

import type {
  DesktopFleetRemoteTarget,
  DesktopFleetSnapshot,
  DesktopFleetWorker,
} from "@/lib/desktopBridge";
import { fleetReportSummary } from "./desktopFleetWorkerState";
import { FLEET_TYPE as TYPE } from "./desktopFleetUi";
import { DESKTOP_UI as UI } from "./desktopUiTokens";

type ActivityRow = {
  id: string;
  name: string;
  role: string;
  status: string;
  detail: string;
  meta: string;
};

function matchingDelegation(
  snapshot: DesktopFleetSnapshot | null | undefined,
  desktopId: string,
  target: DesktopFleetRemoteTarget,
) {
  const selectors = [
    String(target.target_selector || ""),
    String(target.identity_id || ""),
  ];
  const normalized = new Set(selectors.filter(Boolean));
  return (snapshot?.delegations || []).find(
    (item) =>
      item.desktop_id === desktopId &&
      (normalized.has(String(item.target_selector || "")) ||
        (target.target_kind === "manager" && item.target_kind === "manager")),
  );
}

function workerActivity(
  snapshot: DesktopFleetSnapshot | null | undefined,
  worker: DesktopFleetWorker,
): ActivityRow {
  const task =
    (snapshot?.tasks || []).find(
      (item) =>
        item.worker_id === worker.worker_id && item.status === "running",
    ) ||
    (snapshot?.tasks || []).find(
      (item) => item.worker_id === worker.worker_id && item.status === "queued",
    );
  const report = (snapshot?.reports || []).find(
    (item) => item.worker_id === worker.worker_id,
  );
  return {
    id: worker.worker_id,
    name: worker.display_name,
    role: "Worker",
    status: task?.status || worker.status || "ready",
    detail:
      task?.prompt || fleetReportSummary(report) || "No activity reported yet.",
    meta: task
      ? "Current work"
      : report
        ? `Latest report · ${report.confidence || "unrated"} confidence`
        : "Waiting for work",
  };
}

function targetActivity(
  snapshot: DesktopFleetSnapshot | null | undefined,
  desktopId: string,
  target: DesktopFleetRemoteTarget,
): ActivityRow {
  const delegation = matchingDelegation(snapshot, desktopId, target);
  const report = delegation?.report || {};
  return {
    id: String(
      target.identity_id || target.target_selector || target.display_name,
    ),
    name: target.display_name,
    role: target.target_kind === "manager" ? "Main identity" : "Worker",
    status: delegation?.status || target.status || "ready",
    detail: fleetReportSummary({
      summary:
        report.summary || delegation?.prompt || "No activity reported yet.",
      provider_failure: report.provider_failure,
    }),
    meta: delegation
      ? "Most recent delegated work"
      : "Available on this computer",
  };
}

export function DesktopFleetComputerActivity({
  snapshot,
  desktopId,
  targets,
}: {
  snapshot: DesktopFleetSnapshot | null | undefined;
  desktopId: string;
  targets: DesktopFleetRemoteTarget[];
}) {
  const workers = (snapshot?.workers || []).filter(
    (worker) => worker.machine_desktop_id === desktopId,
  );
  const workerIds = new Set(workers.map((worker) => worker.worker_id));
  const realWorkerSelectors = new Set([
    ...workerIds,
    ...(snapshot?.identities || [])
      .filter((identity) =>
        Boolean(identity.worker_id && workerIds.has(identity.worker_id)),
      )
      .map((identity) => identity.identity_id),
  ]);
  const rows: ActivityRow[] = [
    ...workers.map((worker) => workerActivity(snapshot, worker)),
    ...targets
      .filter(
        (target) =>
          !realWorkerSelectors.has(String(target.target_selector || "")) &&
          !realWorkerSelectors.has(String(target.identity_id || "")),
      )
      .map((target) => targetActivity(snapshot, desktopId, target)),
  ];

  return (
    <View style={styles.section}>
      <View style={styles.headingRow}>
        <View>
          <Text style={styles.eyebrow}>WORKER ACTIVITY</Text>
          <Text style={styles.title}>Latest on this computer</Text>
        </View>
        <Text style={styles.count}>{rows.length}</Text>
      </View>

      {rows.length ? (
        rows.map((row) => (
          <View key={row.id} style={styles.row}>
            <View style={styles.rowHeader}>
              <View style={styles.identity}>
                <Text style={styles.name}>{row.name}</Text>
                <Text style={styles.role}>{row.role}</Text>
              </View>
              <Text style={styles.status}>{row.status.toUpperCase()}</Text>
            </View>
            <Text style={styles.detail} numberOfLines={4}>
              {row.detail}
            </Text>
            <Text style={styles.meta}>{row.meta}</Text>
          </View>
        ))
      ) : (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>No workers exposed yet</Text>
          <Text style={styles.emptyText}>
            This computer is connected, but it has not exposed a worker identity
            or reported activity.
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    flex: 1,
    minWidth: 300,
    padding: 14,
    gap: 10,
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surface,
  },
  headingRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 10,
  },
  eyebrow: {
    color: UI.color.accentStrong,
    fontFamily: UI.type.mono,
    fontSize: TYPE.eyebrow,
    fontWeight: "900",
    letterSpacing: 0.8,
  },
  title: {
    marginTop: 4,
    color: UI.color.text,
    fontSize: TYPE.sectionTitle,
    fontWeight: "900",
  },
  count: {
    minWidth: 30,
    color: UI.color.accentStrong,
    fontSize: TYPE.sectionTitle,
    fontWeight: "900",
    textAlign: "right",
  },
  row: {
    padding: 11,
    gap: 6,
    borderWidth: 1,
    borderColor: UI.color.border,
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.canvas,
  },
  rowHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 8,
  },
  identity: { flex: 1, gap: 2 },
  name: { color: UI.color.text, fontSize: TYPE.body, fontWeight: "900" },
  role: { color: UI.color.textSubtle, fontSize: TYPE.meta },
  status: {
    color: UI.color.accentStrong,
    fontFamily: UI.type.mono,
    fontSize: TYPE.micro,
    fontWeight: "900",
  },
  detail: {
    color: UI.color.textMuted,
    fontSize: TYPE.body,
    lineHeight: TYPE.bodyLine,
  },
  meta: {
    color: UI.color.textSubtle,
    fontFamily: UI.type.mono,
    fontSize: TYPE.micro,
  },
  empty: {
    minHeight: 150,
    padding: 18,
    alignItems: "center",
    justifyContent: "center",
    gap: 5,
  },
  emptyTitle: { color: UI.color.text, fontSize: TYPE.body, fontWeight: "900" },
  emptyText: {
    color: UI.color.textSubtle,
    fontSize: TYPE.body,
    lineHeight: TYPE.bodyLine,
    textAlign: "center",
  },
});
