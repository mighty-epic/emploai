from __future__ import annotations

from app_backend.fleet_policy import FLEET_PREVIEW_MODE

REMOTE_SHORT_SESSION_TTL_SECONDS = 60 * 60 * 12
REMOTE_REMEMBERED_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_SESSION_TTL_SECONDS = REMOTE_REMEMBERED_SESSION_TTL_SECONDS
REMOTE_PAIRING_TTL_SECONDS = 60 * 10
FLEET_ENROLLMENT_TTL_SECONDS = 60 * 30

class RemoteControlStoreAuthMixin:
    def _auth_challenge_view(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        expires_at = float(row["expires_at"] or time.time())
        resend_available_at = float(row["resend_available_at"] or time.time())
        return {
            "status": "otp_required",
            "challenge_id": str(row["challenge_id"] or ""),
            "email": str(row["email"] or ""),
            "purpose": str(row["purpose"] or "login_verify"),
            "expires_at": expires_at,
            "expires_in_seconds": max(0, int(expires_at - time.time())),
            "resend_available_in_seconds": max(0, int(resend_available_at - time.time())),
        }

    def _token_ttl_for_remember_me(self, remember_me: bool) -> int:
        return REMOTE_REMEMBERED_SESSION_TTL_SECONDS if remember_me else REMOTE_SHORT_SESSION_TTL_SECONDS

    def _oauth_provider_labels_for_user_locked(self, user_id: int) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT provider
            FROM oauth_identities
            WHERE user_id = ?
            ORDER BY provider
            """,
            (int(user_id),),
        ).fetchall()
        labels: list[str] = []
        for row in rows:
            provider = str(row["provider"] or "").strip().casefold()
            if provider == "google":
                labels.append("Google")
            elif provider:
                labels.append(provider[:1].upper() + provider[1:])
        return labels

    def _raise_password_login_error_for_user_locked(self, user_id: int) -> None:
        providers = self._oauth_provider_labels_for_user_locked(user_id)
        if "Google" in providers:
            raise ValueError("This email is registered with Google. Sign in with Google instead.")
        if providers:
            provider_text = ", ".join(providers)
            raise ValueError(f"This email is registered with {provider_text}. Sign in with that provider instead.")
        raise ValueError("Invalid email or password")

    def _delete_unverified_signup_user_if_orphaned_locked(self, user_id: int) -> None:
        active_signup = self._conn.execute(
            """
            SELECT 1
            FROM auth_otp_challenges
            WHERE user_id = ?
              AND purpose = 'signup_verify'
              AND consumed_at IS NULL
              AND replaced_at IS NULL
              AND expires_at > ?
            LIMIT 1
            """,
            (int(user_id), time.time()),
        ).fetchone()
        if active_signup:
            return
        user = self._conn.execute("SELECT * FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
        if not user or user["email_verified_at"]:
            return
        linked_oauth = self._conn.execute(
            "SELECT 1 FROM oauth_identities WHERE user_id = ? LIMIT 1",
            (int(user_id),),
        ).fetchone()
        if linked_oauth:
            return
        for table in ("user_profiles", "user_secrets", "shared_state", "desktops", "mobiles", "remote_sessions"):
            self._conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (int(user_id),))
        self._conn.execute("DELETE FROM users WHERE user_id = ? AND email_verified_at IS NULL", (int(user_id),))

    def _pending_signup_challenge_for_email_locked(self, email: str) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT *
            FROM auth_otp_challenges
            WHERE email = ?
              AND purpose = 'signup_verify'
              AND consumed_at IS NULL
              AND replaced_at IS NULL
              AND expires_at > ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (_normalize_email(email), time.time()),
        ).fetchone()

    def _create_auth_otp_challenge_locked(
        self,
        *,
        user_id: int,
        email: str,
        purpose: str,
        actor_kind: str,
        device_name: Optional[str],
        device_platform: Optional[str],
        device_key: Optional[str],
        remember_me: bool,
        pending_password_salt: Optional[str] = None,
        pending_password_hash: Optional[str] = None,
        pending_display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if actor_kind not in {"mobile", "desktop"}:
            raise ValueError("actor_kind must be mobile or desktop")
        normalized_purpose = str(purpose or "").strip()
        if normalized_purpose not in {"signup_verify", "login_verify"}:
            raise ValueError("Unsupported verification purpose")
        normalized_email = _normalize_email(email)

        now = time.time()
        if normalized_purpose == "signup_verify":
            self._conn.execute(
                """
                UPDATE auth_otp_challenges
                SET replaced_at = ?,
                    pending_password_salt = NULL,
                    pending_password_hash = NULL
                WHERE email = ? AND purpose = ? AND consumed_at IS NULL AND replaced_at IS NULL
                """,
                (now, normalized_email, normalized_purpose),
            )
        else:
            self._conn.execute(
                """
                UPDATE auth_otp_challenges
                SET replaced_at = ?
                WHERE user_id = ? AND purpose = ? AND consumed_at IS NULL AND replaced_at IS NULL
                """,
                (now, int(user_id), normalized_purpose),
            )
        challenge_id = f"otp_{secrets.token_urlsafe(24)}"
        code = f"{secrets.randbelow(1_000_000):06d}"
        salt = secrets.token_hex(16)
        ttl_seconds = self._token_ttl_for_remember_me(bool(remember_me))
        self._conn.execute(
            """
            INSERT INTO auth_otp_challenges(
                challenge_id, user_id, email, purpose, code_salt, code_hash,
                pending_password_salt, pending_password_hash, pending_display_name,
                actor_kind, device_name, device_platform, device_key, remember_me, token_ttl_seconds,
                created_at, expires_at, resend_available_at, attempt_count, max_attempts, consumed_at, replaced_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                challenge_id,
                int(user_id),
                normalized_email,
                normalized_purpose,
                salt,
                _hash_otp_code(code, salt),
                (pending_password_salt or "").strip() or None,
                (pending_password_hash or "").strip() or None,
                (pending_display_name or "").strip()[:MAX_DISPLAY_NAME_CHARS] or None,
                actor_kind,
                (device_name or "").strip()[:MAX_DISPLAY_NAME_CHARS] or None,
                (device_platform or "").strip()[:MAX_DEVICE_PLATFORM_CHARS] or None,
                (device_key or "").strip()[:MAX_DEVICE_KEY_CHARS] or None,
                1 if remember_me else 0,
                ttl_seconds,
                now,
                now + AUTH_OTP_TTL_SECONDS,
                now + AUTH_OTP_RESEND_COOLDOWN_SECONDS,
                0,
                AUTH_OTP_MAX_ATTEMPTS,
                None,
                None,
            ),
        )
        row = self._conn.execute("SELECT * FROM auth_otp_challenges WHERE challenge_id = ?", (challenge_id,)).fetchone()
        return {**self._auth_challenge_view(row), "otp_code": code}

    def begin_signup_otp(
        self,
        *,
        email: str,
        password: str,
        display_name: Optional[str] = None,
        actor_kind: str,
        device_name: Optional[str] = None,
        device_platform: Optional[str] = None,
        device_key: Optional[str] = None,
        remember_me: bool = False,
    ) -> Dict[str, Any]:
        normalized_email = _normalize_email(email)
        if not normalized_email or len(normalized_email) > MAX_EMAIL_CHARS or "@" not in normalized_email:
            raise ValueError("A valid email is required")
        errors = _strong_password_errors(password, email=normalized_email, display_name=display_name)
        if errors:
            raise ValueError(" ".join(errors))

        with self._lock:
            self._cleanup_locked()
            existing = self._conn.execute("SELECT * FROM users WHERE email = ?", (normalized_email,)).fetchone()
            if existing and existing["email_verified_at"]:
                raise ValueError("An account with that email already exists")
            now = time.time()
            password_salt = secrets.token_hex(16)
            password_hash = _hash_password(password, password_salt)
            pending_display_name = (display_name or "").strip()[:MAX_DISPLAY_NAME_CHARS] or normalized_email.split("@", 1)[0]
            if existing:
                user_id = int(existing["user_id"])
                self._conn.execute(
                    """
                    UPDATE auth_otp_challenges
                    SET replaced_at = ?
                    WHERE user_id = ? AND purpose = 'signup_verify' AND consumed_at IS NULL AND replaced_at IS NULL
                    """,
                    (now, user_id),
                )
                self._conn.execute(
                    """
                    UPDATE users
                    SET display_name = ?,
                        password_salt = ?,
                        password_hash = ?
                    WHERE user_id = ? AND email_verified_at IS NULL
                    """,
                    (pending_display_name, password_salt, password_hash, user_id),
                )
            else:
                user_id = self._next_user_id_locked()
                self._conn.execute(
                    """
                    INSERT INTO users(user_id, email, display_name, password_salt, password_hash, created_at, last_login_at, email_verified_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        normalized_email,
                        pending_display_name,
                        password_salt,
                        password_hash,
                        now,
                        None,
                        None,
                    ),
                )
                self._ensure_shared_state_locked(user_id)
                self._ensure_user_profile_locked(user_id)

            challenge = self._create_auth_otp_challenge_locked(
                user_id=user_id,
                email=normalized_email,
                purpose="signup_verify",
                actor_kind=actor_kind,
                device_name=device_name,
                device_platform=device_platform,
                device_key=device_key,
                remember_me=remember_me,
                pending_password_salt=password_salt,
                pending_password_hash=password_hash,
                pending_display_name=pending_display_name,
            )
            self._conn.commit()
            self._secure_db_files()
            return challenge

    def begin_login_otp(
        self,
        *,
        email: str,
        password: str,
        actor_kind: str,
        device_name: Optional[str] = None,
        device_platform: Optional[str] = None,
        device_key: Optional[str] = None,
        remember_me: bool = False,
    ) -> Dict[str, Any]:
        normalized_email = _normalize_email(email)
        if actor_kind not in {"mobile", "desktop"}:
            raise ValueError("actor_kind must be mobile or desktop")
        if not normalized_email or len(normalized_email) > MAX_EMAIL_CHARS:
            raise ValueError("Invalid email or password")
        if len(password) > MAX_PASSWORD_CHARS:
            raise ValueError("Invalid email or password")

        with self._lock:
            self._cleanup_locked()
            user = self._conn.execute("SELECT * FROM users WHERE email = ?", (normalized_email,)).fetchone()
            if not user:
                pending_signup = self._pending_signup_challenge_for_email_locked(normalized_email)
                if pending_signup:
                    pending_salt = str(pending_signup["pending_password_salt"] or "")
                    pending_hash = str(pending_signup["pending_password_hash"] or "")
                    if pending_salt and pending_hash:
                        expected = _hash_password(password, pending_salt)
                        if hmac.compare_digest(expected, pending_hash):
                            raise ValueError("Finish account verification before signing in. Create the account again if the code was not delivered.")
                raise ValueError("Invalid email or password")
            expected = _hash_password(password, str(user["password_salt"] or ""))
            if not hmac.compare_digest(expected, str(user["password_hash"] or "")):
                self._raise_password_login_error_for_user_locked(int(user["user_id"]))
            if not user["email_verified_at"]:
                raise ValueError("Finish account verification before signing in. Create the account again if the code was not delivered.")
            challenge = self._create_auth_otp_challenge_locked(
                user_id=int(user["user_id"]),
                email=normalized_email,
                purpose="login_verify",
                actor_kind=actor_kind,
                device_name=device_name,
                device_platform=device_platform,
                device_key=device_key,
                remember_me=remember_me,
            )
            self._conn.commit()
            self._secure_db_files()
            return challenge

    def resend_auth_otp(self, *, challenge_id: str) -> Dict[str, Any]:
        clean_challenge_id = str(challenge_id or "").strip()
        if not clean_challenge_id:
            raise ValueError("Verification challenge is required")
        with self._lock:
            self._cleanup_locked()
            row = self._conn.execute("SELECT * FROM auth_otp_challenges WHERE challenge_id = ?", (clean_challenge_id,)).fetchone()
            if not row or row["consumed_at"] or row["replaced_at"]:
                raise ValueError("Verification challenge expired. Start again.")
            now = time.time()
            if float(row["expires_at"] or 0) < now:
                raise ValueError("Verification challenge expired. Start again.")
            if float(row["resend_available_at"] or 0) > now:
                wait_seconds = max(1, int(float(row["resend_available_at"]) - now))
                raise ValueError(f"Wait {wait_seconds} seconds before requesting another code.")
            challenge = self._create_auth_otp_challenge_locked(
                user_id=int(row["user_id"]),
                email=str(row["email"] or ""),
                purpose=str(row["purpose"] or "login_verify"),
                actor_kind=str(row["actor_kind"] or "mobile"),
                device_name=row["device_name"],
                device_platform=row["device_platform"],
                device_key=row["device_key"],
                remember_me=bool(row["remember_me"]),
                pending_password_salt=row["pending_password_salt"] if "pending_password_salt" in row.keys() else None,
                pending_password_hash=row["pending_password_hash"] if "pending_password_hash" in row.keys() else None,
                pending_display_name=row["pending_display_name"] if "pending_display_name" in row.keys() else None,
            )
            self._conn.commit()
            self._secure_db_files()
            return challenge

    def invalidate_auth_otp_challenge(self, *, challenge_id: str) -> bool:
        clean_challenge_id = str(challenge_id or "").strip()
        if not clean_challenge_id:
            return False
        with self._lock:
            row = self._conn.execute(
                "SELECT user_id, purpose FROM auth_otp_challenges WHERE challenge_id = ?",
                (clean_challenge_id,),
            ).fetchone()
            cursor = self._conn.execute(
                """
                UPDATE auth_otp_challenges
                SET replaced_at = ?,
                    pending_password_salt = NULL,
                    pending_password_hash = NULL
                WHERE challenge_id = ? AND consumed_at IS NULL AND replaced_at IS NULL
                """,
                (time.time(), clean_challenge_id),
            )
            if row and str(row["purpose"] or "") == "signup_verify":
                self._delete_unverified_signup_user_if_orphaned_locked(int(row["user_id"]))
            self._conn.commit()
            self._secure_db_files()
            return cursor.rowcount > 0

    def verify_auth_otp(self, *, challenge_id: str, code: str) -> Dict[str, Any]:
        clean_challenge_id = str(challenge_id or "").strip()
        clean_code = re.sub(r"\D+", "", str(code or ""))
        if not clean_challenge_id or len(clean_code) != 6:
            raise ValueError("Enter the 6-digit verification code.")
        with self._lock:
            self._cleanup_locked()
            row = self._conn.execute("SELECT * FROM auth_otp_challenges WHERE challenge_id = ?", (clean_challenge_id,)).fetchone()
            if not row or row["consumed_at"] or row["replaced_at"]:
                raise ValueError("Verification challenge expired. Start again.")
            now = time.time()
            if float(row["expires_at"] or 0) < now:
                raise ValueError("Verification challenge expired. Start again.")
            attempt_count = int(row["attempt_count"] or 0)
            max_attempts = int(row["max_attempts"] or AUTH_OTP_MAX_ATTEMPTS)
            if attempt_count >= max_attempts:
                raise ValueError("Too many incorrect verification attempts. Start again.")
            expected = str(row["code_hash"] or "")
            received = _hash_otp_code(clean_code, str(row["code_salt"] or ""))
            if not hmac.compare_digest(expected, received):
                attempt_count += 1
                remaining = max(0, max_attempts - attempt_count)
                if remaining <= 0:
                    self._conn.execute(
                        """
                        UPDATE auth_otp_challenges
                        SET attempt_count = ?,
                            replaced_at = ?,
                            pending_password_salt = NULL,
                            pending_password_hash = NULL
                        WHERE challenge_id = ?
                        """,
                        (attempt_count, now, clean_challenge_id),
                    )
                    if str(row["purpose"] or "") == "signup_verify":
                        self._delete_unverified_signup_user_if_orphaned_locked(int(row["user_id"]))
                    self._conn.commit()
                    raise ValueError("Too many incorrect verification attempts. Start again.")
                self._conn.execute(
                    "UPDATE auth_otp_challenges SET attempt_count = ? WHERE challenge_id = ?",
                    (attempt_count, clean_challenge_id),
                )
                self._conn.commit()
                raise ValueError(f"Incorrect verification code. {remaining} attempt{'s' if remaining != 1 else ''} left.")

            user_id = int(row["user_id"] or 0)
            if user_id <= 0:
                raise ValueError("Verification challenge is invalid.")
            user = self._conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not user:
                if str(row["purpose"] or "") != "signup_verify":
                    raise ValueError("Account no longer exists.")
                pending_salt = str((row["pending_password_salt"] if "pending_password_salt" in row.keys() else None) or "")
                pending_hash = str((row["pending_password_hash"] if "pending_password_hash" in row.keys() else None) or "")
                if not pending_salt or not pending_hash:
                    raise ValueError("Account no longer exists.")
                normalized_email = _normalize_email(str(row["email"] or ""))
                if not normalized_email:
                    raise ValueError("Verification challenge is invalid.")
                existing_email_user = self._conn.execute("SELECT * FROM users WHERE email = ?", (normalized_email,)).fetchone()
                if existing_email_user:
                    raise ValueError("An account with that email already exists")
                self._conn.execute(
                    """
                    INSERT INTO users(user_id, email, display_name, password_salt, password_hash, created_at, last_login_at, email_verified_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        normalized_email,
                        (str(row["pending_display_name"] if "pending_display_name" in row.keys() else "") or "").strip()
                        or normalized_email.split("@", 1)[0],
                        pending_salt,
                        pending_hash,
                        float(row["created_at"] or now),
                        None,
                        now,
                    ),
                )
                self._ensure_shared_state_locked(user_id)
                self._ensure_user_profile_locked(user_id)
                user = self._conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not user["email_verified_at"]:
                self._conn.execute("UPDATE users SET email_verified_at = ? WHERE user_id = ?", (now, user_id))
            self._conn.execute(
                """
                UPDATE auth_otp_challenges
                SET consumed_at = ?,
                    pending_password_salt = NULL,
                    pending_password_hash = NULL
                WHERE challenge_id = ?
                """,
                (now, clean_challenge_id),
            )
            result = self._create_remote_session_locked(
                user_id=user_id,
                actor_kind=str(row["actor_kind"] or "mobile"),
                device_name=row["device_name"],
                device_platform=row["device_platform"],
                device_key=row["device_key"],
                token_ttl_seconds=int(row["token_ttl_seconds"] or REMOTE_SHORT_SESSION_TTL_SECONDS),
            )
            result["remember_me"] = bool(row["remember_me"])
            self._conn.commit()
            self._secure_db_files()
            return result

    def register_user(self, *, email: str, password: str, display_name: Optional[str] = None) -> Dict[str, Any]:
        normalized_email = _normalize_email(email)
        if not normalized_email or len(normalized_email) > MAX_EMAIL_CHARS or "@" not in normalized_email:
            raise ValueError("A valid email is required")
        errors = _strong_password_errors(password, email=normalized_email, display_name=display_name)
        if errors:
            raise ValueError(" ".join(errors))

        with self._lock:
            self._cleanup_locked()
            existing = self._conn.execute("SELECT user_id FROM users WHERE email = ?", (normalized_email,)).fetchone()
            if existing:
                raise ValueError("An account with that email already exists")
            user_id = self._next_user_id_locked()
            now = time.time()
            salt = secrets.token_hex(16)
            self._conn.execute(
                """
                INSERT INTO users(user_id, email, display_name, password_salt, password_hash, created_at, last_login_at, email_verified_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    normalized_email,
                    (display_name or "").strip()[:MAX_DISPLAY_NAME_CHARS] or normalized_email.split("@", 1)[0],
                    salt,
                    _hash_password(password, salt),
                    now,
                    None,
                    now,
                ),
            )
            self._ensure_shared_state_locked(user_id)
            self._ensure_user_profile_locked(user_id)
            self._conn.commit()
            self._secure_db_files()
            user = self._conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return self._user_view(user)

    def login(
        self,
        *,
        email: str,
        password: str,
        actor_kind: str,
        device_name: Optional[str] = None,
        device_platform: Optional[str] = None,
        device_key: Optional[str] = None,
        token_ttl_seconds: int = REMOTE_SESSION_TTL_SECONDS,
    ) -> Dict[str, Any]:
        normalized_email = _normalize_email(email)
        if actor_kind not in {"mobile", "desktop"}:
            raise ValueError("actor_kind must be mobile or desktop")
        if not normalized_email or len(normalized_email) > MAX_EMAIL_CHARS:
            raise ValueError("Invalid email or password")
        if len(password) > MAX_PASSWORD_CHARS:
            raise ValueError("Invalid email or password")

        with self._lock:
            self._cleanup_locked()
            user = self._conn.execute("SELECT * FROM users WHERE email = ?", (normalized_email,)).fetchone()
            if not user:
                raise ValueError("Invalid email or password")
            expected = _hash_password(password, str(user["password_salt"] or ""))
            if not hmac.compare_digest(expected, str(user["password_hash"] or "")):
                self._raise_password_login_error_for_user_locked(int(user["user_id"]))
            if not user["email_verified_at"]:
                raise ValueError("Finish account verification before signing in. Create the account again if the code was not delivered.")

            user_id = int(user["user_id"])
            result = self._create_remote_session_locked(
                user_id=user_id,
                actor_kind=actor_kind,
                device_name=device_name,
                device_platform=device_platform,
                device_key=device_key,
                token_ttl_seconds=token_ttl_seconds,
            )
            self._conn.commit()
            self._secure_db_files()
            return result

    def create_oauth_login_request(
        self,
        *,
        provider: str,
        actor_kind: str,
        device_name: Optional[str] = None,
        device_platform: Optional[str] = None,
        device_key: Optional[str] = None,
        ttl_seconds: int = 300,
        remember_me: bool = False,
    ) -> Dict[str, Any]:
        normalized_provider = str(provider or "").strip().casefold()
        if normalized_provider not in {"google"}:
            raise ValueError("Unsupported OAuth provider")
        if actor_kind not in {"mobile", "desktop"}:
            raise ValueError("actor_kind must be mobile or desktop")
        request_id = f"oauth_{secrets.token_hex(12)}"
        poll_token = secrets.token_urlsafe(36)
        state = secrets.token_urlsafe(36)
        now = time.time()
        with self._lock:
            self._cleanup_locked()
            self._conn.execute(
                """
                INSERT INTO oauth_login_requests(
                    request_id, poll_token_hash, state_hash, provider, actor_kind, device_name, device_platform,
                    device_key, status, user_id, email, error, created_at, expires_at, remember_me, token_ttl_seconds,
                    completed_at, consumed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    _hash_token(poll_token),
                    _hash_token(state),
                    normalized_provider,
                    actor_kind,
                    (device_name or "").strip()[:MAX_DISPLAY_NAME_CHARS] or None,
                    (device_platform or "").strip()[:MAX_DEVICE_PLATFORM_CHARS] or None,
                    (device_key or "").strip()[:MAX_DEVICE_KEY_CHARS] or None,
                    "pending",
                    None,
                    None,
                    None,
                    now,
                    now + ttl_seconds,
                    1 if remember_me else 0,
                    self._token_ttl_for_remember_me(bool(remember_me)),
                    None,
                    None,
                ),
            )
            self._conn.commit()
            self._secure_db_files()
            return {
                "request_id": request_id,
                "poll_token": poll_token,
                "state": state,
                "expires_at": now + ttl_seconds,
            }

    def _find_or_create_oauth_user_locked(
        self,
        *,
        provider: str,
        subject: str,
        email: str,
        email_verified: bool,
        display_name: Optional[str],
        avatar_url: Optional[str],
    ) -> int:
        provider = str(provider or "").strip().casefold()
        subject = str(subject or "").strip()[:512]
        if not provider or not subject:
            raise ValueError("OAuth identity is invalid")
        normalized_email = _normalize_email(email)
        if not normalized_email or len(normalized_email) > MAX_EMAIL_CHARS or "@" not in normalized_email or not email_verified:
            raise ValueError("Google account email must be verified")

        identity = self._conn.execute(
            "SELECT * FROM oauth_identities WHERE provider = ? AND subject = ?",
            (provider, subject),
        ).fetchone()
        now = time.time()
        if identity:
            user_id = int(identity["user_id"])
            self._conn.execute(
                """
                UPDATE oauth_identities
                SET email = ?, email_verified = ?, display_name = ?, avatar_url = ?, last_login_at = ?
                WHERE provider = ? AND subject = ?
                """,
                (
                    normalized_email,
                    1 if email_verified else 0,
                    (display_name or "").strip()[:MAX_DISPLAY_NAME_CHARS] or None,
                    _safe_string(avatar_url, max_length=512),
                    now,
                    provider,
                    subject,
                ),
            )
            return user_id

        user = self._conn.execute("SELECT * FROM users WHERE email = ?", (normalized_email,)).fetchone()
        if user:
            user_id = int(user["user_id"])
            if email_verified and not user["email_verified_at"]:
                self._conn.execute("UPDATE users SET email_verified_at = ? WHERE user_id = ?", (now, user_id))
        else:
            user_id = self._next_user_id_locked()
            salt = secrets.token_hex(16)
            disabled_password = secrets.token_urlsafe(64)
            self._conn.execute(
                """
                INSERT INTO users(user_id, email, display_name, password_salt, password_hash, created_at, last_login_at, email_verified_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    normalized_email,
                    (display_name or "").strip()[:MAX_DISPLAY_NAME_CHARS] or normalized_email.split("@", 1)[0],
                    salt,
                    _hash_password(disabled_password, salt),
                    now,
                    None,
                    now,
                ),
            )
            self._ensure_shared_state_locked(user_id)
            self._ensure_user_profile_locked(user_id)

        self._conn.execute(
            """
                INSERT INTO oauth_identities(
                    provider, subject, user_id, email, email_verified, display_name, avatar_url, created_at, last_login_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
            (
                provider,
                subject,
                user_id,
                normalized_email,
                1 if email_verified else 0,
                (display_name or "").strip()[:MAX_DISPLAY_NAME_CHARS] or None,
                _safe_string(avatar_url, max_length=512),
                now,
                now,
            ),
        )
        return user_id

    def complete_oauth_login_request(
        self,
        *,
        provider: str,
        state: str,
        subject: str,
        email: str,
        email_verified: bool,
        display_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_provider = str(provider or "").strip().casefold()
        with self._lock:
            self._cleanup_locked()
            row = self._conn.execute(
                "SELECT * FROM oauth_login_requests WHERE state_hash = ? AND provider = ?",
                (_hash_token(state), normalized_provider),
            ).fetchone()
            if not row:
                raise KeyError("Unknown OAuth login request")
            now = time.time()
            if float(row["expires_at"] or 0) < now:
                self._conn.execute(
                    "UPDATE oauth_login_requests SET status = ?, error = ? WHERE request_id = ?",
                    ("expired", "Login request expired", row["request_id"]),
                )
                self._conn.commit()
                raise ValueError("Login request expired")
            if row["status"] == "complete":
                return {"request_id": row["request_id"], "status": "complete", "user_id": int(row["user_id"])}
            if row["status"] != "pending":
                raise ValueError(str(row["error"] or "Login request is no longer pending"))

            try:
                if not str(subject or "").strip():
                    raise ValueError("Google account subject is missing")
                user_id = self._find_or_create_oauth_user_locked(
                    provider=normalized_provider,
                    subject=str(subject or "").strip(),
                    email=_normalize_email(email),
                    email_verified=bool(email_verified),
                    display_name=(display_name or "").strip() or None,
                    avatar_url=(avatar_url or "").strip() or None,
                )
                self._conn.execute(
                    """
                    UPDATE oauth_login_requests
                    SET status = ?, user_id = ?, email = ?, error = ?, completed_at = ?
                    WHERE request_id = ?
                    """,
                    ("complete", user_id, _normalize_email(email), None, now, row["request_id"]),
                )
                self._conn.commit()
                self._secure_db_files()
                return {"request_id": row["request_id"], "status": "complete", "user_id": user_id}
            except Exception as exc:
                self._conn.execute(
                    "UPDATE oauth_login_requests SET status = ?, error = ?, completed_at = ? WHERE request_id = ?",
                    ("error", str(exc), now, row["request_id"]),
                )
                self._conn.commit()
                self._secure_db_files()
                raise

    def fail_oauth_login_request(self, *, provider: str, state: str, error: str) -> None:
        normalized_provider = str(provider or "").strip().casefold()
        with self._lock:
            self._conn.execute(
                """
                UPDATE oauth_login_requests
                SET status = ?, error = ?, completed_at = ?
                WHERE state_hash = ? AND provider = ? AND status = ?
                """,
                ("error", str(error or "OAuth login failed")[:500], time.time(), _hash_token(state), normalized_provider, "pending"),
            )
            self._conn.commit()
            self._secure_db_files()

    def get_oauth_login_request_status(self, *, provider: str, state: str) -> Optional[Dict[str, Any]]:
        normalized_provider = str(provider or "").strip().casefold()
        if not normalized_provider or not str(state or "").strip():
            return None
        with self._lock:
            self._cleanup_locked()
            row = self._conn.execute(
                "SELECT request_id, provider, actor_kind, status, error, expires_at, consumed_at FROM oauth_login_requests "
                "WHERE state_hash = ? AND provider = ?",
                (_hash_token(state), normalized_provider),
            ).fetchone()
            if not row:
                self._conn.commit()
                return None
            self._conn.commit()
            return {
                "request_id": str(row["request_id"] or ""),
                "provider": str(row["provider"] or ""),
                "actor_kind": str(row["actor_kind"] or ""),
                "status": str(row["status"] or "pending"),
                "error": row["error"],
                "expires_at": float(row["expires_at"] or 0),
                "consumed": bool(row["consumed_at"]),
            }

    def consume_oauth_login_request(
        self,
        *,
        request_id: str,
        poll_token: str,
        token_ttl_seconds: int = REMOTE_SESSION_TTL_SECONDS,
    ) -> Dict[str, Any]:
        with self._lock:
            self._cleanup_locked()
            row = self._conn.execute(
                "SELECT * FROM oauth_login_requests WHERE request_id = ?",
                (str(request_id or "").strip(),),
            ).fetchone()
            if not row:
                return {"status": "expired", "error": "Login request expired"}
            if not hmac.compare_digest(str(row["poll_token_hash"] or ""), _hash_token(poll_token or "")):
                raise ValueError("Invalid OAuth poll token")
            now = time.time()
            if float(row["expires_at"] or 0) < now:
                self._conn.execute(
                    "UPDATE oauth_login_requests SET status = ?, error = ? WHERE request_id = ?",
                    ("expired", "Login request expired", row["request_id"]),
                )
                self._conn.commit()
                return {"status": "expired", "error": "Login request expired"}
            status = str(row["status"] or "pending")
            if status != "complete":
                return {"status": status, "error": row["error"]}
            if row["consumed_at"]:
                return {"status": "expired", "error": "Login request already consumed"}
            user_id = int(row["user_id"] or 0)
            if user_id <= 0:
                return {"status": "error", "error": "OAuth login completed without an account"}
            result = self._create_remote_session_locked(
                user_id=user_id,
                actor_kind=str(row["actor_kind"] or "mobile"),
                device_name=row["device_name"],
                device_platform=row["device_platform"],
                device_key=row["device_key"],
                token_ttl_seconds=int(row["token_ttl_seconds"] or token_ttl_seconds),
            )
            self._conn.execute(
                "UPDATE oauth_login_requests SET consumed_at = ? WHERE request_id = ?",
                (now, row["request_id"]),
            )
            self._conn.commit()
            self._secure_db_files()
            result["status"] = "complete"
            result["remember_me"] = bool(row["remember_me"])
            return result
