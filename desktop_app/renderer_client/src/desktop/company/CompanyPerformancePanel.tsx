import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  createCompanyMetric,
  recordCompanyFinancialEntry,
  recordCompanyMetricObservation,
  type CompanyDetail,
  type CompanyOperatingModel,
} from '@/lib/appApi';
import { userFacingError } from '../../../lib/diagnostics';


type Props = {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  company: CompanyDetail | null;
  operatingModel: CompanyOperatingModel | null;
  onChanged: () => Promise<void>;
};

type PerformanceTab = 'metrics' | 'financials';

function text(value: unknown, fallback = '') {
  const normalized = String(value ?? '').trim();
  return normalized || fallback;
}

function numberValue(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function money(value: number, currency: string) {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency}`;
  }
}

export function CompanyPerformancePanel({
  apiBaseUrl,
  token,
  companyId,
  company,
  operatingModel,
  onChanged,
}: Props) {
  const [tab, setTab] = useState<PerformanceTab>('metrics');
  const [form, setForm] = useState<'metric' | 'observation' | 'financial' | null>(null);
  const [selectedMetricId, setSelectedMetricId] = useState('');
  const [name, setName] = useState('');
  const [definition, setDefinition] = useState('');
  const [formula, setFormula] = useState('');
  const [unit, setUnit] = useState('');
  const [source, setSource] = useState('');
  const [cadence, setCadence] = useState('monthly');
  const [value, setValue] = useState('');
  const [confidence, setConfidence] = useState('unknown');
  const [period, setPeriod] = useState('');
  const [note, setNote] = useState('');
  const [entryType, setEntryType] = useState<'revenue' | 'cost'>('revenue');
  const [amount, setAmount] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [description, setDescription] = useState('');
  const [recognizedAt, setRecognizedAt] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const metrics = operatingModel?.metrics || company?.metrics || [];
  const financialEntries = operatingModel?.financial_entries || company?.financial_entries || [];
  const financialTotals = useMemo(() => {
    const totals = new Map<string, { revenue: number; cost: number }>();
    financialEntries.forEach((entry: any) => {
      const amountValue = numberValue(entry.amount);
      const entryCurrency = text(entry.currency).toUpperCase();
      if (amountValue === null || !entryCurrency) return;
      const current = totals.get(entryCurrency) || { revenue: 0, cost: 0 };
      if (entry.entry_type === 'revenue') current.revenue += amountValue;
      if (entry.entry_type === 'cost') current.cost += amountValue;
      totals.set(entryCurrency, current);
    });
    return [...totals.entries()];
  }, [financialEntries]);

  const resetForm = () => {
    setForm(null);
    setError(null);
    setName('');
    setDefinition('');
    setFormula('');
    setUnit('');
    setSource('');
    setCadence('monthly');
    setValue('');
    setConfidence('unknown');
    setPeriod('');
    setNote('');
    setAmount('');
    setDescription('');
    setRecognizedAt('');
  };

  const saveMetric = async () => {
    setSaving(true);
    setError(null);
    try {
      await createCompanyMetric(apiBaseUrl, token, companyId, {
        name: name.trim(),
        definition: definition.trim(),
        formula: formula.trim(),
        unit: unit.trim(),
        source: source.trim(),
        cadence: cadence.trim() || 'monthly',
      });
      resetForm();
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The metric could not be defined.'));
    } finally {
      setSaving(false);
    }
  };

  const saveObservation = async () => {
    setSaving(true);
    setError(null);
    try {
      const parsedValue = numberValue(value);
      await recordCompanyMetricObservation(apiBaseUrl, token, companyId, selectedMetricId, {
        value: parsedValue === null ? value.trim() : parsedValue,
        period_end: period.trim() || null,
        confidence: confidence.trim() || 'unknown',
        evidence: source.trim() ? [{ source: source.trim() }] : [],
        note: note.trim() || null,
      });
      resetForm();
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The metric observation could not be recorded.'));
    } finally {
      setSaving(false);
    }
  };

  const saveFinancialEntry = async () => {
    const parsedAmount = numberValue(amount);
    if (parsedAmount === null) {
      setError('Enter a valid non-negative amount.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await recordCompanyFinancialEntry(apiBaseUrl, token, companyId, {
        entry_type: entryType,
        amount: parsedAmount,
        currency: currency.trim().toUpperCase(),
        description: description.trim(),
        recognized_at: recognizedAt.trim(),
        source: source.trim(),
        evidence: [{ source: source.trim() }],
      });
      resetForm();
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The financial fact could not be recorded.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.content}>
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>EVIDENCE BEFORE SCORES</Text>
          <Text style={styles.title}>Performance</Text>
        </View>
        <View style={styles.tabs}>
          <Tab label="Metrics" selected={tab === 'metrics'} onPress={() => { setTab('metrics'); resetForm(); }} />
          <Tab label="Financial facts" selected={tab === 'financials'} onPress={() => { setTab('financials'); resetForm(); }} />
        </View>
      </View>
      <Text style={styles.guard}>
        Values appear only after a definition and source are recorded. Revenue, costs, and profit are never inferred from chats or activity.
      </Text>

      {tab === 'metrics' ? (
        <>
          <View style={styles.toolbar}>
            <Text style={styles.count}>{metrics.length} defined</Text>
            <Pressable accessibilityRole="button" style={styles.action} onPress={() => { setForm(form === 'metric' ? null : 'metric'); setError(null); }}>
              <Text style={styles.actionText}>{form === 'metric' ? 'Close' : 'Define metric'}</Text>
            </Pressable>
          </View>
          {form === 'metric' ? (
            <View style={styles.editor}>
              <TextInput accessibilityLabel="Metric name" style={styles.input} value={name} placeholder="Metric name" placeholderTextColor="#60768b" onChangeText={setName} />
              <View style={styles.split}>
                <TextInput accessibilityLabel="Metric unit" style={[styles.input, styles.flexInput]} value={unit} placeholder="Unit" placeholderTextColor="#60768b" onChangeText={setUnit} />
                <TextInput accessibilityLabel="Metric cadence" style={[styles.input, styles.flexInput]} value={cadence} placeholder="Cadence" placeholderTextColor="#60768b" onChangeText={setCadence} />
              </View>
              <TextInput accessibilityLabel="Metric definition" style={styles.input} value={definition} placeholder="What this measures" placeholderTextColor="#60768b" onChangeText={setDefinition} />
              <TextInput accessibilityLabel="Metric formula" style={styles.input} value={formula} placeholder="Exact formula" placeholderTextColor="#60768b" onChangeText={setFormula} />
              <TextInput accessibilityLabel="Metric source" style={styles.input} value={source} placeholder="Authoritative source" placeholderTextColor="#60768b" onChangeText={setSource} />
              {error ? <Text style={styles.error}>{error}</Text> : null}
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ disabled: saving || !name.trim() || !definition.trim() || !formula.trim() || !unit.trim() || !source.trim() }}
                disabled={saving || !name.trim() || !definition.trim() || !formula.trim() || !unit.trim() || !source.trim()}
                style={[styles.save, saving || !name.trim() || !definition.trim() || !formula.trim() || !unit.trim() || !source.trim() ? styles.disabled : null]}
                onPress={() => void saveMetric()}
              >
                <Text style={styles.saveText}>{saving ? 'Saving…' : 'Define metric'}</Text>
              </Pressable>
            </View>
          ) : null}
          {form === 'observation' ? (
            <View style={styles.editor}>
              <Text style={styles.editorTitle}>Record observation</Text>
              <View style={styles.split}>
                <TextInput accessibilityLabel="Metric value" style={[styles.input, styles.flexInput]} value={value} placeholder="Value" placeholderTextColor="#60768b" onChangeText={setValue} />
                <TextInput accessibilityLabel="Metric confidence" style={[styles.input, styles.flexInput]} value={confidence} placeholder="Confidence" placeholderTextColor="#60768b" onChangeText={setConfidence} />
                <TextInput accessibilityLabel="Metric period end" style={[styles.input, styles.flexInput]} value={period} placeholder="Period end · optional" placeholderTextColor="#60768b" onChangeText={setPeriod} />
              </View>
              <TextInput accessibilityLabel="Observation evidence" style={styles.input} value={source} placeholder="Evidence or source · optional" placeholderTextColor="#60768b" onChangeText={setSource} />
              <TextInput accessibilityLabel="Observation note" style={styles.input} value={note} placeholder="Note · optional" placeholderTextColor="#60768b" onChangeText={setNote} />
              {error ? <Text style={styles.error}>{error}</Text> : null}
              <View style={styles.editorActions}>
                <Pressable accessibilityRole="button" style={styles.secondary} onPress={resetForm}><Text style={styles.secondaryText}>Cancel</Text></Pressable>
                <Pressable accessibilityRole="button" accessibilityState={{ disabled: saving || !value.trim() }} disabled={saving || !value.trim()} style={[styles.save, saving || !value.trim() ? styles.disabled : null]} onPress={() => void saveObservation()}>
                  <Text style={styles.saveText}>{saving ? 'Saving…' : 'Record'}</Text>
                </Pressable>
              </View>
            </View>
          ) : null}
          {metrics.length ? (
            <View style={styles.list}>
              {metrics.map((metric: any) => {
                const observations = Array.isArray(metric.observations) ? metric.observations : [];
                const latest = observations[observations.length - 1];
                return (
                  <View key={text(metric.metric_id)} style={styles.row}>
                    <View style={styles.rowCopy}>
                      <Text style={styles.rowTitle}>{text(metric.name, 'Metric')}</Text>
                      <Text style={styles.rowMeta}>{text(metric.formula)} · source: {text(metric.source, 'not recorded')}</Text>
                      <Text style={styles.latest}>
                        {latest ? `${text(latest.value)} ${text(metric.unit)} · ${text(latest.confidence, 'unknown')} confidence` : 'No observations yet'}
                      </Text>
                    </View>
                    <Pressable
                      accessibilityRole="button"
                      style={styles.recordAction}
                      onPress={() => {
                        setSelectedMetricId(text(metric.metric_id));
                        setForm('observation');
                        setSource('');
                        setError(null);
                      }}
                    >
                      <Text style={styles.recordActionText}>Record</Text>
                    </Pressable>
                  </View>
                );
              })}
            </View>
          ) : <Text style={styles.empty}>No metrics have been defined.</Text>}
        </>
      ) : (
        <>
          <View style={styles.toolbar}>
            <Text style={styles.count}>{financialEntries.length} sourced entries</Text>
            <Pressable accessibilityRole="button" style={styles.action} onPress={() => { setForm(form === 'financial' ? null : 'financial'); setError(null); }}>
              <Text style={styles.actionText}>{form === 'financial' ? 'Close' : 'Add fact'}</Text>
            </Pressable>
          </View>
          {financialTotals.length ? (
            <View style={styles.totalStrip}>
              {financialTotals.map(([entryCurrency, totals]) => (
                <View key={entryCurrency} style={styles.total}>
                  <Text style={styles.totalCurrency}>{entryCurrency}</Text>
                  <Text style={styles.totalValue}>{money(totals.revenue - totals.cost, entryCurrency)}</Text>
                  <Text style={styles.totalMeta}>Revenue {money(totals.revenue, entryCurrency)} · Cost {money(totals.cost, entryCurrency)}</Text>
                </View>
              ))}
            </View>
          ) : null}
          {form === 'financial' ? (
            <View style={styles.editor}>
              <View style={styles.tabs}>
                <Tab label="Revenue" selected={entryType === 'revenue'} onPress={() => setEntryType('revenue')} />
                <Tab label="Cost" selected={entryType === 'cost'} onPress={() => setEntryType('cost')} />
              </View>
              <View style={styles.split}>
                <TextInput accessibilityLabel="Financial amount" style={[styles.input, styles.flexInput]} value={amount} placeholder="Amount" placeholderTextColor="#60768b" onChangeText={setAmount} />
                <TextInput accessibilityLabel="Financial currency" style={[styles.input, styles.currencyInput]} value={currency} placeholder="Currency" placeholderTextColor="#60768b" onChangeText={setCurrency} />
                <TextInput accessibilityLabel="Recognition date" style={[styles.input, styles.flexInput]} value={recognizedAt} placeholder="Recognition date" placeholderTextColor="#60768b" onChangeText={setRecognizedAt} />
              </View>
              <TextInput accessibilityLabel="Financial description" style={styles.input} value={description} placeholder="Description" placeholderTextColor="#60768b" onChangeText={setDescription} />
              <TextInput accessibilityLabel="Financial source" style={styles.input} value={source} placeholder="Invoice, ledger, or exact source" placeholderTextColor="#60768b" onChangeText={setSource} />
              {error ? <Text style={styles.error}>{error}</Text> : null}
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ disabled: saving || numberValue(amount) === null || !currency.trim() || !description.trim() || !recognizedAt.trim() || !source.trim() }}
                disabled={saving || numberValue(amount) === null || !currency.trim() || !description.trim() || !recognizedAt.trim() || !source.trim()}
                style={[styles.save, saving || numberValue(amount) === null || !currency.trim() || !description.trim() || !recognizedAt.trim() || !source.trim() ? styles.disabled : null]}
                onPress={() => void saveFinancialEntry()}
              >
                <Text style={styles.saveText}>{saving ? 'Saving…' : 'Record financial fact'}</Text>
              </Pressable>
            </View>
          ) : null}
          {financialEntries.length ? (
            <View style={styles.list}>
              {financialEntries.map((entry: any) => (
                <View key={text(entry.financial_entry_id)} style={styles.row}>
                  <View style={styles.rowCopy}>
                    <Text style={styles.rowTitle}>{text(entry.description, 'Financial entry')}</Text>
                    <Text style={styles.rowMeta}>{text(entry.recognized_at)} · source: {text(entry.source, 'not recorded')}</Text>
                  </View>
                  <View style={styles.moneyCopy}>
                    <Text style={[styles.moneyValue, entry.entry_type === 'cost' ? styles.cost : styles.revenue]}>
                      {entry.entry_type === 'cost' ? '−' : '+'}{money(numberValue(entry.amount) || 0, text(entry.currency, 'USD'))}
                    </Text>
                    <Text style={styles.moneyType}>{text(entry.entry_type).toUpperCase()}</Text>
                  </View>
                </View>
              ))}
            </View>
          ) : <Text style={styles.empty}>No revenue or cost facts have been recorded.</Text>}
        </>
      )}
    </View>
  );
}

function Tab({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="tab" accessibilityState={{ selected }} style={[styles.tab, selected ? styles.tabSelected : null]} onPress={onPress}>
      <Text style={[styles.tabText, selected ? styles.tabTextSelected : null]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 18, gap: 12 },
  header: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 },
  eyebrow: { color: '#5fd3e5', fontSize: 8, fontWeight: '900', letterSpacing: 1 },
  title: { color: '#edf5fb', fontSize: 17, fontWeight: '800', marginTop: 3 },
  guard: { color: '#7a90a3', fontSize: 10, lineHeight: 15, maxWidth: 760 },
  tabs: { flexDirection: 'row', gap: 3 },
  tab: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 7, backgroundColor: '#0e1b26' },
  tabSelected: { backgroundColor: '#17313b' },
  tabText: { color: '#74899c', fontSize: 9, fontWeight: '800' },
  tabTextSelected: { color: '#78ddea' },
  toolbar: { minHeight: 34, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  count: { color: '#758b9f', fontSize: 9 },
  action: { paddingHorizontal: 11, paddingVertical: 8, borderRadius: 7, backgroundColor: '#17313b' },
  actionText: { color: '#79ddea', fontSize: 9, fontWeight: '800' },
  editor: { padding: 12, borderRadius: 9, backgroundColor: '#0c1721', gap: 7 },
  editorTitle: { color: '#dce8f1', fontSize: 11, fontWeight: '800' },
  input: { minHeight: 37, borderRadius: 7, backgroundColor: '#101f2b', color: '#e2edf5', paddingHorizontal: 10, paddingVertical: 8, fontSize: 10, outlineStyle: 'none' } as any,
  split: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  flexInput: { flex: 1, minWidth: 150 },
  currencyInput: { width: 100 },
  save: { alignSelf: 'flex-end', paddingHorizontal: 12, paddingVertical: 9, borderRadius: 7, backgroundColor: '#70d7e5' },
  saveText: { color: '#061219', fontSize: 9, fontWeight: '900' },
  secondary: { paddingHorizontal: 11, paddingVertical: 9 },
  secondaryText: { color: '#8297aa', fontSize: 9, fontWeight: '800' },
  editorActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 4 },
  disabled: { opacity: 0.45 },
  error: { color: '#f0a0a6', fontSize: 9 },
  list: { borderTopWidth: 1, borderTopColor: '#1b2a39' },
  row: { minHeight: 66, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#172635', flexDirection: 'row', alignItems: 'center', gap: 12 },
  rowCopy: { flex: 1, minWidth: 0 },
  rowTitle: { color: '#e3edf5', fontSize: 11, fontWeight: '800' },
  rowMeta: { color: '#687f93', fontSize: 8, lineHeight: 12, marginTop: 3 },
  latest: { color: '#8da3b5', fontSize: 9, marginTop: 4 },
  recordAction: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 7, backgroundColor: '#10242e' },
  recordActionText: { color: '#6fd8e6', fontSize: 8, fontWeight: '900' },
  totalStrip: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  total: { minWidth: 210, flexGrow: 1, padding: 11, borderRadius: 8, backgroundColor: '#0d1923' },
  totalCurrency: { color: '#6fd6e4', fontSize: 8, fontWeight: '900' },
  totalValue: { color: '#e3edf5', fontSize: 16, fontWeight: '800', marginTop: 3 },
  totalMeta: { color: '#71879b', fontSize: 8, marginTop: 4 },
  moneyCopy: { alignItems: 'flex-end' },
  moneyValue: { fontSize: 11, fontWeight: '900' },
  revenue: { color: '#61d3a0' },
  cost: { color: '#f0a0a6' },
  moneyType: { color: '#657d91', fontSize: 7, fontWeight: '900', marginTop: 3 },
  empty: { color: '#708599', fontSize: 10, paddingVertical: 8 },
});
