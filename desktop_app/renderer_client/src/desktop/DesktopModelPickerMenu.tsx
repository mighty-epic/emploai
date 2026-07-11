import { Pressable, ScrollView, Text, View } from 'react-native';

import { modelProviderKey } from './modelProviders';

type ModelProviderGroup = {
  provider: string;
  models: string[];
};

type ModelVariantOption = {
  id: string;
  label: string;
};

type Props = {
  styles: any;
  MonoIcon: any;
  draftModelGroups: ModelProviderGroup[];
  currentModelLabel: string;
  currentVariant: string;
  currentVariantHasControls: boolean;
  currentVariantOptions: ModelVariantOption[];
  currentPlannerLabel: string;
  plannerModelGroups: ModelProviderGroup[];
  expandedModelProviders: Record<string, boolean>;
  expandedPlannerProviders: Record<string, boolean>;
  setExpandedModelProviders: (updater: any) => void;
  setExpandedPlannerProviders: (updater: any) => void;
  chooseModel: (model: string) => void | Promise<void>;
  chooseVariant: (variant: string) => void | Promise<void>;
  choosePlannerModel: (model: string | null) => void | Promise<void>;
  scrollStyle?: any;
  emptyTitle: string;
  emptyText: string;
};

function anyExpanded(values: Record<string, boolean>) {
  return Object.values(values || {}).some(Boolean);
}

function selectedProviderKey(groups: ModelProviderGroup[], model: string) {
  return modelProviderKey(groups.find((group) => group.models.includes(model))?.provider);
}

function firstProviderKey(groups: ModelProviderGroup[]) {
  return modelProviderKey(groups[0]?.provider);
}

export function DesktopModelPickerMenu({
  styles,
  MonoIcon,
  draftModelGroups,
  currentModelLabel,
  currentVariant,
  currentVariantHasControls,
  currentVariantOptions,
  currentPlannerLabel,
  plannerModelGroups,
  expandedModelProviders,
  expandedPlannerProviders,
  setExpandedModelProviders,
  setExpandedPlannerProviders,
  chooseModel,
  chooseVariant,
  choosePlannerModel,
  scrollStyle,
  emptyTitle,
  emptyText,
}: Props) {
  const modelProvider = selectedProviderKey(draftModelGroups, currentModelLabel) || firstProviderKey(draftModelGroups);
  const plannerProvider = currentPlannerLabel === 'auto'
    ? firstProviderKey(plannerModelGroups)
    : selectedProviderKey(plannerModelGroups, currentPlannerLabel) || firstProviderKey(plannerModelGroups);
  const showReasoningControls = currentVariantHasControls && currentVariantOptions.length > 0;
  const modelExpanded = anyExpanded(expandedModelProviders);
  const plannerExpanded = anyExpanded(expandedPlannerProviders);
  const plannerDisplay = currentPlannerLabel === 'auto' ? `Automatic · ${currentModelLabel}` : currentPlannerLabel;
  const hasAnyChoices = Boolean(draftModelGroups.length || plannerModelGroups.length || showReasoningControls);

  const toggleModelProviders = () => {
    if (!modelProvider) return;
    setExpandedModelProviders((current: Record<string, boolean>) => ({
      ...current,
      [modelProvider]: !current?.[modelProvider],
    }));
  };

  const togglePlannerProviders = () => {
    if (!plannerProvider) return;
    setExpandedPlannerProviders((current: Record<string, boolean>) => ({
      ...current,
      [plannerProvider]: !current?.[plannerProvider],
    }));
  };

  const renderProviderGroups = (
    groups: ModelProviderGroup[],
    expandedProviders: Record<string, boolean>,
    setExpandedProviders: (updater: any) => void,
    selectedModel: string,
    onSelect: (model: string) => void | Promise<void>,
    keyPrefix: string,
  ) => (
    <View style={styles.modelProviderDropdownList}>
      {groups.map((group) => {
        const providerKey = modelProviderKey(group.provider);
        const expanded = Boolean(expandedProviders[providerKey]);
        const selected = group.models.find((model) => model === selectedModel) || null;
        return (
          <View key={`${keyPrefix}-provider-${group.provider}`} style={styles.modelProviderDropdown}>
            <Pressable
              style={({ hovered }: any) => [
                styles.modelProviderDropdownHeader,
                hovered ? styles.modelProviderDropdownHeaderHovered : null,
                selected ? styles.modelProviderDropdownHeaderActive : null,
              ]}
              onPress={() => setExpandedProviders((current: Record<string, boolean>) => ({
                ...current,
                [providerKey]: !current?.[providerKey],
              }))}
            >
              <View style={styles.modelProviderDropdownCopy}>
                <Text style={styles.modelProviderDropdownTitle}>{group.provider}</Text>
                <Text style={styles.modelProviderDropdownMeta} numberOfLines={1}>
                  {selected || `${group.models.length} models`}
                </Text>
              </View>
              <MonoIcon name={expanded ? 'chevron_up' : 'chevron_down'} style={styles.modelProviderDropdownChevron} />
            </Pressable>
            {expanded ? (
              <View style={styles.modelProviderDropdownBody}>
                {group.models.map((model) => {
                  const modelSelected = model === selectedModel;
                  return (
                    <Pressable
                      key={`${keyPrefix}-${group.provider}-${model}`}
                      style={({ hovered }: any) => [
                        styles.modelListItem,
                        styles.modelNestedListItem,
                        hovered ? styles.modelListItemHovered : null,
                        modelSelected ? styles.modelListItemActive : null,
                      ]}
                      onPress={() => void onSelect(model)}
                    >
                      <View style={styles.modelListItemCopy}>
                        <Text style={[styles.modelListItemTitle, modelSelected ? styles.modelListItemTitleActive : null]} numberOfLines={1}>
                          {model}
                        </Text>
                      </View>
                      <Text style={[styles.modelListItemMeta, modelSelected ? styles.modelListItemMetaActive : null]}>
                        {modelSelected ? 'Current' : 'Select'}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            ) : null}
          </View>
        );
      })}
    </View>
  );

  if (!hasAnyChoices) {
    return (
      <View style={styles.commandPanelEmpty}>
        <Text style={styles.commandPanelEmptyTitle}>{emptyTitle}</Text>
        <Text style={styles.commandPanelEmptyText}>{emptyText}</Text>
      </View>
    );
  }

  return (
    <ScrollView style={scrollStyle || styles.modelPickerScroll} contentContainerStyle={styles.modelPickerCompactContent}>
      {showReasoningControls ? (
        <View style={styles.modelPickerCompactGroup}>
          <Text style={styles.modelPickerCompactLabel}>Reasoning</Text>
          {currentVariantOptions.map((option) => {
            const selected = option.id === currentVariant;
            return (
              <Pressable
                key={`model-variant-${option.id}`}
                style={({ hovered }: any) => [
                  styles.modelPickerCompactRow,
                  hovered ? styles.modelPickerCompactRowHovered : null,
                ]}
                onPress={() => void chooseVariant(option.id)}
              >
                <Text style={styles.modelPickerCompactText}>{option.label}</Text>
                {selected ? <Text style={styles.modelPickerCompactCheck}>✓</Text> : null}
              </Pressable>
            );
          })}
        </View>
      ) : null}

      {showReasoningControls && draftModelGroups.length ? <View style={styles.modelPickerCompactDivider} /> : null}

      {draftModelGroups.length ? (
        <View style={styles.modelPickerCompactGroup}>
          <Pressable
            style={({ hovered }: any) => [
              styles.modelPickerCompactRow,
              hovered ? styles.modelPickerCompactRowHovered : null,
            ]}
            onPress={toggleModelProviders}
          >
            <View style={styles.modelPickerCompactRowCopy}>
              <Text style={styles.modelPickerCompactKicker}>Main model</Text>
              <Text style={styles.modelPickerCompactText} numberOfLines={1}>{currentModelLabel}</Text>
            </View>
            <MonoIcon name={modelExpanded ? 'chevron_up' : 'chevron_down'} style={styles.modelPickerCompactChevron} />
          </Pressable>
          {modelExpanded ? renderProviderGroups(
            draftModelGroups,
            expandedModelProviders,
            setExpandedModelProviders,
            currentModelLabel,
            chooseModel,
            'model',
          ) : null}
        </View>
      ) : null}

      {plannerModelGroups.length ? (
        <>
          {(showReasoningControls || draftModelGroups.length) ? <View style={styles.modelPickerCompactDivider} /> : null}
          <View style={styles.modelPickerCompactGroup}>
            <Pressable
              style={({ hovered }: any) => [
                styles.modelPickerCompactRow,
                hovered ? styles.modelPickerCompactRowHovered : null,
              ]}
              onPress={togglePlannerProviders}
            >
              <View style={styles.modelPickerCompactRowCopy}>
                <Text style={styles.modelPickerCompactKicker}>Planner model</Text>
                <Text style={styles.modelPickerCompactText} numberOfLines={1}>{plannerDisplay}</Text>
              </View>
              <MonoIcon name={plannerExpanded ? 'chevron_up' : 'chevron_down'} style={styles.modelPickerCompactChevron} />
            </Pressable>
            {plannerExpanded ? (
              <View style={styles.modelPickerPlannerBody}>
                <Pressable
                  style={({ hovered }: any) => [
                    styles.modelListItem,
                    styles.modelAutoListItem,
                    hovered ? styles.modelListItemHovered : null,
                    currentPlannerLabel === 'auto' ? styles.modelListItemActive : null,
                  ]}
                  onPress={() => void choosePlannerModel(null)}
                >
                  <View style={styles.modelListItemCopy}>
                    <Text style={[styles.modelListItemTitle, currentPlannerLabel === 'auto' ? styles.modelListItemTitleActive : null]}>
                      Automatic
                    </Text>
                  </View>
                  <Text style={[styles.modelListItemMeta, currentPlannerLabel === 'auto' ? styles.modelListItemMetaActive : null]}>
                    {currentPlannerLabel === 'auto' ? 'Current' : 'Select'}
                  </Text>
                </Pressable>
                {renderProviderGroups(
                  plannerModelGroups,
                  expandedPlannerProviders,
                  setExpandedPlannerProviders,
                  currentPlannerLabel,
                  choosePlannerModel,
                  'planner',
                )}
              </View>
            ) : null}
          </View>
        </>
      ) : null}
    </ScrollView>
  );
}
