import { useMemo } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import qrcode from 'qrcode-generator';

type PairingQrCodeProps = {
  value: string;
  size?: number;
  quietZone?: number;
  foregroundColor?: string;
  backgroundColor?: string;
  style?: StyleProp<ViewStyle>;
};

function createMatrix(value: string) {
  const qr = qrcode(0, 'M');
  qr.addData(value);
  qr.make();
  const moduleCount = qr.getModuleCount();
  const rows: boolean[][] = [];
  for (let row = 0; row < moduleCount; row += 1) {
    const cells: boolean[] = [];
    for (let col = 0; col < moduleCount; col += 1) {
      cells.push(qr.isDark(row, col));
    }
    rows.push(cells);
  }
  return { moduleCount, rows };
}

export function PairingQrCode({
  value,
  size = 196,
  quietZone = 12,
  foregroundColor = '#07111f',
  backgroundColor = '#ffffff',
  style,
}: PairingQrCodeProps) {
  const matrix = useMemo(() => createMatrix(value || ' '), [value]);
  const moduleSize = Math.max(2, Math.floor((size - quietZone * 2) / matrix.moduleCount));
  const renderedSize = moduleSize * matrix.moduleCount + quietZone * 2;

  return (
    <View
      accessibilityLabel="Phone pairing QR code"
      style={[
        styles.frame,
        { width: renderedSize, height: renderedSize, padding: quietZone, backgroundColor },
        style,
      ]}
    >
      {matrix.rows.map((row, rowIndex) => (
        <View key={`qr-row-${rowIndex}`} style={styles.row}>
          {row.map((dark, colIndex) => (
            <View
              key={`qr-cell-${rowIndex}-${colIndex}`}
              style={{
                width: moduleSize,
                height: moduleSize,
                backgroundColor: dark ? foregroundColor : backgroundColor,
              }}
            />
          ))}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    borderRadius: 8,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
  },
});
