import { useEffect, useRef, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  fetchCompanyContext,
  selectCompanyContext,
  type CompanyContext,
} from '@/lib/appApi';
import { rememberActiveCompanyId } from '@/lib/activeCompanyContext';
import type { LocalConfirm } from '@/lib/sharedConfirmations';
import { userFacingError } from '../../lib/diagnostics';


type Props = {
  apiBaseUrl?: string | null;
  token?: string | null;
  confirmAction: LocalConfirm;
};


function hasPotentialUnsavedDraft() {
  if (Platform.OS !== 'web' || typeof document === 'undefined') return false;
  const fields = Array.from(
    document.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>(
      'input:not([disabled]):not([readonly]), textarea:not([disabled]):not([readonly])',
    ),
  );
  return fields.some((field) => {
    if (field.type === 'search') return false;
    return field.value.trim() !== String(field.defaultValue || '').trim();
  });
}

export function DesktopCompanySwitcher({ apiBaseUrl, token, confirmAction }: Props) {
  const [context, setContext] = useState<CompanyContext | null>(null);
  const [open, setOpen] = useState(false);
  const [busyCompanyId, setBusyCompanyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestVersionRef = useRef(0);

  useEffect(() => {
    if (!apiBaseUrl || !token) {
      setContext(null);
      return;
    }
    const requestVersion = ++requestVersionRef.current;
    setError(null);
    void fetchCompanyContext(apiBaseUrl, token)
      .then((next) => {
        if (requestVersion === requestVersionRef.current) {
          rememberActiveCompanyId(next.active_company_id);
          setContext(next);
        }
      })
      .catch((reason) => {
        if (requestVersion === requestVersionRef.current) {
          setError(userFacingError(reason, 'Company context is unavailable.'));
        }
      });
  }, [apiBaseUrl, token]);

  const chooseCompany = async (companyId: string) => {
    if (!apiBaseUrl || !token || busyCompanyId) return;
    if (companyId === context?.active_company_id) {
      setOpen(false);
      return;
    }
    if (hasPotentialUnsavedDraft()) {
      const discard = await confirmAction({
        title: 'Switch Companies with unsaved text?',
        message: (
          'Text that has not been saved or sent belongs to the current Company and may be lost. '
          + 'Background work can continue and will keep its Company label.'
        ),
        confirmLabel: 'Discard draft and switch',
        cancelLabel: 'Stay here',
        tone: 'danger',
        details: [
          'Saved records and chats are unaffected.',
          'The new Company opens as a complete application context, not as a Fleet filter.',
        ],
      });
      if (!discard) return;
    }
    setBusyCompanyId(companyId);
    setError(null);
    try {
      const next = await selectCompanyContext(apiBaseUrl, token, companyId);
      rememberActiveCompanyId(next.active_company_id);
      setContext(next);
      setOpen(false);
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        window.location.reload();
      }
    } catch (reason) {
      setError(userFacingError(reason, 'Company was not switched.'));
    } finally {
      setBusyCompanyId(null);
    }
  };

  const activeSummary = context?.companies.find(
    (item) => item.company_id === context.active_company_id,
  );
  const label = activeSummary?.display_name
    || context?.active_company?.manifest?.display_name as string
    || (error ? 'Company unavailable' : 'Company');

  return (
    <View style={styles.anchor}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Current company: ${label}. Open company switcher`}
        accessibilityState={{ expanded: open }}
        style={({ hovered, pressed }: any) => [
          styles.trigger,
          hovered ? styles.triggerHovered : null,
          pressed ? styles.triggerPressed : null,
          error ? styles.triggerError : null,
        ]}
        onPress={() => setOpen((current) => !current)}
      >
        <View style={[styles.statusDot, error ? styles.statusDotError : null]} />
        <Text style={styles.triggerLabel} numberOfLines={1}>{label}</Text>
        <Text style={styles.chevron}>{open ? '▴' : '▾'}</Text>
      </Pressable>

      {open ? (
        <View style={styles.menu}>
          <View style={styles.menuHeader}>
            <Text style={styles.menuEyebrow}>ACTIVE COMPANY</Text>
            <Text style={styles.menuHint}>The whole app uses this company context.</Text>
          </View>
          {context?.companies.map((company) => {
            const selected = company.company_id === context.active_company_id;
            const unavailable = company.status !== 'active';
            return (
              <Pressable
                key={company.company_id}
                accessibilityRole="menuitem"
                accessibilityState={{ selected, disabled: unavailable }}
                disabled={unavailable || Boolean(busyCompanyId)}
                style={({ hovered, pressed }: any) => [
                  styles.companyRow,
                  hovered && !unavailable ? styles.companyRowHovered : null,
                  selected ? styles.companyRowSelected : null,
                  pressed ? styles.companyRowPressed : null,
                  unavailable ? styles.companyRowDisabled : null,
                ]}
                onPress={() => void chooseCompany(company.company_id)}
              >
                <View style={styles.companyCopy}>
                  <Text style={styles.companyName} numberOfLines={1}>
                    {company.display_name}
                  </Text>
                  <Text style={styles.companyMeta} numberOfLines={1}>
                    {company.ownership === 'root' ? 'Owned on this computer' : 'Worker membership'}
                  </Text>
                </View>
                <Text style={selected ? styles.selectedMark : styles.companyState}>
                  {busyCompanyId === company.company_id ? '…' : selected ? '✓' : unavailable ? company.status : ''}
                </Text>
              </Pressable>
            );
          })}
          {!context?.companies.length ? (
            <Text style={styles.emptyText}>{error || 'Preparing the local company…'}</Text>
          ) : null}
          {error ? <Text style={styles.errorText}>{error}</Text> : null}
        </View>
      ) : null}
    </View>
  );
}


const styles = StyleSheet.create({
  anchor: {
    position: 'relative',
    zIndex: 80,
  },
  trigger: {
    minWidth: 142,
    maxWidth: 230,
    height: 28,
    paddingHorizontal: 10,
    borderRadius: 8,
    backgroundColor: '#101c2a',
    borderWidth: 1,
    borderColor: '#223448',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },
  triggerHovered: {
    backgroundColor: '#142334',
    borderColor: '#35516c',
  },
  triggerPressed: {
    opacity: 0.84,
  },
  triggerError: {
    borderColor: '#8d4c55',
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 999,
    backgroundColor: '#59d6a2',
  },
  statusDotError: {
    backgroundColor: '#f28b8b',
  },
  triggerLabel: {
    flex: 1,
    color: '#dce9f6',
    fontSize: 12,
    fontWeight: '700',
  },
  chevron: {
    color: '#7f9ab4',
    fontSize: 10,
  },
  menu: {
    position: 'absolute',
    top: 34,
    right: 0,
    width: 300,
    padding: 8,
    borderRadius: 12,
    backgroundColor: '#0c1622',
    borderWidth: 1,
    borderColor: '#273b50',
    shadowColor: '#000000',
    shadowOpacity: 0.44,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 10 },
    elevation: 24,
  },
  menuHeader: {
    paddingHorizontal: 8,
    paddingTop: 5,
    paddingBottom: 8,
  },
  menuEyebrow: {
    color: '#68d8e8',
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 1.1,
  },
  menuHint: {
    color: '#7f93a9',
    fontSize: 11,
    marginTop: 3,
  },
  companyRow: {
    minHeight: 52,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  companyRowHovered: {
    backgroundColor: '#122131',
  },
  companyRowSelected: {
    backgroundColor: '#142a34',
  },
  companyRowPressed: {
    opacity: 0.82,
  },
  companyRowDisabled: {
    opacity: 0.46,
  },
  companyCopy: {
    flex: 1,
  },
  companyName: {
    color: '#eff6fc',
    fontSize: 13,
    fontWeight: '700',
  },
  companyMeta: {
    color: '#7f95ac',
    fontSize: 10,
    marginTop: 2,
  },
  selectedMark: {
    color: '#65dce8',
    fontSize: 15,
    fontWeight: '800',
  },
  companyState: {
    color: '#a7b5c4',
    fontSize: 10,
    textTransform: 'capitalize',
  },
  emptyText: {
    color: '#8ca0b5',
    fontSize: 12,
    padding: 10,
  },
  errorText: {
    color: '#f1a0a6',
    fontSize: 10,
    paddingHorizontal: 8,
    paddingBottom: 5,
  },
});
