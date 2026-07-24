import { FlatList, Pressable, Text, TextInput, View, type StyleProp, type ViewStyle } from 'react-native';

import type { ScheduledJob } from '@/lib/appApi';
import type { DesktopPressableState } from '@/lib/pressableState';
import { automationStyles as styles } from './DesktopAutomations.styles';
import {
  automationMatchesFilter,
  automationNeedsAttention,
  type AutomationEditorDraft,
  type AutomationListFilter,
} from './desktopAutomations';

type Suggestion = { label: string; description: string; schedule: string; draft: AutomationEditorDraft };

type Props = {
  jobs: ScheduledJob[];
  selectedJobId: string | null;
  query: string;
  filter: AutomationListFilter;
  suggestions?: Suggestion[];
  onQueryChange: (value: string) => void;
  onFilterChange: (value: AutomationListFilter) => void;
  onSelect: (job: ScheduledJob) => void;
  onCreate: () => void;
  onSelectSuggestion: (draft: AutomationEditorDraft) => void;
  style?: StyleProp<ViewStyle>;
};

const FILTERS: Array<{ key: AutomationListFilter; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'paused', label: 'Paused' },
];

function timingLine(job: ScheduledJob) {
  const schedule = job.schedule || 'No schedule';
  if (!job.next_run_at || !job.enabled) return `${schedule} · ${job.enabled ? 'Not scheduled' : 'Paused'}`;
  const next = new Date(job.next_run_at);
  if (Number.isNaN(next.getTime())) return schedule;
  return `${schedule} · Next ${new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' }).format(next)}`;
}

export function DesktopAutomationList({
  jobs,
  selectedJobId,
  query,
  filter,
  suggestions = [],
  onQueryChange,
  onFilterChange,
  onSelect,
  onCreate,
  onSelectSuggestion,
  style,
}: Props) {
  const visibleJobs = jobs.filter((job) => automationMatchesFilter(job, filter, query));

  return (
    <View style={[styles.listPane, style]}>
      <View style={styles.listHeader}>
        <View accessibilityRole="radiogroup" accessibilityLabel="Automation filter" style={styles.filterRow}>
          {FILTERS.map((item) => {
            const selected = filter === item.key;
            return (
              <Pressable
                key={item.key}
                accessibilityRole="radio"
                accessibilityState={{ checked: selected }}
                style={({ hovered, pressed }: DesktopPressableState) => [styles.filterButton, selected ? styles.filterButtonActive : null, hovered ? styles.buttonHover : null, pressed ? styles.buttonPressed : null]}
                onPress={() => onFilterChange(item.key)}
              >
                <Text style={[styles.filterText, selected ? styles.filterTextActive : null]}>{item.label}</Text>
              </Pressable>
            );
          })}
        </View>
        <View style={styles.listSearchRow}>
          <TextInput
            accessibilityLabel="Search automations"
            autoComplete="off"
            value={query}
            onChangeText={onQueryChange}
            placeholder="Search scheduled tasks"
            placeholderTextColor="#748194"
            style={styles.searchInput}
          />
          <Pressable accessibilityRole="button" accessibilityLabel="Create automation" style={({ hovered, pressed }: DesktopPressableState) => [styles.listNewButton, hovered ? styles.buttonHover : null, pressed ? styles.buttonPressed : null]} onPress={onCreate}>
            <Text style={styles.listNewButtonText}>＋</Text>
          </Pressable>
        </View>
      </View>

      <FlatList
        data={visibleJobs}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.listContent}
        initialNumToRender={14}
        maxToRenderPerBatch={18}
        windowSize={8}
        ListEmptyComponent={(
          <View style={styles.listEmptyCompact}>
            <Text style={styles.emptyTitle}>{jobs.length ? 'No matching automations' : 'No scheduled tasks yet'}</Text>
            <Text style={styles.emptyCopy}>{jobs.length ? 'Try another search or filter.' : 'Create one or start from a suggestion below.'}</Text>
          </View>
        )}
        ListFooterComponent={!query && suggestions.length ? (
          <View style={styles.suggestionSection}>
            <Text style={styles.suggestionHeading}>Suggestions</Text>
            {suggestions.map((suggestion, index) => (
              <Pressable
                key={suggestion.label}
                accessibilityRole="button"
                accessibilityLabel={`Create ${suggestion.label}`}
                style={({ hovered, pressed }: DesktopPressableState) => [styles.suggestionRow, hovered ? styles.jobRowHover : null, pressed ? styles.buttonPressed : null]}
                onPress={() => onSelectSuggestion(suggestion.draft)}
              >
                <View style={[styles.suggestionGlyph, index === 1 ? styles.suggestionGlyphViolet : index === 2 ? styles.suggestionGlyphGreen : null]}>
                  <Text style={styles.suggestionGlyphText}>{index === 0 ? '◌' : index === 1 ? '▣' : '⌕'}</Text>
                </View>
                <View style={styles.suggestionCopy}>
                  <View style={styles.suggestionTitleRow}>
                    <Text style={styles.suggestionTitle}>{suggestion.label}</Text>
                    <Text style={styles.suggestionSchedule}>{suggestion.schedule}</Text>
                  </View>
                  <Text numberOfLines={2} style={styles.suggestionDescription}>{suggestion.description}</Text>
                </View>
              </Pressable>
            ))}
          </View>
        ) : null}
        renderItem={({ item }) => {
          const selected = item.id === selectedJobId;
          const attention = automationNeedsAttention(item);
          return (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`${item.name}. ${item.enabled ? 'Active' : 'Paused'}. ${item.schedule || 'No schedule'}`}
              accessibilityState={{ selected }}
              style={({ hovered, pressed }: DesktopPressableState) => [styles.jobRowCompact, hovered ? styles.jobRowHover : null, selected ? styles.jobRowSelected : null, pressed ? styles.buttonPressed : null]}
              onPress={() => onSelect(item)}
            >
              <View style={[styles.jobRadio, selected ? styles.jobRadioSelected : null, attention ? styles.jobRadioAttention : null]} />
              <View style={styles.jobCompactCopy}>
                <View style={styles.jobTopRow}>
                  <Text numberOfLines={1} style={styles.jobName}>{item.name}</Text>
                  {!item.enabled ? <Text style={styles.jobStateText}>Paused</Text> : attention ? <Text style={styles.jobAttentionText}>Review</Text> : null}
                </View>
                <Text numberOfLines={1} style={styles.jobTiming}>{timingLine(item)}</Text>
              </View>
            </Pressable>
          );
        }}
      />
    </View>
  );
}
