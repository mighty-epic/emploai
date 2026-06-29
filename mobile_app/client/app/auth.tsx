import { useEffect, useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  remoteLogin,
  remotePollGoogleAuth,
  remoteRegisterAccount,
  remoteResendOtp,
  remoteStartGoogleAuth,
  remoteVerifyOtp,
  type RemoteAuthLoginResult,
  type RemoteAuthOtpChallengeResult,
  type RemoteGoogleAuthPollResult,
} from '@/lib/appApi';
import { InfoHint } from '@/components/InfoHint';
import {
  firstSignupPasswordError,
  passwordRequirementStatus,
} from '@/lib/remoteAuthPasswordPolicy';
import { DEFAULT_REMOTE_API_BASE_URL, getOrCreateMobileDeviceKey, saveAppConfig } from '../lib/appConfig';
import { shortStatusText, userFacingError } from '../lib/diagnostics';

type AuthMode = 'login' | 'signup';

const GOOGLE_POLL_INTERVAL_MS = 1500;
const GOOGLE_POLL_TIMEOUT_MS = 2 * 60 * 1000;
const STARTUP_BUILD_STAMP = 'Safe start v12';

function delay(ms: number) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}

export default function AuthScreen() {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [confirmPasswordVisible, setConfirmPasswordVisible] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [otpChallenge, setOtpChallenge] = useState<RemoteAuthOtpChallengeResult | null>(null);
  const [otpCode, setOtpCode] = useState('');
  const [otpResendAvailableAt, setOtpResendAvailableAt] = useState(0);
  const [resendCooldownSeconds, setResendCooldownSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('Sign in to continue.');
  const [statusDetail, setStatusDetail] = useState('');
  const passwordRequirements = passwordRequirementStatus(password);

  const showStatus = (message: string, detail = '') => {
    setStatus(shortStatusText(message));
    setStatusDetail(detail);
  };

  const applyOtpChallenge = (challenge: RemoteAuthOtpChallengeResult) => {
    const cooldownSeconds = Math.max(0, Number(challenge.resend_available_in_seconds || 0));
    setOtpChallenge(challenge);
    setOtpCode('');
    setOtpResendAvailableAt(cooldownSeconds > 0 ? Date.now() + cooldownSeconds * 1000 : 0);
    setResendCooldownSeconds(Math.ceil(cooldownSeconds));
  };

  const clearOtpChallenge = () => {
    setOtpChallenge(null);
    setOtpCode('');
    setOtpResendAvailableAt(0);
    setResendCooldownSeconds(0);
  };

  useEffect(() => {
    if (!otpChallenge || !otpResendAvailableAt) {
      setResendCooldownSeconds(0);
      return;
    }
    const updateCooldown = () => {
      setResendCooldownSeconds(Math.max(0, Math.ceil((otpResendAvailableAt - Date.now()) / 1000)));
    };
    updateCooldown();
    const timer = globalThis.setInterval(updateCooldown, 1000);
    return () => {
      globalThis.clearInterval(timer);
    };
  }, [otpChallenge?.challenge_id, otpResendAvailableAt]);

  const finishLogin = async (result: RemoteAuthLoginResult | RemoteGoogleAuthPollResult) => {
    const sessionToken = result.session_token || '';
    if (!sessionToken) {
      throw new Error('Sign-in completed without an account token.');
    }
    const pairedDesktopId = result.mobile?.paired_desktop_id || '';
    await saveAppConfig({
      apiBaseUrl: DEFAULT_REMOTE_API_BASE_URL,
      accessToken: sessionToken,
      accountToken: sessionToken,
      accountTokenExpiresAt: Date.now() + Math.max(0, Number(result.expires_in_seconds || 0)) * 1000,
      accountRememberMe: Boolean(result.remember_me),
      accountUserId: result.user?.user_id ? String(result.user.user_id) : '',
      accountEmail: result.user?.email || '',
      accountMobileId: result.mobile?.mobile_id || '',
      pairedDesktopId,
      connectionMode: 'remote_cloud',
    });
    showStatus(pairedDesktopId ? 'Signed in.' : 'Pair this phone.');
    router.replace(pairedDesktopId ? '/chat' : '/pair');
  };

  const submit = async () => {
    const cleanEmail = email.trim();
    const cleanPassword = password.trim();
    if (!cleanEmail || !cleanPassword) {
      showStatus('Email and password required.');
      return;
    }
    if (mode === 'signup') {
      const passwordError = firstSignupPasswordError(
        cleanPassword,
        confirmPassword.trim(),
        cleanEmail,
        displayName.trim(),
      );
      if (passwordError) {
        showStatus(passwordError);
        return;
      }
    }

    setBusy(true);
    showStatus(mode === 'signup' ? 'Creating account...' : 'Signing in...');
    try {
      if (mode === 'signup') {
        const deviceKey = await getOrCreateMobileDeviceKey();
        const authResult = await remoteRegisterAccount(DEFAULT_REMOTE_API_BASE_URL, {
          email: cleanEmail,
          password: cleanPassword,
          display_name: displayName.trim() || undefined,
          actor_kind: 'mobile',
          device_name: 'Kraitos Mobile',
          device_platform: 'mobile',
          device_key: deviceKey,
          remember_me: rememberMe,
        });
        if ((authResult as RemoteAuthLoginResult).session_token) {
          await finishLogin(authResult as RemoteAuthLoginResult);
          return;
        }
        const challenge = authResult as RemoteAuthOtpChallengeResult;
        applyOtpChallenge(challenge);
        showStatus('Verification code sent.', `Sent to ${challenge.email}.`);
        return;
      }

      const deviceKey = await getOrCreateMobileDeviceKey();
      const authResult = await remoteLogin(DEFAULT_REMOTE_API_BASE_URL, {
        email: cleanEmail,
        password: cleanPassword,
        actor_kind: 'mobile',
        device_name: 'Kraitos Mobile',
        device_platform: 'mobile',
        device_key: deviceKey,
        remember_me: rememberMe,
      });
      if ((authResult as RemoteAuthLoginResult).session_token) {
        await finishLogin(authResult as RemoteAuthLoginResult);
        return;
      }
      const challenge = authResult as RemoteAuthOtpChallengeResult;
      applyOtpChallenge(challenge);
      showStatus('Verification code sent.', `Sent to ${challenge.email}.`);
    } catch (error) {
      showStatus(userFacingError(error, mode === 'signup' ? 'Account was not created.' : 'Sign-in failed.'));
    } finally {
      setBusy(false);
    }
  };

  const verifyOtp = async () => {
    if (!otpChallenge) {
      showStatus('Start sign-in again.');
      return;
    }
    if (!otpCode.trim()) {
      showStatus('Enter the code.');
      return;
    }
    setBusy(true);
    showStatus('Verifying code...');
    try {
      const result = await remoteVerifyOtp(DEFAULT_REMOTE_API_BASE_URL, {
        challenge_id: otpChallenge.challenge_id,
        code: otpCode.trim(),
      });
      await finishLogin(result);
    } catch (error) {
      showStatus(userFacingError(error, 'Check the code and try again.'));
    } finally {
      setBusy(false);
    }
  };

  const resendOtp = async () => {
    if (!otpChallenge) {
      showStatus('Start sign-in again.');
      return;
    }
    setBusy(true);
    showStatus('Sending a new code...');
    try {
      const challenge = await remoteResendOtp(DEFAULT_REMOTE_API_BASE_URL, {
        challenge_id: otpChallenge.challenge_id,
      });
      applyOtpChallenge(challenge);
      showStatus('New code sent.', `Sent to ${challenge.email}.`);
    } catch (error) {
      showStatus(userFacingError(error, 'Code was not sent.'));
    } finally {
      setBusy(false);
    }
  };

  const continueWithGoogle = async () => {
    setBusy(true);
    showStatus('Starting Google sign-in...');
    try {
      const deviceKey = await getOrCreateMobileDeviceKey();
      const started = await remoteStartGoogleAuth(DEFAULT_REMOTE_API_BASE_URL, {
        actor_kind: 'mobile',
        device_name: 'Kraitos Mobile',
        device_platform: 'mobile',
        device_key: deviceKey,
        remember_me: rememberMe,
      });
      showStatus('Opening Google...');
      await Linking.openURL(started.auth_url);
      const startedAt = Date.now();
      while (Date.now() - startedAt < GOOGLE_POLL_TIMEOUT_MS) {
        await delay(GOOGLE_POLL_INTERVAL_MS);
        const result = await remotePollGoogleAuth(DEFAULT_REMOTE_API_BASE_URL, {
          request_id: started.request_id,
          poll_token: started.poll_token,
        });
        if (result.status === 'complete') {
          await finishLogin(result);
          return;
        }
        if (result.status === 'error' || result.status === 'expired') {
          throw new Error(result.error || 'Google sign-in did not complete.');
        }
        showStatus('Waiting for Google...');
      }
      throw new Error('Google sign-in timed out. Try again from this screen.');
    } catch (error) {
      showStatus(userFacingError(error, 'Google sign-in did not finish.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.panel}>
        <Text style={styles.brand}>Kraitos</Text>
        <Text style={styles.buildStamp}>{STARTUP_BUILD_STAMP}</Text>
        <Text style={styles.title}>{mode === 'signup' ? 'Create your account' : 'Welcome back'}</Text>
        <Text style={styles.subtitle}>Your account connects this phone with your desktop workspace.</Text>

        <View style={styles.segment}>
          <Pressable
            style={[styles.segmentButton, mode === 'login' ? styles.segmentActive : null]}
            onPress={() => {
              setMode('login');
              clearOtpChallenge();
              setConfirmPassword('');
            }}
            disabled={busy}
          >
            <Text style={[styles.segmentText, mode === 'login' ? styles.segmentTextActive : null]}>Log in</Text>
          </Pressable>
          <Pressable
            style={[styles.segmentButton, mode === 'signup' ? styles.segmentActive : null]}
            onPress={() => {
              setMode('signup');
              clearOtpChallenge();
            }}
            disabled={busy}
          >
            <Text style={[styles.segmentText, mode === 'signup' ? styles.segmentTextActive : null]}>Sign up</Text>
          </Pressable>
        </View>

        {otpChallenge ? (
          <>
            <View style={styles.field}>
              <Text style={styles.label}>Verification code</Text>
              <TextInput
                style={styles.input}
                value={otpCode}
                onChangeText={setOtpCode}
                placeholder="6-digit code"
                placeholderTextColor="#7f93b5"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="number-pad"
                textContentType="oneTimeCode"
                editable={!busy}
              />
            </View>
            <Pressable
              style={[styles.primaryButton, busy ? styles.disabled : null]}
              onPress={verifyOtp}
              disabled={busy}
            >
              <Text style={styles.primaryText}>{busy ? 'Working...' : 'Verify code'}</Text>
            </Pressable>
            <View style={styles.actionRow}>
              <Pressable
                style={[styles.secondaryButton, (busy || resendCooldownSeconds > 0) ? styles.disabled : null]}
                onPress={resendOtp}
                disabled={busy || resendCooldownSeconds > 0}
              >
                <Text style={styles.secondaryText}>
                  {resendCooldownSeconds > 0 ? `Resend in ${resendCooldownSeconds}s` : 'Resend'}
                </Text>
              </Pressable>
              <Pressable
                style={[styles.secondaryButton, busy ? styles.disabled : null]}
                onPress={() => {
                  clearOtpChallenge();
                  showStatus('Sign in to continue.');
                }}
                disabled={busy}
              >
                <Text style={styles.secondaryText}>Back</Text>
              </Pressable>
            </View>
          </>
        ) : (
          <>
            {mode === 'signup' ? (
              <View style={styles.field}>
                <Text style={styles.label}>Display name</Text>
                <TextInput
                  style={styles.input}
                  value={displayName}
                  onChangeText={setDisplayName}
                  placeholder="Your name"
                  placeholderTextColor="#7f93b5"
                  autoCapitalize="words"
                  editable={!busy}
                />
              </View>
            ) : null}

            <View style={styles.field}>
              <Text style={styles.label}>Email</Text>
              <TextInput
                style={styles.input}
                value={email}
                onChangeText={setEmail}
                placeholder="you@example.com"
                placeholderTextColor="#7f93b5"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                textContentType="emailAddress"
                editable={!busy}
              />
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Password</Text>
              <View style={styles.passwordInputRow}>
                <TextInput
                  style={[styles.input, styles.passwordInput]}
                  value={password}
                  onChangeText={setPassword}
                  placeholder={mode === 'signup' ? 'Strong password' : 'Password'}
                  placeholderTextColor="#7f93b5"
                  secureTextEntry={!passwordVisible}
                  textContentType={mode === 'signup' ? 'newPassword' : 'password'}
                  autoCapitalize="none"
                  autoCorrect={false}
                  editable={!busy}
                />
                <Pressable
                  style={styles.peekButton}
                  onPress={() => setPasswordVisible((current) => !current)}
                  disabled={busy}
                >
                  <Text style={styles.peekButtonText}>{passwordVisible ? 'Hide' : 'Show'}</Text>
                </Pressable>
              </View>
            </View>

            {mode === 'signup' ? (
              <>
                <View style={styles.field}>
                  <Text style={styles.label}>Confirm password</Text>
                  <View style={styles.passwordInputRow}>
                    <TextInput
                      style={[styles.input, styles.passwordInput]}
                      value={confirmPassword}
                      onChangeText={setConfirmPassword}
                      placeholder="Write it again"
                      placeholderTextColor="#7f93b5"
                      secureTextEntry={!confirmPasswordVisible}
                      textContentType="newPassword"
                      autoCapitalize="none"
                      autoCorrect={false}
                      editable={!busy}
                    />
                    <Pressable
                      style={styles.peekButton}
                      onPress={() => setConfirmPasswordVisible((current) => !current)}
                      disabled={busy}
                    >
                      <Text style={styles.peekButtonText}>{confirmPasswordVisible ? 'Hide' : 'Show'}</Text>
                    </Pressable>
                  </View>
                </View>
                <View style={styles.passwordChecklist}>
                  {passwordRequirements.map((requirement) => (
                    <Text
                      key={requirement.id}
                      style={[
                        styles.passwordRequirement,
                        requirement.met ? styles.passwordRequirementMet : null,
                      ]}
                    >
                      {requirement.met ? '✓' : '-'} {requirement.label}
                    </Text>
                  ))}
                  {confirmPassword ? (
                    <Text
                      style={[
                        styles.passwordRequirement,
                        password === confirmPassword ? styles.passwordRequirementMet : null,
                      ]}
                    >
                      {password === confirmPassword ? '✓' : '-'} Passwords match
                    </Text>
                  ) : null}
                </View>
              </>
            ) : null}

            <Pressable style={styles.rememberRow} onPress={() => setRememberMe((current) => !current)} disabled={busy}>
              <View style={[styles.rememberBox, rememberMe ? styles.rememberBoxActive : null]}>
                <Text style={styles.rememberCheck}>{rememberMe ? '✓' : ''}</Text>
              </View>
              <Text style={styles.rememberText}>Remember me for 7 days</Text>
            </Pressable>

            <Pressable
              style={[styles.primaryButton, busy ? styles.disabled : null]}
              onPress={submit}
              disabled={busy}
            >
              <Text style={styles.primaryText}>{busy ? 'Working...' : mode === 'signup' ? 'Create account' : 'Log in'}</Text>
            </Pressable>

            <View style={styles.dividerRow}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>or</Text>
              <View style={styles.dividerLine} />
            </View>

            <Pressable
              style={[styles.googleButton, busy ? styles.disabled : null]}
              onPress={continueWithGoogle}
              disabled={busy}
            >
              <Text style={styles.googleText}>Continue with Google</Text>
            </Pressable>
          </>
        )}

        <View style={styles.statusRow}>
          <Text style={styles.status}>{status}</Text>
          {statusDetail ? <InfoHint text={statusDetail} /> : null}
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0b1020',
    justifyContent: 'center',
    padding: 20,
  },
  panel: {
    gap: 16,
  },
  brand: {
    color: '#7cc7ff',
    fontSize: 15,
    fontWeight: '700',
  },
  buildStamp: {
    color: '#8fa3c8',
    fontSize: 12,
    fontWeight: '700',
  },
  title: {
    color: '#ffffff',
    fontSize: 28,
    fontWeight: '800',
  },
  subtitle: {
    color: '#b8c7e6',
    fontSize: 15,
    lineHeight: 22,
  },
  segment: {
    flexDirection: 'row',
    backgroundColor: '#111a31',
    borderRadius: 8,
    padding: 4,
    gap: 4,
  },
  segmentButton: {
    minHeight: 44,
    flex: 1,
    borderRadius: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  segmentActive: {
    backgroundColor: '#2d4674',
  },
  segmentText: {
    color: '#aebfe0',
    fontWeight: '700',
  },
  segmentTextActive: {
    color: '#ffffff',
  },
  field: {
    gap: 7,
  },
  label: {
    color: '#dce8ff',
    fontSize: 13,
    fontWeight: '700',
  },
  input: {
    minHeight: 48,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#263659',
    backgroundColor: '#111a31',
    color: '#ffffff',
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
  },
  passwordInputRow: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#263659',
    backgroundColor: '#111a31',
  },
  passwordInput: {
    flex: 1,
    width: 0,
    minHeight: 46,
    borderWidth: 0,
    backgroundColor: 'transparent',
  },
  peekButton: {
    minHeight: 44,
    minWidth: 62,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  peekButtonText: {
    color: '#7cc7ff',
    fontSize: 13,
    fontWeight: '800',
  },
  passwordChecklist: {
    gap: 5,
    paddingHorizontal: 2,
  },
  passwordRequirement: {
    color: '#ffb4b4',
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
  },
  passwordRequirementMet: {
    color: '#8ee6b0',
  },
  rememberRow: {
    minHeight: 36,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  rememberBox: {
    width: 20,
    height: 20,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: '#51668d',
    backgroundColor: '#111a31',
    alignItems: 'center',
    justifyContent: 'center',
  },
  rememberBoxActive: {
    backgroundColor: '#7cc7ff',
    borderColor: '#7cc7ff',
  },
  rememberCheck: {
    color: '#07111f',
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 16,
  },
  rememberText: {
    color: '#dce8ff',
    fontSize: 14,
    fontWeight: '700',
  },
  primaryButton: {
    minHeight: 48,
    borderRadius: 8,
    backgroundColor: '#3b82f6',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  disabled: {
    opacity: 0.55,
  },
  primaryText: {
    color: '#ffffff',
    fontWeight: '800',
    fontSize: 15,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
  },
  secondaryButton: {
    minHeight: 44,
    flex: 1,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#2a3b61',
    backgroundColor: '#111a31',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 14,
  },
  secondaryText: {
    color: '#dce8ff',
    fontWeight: '800',
    fontSize: 14,
  },
  dividerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: '#263659',
  },
  dividerText: {
    color: '#8fa3c8',
    fontSize: 12,
    fontWeight: '800',
  },
  googleButton: {
    minHeight: 48,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#d8e0f0',
    backgroundColor: '#ffffff',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  googleText: {
    color: '#172033',
    fontWeight: '800',
    fontSize: 15,
  },
  status: {
    color: '#b8c7e6',
    fontSize: 13,
    lineHeight: 20,
    flexShrink: 1,
  },
  statusRow: {
    minHeight: 24,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
});
