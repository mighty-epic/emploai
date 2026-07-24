import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  createCompanyDepartment,
  createCompanyPosition,
  fetchCompanyEligibleIdentities,
  fetchCompanyJobCatalog,
  type CompanyDetail,
  type CompanyJobCatalog,
  type CompanyJobTemplate,
  type CompanyOperatingModel,
} from '@/lib/appApi';
import type { DesktopFleetIdentity } from '@/lib/desktopBridge';
import type { LocalConfirm } from '@/lib/sharedConfirmations';
import { userFacingError } from '../../../lib/diagnostics';
import { CompanyReadinessReview } from './CompanyReadinessReview';
import { CompanyJobContractEditor } from './CompanyJobContractEditor';
import { CompanyOrgChart } from './CompanyOrgChart';
import { CompanyPositionOccupantEditor } from './CompanyPositionOccupantEditor';


type Props = {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  company: CompanyDetail | null;
  operatingModel: CompanyOperatingModel | null;
  identities: DesktopFleetIdentity[];
  confirmAction: LocalConfirm;
  onChanged: () => Promise<void>;
};

export function CompanyWorkforcePanel({
  apiBaseUrl,
  token,
  companyId,
  company,
  operatingModel,
  identities,
  confirmAction,
  onChanged,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [departmentEditorOpen, setDepartmentEditorOpen] = useState(false);
  const [departmentName, setDepartmentName] = useState('');
  const [departmentMandate, setDepartmentMandate] = useState('');
  const [selectedDepartmentId, setSelectedDepartmentId] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<CompanyJobCatalog | null>(null);
  const [eligibleIdentities, setEligibleIdentities] = useState<DesktopFleetIdentity[]>([]);
  const [query, setQuery] = useState('');
  const [employeeQuery, setEmployeeQuery] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState<CompanyJobTemplate | null>(null);
  const [selectedIdentityId, setSelectedIdentityId] = useState<string | null>(null);
  const [selectedManagerId, setSelectedManagerId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [loadingCatalog, setLoadingCatalog] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reviewingContractId, setReviewingContractId] = useState<string | null>(null);
  const [editingContractId, setEditingContractId] = useState<string | null>(null);
  const [changingPositionId, setChangingPositionId] = useState<string | null>(null);
  const [visibleEmployeeLimit, setVisibleEmployeeLimit] = useState(50);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing || catalog || loadingCatalog) return;
    setLoadingCatalog(true);
    setError(null);
    void fetchCompanyJobCatalog(apiBaseUrl, token)
      .then(setCatalog)
      .catch((reason) => setError(userFacingError(reason, 'The local job catalog could not be opened.')))
      .finally(() => setLoadingCatalog(false));
  }, [apiBaseUrl, catalog, editing, loadingCatalog, token]);

  useEffect(() => {
    if (!editing || !companyId) return;
    void fetchCompanyEligibleIdentities(apiBaseUrl, token, companyId)
      .then((payload) => setEligibleIdentities(payload.items as DesktopFleetIdentity[]))
      .catch((reason) => setError(userFacingError(reason, 'Eligible local identities could not be loaded.')));
  }, [apiBaseUrl, companyId, editing, token]);

  const employees = company?.employees || [];
  const departments = operatingModel?.departments || company?.departments || [];
  const positions = operatingModel?.positions || company?.positions || [];
  const contracts = operatingModel?.job_contracts || company?.job_contracts || [];
  const employeeByIdentity = new Map(employees.map((item) => [item.identity_id, item]));
  const managerIdentities = employees.filter((item) => item.system_role === 'manager');
  const defaultManagerId = managerIdentities[0]?.identity_id || null;
  const changingPosition = positions.find(
    (item) => item.position_id === changingPositionId,
  ) || null;

  const filteredJobs = useMemo(() => {
    const cleanQuery = query.trim().toLowerCase();
    const items = catalog?.items || [];
    if (!cleanQuery) return items.slice(0, 10);
    return items.filter((item) => (
      item.title.toLowerCase().includes(cleanQuery)
      || item.division_label.toLowerCase().includes(cleanQuery)
      || item.purpose.toLowerCase().includes(cleanQuery)
      || item.responsibilities.some((value) => value.toLowerCase().includes(cleanQuery))
    )).slice(0, 20);
  }, [catalog?.items, query]);
  const visibleEmployees = useMemo(() => {
    const cleanQuery = employeeQuery.trim().toLowerCase();
    if (!cleanQuery) return employees;
    return employees.filter((employee) => {
      const position = positions.find(
        (item) => item.position_id === employee.position_id,
      );
      const department = departments.find(
        (item: any) => String(item.department_id) === String(position?.department_id || ''),
      ) as any;
      return [
        employee.display_name,
        employee.company_role,
        position?.title,
        department?.name,
      ].some((value) => String(value || '').toLowerCase().includes(cleanQuery));
    });
  }, [departments, employeeQuery, employees, positions]);
  const pagedEmployees = visibleEmployees.slice(0, visibleEmployeeLimit);

  useEffect(() => {
    setVisibleEmployeeLimit(50);
  }, [companyId, employeeQuery]);

  const chooseTemplate = (template: CompanyJobTemplate) => {
    setSelectedTemplate(template);
    setTitle(template.title);
  };

  const submit = async () => {
    if (!companyId || !title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createCompanyPosition(apiBaseUrl, token, companyId, {
        title: title.trim(),
        template_id: selectedTemplate?.template_id || null,
        manager_identity_id: selectedManagerId || defaultManagerId,
        identity_id: selectedIdentityId,
        department_id: selectedDepartmentId,
        overlay: {},
      });
      setEditing(false);
      setQuery('');
      setSelectedTemplate(null);
      setSelectedIdentityId(null);
      setSelectedManagerId(null);
      setSelectedDepartmentId(null);
      setTitle('');
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The position could not be created.'));
    } finally {
      setSaving(false);
    }
  };

  const submitDepartment = async () => {
    if (!departmentName.trim() || !departmentMandate.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createCompanyDepartment(apiBaseUrl, token, companyId, {
        name: departmentName.trim(),
        mandate: departmentMandate.trim(),
        manager_identity_id: defaultManagerId,
      });
      setSelectedDepartmentId(String(created.department_id || '') || null);
      setDepartmentName('');
      setDepartmentMandate('');
      setDepartmentEditorOpen(false);
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The department could not be created.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.content}>
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>PEOPLE AND RESPONSIBILITY</Text>
          <Text style={styles.title}>Workforce</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          style={({ hovered, pressed }: any) => [
            styles.primaryAction,
            hovered ? styles.primaryActionHovered : null,
            pressed ? styles.pressed : null,
          ]}
          onPress={() => {
            setEditing((value) => !value);
            setError(null);
          }}
        >
          <Text style={styles.primaryActionText}>{editing ? 'Close' : 'Add role'}</Text>
        </Pressable>
      </View>

      <View style={styles.departmentBar}>
        <View style={styles.rowCopy}>
          <Text style={styles.fieldLabel}>OPTIONAL DEPARTMENTS · {departments.length}</Text>
          <Text style={styles.rowMeta}>Flat responsibility groups only; computers and manager routes do not change.</Text>
        </View>
        <Pressable accessibilityRole="button" style={styles.reviewAction} onPress={() => setDepartmentEditorOpen((value) => !value)}>
          <Text style={styles.reviewActionText}>{departmentEditorOpen ? 'Close' : 'Add department'}</Text>
        </Pressable>
      </View>
      {departmentEditorOpen ? (
        <View style={styles.departmentEditor}>
          <TextInput
            accessibilityLabel="Department name"
            style={[styles.input, styles.departmentName]}
            value={departmentName}
            placeholder="Department name"
            placeholderTextColor="#60768b"
            onChangeText={setDepartmentName}
          />
          <TextInput
            accessibilityLabel="Department mandate"
            style={[styles.input, styles.departmentMandate]}
            value={departmentMandate}
            placeholder="What this department owns"
            placeholderTextColor="#60768b"
            onChangeText={setDepartmentMandate}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: saving || !departmentName.trim() || !departmentMandate.trim() }}
            disabled={saving || !departmentName.trim() || !departmentMandate.trim()}
            style={[styles.saveAction, saving || !departmentName.trim() || !departmentMandate.trim() ? styles.disabled : null]}
            onPress={() => void submitDepartment()}
          >
            <Text style={styles.saveActionText}>{saving ? 'Saving…' : 'Create'}</Text>
          </Pressable>
        </View>
      ) : null}

      {editing ? (
        <View style={styles.editor}>
          <View style={styles.editorIntro}>
            <View style={styles.editorIntroCopy}>
              <Text style={styles.editorTitle}>Define the job, then assign an identity</Text>
              <Text style={styles.editorBody}>
                The Agency Agents catalog is a starting template. It does not enable tools, grant authority, or make an employee ready automatically.
              </Text>
            </View>
            <Text style={styles.experimental}>EXPERIMENTAL CATALOG</Text>
          </View>

          <Text style={styles.fieldLabel}>Job catalog</Text>
          <TextInput
            accessibilityLabel="Search job catalog"
            style={styles.input}
            value={query}
            placeholder="Search 245 jobs by title, division, or responsibility"
            placeholderTextColor="#60768b"
            onChangeText={setQuery}
          />
          <View style={styles.catalog}>
            {loadingCatalog ? <Text style={styles.muted}>Opening the bundled local catalog…</Text> : null}
            {!loadingCatalog && catalog ? (
              <>
                <Text style={styles.catalogMeta}>
                  {catalog.template_count} jobs · {catalog.divisions.length} divisions · {catalog.source.license || 'MIT'} · no cloud lookup
                </Text>
                {filteredJobs.map((item) => {
                  const selected = selectedTemplate?.template_id === item.template_id;
                  return (
                    <Pressable
                      key={item.template_id}
                      accessibilityRole="button"
                      accessibilityState={{ selected }}
                      style={({ hovered }: any) => [
                        styles.catalogRow,
                        hovered ? styles.catalogRowHovered : null,
                        selected ? styles.catalogRowSelected : null,
                      ]}
                      onPress={() => chooseTemplate(item)}
                    >
                      <View style={styles.rowCopy}>
                        <Text style={styles.rowTitle}>{item.title}</Text>
                        <Text style={styles.rowMeta}>{item.division_label} · {item.purpose || 'Job template'}</Text>
                      </View>
                      <Text style={styles.rowBadge}>{item.review_status}</Text>
                    </Pressable>
                  );
                })}
                {!filteredJobs.length ? <Text style={styles.muted}>No job matches that search.</Text> : null}
              </>
            ) : null}
          </View>

          <Text style={styles.fieldLabel}>Position title</Text>
          <TextInput
            accessibilityLabel="Position title"
            style={styles.input}
            value={title}
            placeholder="Choose a template or enter a custom title"
            placeholderTextColor="#60768b"
            onChangeText={setTitle}
          />

          <Text style={styles.fieldLabel}>Identity</Text>
          <View style={styles.choiceWrap}>
            <Choice
              label="Leave position open"
              meta="Assign later"
              selected={!selectedIdentityId}
              onPress={() => setSelectedIdentityId(null)}
            />
            {(eligibleIdentities.length ? eligibleIdentities : identities).map((identity) => {
              const employee = employeeByIdentity.get(identity.identity_id);
              const computerName = String(identity.metadata?.computer_name || '').trim();
              return (
                <Choice
                  key={identity.identity_id}
                  label={identity.display_name}
                  meta={employee
                    ? `${employee.company_role} · ${computerName || 'this computer'}`
                    : `${identity.role} · onboard to company`}
                  selected={selectedIdentityId === identity.identity_id}
                  onPress={() => setSelectedIdentityId(identity.identity_id)}
                />
              );
            })}
          </View>

          {managerIdentities.length > 1 ? (
            <>
              <Text style={styles.fieldLabel}>Reports to</Text>
              <View style={styles.choiceWrap}>
                {managerIdentities.map((manager) => (
                  <Choice
                    key={manager.identity_id}
                    label={manager.display_name}
                    meta={manager.company_role || 'Company manager'}
                    selected={(selectedManagerId || defaultManagerId) === manager.identity_id}
                    onPress={() => setSelectedManagerId(manager.identity_id)}
                  />
                ))}
              </View>
            </>
          ) : null}

          {departments.length ? (
            <>
              <Text style={styles.fieldLabel}>Department · optional</Text>
              <View style={styles.choiceWrap}>
                <Choice
                  label="No department"
                  meta="Keep this position independent"
                  selected={!selectedDepartmentId}
                  onPress={() => setSelectedDepartmentId(null)}
                />
                {departments.map((department: any) => (
                  <Choice
                    key={String(department.department_id)}
                    label={String(department.name || 'Department')}
                    meta={String(department.mandate || 'Responsibility group')}
                    selected={selectedDepartmentId === String(department.department_id)}
                    onPress={() => setSelectedDepartmentId(String(department.department_id))}
                  />
                ))}
              </View>
            </>
          ) : null}

          {error ? <Text style={styles.error}>{error}</Text> : null}
          <View style={styles.editorFooter}>
            <Text style={styles.editorHint}>No department is created by default. The employee remains owned by this computer.</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: saving || !title.trim() }}
              disabled={saving || !title.trim()}
              style={[styles.saveAction, saving || !title.trim() ? styles.disabled : null]}
              onPress={() => void submit()}
            >
              <Text style={styles.saveActionText}>{saving ? 'Saving…' : selectedIdentityId ? 'Onboard and create role' : 'Create open role'}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {error && !editing ? <Text style={styles.error}>{error}</Text> : null}

      <CompanyOrgChart
        employees={employees}
        positions={positions}
        departments={departments}
      />

      {employees.length > 8 ? (
        <TextInput
          accessibilityLabel="Search Company workforce"
          style={styles.input}
          value={employeeQuery}
          placeholder="Search employees, jobs, or departments"
          placeholderTextColor="#60768b"
          onChangeText={setEmployeeQuery}
        />
      ) : null}
      <View style={styles.list}>
        {pagedEmployees.map((employee) => {
          const position = positions.find((item) => item.position_id === employee.position_id);
          const contract = contracts.find((item) => item.job_contract_id === employee.job_contract_id);
          return (
            <View key={employee.employee_id}>
              <View style={styles.employeeRow}>
                <View style={styles.avatar}>
                  <Text style={styles.avatarText}>{employee.display_name.slice(0, 1).toUpperCase()}</Text>
                </View>
                <View style={styles.rowCopy}>
                  <Text style={styles.rowTitle}>{employee.display_name}</Text>
                  <Text style={styles.rowMeta}>
                    {position?.title || employee.company_role}
                    {position?.department_id
                      ? ` · ${String((departments.find((item: any) => String(item.department_id) === position.department_id) as any)?.name || 'Department')}`
                      : ''}
                    {' · '}
                    {employee.system_role}
                    {employee.protected ? ' · protected' : ''}
                  </Text>
                </View>
                <View style={styles.rowActions}>
                  <Text style={contract?.status === 'ready' ? styles.ready : styles.incomplete}>
                    {(contract?.status || employee.job_contract_status).replace(/_/g, ' ')}
                  </Text>
                  {contract ? (
                    <>
                      <Pressable
                        accessibilityRole="button"
                        style={styles.reviewAction}
                        onPress={() => {
                          setEditingContractId((current) => (
                            current === contract.job_contract_id ? null : contract.job_contract_id
                          ));
                          setReviewingContractId(null);
                        }}
                      >
                        <Text style={styles.reviewActionText}>
                          {editingContractId === contract.job_contract_id ? 'Close' : 'Edit job'}
                        </Text>
                      </Pressable>
                      <Pressable
                        accessibilityRole="button"
                        style={styles.reviewAction}
                        onPress={() => {
                          setReviewingContractId((current) => (
                            current === contract.job_contract_id ? null : contract.job_contract_id
                          ));
                          setEditingContractId(null);
                        }}
                      >
                        <Text style={styles.reviewActionText}>
                          {reviewingContractId === contract.job_contract_id ? 'Close' : 'Readiness'}
                        </Text>
                      </Pressable>
                    </>
                  ) : null}
                  {position ? (
                    <Pressable
                      accessibilityRole="button"
                      style={styles.reviewAction}
                      onPress={() => {
                        setChangingPositionId((current) => (
                          current === position.position_id ? null : position.position_id
                        ));
                        setEditingContractId(null);
                        setReviewingContractId(null);
                      }}
                    >
                      <Text style={styles.reviewActionText}>
                        {changingPositionId === position.position_id ? 'Close' : 'Occupant'}
                      </Text>
                    </Pressable>
                  ) : null}
                </View>
              </View>
              {contract && editingContractId === contract.job_contract_id ? (
                <CompanyJobContractEditor
                  apiBaseUrl={apiBaseUrl}
                  token={token}
                  companyId={companyId}
                  contract={contract}
                  employeeName={employee.display_name}
                  onClose={() => setEditingContractId(null)}
                  onSaved={onChanged}
                />
              ) : null}
              {contract && reviewingContractId === contract.job_contract_id ? (
                <CompanyReadinessReview
                  apiBaseUrl={apiBaseUrl}
                  token={token}
                  companyId={companyId}
                  contract={contract}
                  employeeName={employee.display_name}
                  reviewerIdentityId={defaultManagerId}
                  onClose={() => setReviewingContractId(null)}
                  onSaved={onChanged}
                />
              ) : null}
            </View>
          );
        })}
        {employees.length && !visibleEmployees.length ? (
          <Text style={styles.muted}>No employee matches that search.</Text>
        ) : null}
        {visibleEmployees.length > pagedEmployees.length ? (
          <Pressable
            accessibilityRole="button"
            style={styles.moreAction}
            onPress={() => setVisibleEmployeeLimit((current) => current + 50)}
          >
            <Text style={styles.moreActionText}>
              Show {Math.min(50, visibleEmployees.length - pagedEmployees.length)} more employees
            </Text>
          </Pressable>
        ) : null}
      </View>

      {changingPosition ? (
        <CompanyPositionOccupantEditor
          apiBaseUrl={apiBaseUrl}
          token={token}
          companyId={companyId}
          position={changingPosition}
          currentEmployee={employees.find(
            (item) => item.identity_id === changingPosition.occupant_identity_id,
          ) || null}
          employees={employees}
          positions={positions}
          confirmAction={confirmAction}
          onClose={() => setChangingPositionId(null)}
          onChanged={onChanged}
        />
      ) : null}

      {positions.filter((item) => !item.occupant_identity_id).length ? (
        <View style={styles.openPositions}>
          <Text style={styles.fieldLabel}>OPEN POSITIONS</Text>
          {positions.filter((item) => !item.occupant_identity_id).map((position) => (
            <View key={position.position_id} style={styles.compactRow}>
              <Text style={styles.rowTitle}>{position.title}</Text>
              <Text style={styles.rowBadge}>unassigned</Text>
              <Pressable
                accessibilityRole="button"
                style={styles.reviewAction}
                onPress={() => setChangingPositionId(position.position_id)}
              >
                <Text style={styles.reviewActionText}>Assign</Text>
              </Pressable>
            </View>
          ))}
        </View>
      ) : null}

      {!company?.departments.length ? (
        <Text style={styles.footnote}>No departments. Add one later only when shared policy or queue ownership makes it useful.</Text>
      ) : null}
    </View>
  );
}

function Choice({
  label,
  meta,
  selected,
  onPress,
}: {
  label: string;
  meta: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      style={[styles.choice, selected ? styles.choiceSelected : null]}
      onPress={onPress}
    >
      <View style={[styles.radio, selected ? styles.radioSelected : null]} />
      <View style={styles.rowCopy}>
        <Text style={styles.rowTitle}>{label}</Text>
        <Text style={styles.rowMeta}>{meta}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 18, gap: 14 },
  header: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12 },
  eyebrow: { color: '#5fd3e5', fontSize: 8, fontWeight: '800', letterSpacing: 1.05 },
  title: { color: '#edf5fb', fontSize: 17, fontWeight: '800', marginTop: 3 },
  primaryAction: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 7, backgroundColor: '#17313b' },
  primaryActionHovered: { backgroundColor: '#21414b' },
  primaryActionText: { color: '#79ddea', fontSize: 10, fontWeight: '800' },
  pressed: { opacity: 0.76 },
  editor: { borderRadius: 10, backgroundColor: '#0c1721', padding: 14, gap: 9 },
  departmentBar: { minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: 12, borderTopWidth: 1, borderBottomWidth: 1, borderColor: '#172635', paddingVertical: 8 },
  departmentEditor: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 7, padding: 10, borderRadius: 8, backgroundColor: '#0c1721' },
  departmentName: { width: 190 },
  departmentMandate: { flex: 1, minWidth: 260 },
  editorIntro: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  editorIntroCopy: { flex: 1 },
  editorTitle: { color: '#e7f0f7', fontSize: 13, fontWeight: '800' },
  editorBody: { color: '#7d93a6', fontSize: 10, lineHeight: 15, marginTop: 4, maxWidth: 700 },
  experimental: { color: '#dda85b', fontSize: 8, fontWeight: '900', letterSpacing: 0.65 },
  fieldLabel: { color: '#758ca0', fontSize: 8, fontWeight: '800', letterSpacing: 0.7, marginTop: 3 },
  input: {
    minHeight: 38,
    borderRadius: 7,
    backgroundColor: '#101f2b',
    color: '#e2edf5',
    paddingHorizontal: 11,
    paddingVertical: 8,
    fontSize: 11,
    outlineStyle: 'none',
  } as any,
  catalog: { maxHeight: 300, overflow: 'scroll', gap: 2 },
  catalogMeta: { color: '#667d91', fontSize: 9, paddingVertical: 4 },
  catalogRow: { minHeight: 48, paddingHorizontal: 9, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 10, borderRadius: 7 },
  catalogRowHovered: { backgroundColor: '#101f2b' },
  catalogRowSelected: { backgroundColor: '#17313b' },
  rowCopy: { flex: 1, minWidth: 0 },
  rowTitle: { color: '#e1ebf3', fontSize: 11, fontWeight: '700' },
  rowMeta: { color: '#70869a', fontSize: 9, lineHeight: 13, marginTop: 2 },
  rowBadge: { color: '#7590a5', fontSize: 8, fontWeight: '800', textTransform: 'uppercase' },
  choiceWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  choice: { minWidth: 190, maxWidth: 290, flexGrow: 1, padding: 9, flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: 7, backgroundColor: '#101e29' },
  choiceSelected: { backgroundColor: '#18343e' },
  radio: { width: 8, height: 8, borderRadius: 999, borderWidth: 1, borderColor: '#5d788d' },
  radioSelected: { borderColor: '#70dce9', backgroundColor: '#70dce9' },
  editorFooter: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 5 },
  editorHint: { flex: 1, color: '#687f93', fontSize: 9, lineHeight: 13 },
  saveAction: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: 7, backgroundColor: '#70d7e5' },
  saveActionText: { color: '#061219', fontSize: 10, fontWeight: '900' },
  disabled: { opacity: 0.45 },
  error: { color: '#f0a0a6', fontSize: 10, lineHeight: 14 },
  muted: { color: '#6d8396', fontSize: 10, paddingVertical: 9 },
  list: { borderTopWidth: 1, borderTopColor: '#1b2a39' },
  moreAction: { alignSelf: 'flex-start', marginTop: 8, paddingHorizontal: 11, paddingVertical: 7, borderRadius: 7, backgroundColor: '#132732' },
  moreActionText: { color: '#73d9e6', fontSize: 9, fontWeight: '800' },
  employeeRow: { minHeight: 62, paddingVertical: 9, paddingHorizontal: 2, borderBottomWidth: 1, borderBottomColor: '#172635', flexDirection: 'row', alignItems: 'center', gap: 11 },
  avatar: { width: 34, height: 34, borderRadius: 9, backgroundColor: '#17313c', alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: '#77dce8', fontSize: 13, fontWeight: '900' },
  ready: { color: '#61d3a0', fontSize: 8, fontWeight: '900', textTransform: 'uppercase' },
  incomplete: { color: '#dda85b', fontSize: 8, fontWeight: '900', textTransform: 'uppercase' },
  rowActions: { alignItems: 'flex-end', gap: 5 },
  reviewAction: { paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6, backgroundColor: '#132a35' },
  reviewActionText: { color: '#70d7e5', fontSize: 8, fontWeight: '800' },
  openPositions: { gap: 3 },
  compactRow: { minHeight: 38, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: '#172635' },
  footnote: { color: '#708599', fontSize: 10, lineHeight: 15 },
});
