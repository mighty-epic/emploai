import { PropsWithChildren, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

type Props = PropsWithChildren<{
  title: string;
  meta?: string;
  defaultExpanded?: boolean;
}>;

export function CollapsibleSection({ title, meta, defaultExpanded = false, children }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <View style={styles.card}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${expanded ? 'Hide' : 'Show'} ${title}`}
        accessibilityState={{ expanded }}
        style={styles.header}
        onPress={() => setExpanded((prev) => !prev)}
      >
        <View style={styles.heading}>
          <Text style={styles.title}>{title}</Text>
          {meta ? <Text style={styles.meta}>{meta}</Text> : null}
        </View>
        <Text style={styles.toggle}>{expanded ? 'Hide' : 'Show'}</Text>
      </Pressable>
      {expanded ? <View style={styles.body}>{children}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#141c33',
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 10,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  heading: {
    flex: 1,
    gap: 4,
  },
  title: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '700',
  },
  meta: {
    color: '#91a3c8',
    fontSize: 12,
  },
  toggle: {
    color: '#7cc7ff',
    fontWeight: '700',
    fontSize: 13,
  },
  body: {
    gap: 10,
  },
});
