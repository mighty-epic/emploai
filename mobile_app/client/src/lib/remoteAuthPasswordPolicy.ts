export type PasswordRequirement = {
  id: 'length' | 'lowercase' | 'uppercase' | 'number' | 'symbol' | 'maxLength';
  label: string;
  met: boolean;
};

const COMMON_WEAK_PASSWORDS = new Set([
  'password',
  'password1',
  'password12',
  'password123',
  'password123!',
  'qwerty123',
  'qwerty123!',
  'letmein123',
  'admin12345',
  'welcome123',
  'changeme123',
  '123456789',
  '1234567890',
]);

export function passwordRequirementStatus(password: string): PasswordRequirement[] {
  return [
    { id: 'length', label: 'At least 12 characters', met: password.length >= 12 },
    { id: 'lowercase', label: 'Lowercase letter', met: /[a-z]/.test(password) },
    { id: 'uppercase', label: 'Uppercase letter', met: /[A-Z]/.test(password) },
    { id: 'number', label: 'Number', met: /\d/.test(password) },
    { id: 'symbol', label: 'Special symbol', met: /[^A-Za-z0-9]/.test(password) },
    { id: 'maxLength', label: '256 characters or fewer', met: password.length <= 256 },
  ];
}

export function strongPasswordErrors(password: string, email: string, displayName: string) {
  const errors = passwordRequirementStatus(password)
    .filter((requirement) => !requirement.met)
    .map((requirement) => `Missing: ${requirement.label}.`);

  const normalized = password.toLowerCase();
  if (COMMON_WEAK_PASSWORDS.has(normalized.replace(/\s+/g, ''))) {
    errors.push('Avoid common weak passwords.');
  }

  const emailLocalPart = email.split('@')[0]?.toLowerCase().replace(/[^a-z0-9]/g, '') || '';
  const cleanedName = displayName.toLowerCase().replace(/[^a-z0-9]/g, '');
  const cleanedPassword = normalized.replace(/[^a-z0-9]/g, '');
  if (emailLocalPart.length >= 4 && cleanedPassword.includes(emailLocalPart)) {
    errors.push('Do not include your email name.');
  }
  if (cleanedName.length >= 4 && cleanedPassword.includes(cleanedName)) {
    errors.push('Do not include your display name.');
  }
  if (/(.)\1{4,}/.test(password)) {
    errors.push('Avoid repeated characters.');
  }
  if (/0123|1234|2345|3456|4567|5678|6789|abcd|bcde|cdef|qwer|wert|asdf|sdfg|zxcv/i.test(password)) {
    errors.push('Avoid obvious keyboard or number sequences.');
  }
  return errors;
}

export function firstSignupPasswordError(
  password: string,
  confirmPassword: string,
  email: string,
  displayName: string,
) {
  if (!confirmPassword) {
    return 'Confirm your password.';
  }
  if (password !== confirmPassword) {
    return 'Passwords do not match.';
  }
  return strongPasswordErrors(password, email, displayName)[0] || '';
}
