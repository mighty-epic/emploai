from __future__ import annotations

from app_backend.fleet_policy import FLEET_PREVIEW_MODE

REMOTE_SHORT_SESSION_TTL_SECONDS = 60 * 60 * 12
REMOTE_REMEMBERED_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REMOTE_SESSION_TTL_SECONDS = REMOTE_REMEMBERED_SESSION_TTL_SECONDS
REMOTE_PAIRING_TTL_SECONDS = 60 * 10
FLEET_ENROLLMENT_TTL_SECONDS = 60 * 30

class RemoteControlStoreCoreMixin:
    def _connect(self) -> sqlite3.Connection:
        previous_umask: Optional[int] = None
        try:
            previous_umask = os.umask(0o077)
        except Exception:
            previous_umask = None
        try:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        finally:
            if previous_umask is not None:
                try:
                    os.umask(previous_umask)
                except Exception:
                    pass
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        self._secure_db_files()
        return conn

    def _secure_db_files(self) -> None:
        _secure_chmod(self.db_path, 0o600)
        _secure_chmod(self.db_path.with_name(f"{self.db_path.name}-wal"), 0o600)
        _secure_chmod(self.db_path.with_name(f"{self.db_path.name}-shm"), 0o600)
        _secure_chmod(self.root_path / SECRET_VAULT_KEY_FILENAME, 0o600)

    def _secret_vault_master_key(self) -> bytes:
        configured = _decode_secret_vault_key(os.getenv(SECRET_VAULT_KEY_ENV, ""))
        if configured:
            return configured
        key_path = self.root_path / SECRET_VAULT_KEY_FILENAME
        if key_path.exists():
            decoded = _decode_secret_vault_key(key_path.read_text(encoding="utf-8"))
            if decoded:
                _secure_chmod(key_path, 0o600)
                return decoded
        key = secrets.token_bytes(32)
        encoded = base64.urlsafe_b64encode(key).decode("ascii")
        previous_umask: Optional[int] = None
        try:
            previous_umask = os.umask(0o077)
        except Exception:
            previous_umask = None
        try:
            key_path.write_text(f"{encoded}\n", encoding="utf-8")
        finally:
            if previous_umask is not None:
                try:
                    os.umask(previous_umask)
                except Exception:
                    pass
        _secure_chmod(key_path, 0o600)
        return key

    def _user_secret_key(self, user_id: int) -> bytes:
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=f"emploai:user-secret:{int(user_id)}".encode("utf-8"),
            info=b"emploai-remote-user-secret-v1",
        ).derive(self._secret_vault_master_key())

    def _encrypt_user_secret(self, *, user_id: int, namespace: str, name: str, value: str) -> tuple[bytes, bytes]:
        nonce = secrets.token_bytes(12)
        aad = f"{int(user_id)}:{namespace}:{name}:{SECRET_VAULT_KEY_VERSION}".encode("utf-8")
        ciphertext = AESGCM(self._user_secret_key(int(user_id))).encrypt(nonce, str(value).encode("utf-8"), aad)
        return ciphertext, nonce

    def _decrypt_user_secret(self, *, user_id: int, namespace: str, name: str, ciphertext: bytes, nonce: bytes, key_version: str) -> str:
        aad = f"{int(user_id)}:{namespace}:{name}:{key_version}".encode("utf-8")
        plaintext = AESGCM(self._user_secret_key(int(user_id))).decrypt(nonce, ciphertext, aad)
        return plaintext.decode("utf-8")

    def _initialize(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_login_at REAL,
                    email_verified_at REAL
                );
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_secrets (
                    user_id INTEGER NOT NULL,
                    namespace TEXT NOT NULL,
                    name TEXT NOT NULL,
                    ciphertext BLOB NOT NULL,
                    nonce BLOB NOT NULL,
                    key_version TEXT NOT NULL,
                    redacted_value TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(user_id, namespace, name)
                );
                CREATE TABLE IF NOT EXISTS oauth_identities (
                    provider TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    email TEXT NOT NULL,
                    email_verified INTEGER NOT NULL DEFAULT 0,
                    display_name TEXT,
                    avatar_url TEXT,
                    created_at REAL NOT NULL,
                    last_login_at REAL,
                    PRIMARY KEY(provider, subject)
                );
                CREATE TABLE IF NOT EXISTS oauth_login_requests (
                    request_id TEXT PRIMARY KEY,
                    poll_token_hash TEXT NOT NULL UNIQUE,
                    state_hash TEXT NOT NULL UNIQUE,
                    provider TEXT NOT NULL,
                    actor_kind TEXT NOT NULL,
                    device_name TEXT,
                    device_platform TEXT,
                    device_key TEXT,
                    status TEXT NOT NULL,
                    user_id INTEGER,
                    email TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    remember_me INTEGER NOT NULL DEFAULT 0,
                    token_ttl_seconds INTEGER NOT NULL DEFAULT 43200,
                    completed_at REAL,
                    consumed_at REAL
                );
                CREATE TABLE IF NOT EXISTS auth_otp_challenges (
                    challenge_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    email TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    code_salt TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    pending_password_salt TEXT,
                    pending_password_hash TEXT,
                    pending_display_name TEXT,
                    actor_kind TEXT NOT NULL,
                    device_name TEXT,
                    device_platform TEXT,
                    device_key TEXT,
                    remember_me INTEGER NOT NULL DEFAULT 0,
                    token_ttl_seconds INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    resend_available_at REAL NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    consumed_at REAL,
                    replaced_at REAL
                );
                CREATE TABLE IF NOT EXISTS remote_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    actor_kind TEXT NOT NULL,
                    desktop_id TEXT,
                    mobile_id TEXT,
                    created_at REAL NOT NULL,
                    last_used_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked_at REAL
                );
                CREATE TABLE IF NOT EXISTS remote_desktop_commands (
                    command_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    desktop_id TEXT NOT NULL,
                    command_type TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    wants_reply INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    claimed_at REAL,
                    claimed_by_instance_id TEXT,
                    completed_at REAL
                );
                CREATE TABLE IF NOT EXISTS desktops (
                    desktop_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    device_key TEXT,
                    display_name TEXT,
                    device_platform TEXT,
                    status TEXT NOT NULL DEFAULT 'offline',
                    detail TEXT,
                    created_at REAL NOT NULL,
                    last_seen_at REAL,
                    last_heartbeat_at REAL,
                    paired_mobile_ids TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS mobiles (
                    mobile_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    device_name TEXT,
                    device_platform TEXT,
                    device_key TEXT,
                    paired_desktop_id TEXT,
                    created_at REAL NOT NULL,
                    last_used_at REAL
                );
                CREATE TABLE IF NOT EXISTS pairings (
                    pairing_id TEXT PRIMARY KEY,
                    pairing_token_hash TEXT NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL,
                    desktop_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    used_at REAL,
                    revoked_at REAL
                );
                CREATE TABLE IF NOT EXISTS shared_state (
                    user_id INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fleet_instances (
                    instance_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    desktop_id TEXT,
                    worker_id TEXT,
                    display_name TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    reset_at REAL
                );
                CREATE TABLE IF NOT EXISTS fleet_workers (
                    worker_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    machine_desktop_id TEXT,
                    instance_id TEXT,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'idle',
                    detail TEXT,
                    group_id TEXT,
                    active_task_id TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_seen_at REAL
                );
                CREATE TABLE IF NOT EXISTS fleet_groups (
                    group_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    display_name TEXT NOT NULL,
                    description TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fleet_enrollments (
                    enrollment_id TEXT PRIMARY KEY,
                    enrollment_token_hash TEXT NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL,
                    created_by_desktop_id TEXT,
                    display_name TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    used_at REAL,
                    revoked_at REAL
                );
                CREATE TABLE IF NOT EXISTS fleet_connection_permissions (
                    user_id INTEGER NOT NULL,
                    desktop_id TEXT NOT NULL,
                    permissions TEXT NOT NULL DEFAULT '{}',
                    capabilities TEXT NOT NULL DEFAULT '{}',
                    pending_request TEXT,
                    last_decision TEXT,
                    source TEXT,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(user_id, desktop_id)
                );
                CREATE TABLE IF NOT EXISTS fleet_permission_requests (
                    request_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    desktop_id TEXT NOT NULL,
                    requested TEXT NOT NULL DEFAULT '{}',
                    reason TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at REAL NOT NULL,
                    decided_at REAL
                );
                CREATE TABLE IF NOT EXISTS fleet_delegations (
                    delegation_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    desktop_id TEXT NOT NULL,
                    target_kind TEXT NOT NULL,
                    target_selector TEXT,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    report TEXT NOT NULL DEFAULT '{}',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    started_at REAL,
                    completed_at REAL,
                    canceled_at REAL
                );
                CREATE TABLE IF NOT EXISTS fleet_upstream_requests (
                    request_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    desktop_id TEXT NOT NULL,
                    identity_id TEXT,
                    identity_label TEXT,
                    task_id TEXT,
                    request_kind TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    response TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    decided_at REAL
                );
                CREATE TABLE IF NOT EXISTS fleet_tasks (
                    task_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    worker_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    source TEXT,
                    queue_position INTEGER NOT NULL DEFAULT 0,
                    report_id TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    started_at REAL,
                    completed_at REAL,
                    canceled_at REAL
                );
                CREATE TABLE IF NOT EXISTS fleet_reports (
                    report_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    worker_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    evidence TEXT NOT NULL DEFAULT '[]',
                    artifacts TEXT NOT NULL DEFAULT '[]',
                    blockers TEXT NOT NULL DEFAULT '[]',
                    confidence TEXT,
                    next_suggested_action TEXT,
                    raw TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fleet_workspace_bindings (
                    binding_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    workspace_id TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    label TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(user_id, workspace_id, machine_id)
                );
                CREATE TABLE IF NOT EXISTS fleet_tool_grants (
                    grant_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    target_kind TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    tool_pack_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    task_id TEXT,
                    requested_turns INTEGER NOT NULL DEFAULT 1,
                    approved_turns INTEGER,
                    remaining_turns INTEGER,
                    requested_by TEXT,
                    approved_by TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL
                );
                CREATE TABLE IF NOT EXISTS fleet_locks (
                    lock_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    resource_kind TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    owner_kind TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    task_id TEXT,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(user_id, resource_kind, resource_id)
                );
                CREATE TABLE IF NOT EXISTS fleet_audit_events (
                    event_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_kind TEXT,
                    actor_id TEXT,
                    target_kind TEXT,
                    target_id TEXT,
                    task_id TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS automations (
                    automation_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    schedule TEXT,
                    schedule_mode TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'active',
                    target_kind TEXT NOT NULL DEFAULT 'active_identity',
                    target_identity_id TEXT,
                    target_group_id TEXT,
                    target_chat_id TEXT,
                    chat_target TEXT NOT NULL DEFAULT 'existing_or_new',
                    permission_mode TEXT,
                    tool_packs TEXT NOT NULL DEFAULT '[]',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    next_run_at REAL,
                    last_run_at REAL,
                    run_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    one_time INTEGER NOT NULL DEFAULT 0,
                    requires_confirmation INTEGER NOT NULL DEFAULT 0,
                    confirmation_status TEXT,
                    confirmation_expires_at REAL,
                    PRIMARY KEY(user_id, automation_id)
                );
                CREATE TABLE IF NOT EXISTS automation_events (
                    event_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    automation_id TEXT,
                    event_type TEXT NOT NULL,
                    event_source TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT,
                    importance TEXT NOT NULL DEFAULT 'normal',
                    target_identity_id TEXT,
                    target_chat_id TEXT,
                    dedupe_key TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    scheduled_for REAL,
                    acknowledged_at REAL,
                    UNIQUE(user_id, dedupe_key)
                );
                CREATE TABLE IF NOT EXISTS automation_event_runs (
                    event_run_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    event_id TEXT,
                    automation_id TEXT,
                    status TEXT NOT NULL,
                    target_identity_id TEXT,
                    target_chat_id TEXT,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    next_attempt_at REAL,
                    started_at REAL,
                    completed_at REAL,
                    error TEXT,
                    result TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS process_waits (
                    process_wait_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    session_id TEXT,
                    command_id TEXT NOT NULL,
                    pid INTEGER,
                    command TEXT,
                    cwd TEXT,
                    shell TEXT,
                    status TEXT NOT NULL,
                    resume_policy TEXT,
                    persistent INTEGER NOT NULL DEFAULT 0,
                    ready_patterns TEXT NOT NULL DEFAULT '[]',
                    meaningful_output_patterns TEXT NOT NULL DEFAULT '[]',
                    failure_patterns TEXT NOT NULL DEFAULT '[]',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    started_at REAL NOT NULL,
                    last_event_at REAL,
                    completed_at REAL,
                    UNIQUE(user_id, command_id)
                );
                CREATE TABLE IF NOT EXISTS planner_contracts (
                    contract_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    session_id TEXT,
                    turn_id TEXT,
                    status TEXT NOT NULL,
                    action TEXT,
                    contract TEXT NOT NULL DEFAULT '{}',
                    corrections TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    injected_at REAL,
                    UNIQUE(user_id, session_id, turn_id)
                );
                CREATE TABLE IF NOT EXISTS recovery_archive (
                    archive_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    object_kind TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    display_name TEXT,
                    status TEXT NOT NULL DEFAULT 'archived',
                    payload TEXT NOT NULL DEFAULT '{}',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    archived_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    restored_at REAL,
                    purged_at REAL
                );
                CREATE TABLE IF NOT EXISTS pending_confirmations (
                    confirmation_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    action_kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    risk_tier TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    origin_surface TEXT,
                    origin_identity_id TEXT,
                    origin_chat_id TEXT,
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    decided_at REAL,
                    decided_by_surface TEXT,
                    decided_by_actor TEXT
                );
                CREATE TABLE IF NOT EXISTS automation_loop_guards (
                    user_id INTEGER NOT NULL,
                    guard_key TEXT NOT NULL,
                    window_start REAL NOT NULL,
                    event_count INTEGER NOT NULL DEFAULT 0,
                    last_failure_at REAL,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(user_id, guard_key)
                );
                CREATE INDEX IF NOT EXISTS idx_remote_sessions_user ON remote_sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_remote_desktop_commands_pending ON remote_desktop_commands(user_id, desktop_id, status, expires_at, created_at);
                CREATE INDEX IF NOT EXISTS idx_desktops_user ON desktops(user_id);
                CREATE INDEX IF NOT EXISTS idx_mobiles_user ON mobiles(user_id);
                CREATE INDEX IF NOT EXISTS idx_pairings_user ON pairings(user_id);
                CREATE INDEX IF NOT EXISTS idx_oauth_identities_user ON oauth_identities(user_id);
                CREATE INDEX IF NOT EXISTS idx_oauth_login_requests_expires ON oauth_login_requests(expires_at);
                CREATE INDEX IF NOT EXISTS idx_auth_otp_challenges_user ON auth_otp_challenges(user_id, purpose, expires_at);
                CREATE INDEX IF NOT EXISTS idx_auth_otp_challenges_email ON auth_otp_challenges(email, purpose, created_at);
                CREATE INDEX IF NOT EXISTS idx_user_secrets_user ON user_secrets(user_id, namespace);
                CREATE INDEX IF NOT EXISTS idx_fleet_instances_user ON fleet_instances(user_id, role);
                CREATE INDEX IF NOT EXISTS idx_fleet_workers_user ON fleet_workers(user_id, status);
                CREATE INDEX IF NOT EXISTS idx_fleet_tasks_worker ON fleet_tasks(user_id, worker_id, status, queue_position);
                CREATE INDEX IF NOT EXISTS idx_fleet_reports_worker ON fleet_reports(user_id, worker_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_fleet_delegations_desktop ON fleet_delegations(user_id, desktop_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_fleet_permission_requests_desktop ON fleet_permission_requests(user_id, desktop_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_fleet_upstream_requests_desktop ON fleet_upstream_requests(user_id, desktop_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_fleet_audit_user ON fleet_audit_events(user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_automations_user ON automations(user_id, enabled, next_run_at);
                CREATE INDEX IF NOT EXISTS idx_automation_events_user ON automation_events(user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_automation_event_runs_user ON automation_event_runs(user_id, status, created_at);
                CREATE INDEX IF NOT EXISTS idx_process_waits_user ON process_waits(user_id, status, last_event_at);
                CREATE INDEX IF NOT EXISTS idx_planner_contracts_user ON planner_contracts(user_id, session_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_recovery_archive_user ON recovery_archive(user_id, status, archived_at);
                CREATE INDEX IF NOT EXISTS idx_pending_confirmations_user ON pending_confirmations(user_id, status, expires_at);
                CREATE INDEX IF NOT EXISTS idx_automation_loop_guards_user ON automation_loop_guards(user_id, updated_at);
                """
            )
            existing_user_columns = {
                str(row["name"])
                for row in self._conn.execute("PRAGMA table_info(users)").fetchall()
            }
            if "email_verified_at" not in existing_user_columns:
                self._conn.execute("ALTER TABLE users ADD COLUMN email_verified_at REAL")
            existing_otp_columns = {
                str(row["name"])
                for row in self._conn.execute("PRAGMA table_info(auth_otp_challenges)").fetchall()
            }
            if "pending_password_salt" not in existing_otp_columns:
                self._conn.execute("ALTER TABLE auth_otp_challenges ADD COLUMN pending_password_salt TEXT")
            if "pending_password_hash" not in existing_otp_columns:
                self._conn.execute("ALTER TABLE auth_otp_challenges ADD COLUMN pending_password_hash TEXT")
            if "pending_display_name" not in existing_otp_columns:
                self._conn.execute("ALTER TABLE auth_otp_challenges ADD COLUMN pending_display_name TEXT")
            existing_oauth_request_columns = {
                str(row["name"])
                for row in self._conn.execute("PRAGMA table_info(oauth_login_requests)").fetchall()
            }
            if "remember_me" not in existing_oauth_request_columns:
                self._conn.execute("ALTER TABLE oauth_login_requests ADD COLUMN remember_me INTEGER NOT NULL DEFAULT 0")
            if "token_ttl_seconds" not in existing_oauth_request_columns:
                self._conn.execute(
                    "ALTER TABLE oauth_login_requests ADD COLUMN token_ttl_seconds INTEGER NOT NULL DEFAULT 43200"
                )
            existing_fleet_permission_columns = {
                str(row["name"])
                for row in self._conn.execute("PRAGMA table_info(fleet_connection_permissions)").fetchall()
            }
            if "capabilities" not in existing_fleet_permission_columns:
                self._conn.execute(
                    "ALTER TABLE fleet_connection_permissions ADD COLUMN capabilities TEXT NOT NULL DEFAULT '{}'"
                )
            existing_upstream_request_columns = {
                str(row["name"])
                for row in self._conn.execute("PRAGMA table_info(fleet_upstream_requests)").fetchall()
            }
            if "task_id" not in existing_upstream_request_columns:
                self._conn.execute("ALTER TABLE fleet_upstream_requests ADD COLUMN task_id TEXT")
            self._conn.commit()
            if self._meta_get("schema_version") is None:
                self._migrate_json_store_if_needed()
                self._meta_set("schema_version", str(SCHEMA_VERSION))
            self._cleanup_locked()
            self._conn.commit()
            self._secure_db_files()

    def _meta_get(self, key: str) -> Optional[str]:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def _meta_set(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def _migrate_json_store_if_needed(self) -> None:
        if not self.file_path.exists():
            return
        try:
            payload = json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return

        for raw_user in dict(payload.get("users") or {}).values():
            if not isinstance(raw_user, dict):
                continue
            user_id = int(raw_user.get("user_id") or 0)
            if user_id <= 0:
                continue
            email = str(raw_user.get("email") or "").strip().casefold()
            if not email:
                continue
            self._conn.execute(
                """
                INSERT OR IGNORE INTO users(
                    user_id, email, display_name, password_salt, password_hash, created_at, last_login_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    email,
                    str(raw_user.get("display_name") or "").strip() or email.split("@", 1)[0],
                    str(raw_user.get("password_salt") or ""),
                    str(raw_user.get("password_hash") or ""),
                    float(raw_user.get("created_at") or time.time()),
                    raw_user.get("last_login_at"),
                ),
            )

        for token_hash, raw_session in dict(payload.get("remote_sessions") or {}).items():
            if not isinstance(raw_session, dict):
                continue
            safe_hash = str(token_hash or "").strip()
            if len(safe_hash) != 64:
                token_value = str(raw_session.get("token_value") or "").strip()
                safe_hash = _hash_token(token_value) if token_value else ""
            if not safe_hash:
                continue
            self._conn.execute(
                """
                INSERT OR IGNORE INTO remote_sessions(
                    token_hash, user_id, actor_kind, desktop_id, mobile_id, created_at, last_used_at, expires_at, revoked_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe_hash,
                    int(raw_session.get("user_id") or 0),
                    str(raw_session.get("actor_kind") or ""),
                    raw_session.get("desktop_id"),
                    raw_session.get("mobile_id"),
                    float(raw_session.get("created_at") or time.time()),
                    float(raw_session.get("last_used_at") or time.time()),
                    float(raw_session.get("expires_at") or time.time()),
                    raw_session.get("revoked_at"),
                ),
            )

        for raw_desktop in dict(payload.get("desktops") or {}).values():
            if not isinstance(raw_desktop, dict):
                continue
            desktop_id = str(raw_desktop.get("desktop_id") or "").strip()
            if not desktop_id:
                continue
            self._conn.execute(
                """
                INSERT OR IGNORE INTO desktops(
                    desktop_id, user_id, device_key, display_name, device_platform, status, detail,
                    created_at, last_seen_at, last_heartbeat_at, paired_mobile_ids
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    desktop_id,
                    int(raw_desktop.get("user_id") or 0),
                    raw_desktop.get("device_key"),
                    raw_desktop.get("display_name"),
                    raw_desktop.get("device_platform"),
                    str(raw_desktop.get("status") or "offline"),
                    raw_desktop.get("detail"),
                    float(raw_desktop.get("created_at") or time.time()),
                    raw_desktop.get("last_seen_at"),
                    raw_desktop.get("last_heartbeat_at"),
                    _json_dumps(list(raw_desktop.get("paired_mobile_ids") or [])),
                ),
            )

        for raw_mobile in dict(payload.get("mobiles") or {}).values():
            if not isinstance(raw_mobile, dict):
                continue
            mobile_id = str(raw_mobile.get("mobile_id") or "").strip()
            if not mobile_id:
                continue
            self._conn.execute(
                """
                INSERT OR IGNORE INTO mobiles(
                    mobile_id, user_id, device_name, device_platform, device_key, paired_desktop_id, created_at, last_used_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mobile_id,
                    int(raw_mobile.get("user_id") or 0),
                    raw_mobile.get("device_name"),
                    raw_mobile.get("device_platform"),
                    raw_mobile.get("device_key"),
                    raw_mobile.get("paired_desktop_id"),
                    float(raw_mobile.get("created_at") or time.time()),
                    raw_mobile.get("last_used_at"),
                ),
            )

        for raw_pairing in dict(payload.get("pairings") or {}).values():
            if not isinstance(raw_pairing, dict):
                continue
            pairing_id = str(raw_pairing.get("pairing_id") or "").strip()
            pairing_token = str(raw_pairing.get("pairing_token") or "").strip()
            if not pairing_id or not pairing_token:
                continue
            self._conn.execute(
                """
                INSERT OR IGNORE INTO pairings(
                    pairing_id, pairing_token_hash, user_id, desktop_id, created_at, expires_at, used_at, revoked_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pairing_id,
                    _hash_token(pairing_token),
                    int(raw_pairing.get("user_id") or 0),
                    str(raw_pairing.get("desktop_id") or ""),
                    float(raw_pairing.get("created_at") or time.time()),
                    float(raw_pairing.get("expires_at") or time.time()),
                    raw_pairing.get("used_at"),
                    raw_pairing.get("revoked_at"),
                ),
            )

        for user_key, raw_state in dict(payload.get("shared_state") or {}).items():
            if not isinstance(raw_state, dict):
                continue
            try:
                user_id = int(raw_state.get("user_id") or user_key)
            except Exception:
                continue
            raw_state.setdefault("sidebar_state", _empty_sidebar_state())
            self._conn.execute(
                "INSERT OR REPLACE INTO shared_state(user_id, payload) VALUES(?, ?)",
                (user_id, _json_dumps(raw_state)),
            )

        for row in self._conn.execute("SELECT user_id FROM users").fetchall():
            self._ensure_user_profile_locked(int(row["user_id"]))

        self._meta_set("json_migrated_at", str(time.time()))

    def _cleanup_locked(self) -> None:
        now = time.time()
        self._conn.execute(
            "DELETE FROM pairings WHERE revoked_at IS NOT NULL OR used_at IS NOT NULL OR (expires_at > 0 AND expires_at < ?)",
            (now,),
        )
        self._conn.execute(
            "DELETE FROM remote_sessions WHERE revoked_at IS NOT NULL OR (expires_at > 0 AND expires_at < ?)",
            (now,),
        )
        self._conn.execute(
            """
            UPDATE remote_desktop_commands
            SET status = 'expired', completed_at = ?, error = 'Remote desktop command expired'
            WHERE status IN ('pending', 'claimed') AND expires_at > 0 AND expires_at < ?
            """,
            (now, now),
        )
        self._conn.execute(
            """
            DELETE FROM remote_desktop_commands
            WHERE status IN ('completed', 'failed', 'expired') AND completed_at IS NOT NULL AND completed_at < ?
            """,
            (now - 600,),
        )
        self._conn.execute(
            """
            UPDATE remote_desktop_commands
            SET status = 'pending', claimed_at = NULL, claimed_by_instance_id = NULL
            WHERE status = 'claimed' AND claimed_at IS NOT NULL AND claimed_at < ? AND completed_at IS NULL
            """,
            (now - 30,),
        )
        self._conn.execute(
            "DELETE FROM oauth_login_requests WHERE consumed_at IS NOT NULL OR (expires_at > 0 AND expires_at < ?)",
            (now,),
        )
        orphaned_signup_user_ids = [
            int(row["user_id"])
            for row in self._conn.execute(
                """
                SELECT DISTINCT user_id
                FROM auth_otp_challenges
                WHERE purpose = 'signup_verify'
                  AND consumed_at IS NULL
                  AND (replaced_at IS NOT NULL OR (expires_at > 0 AND expires_at < ?))
                """,
                (now,),
            ).fetchall()
        ]
        self._conn.execute(
            "DELETE FROM auth_otp_challenges WHERE consumed_at IS NOT NULL OR replaced_at IS NOT NULL OR (expires_at > 0 AND expires_at < ?)",
            (now,),
        )
        for user_id in orphaned_signup_user_ids:
            self._delete_unverified_signup_user_if_orphaned_locked(user_id)
        self._conn.execute(
            "DELETE FROM fleet_locks WHERE expires_at > 0 AND expires_at < ?",
            (now,),
        )
