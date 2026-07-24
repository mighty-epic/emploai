import { useMemo, useState, type ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type {
  CompanyEmployee,
  CompanyPosition,
} from '@/lib/appApi';


type DepartmentRecord = Record<string, unknown>;
const MAX_VISIBLE_NODES = 60;


export function CompanyOrgChart({
  employees,
  positions,
  departments,
}: {
  employees: CompanyEmployee[];
  positions: CompanyPosition[];
  departments: DepartmentRecord[];
}) {
  const [open, setOpen] = useState(false);
  const chart = useMemo(() => {
    const employeeByIdentity = new Map(
      employees.map((employee) => [employee.identity_id, employee]),
    );
    const departmentById = new Map(
      departments.map((department) => [
        String(department.department_id || ''),
        String(department.name || 'Department'),
      ]),
    );
    const activePositions = positions.filter(
      (position) => !['archived', 'closed'].includes(position.status),
    );
    const positionByOccupant = new Map(
      activePositions
        .filter((position) => position.occupant_identity_id)
        .map((position) => [String(position.occupant_identity_id), position]),
    );
    const childrenByManager = new Map<string, CompanyPosition[]>();
    const roots: CompanyPosition[] = [];
    activePositions.forEach((position) => {
      const managerId = String(position.manager_identity_id || '');
      if (
        managerId
        && positionByOccupant.has(managerId)
        && managerId !== position.occupant_identity_id
      ) {
        childrenByManager.set(managerId, [
          ...(childrenByManager.get(managerId) || []),
          position,
        ]);
      } else {
        roots.push(position);
      }
    });
    const sortPositions = (items: CompanyPosition[]) => [...items].sort(
      (left, right) => left.title.localeCompare(right.title),
    );
    return {
      employeeByIdentity,
      departmentById,
      childrenByManager,
      roots: sortPositions(roots),
      sortPositions,
      activePositionCount: activePositions.length,
    };
  }, [departments, employees, positions]);

  let renderedNodes = 0;
  const renderNode = (
    position: CompanyPosition,
    depth: number,
    ancestry: Set<string>,
  ): ReactNode => {
    if (renderedNodes >= MAX_VISIBLE_NODES) return null;
    renderedNodes += 1;
    const occupantId = String(position.occupant_identity_id || '');
    const employee = chart.employeeByIdentity.get(occupantId);
    const department = chart.departmentById.get(
      String(position.department_id || ''),
    );
    const cycle = ancestry.has(position.position_id);
    const nextAncestry = new Set(ancestry);
    nextAncestry.add(position.position_id);
    const children = occupantId
      ? chart.sortPositions(chart.childrenByManager.get(occupantId) || [])
      : [];
    return (
      <View key={position.position_id}>
        <View style={[styles.node, { marginLeft: Math.min(depth, 6) * 18 }]}>
          <View style={styles.connector} />
          <View style={styles.nodeCopy}>
            <Text style={styles.nodeTitle}>{position.title}</Text>
            <Text style={styles.nodeMeta}>
              {employee?.display_name || 'Open position'}
              {department ? ` · ${department}` : ''}
              {cycle ? ' · reporting cycle needs attention' : ''}
            </Text>
          </View>
          <Text style={employee ? styles.occupied : styles.openState}>
            {employee ? employee.system_role : 'OPEN'}
          </Text>
        </View>
        {!cycle
          ? children.map((child) => renderNode(child, depth + 1, nextAncestry))
          : null}
      </View>
    );
  };

  return (
    <View style={styles.section}>
      <View style={styles.header}>
        <View style={styles.copy}>
          <Text style={styles.eyebrow}>REPORTING STRUCTURE</Text>
          <Text style={styles.title}>Organization map</Text>
          <Text style={styles.meta}>
            {chart.activePositionCount} position{chart.activePositionCount === 1 ? '' : 's'} · job authority, not computer topology
          </Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ expanded: open }}
          style={styles.action}
          onPress={() => setOpen((value) => !value)}
        >
          <Text style={styles.actionText}>{open ? 'Collapse' : 'Show'}</Text>
        </Pressable>
      </View>
      {open ? (
        <View style={styles.chart}>
          {chart.roots.length
            ? chart.roots.map((position) => renderNode(position, 0, new Set()))
            : <Text style={styles.empty}>No positions yet. Protected baseline identities remain available.</Text>}
          {chart.activePositionCount > MAX_VISIBLE_NODES ? (
            <Text style={styles.limit}>
              Showing the first {MAX_VISIBLE_NODES} positions. Use Workforce search to locate the rest.
            </Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}


const styles = StyleSheet.create({
  section: { borderTopWidth: 1, borderTopColor: '#182837', borderBottomWidth: 1, borderBottomColor: '#182837' },
  header: { minHeight: 62, flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8 },
  copy: { flex: 1, minWidth: 0 },
  eyebrow: { color: '#5fd3e5', fontSize: 8, fontWeight: '800', letterSpacing: 0.9 },
  title: { color: '#e3edf4', fontSize: 12, fontWeight: '800', marginTop: 3 },
  meta: { color: '#6f8498', fontSize: 9, marginTop: 3 },
  action: { paddingHorizontal: 11, paddingVertical: 7, borderRadius: 7, backgroundColor: '#132732' },
  actionText: { color: '#73d9e6', fontSize: 9, fontWeight: '800' },
  chart: { paddingVertical: 8 },
  node: { minHeight: 42, flexDirection: 'row', alignItems: 'center', gap: 8, borderBottomWidth: 1, borderBottomColor: '#142331' },
  connector: { width: 8, height: 1, backgroundColor: '#315063' },
  nodeCopy: { flex: 1, minWidth: 0 },
  nodeTitle: { color: '#dce8f1', fontSize: 10, fontWeight: '700' },
  nodeMeta: { color: '#70869a', fontSize: 8, marginTop: 2 },
  occupied: { color: '#6dcfa0', fontSize: 8, textTransform: 'uppercase' },
  openState: { color: '#d2a26d', fontSize: 8, fontWeight: '800' },
  empty: { color: '#71879a', fontSize: 9, paddingVertical: 8 },
  limit: { color: '#d2a26d', fontSize: 9, paddingTop: 9 },
});
