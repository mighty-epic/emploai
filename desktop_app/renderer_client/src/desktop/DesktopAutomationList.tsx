import { FlatList, Pressable, Text, TextInput, View, type StyleProp, type ViewStyle } from 'react-native';

import type { ScheduledJob } from '@/lib/appApi';
import type { DesktopPressableState } from '@/lib/pressableState';
import { automationStyles as styles } from './DesktopAutomations.styles';
import {
  automationMatchesFilter,
  automationNeedsAttention,
  type AutomationListFilter,
} from './desktopAutomations';

type Props = {
  jobs: ScheduledJob[];
  selectedJobId: string | null;
  query: string;
  filter: AutomationListFilter;
  onQueryChange: (value: string) => void;
  onFilterChange: (value: AutomationListFilter) => void;
  onSelect: (job: ScheduledJob) => void;
  style?: StyleProp<ViewStyle>;
};

const FILTERS: Array<{ key: AutomationListFilter; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'paused', label: 'Paused' },
  { key: 'attention', label: 'Needs Attention' },
];

function statusFor(job: ScheduledJob) {
  if (automationNeedsAttention(job)) return { label: 'Attention', tone: 'attention' as const };
  if (!job.enabled) return { label: 'Paused', tone: 'paused' as const };
  return { label: 'Active', tone: 'active' as const };
}

export function DesktopAutomationList({ jobs, selectedJobId, query, filter, onQueryChange, onFilterChange, onSelect, style }: Props) {
  const visibleJobs = jobs.filter((job) => automationMatchesFilter(job, filter, query));

  return (
    <View style={[styles.listPane, style]}>
      <View style={styles.listHeader}>
        <View style={styles.listTitleRow}>
          <Text style={styles.sectionTitle}>Schedules</Text>
          <Text style={styles.sectionMeta}>{jobs.length}</Text>
        </View>
        <TextInput
          accessibilityLabel="Search automations"
          autoComplete="off"
          value={query}
          onChangeText={onQueryChange}
          placeholder="Search tasks or schedules…"
          placeholderTextColor="#748194"
          style={styles.searchInput}
        />
        <View accessibilityRole="radiogroup" accessibilityLabel="Automation filter" style={styles.filterRow}>
          {FILTERS.map((item) => {
            const selected = filter === item.key;
            return (
              <Pressable
                key={item.key}
                accessibilityRole="radio"
                accessibilityState={{ checked: selected }}
                style={({ hovered, pressed }: DesktopPressableState) => [
                  styles.filterButton,
                  selected ? styles.filterButtonActive : null,
                  hovered ? styles.buttonHover : null,
                  pressed ? styles.buttonPressed : null,
                ]}
                onPress={() => onFilterChange(item.key)}
              >
                <Text style={[styles.filterText, selected ? styles.filterTextActive : null]}>{item.label}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>
      {visibleJobs.length ? (
        <FlatList
          data={visibleJobs}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          initialNumToRender={14}
          maxToRenderPerBatch={18}
          windowSize={8}
          renderItem={({ item }) => {
            const selected = item.id === selectedJobId;
            const status = statusFor(item);
            return (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`${item.name}. ${status.label}. ${item.schedule || 'No schedule'}`}
                accessibilityState={{ selected }}
                style={({ hovered, pressed }: DesktopPressableState) => [
                  styles.jobRow,
                  hovered ? styles.jobRowHover : null,
                  selected ? styles.jobRowSelected : null,
                  pressed ? styles.buttonPressed : null,
                ]}
                onPress={() => onSelect(item)}
              >
                <View style={styles.jobTopRow}>
                  <Text numberOfLines={1} style={styles.jobName}>{item.name}</Text>
                  <View style={[
                    styles.statusBadge,
                    status.tone === 'paused' ? styles.statusBadgePaused : null,
                    status.tone === 'attention' ? styles.statusBadgeAttention : null,
                  ]}>
                    <Text style={[
                      styles.statusBadgeText,
                      status.tone === 'paused' ? styles.statusBadgeTextPaused : null,
                      status.tone === 'attention' ? styles.statusBadgeTextAttention : null,
                    ]}>{status.label}</Text>
                  </View>
                </View>
                <Text numberOfLines={1} style={styles.jobSchedule}>{item.schedule || 'No schedule'}</Text>
                <Text numberOfLines={2} style={styles.jobPrompt}>{item.prompt || 'No task description'}</Text>
              </Pressable>
            );
          }}
        />
      ) : (
        <View style={styles.listEmpty}>
          <Text style={styles.emptyTitle}>{jobs.length ? 'No matching automations' : 'No automations yet'}</Text>
          <Text style={styles.emptyCopy}>{jobs.length ? 'Try another search or filter.' : 'Create a scheduled task or reminder.'}</Text>
        </View>
      )}
    </View>
  );
}
