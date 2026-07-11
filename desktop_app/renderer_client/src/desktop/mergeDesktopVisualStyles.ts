import { StyleSheet } from 'react-native';

type StyleMap = Record<string, any>;

// Visual overrides must compose with the existing style object. Replacing a
// style key outright would also replace its layout properties (flex, size,
// position), which turns a palette change into an accidental layout rewrite.
export function mergeDesktopVisualStyles<Base extends StyleMap, Visual extends StyleMap>(
  base: Base,
  visual: Visual,
): Base & Visual {
  const merged: StyleMap = { ...base };

  Object.entries(visual).forEach(([key, visualStyle]) => {
    merged[key] = key in base
      ? StyleSheet.compose(base[key], visualStyle)
      : visualStyle;
  });

  return merged as Base & Visual;
}
