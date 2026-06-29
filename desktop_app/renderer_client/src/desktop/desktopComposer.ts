export function getCommandSuggestionQuery(value: string) {
  const trimmedStart = value.trimStart();
  if (!trimmedStart.startsWith('/')) {
    return null;
  }

  const commandText = trimmedStart.slice(1);
  if (commandText.includes('\n') || /\s/.test(commandText)) {
    return null;
  }

  return commandText.toLowerCase();
}

export function parseComposerSlashCommand(value: string) {
  const trimmed = value.trim();
  if (!trimmed.startsWith('/')) {
    return null;
  }

  const body = trimmed.slice(1);
  const firstSpace = body.search(/\s/);
  const name = (firstSpace >= 0 ? body.slice(0, firstSpace) : body).trim().toLowerCase();
  const rawArgs = firstSpace >= 0 ? body.slice(firstSpace + 1).trim() : '';
  if (!name) {
    return null;
  }
  return { name, rawArgs };
}
