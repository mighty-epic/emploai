const UPDATE_STASH_PREFIX = 'EmploAI automatic update backup';

function parseGitStatusOutput(output) {
  return String(output || '')
    .split(/\r?\n/)
    .filter((line) => line.length >= 3)
    .map((line) => ({
      code: line.slice(0, 2),
      path: line.slice(3).trim(),
    }))
    .filter((entry) => entry.path);
}

function gitUpdateSafetyState({ updateAvailable, dirty, diverged, pullTarget }) {
  const blocked = Boolean(updateAvailable && (diverged || !pullTarget));
  return {
    blocked,
    requiresManualUpdate: Boolean(updateAvailable && dirty && !blocked),
  };
}

function createGitUpdateServices({ runGit, now = () => new Date() }) {
  if (typeof runGit !== 'function') {
    throw new Error('runGit is required');
  }

  async function getDirtyState() {
    try {
      const output = await runGit(
        ['status', '--porcelain', '--untracked-files=all'],
        { maxBuffer: 2 * 1024 * 1024 },
      );
      const entries = parseGitStatusOutput(output);
      return {
        dirty: entries.length > 0,
        count: entries.length,
        entries,
      };
    } catch (_error) {
      return {
        dirty: false,
        count: 0,
        entries: [],
      };
    }
  }

  async function preserveLocalChanges(changeCount) {
    const count = Math.max(0, Number.parseInt(String(changeCount || 0), 10) || 0);
    if (!count) {
      return null;
    }
    const timestamp = now().toISOString().replace(/[:.]/g, '-');
    const label = `${UPDATE_STASH_PREFIX} ${timestamp} (${count} change${count === 1 ? '' : 's'})`;
    const output = await runGit(
      ['stash', 'push', '--include-untracked', '--message', label],
      { timeoutMs: 2 * 60 * 1000, maxBuffer: 2 * 1024 * 1024 },
    );
    if (/no local changes to save/i.test(String(output || ''))) {
      return null;
    }
    const stashCommit = await runGit(['rev-parse', '--verify', 'refs/stash']);
    if (!stashCommit) {
      throw new Error('Local project changes could not be backed up safely.');
    }
    return {
      count,
      label,
      stashCommit,
    };
  }

  async function restoreLocalChanges(backup) {
    if (!backup?.stashCommit) {
      return false;
    }
    const currentStash = await runGit(['rev-parse', '--verify', 'refs/stash']);
    if (currentStash !== backup.stashCommit) {
      throw new Error('The update backup is no longer the newest Git stash.');
    }
    await runGit(
      ['stash', 'pop', '--index'],
      { timeoutMs: 2 * 60 * 1000, maxBuffer: 2 * 1024 * 1024 },
    );
    return true;
  }

  return {
    getDirtyState,
    preserveLocalChanges,
    restoreLocalChanges,
  };
}

module.exports = {
  UPDATE_STASH_PREFIX,
  createGitUpdateServices,
  gitUpdateSafetyState,
  parseGitStatusOutput,
};
