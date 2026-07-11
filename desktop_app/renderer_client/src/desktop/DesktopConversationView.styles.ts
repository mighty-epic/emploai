import { desktopConversationStylesPart1 } from './DesktopConversationView.styles.part1';
import { desktopConversationStylesPart2 } from './DesktopConversationView.styles.part2';
import { desktopConversationStylesPart3 } from './DesktopConversationView.styles.part3';
import { desktopConversationStylesPart4 } from './DesktopConversationView.styles.part4';
import { desktopConversationVisualStyles } from './DesktopConversationView.visualStyles';
import { mergeDesktopVisualStyles } from './mergeDesktopVisualStyles';

const baseStyles = {
  ...desktopConversationStylesPart1,
  ...desktopConversationStylesPart2,
  ...desktopConversationStylesPart3,
  ...desktopConversationStylesPart4,
};

export const styles = mergeDesktopVisualStyles(baseStyles, desktopConversationVisualStyles);
