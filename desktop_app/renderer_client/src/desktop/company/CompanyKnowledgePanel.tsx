import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  publishCompanyKnowledge,
  reviewCompanyKnowledge,
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

export function CompanyKnowledgePanel({
  apiBaseUrl,
  token,
  companyId,
  company,
  operatingModel,
  onChanged,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [source, setSource] = useState('');
  const [reviewDueAt, setReviewDueAt] = useState('');
  const [saving, setSaving] = useState(false);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const knowledge = operatingModel?.knowledge || company?.knowledge || [];

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      await publishCompanyKnowledge(apiBaseUrl, token, companyId, {
        title: title.trim(),
        content: content.trim(),
        provenance: {
          source: source.trim(),
          published_by: 'local_operator_or_manager',
        },
        sensitivity: 'company',
        review_due_at: reviewDueAt.trim() || null,
      });
      setTitle('');
      setContent('');
      setSource('');
      setReviewDueAt('');
      setEditing(false);
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The Company knowledge item could not be published.'));
    } finally {
      setSaving(false);
    }
  };

  const markReviewed = async (knowledgeId: string) => {
    setReviewingId(knowledgeId);
    setError(null);
    try {
      await reviewCompanyKnowledge(apiBaseUrl, token, companyId, knowledgeId, null);
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The knowledge review could not be saved.'));
    } finally {
      setReviewingId(null);
    }
  };

  return (
    <View style={styles.content}>
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>APPROVED COMPANY MEMORY</Text>
          <Text style={styles.title}>Knowledge</Text>
        </View>
        <Pressable accessibilityRole="button" style={styles.action} onPress={() => setEditing((current) => !current)}>
          <Text style={styles.actionText}>{editing ? 'Close' : 'Publish'}</Text>
        </Pressable>
      </View>
      <Text style={styles.guard}>
        Only deliberately published handbook and policy material belongs here. Chats, private memory, credentials, and full child transcripts are never copied automatically.
      </Text>

      {editing ? (
        <View style={styles.editor}>
          <TextInput
            accessibilityLabel="Knowledge title"
            style={styles.input}
            value={title}
            placeholder="Knowledge title"
            placeholderTextColor="#60768b"
            onChangeText={setTitle}
          />
          <TextInput
            accessibilityLabel="Knowledge content"
            multiline
            style={[styles.input, styles.contentInput]}
            value={content}
            placeholder="Approved material"
            placeholderTextColor="#60768b"
            onChangeText={setContent}
          />
          <View style={styles.split}>
            <TextInput
              accessibilityLabel="Knowledge source"
              style={[styles.input, styles.flexInput]}
              value={source}
              placeholder="Exact source or operator decision"
              placeholderTextColor="#60768b"
              onChangeText={setSource}
            />
            <TextInput
              accessibilityLabel="Knowledge review due date"
              style={[styles.input, styles.dateInput]}
              value={reviewDueAt}
              placeholder="Review due · optional"
              placeholderTextColor="#60768b"
              onChangeText={setReviewDueAt}
            />
          </View>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <View style={styles.footer}>
            <Text style={styles.hint}>A source is required. Unknown or stale material should not be published as fact.</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: saving || !title.trim() || !content.trim() || !source.trim() }}
              disabled={saving || !title.trim() || !content.trim() || !source.trim()}
              style={[styles.save, saving || !title.trim() || !content.trim() || !source.trim() ? styles.disabled : null]}
              onPress={() => void submit()}
            >
              <Text style={styles.saveText}>{saving ? 'Publishing…' : 'Publish item'}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {knowledge.length ? (
        <View style={styles.list}>
          {knowledge.map((item: any) => (
            <View key={String(item.knowledge_id || item.id)} style={styles.row}>
              <View style={styles.rowCopy}>
                <Text style={styles.rowTitle}>{String(item.title || 'Knowledge item')}</Text>
                <Text style={styles.rowContent} numberOfLines={3}>{String(item.content || '')}</Text>
                <Text style={styles.rowMeta}>
                  Source: {String(item.provenance?.source || item.provenance || 'Unspecified')}
                  {item.review_due_at ? ` · review ${String(item.review_due_at)}` : ''}
                </Text>
              </View>
              <View style={styles.rowActions}>
                {Number.isFinite(Date.parse(String(item.review_due_at || '')))
                && Date.parse(String(item.review_due_at)) < Date.now() ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityState={{ disabled: Boolean(reviewingId) }}
                    disabled={Boolean(reviewingId)}
                    style={styles.reviewAction}
                    onPress={() => void markReviewed(String(item.knowledge_id || item.id))}
                  >
                    <Text style={styles.reviewActionText}>{reviewingId === String(item.knowledge_id || item.id) ? 'Saving…' : 'Mark reviewed'}</Text>
                  </Pressable>
                ) : null}
                <Text style={styles.status}>{String(item.status || 'active')}</Text>
              </View>
            </View>
          ))}
        </View>
      ) : (
        <Text style={styles.empty}>No Company knowledge has been explicitly published.</Text>
      )}
    </View>
  );
}


const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 18, gap: 12 },
  header: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12 },
  eyebrow: { color: '#5fd3e5', fontSize: 8, fontWeight: '900', letterSpacing: 1 },
  title: { color: '#edf5fb', fontSize: 17, fontWeight: '800', marginTop: 3 },
  action: { paddingHorizontal: 11, paddingVertical: 8, borderRadius: 7, backgroundColor: '#17313b' },
  actionText: { color: '#79ddea', fontSize: 9, fontWeight: '800' },
  guard: { color: '#7a90a3', fontSize: 10, lineHeight: 15, maxWidth: 760 },
  editor: { padding: 12, borderRadius: 9, backgroundColor: '#0c1721', gap: 7 },
  input: { minHeight: 37, borderRadius: 7, backgroundColor: '#101f2b', color: '#e2edf5', paddingHorizontal: 10, paddingVertical: 8, fontSize: 10, outlineStyle: 'none' } as any,
  contentInput: { minHeight: 94, textAlignVertical: 'top' },
  split: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  flexInput: { flex: 1, minWidth: 260 },
  dateInput: { width: 190 },
  footer: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  hint: { flex: 1, color: '#6e8396', fontSize: 9, lineHeight: 13 },
  save: { paddingHorizontal: 12, paddingVertical: 9, borderRadius: 7, backgroundColor: '#70d7e5' },
  saveText: { color: '#061219', fontSize: 9, fontWeight: '900' },
  disabled: { opacity: 0.45 },
  error: { color: '#f0a0a6', fontSize: 9 },
  list: { borderTopWidth: 1, borderTopColor: '#1b2a39' },
  row: { paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: '#172635', flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  rowCopy: { flex: 1, minWidth: 0 },
  rowTitle: { color: '#e3edf5', fontSize: 11, fontWeight: '800' },
  rowContent: { color: '#879cad', fontSize: 10, lineHeight: 15, marginTop: 4 },
  rowMeta: { color: '#667e92', fontSize: 8, marginTop: 5 },
  status: { color: '#61d3a0', fontSize: 8, fontWeight: '900', textTransform: 'uppercase' },
  rowActions: { alignItems: 'flex-end', gap: 5 },
  reviewAction: { paddingHorizontal: 8, paddingVertical: 6, borderRadius: 6, backgroundColor: '#17313b' },
  reviewActionText: { color: '#79ddea', fontSize: 8, fontWeight: '800' },
  empty: { color: '#708599', fontSize: 10, paddingVertical: 8 },
});
