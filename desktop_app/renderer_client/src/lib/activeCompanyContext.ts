const ACTIVE_COMPANY_STORAGE_KEY = 'emploai.activeCompanyId';


export function readActiveCompanyId(): string | null {
  if (typeof window === 'undefined') return null;
  const value = window.localStorage?.getItem(ACTIVE_COMPANY_STORAGE_KEY);
  return String(value || '').trim() || null;
}


export function rememberActiveCompanyId(companyId?: string | null) {
  if (typeof window === 'undefined') return;
  const value = String(companyId || '').trim();
  if (value) {
    window.localStorage?.setItem(ACTIVE_COMPANY_STORAGE_KEY, value);
  } else {
    window.localStorage?.removeItem(ACTIVE_COMPANY_STORAGE_KEY);
  }
}
