# Desktop App To-Test Checklist

This checklist is for testing the desktop app from the repo build, not the packaged MSI. Use throwaway accounts and chats when a test asks you to delete, restore, sign out, or kill a backend process.

## Before Testing

Prepare these accounts and states if possible:

- Google account with a saved provider API key.
- Google account with no provider API key.
- Email/password account with no provider API key.
- Email address that is already registered through Google sign-in.
- Second account for account-switching tests.
- One chat with normal text messages.
- One chat with tool calls.
- One chat with attachments.
- Local backend running from the repo, with a terminal you can stop and restart.

For each test, record:

- Status: Not run, Pass, or Fail.
- App commit/build:
- Account used:
- Notes:
- Screenshot or log path:

## Account And Startup

### A01 Signup OTP enforcement

Steps:
1. Open the desktop app and choose email signup.
2. Enter a new email, password, and any required profile fields.
3. Press Create and wait for the OTP screen.
4. Do not enter an OTP. Go back to sign in and try signing in with the same credentials.

Expected:
- The account is not usable until a valid OTP is entered.
- Sign-in before OTP verification is rejected with a clear message.

Watch for:
- No OTP email/message arrives.
- The account signs in successfully without OTP verification.
- The account is created before OTP is confirmed.

### A02 Google account with saved API key skips setup

Steps:
1. Sign out completely.
2. Sign in with a Google account that already has a saved OpenAI/provider API key.
3. Watch the first few seconds after login carefully.

Expected:
- The app checks key state before showing setup.
- The finish/setup screen never appears, even briefly.
- The user lands directly in the main app.

Watch for:
- Setup flashes for one or two seconds and then disappears.
- The user has to open setup and press Save even though a key already exists.

### A03 Email signup with Google-registered email

Steps:
1. Use an email address that already has an account through Google sign-in.
2. Open email signup.
3. Try to create a password account with that same email.

Expected:
- The app does not create a duplicate account.
- If password linking is supported, the app clearly says it is adding/linking email credentials to the existing account and requires verification.
- If password linking is not supported from signup, signup is blocked and the user is told to use Google sign-in.

Watch for:
- A duplicate account is created.
- The message implies the email is available.
- Password access is added without verification.
- The app moves to OTP for a brand-new account that should not exist.

### A04 Email and Google sign-in resolve to same account

Steps:
1. Sign in with Google using an email address that also has email/password access.
2. Save a harmless account-specific value, such as a test provider API key.
3. Sign out.
4. Sign in with email/password using the same email.
5. Confirm the same saved value appears.
6. Repeat in the opposite direction if possible: save while signed in with email/password, then verify through Google sign-in.

Expected:
- If the identities are linked, both sign-in methods land in the same account.
- Saved API keys, chats, and account-scoped data are shared between both sign-in methods.
- If email/password access is not configured, the app prompts the user to use Google or start an explicit password-linking flow.

Watch for:
- Email/password signs into a separate account.
- Saved API key, chats, or settings are missing when switching methods.
- Any password works without a real password credential.
- The app silently creates or attaches an identity without explaining it.

### A05 Google sign-in cancel or closed browser

Steps:
1. Start Google sign-in.
2. Close the browser window or cancel the OAuth flow before completion.
3. Return to the app.

Expected:
- The app unlocks quickly.
- User sees a clear cancelled sign-in message or returns to the sign-in screen.

Watch for:
- Spinner remains forever.
- Buttons stay disabled.
- User must restart the desktop app.

### A06 Chat sidebar loader while chats load

Steps:
1. Sign into an account with several saved chats.
2. Immediately watch the sidebar/chat list area.
3. Repeat with slow network or after restarting the backend if possible.

Expected:
- A visible loading indicator appears where chats will load.
- Empty-state messaging is not shown until the app knows there are no chats.

Watch for:
- Sidebar looks empty for several seconds.
- User can mistake loading for lost chats.
- Empty folders appear before sessions finish loading.

### A07 Old account data clears immediately on account switch

Steps:
1. Sign into account A and open Setup, Fleet, Recovery, remote secrets, and account-specific panels.
2. Sign out.
3. Sign into account B.
4. Quickly check those same panels before refresh completes.

Expected:
- Account A data clears immediately on sign out or before account B UI renders.
- Account B only shows account B data or loading placeholders.

Watch for:
- Old secrets, fleet devices, recovery items, statuses, or chats flash on screen.
- Account A state remains visible during refresh failures.

### A08 Fleet identities after account switch

Steps:
1. Sign into account A.
2. Open Fleet and wait for manager identities/devices to appear.
3. Sign out.
4. Sign into account B.
5. Immediately open Fleet.

Expected:
- No manager identity from account A appears for account B.
- Fleet either shows account B identities or a loading/empty state.

Watch for:
- Duplicate manager identities.
- Previous account manager lingering during refresh.
- Old manager reappears after a failed refresh.

### A09 Expired or revoked cloud login

Steps:
1. Sign in normally.
2. Revoke/expire the cloud session if possible, or simulate by clearing server token/session state.
3. Restart the desktop app.
4. Try to open chats, setup, fleet, and cloud-backed settings.

Expected:
- The app detects the invalid cloud session and asks the user to sign in again.
- Local-only functionality remains clearly separated from cloud-backed functionality.

Watch for:
- App appears signed in but cloud requests silently fail.
- Account-specific data from a stale session remains visible.
- Repeated background error loops.

### A10 Local startup during cloud/account outage

Steps:
1. Start the desktop app from the repo.
2. Make the cloud backend unavailable or disconnect internet.
3. Observe startup and local app availability.

Expected:
- Local desktop UI starts.
- Cloud/account-dependent panels show offline or retry states.

Watch for:
- Entire desktop app blocks on cloud/account calls.
- Blank screen or endless startup spinner.

### A11 Cloud chat backup preference

Steps:
1. Find the setting that controls whether chats are backed up to cloud.
2. Turn cloud backup on.
3. Create a chat, send messages, sign out, and sign back in on the same account.
4. Turn cloud backup off.
5. Create another chat, sign out, and sign back in.

Expected:
- With backup on, chats are saved locally and backed up to cloud.
- With backup off, the app clearly states cloud recovery is not guaranteed.
- The setting is understandable before data loss can happen.

Watch for:
- No way to choose cloud backup behavior.
- Chats disappear despite backup being on.
- Backup off still uploads everything without user choice.

### A12 Local chats refound after reconnecting to same account

Steps:
1. Sign into an account and create a chat.
2. Sign out.
3. Continue using the app locally if supported, or restart the app.
4. Sign back into the same account.

Expected:
- Local chats belonging to that account are refound and shown.
- If cloud backup is off, local account-owned chats still reattach locally.

Watch for:
- Previously created chats disappear permanently.
- App treats reconnect as a new empty account.
- Chats attach to the wrong account.

## Setup And Secrets

### S01 Saved API key honored by Jarvis and realtime voice

Steps:
1. Sign into an account with a saved OpenAI/provider API key.
2. Confirm the key appears as saved in Settings/Setup.
3. Go to Jarvis and start realtime voice or hold-to-talk.

Expected:
- Voice features recognize the saved key.
- No false "OPENAI_API_KEY is not configured" message appears.

Watch for:
- Jarvis says no API key even though Settings has one.
- Voice uses only environment variables and ignores saved/cloud keys.

### S02 Invalid provider key blocked

Steps:
1. Open Setup/Settings.
2. Enter an obviously invalid provider API key.
3. Save and try sending a chat message or starting Jarvis voice.

Expected:
- Setup blocks the invalid key or clearly marks it invalid before use.
- Chat/voice does not enter a long failing run.

Watch for:
- Invalid key saves as if valid.
- First use fails with confusing backend errors.

### S03 Replace saved provider key

Steps:
1. Save a valid provider API key.
2. Return to Setup.
3. Replace it with another key.
4. Save and use chat/voice.

Expected:
- Replacement is straightforward.
- The app uses the new key after save.

Watch for:
- User must remove the old key first without being told.
- Old key keeps being used.
- UI shows saved but backend still uses stale key.

### S04 Apply Saved Keys behavior

Steps:
1. Sign into an account with remote/cloud-stored provider keys.
2. Open Setup.
3. Press Apply Saved Keys.
4. Send a chat message and start Jarvis voice.

Expected:
- Saved keys are applied to the active local runtime.
- If any key cannot be applied, the app explains which one and why.

Watch for:
- Button appears successful but nothing changes.
- Chat and voice disagree about key availability.

### S05 Setup unsaved changes warning

Steps:
1. Open Setup.
2. Edit an API key or important setting.
3. Close Setup or switch tabs without saving.

Expected:
- User gets a clear unsaved changes warning.
- User can choose stay/discard/save.

Watch for:
- Unsaved edits vanish silently.
- UI implies changes were saved when they were not.

### S06 Numeric setup fields validation

Steps:
1. Open Setup fields that accept numeric values such as timeout, limits, or port-like settings.
2. Enter malformed values such as letters, negative numbers, very large numbers, or decimals where not supported.
3. Save.

Expected:
- Invalid values are rejected with field-level messages.
- Existing valid settings are preserved.

Watch for:
- Invalid settings save.
- Backend breaks on next run.
- Field resets silently without explanation.

### S07 Setup copy buttons feedback

Steps:
1. Open Setup.
2. Use copy buttons for pairing codes, IDs, URLs, or tokens where available.

Expected:
- Button gives immediate copied feedback.
- Failed copy gives a clear failure message.

Watch for:
- No feedback after clicking.
- User cannot tell whether the value copied.

### S08 Gmail saved login save, apply, and remove

Steps:
1. Configure Gmail integration.
2. Save the login or token.
3. Restart the app.
4. Confirm Gmail still works.
5. Remove the saved Gmail login and restart again.

Expected:
- Save persists correctly.
- Apply uses the saved value.
- Remove actually disconnects Gmail.

Watch for:
- Gmail looks connected but calls fail.
- Removed credentials still work.
- Restart changes the displayed state incorrectly.

### S09 Gmail or Telegram save failure preserves input

Steps:
1. Enter Gmail or Telegram credentials.
2. Force a save failure if possible, for example by stopping backend/network.
3. Press Save.

Expected:
- Error is shown.
- Entered values remain available for correction/retry.

Watch for:
- Fields clear before save succeeds.
- User has to re-enter secrets after transient failure.

### S10 Telegram bot token visibility

Steps:
1. Open Telegram setup.
2. Enter or reveal a bot token.
3. Save, close, and reopen setup.

Expected:
- Token is masked by default.
- Reveal is explicit and temporary.

Watch for:
- Full token shown plaintext unnecessarily.
- Token remains visible after tab switch or reopen.

### S11 Pairing code expiry

Steps:
1. Generate a pairing code.
2. Wait until it should expire.
3. Try copying or using the expired code.

Expected:
- Expiry is visible.
- Expired code cannot be copied or is clearly marked unusable.

Watch for:
- Expired code still looks valid.
- Copy button still copies expired code without warning.

### S12 Recovery or cloud backup status placement

Steps:
1. Open Setup and account/cloud settings.
2. Look for recovery and cloud backup status.
3. Toggle or change related settings if available.

Expected:
- Backup/recovery status is visible in a relevant section.
- User can tell whether data is protected.

Watch for:
- Status hidden under unrelated sections.
- User cannot tell if cloud backup is enabled.

## Chat And Composer

### C01 Tool-using responses end with final assistant message

Steps:
1. Open a chat.
2. Ask a question that requires a tool, such as "what do you see on screen?" or "what files are in this directory?"
3. Wait for the tool call to finish.

Expected:
- Tool result appears.
- Assistant sends a final natural-language answer after the tool result.

Watch for:
- Only the command/tool card appears.
- Run stops with no final assistant message.
- Behavior breaks in other modes such as Jarvis, normal chat, or full access.

### C02 First message latency

Steps:
1. Restart the desktop app and local backend from the repo.
2. Create a new chat.
3. Send a simple first message like "hey".
4. Time from pressing Send to first visible response activity and final answer.

Expected:
- First message starts as quickly as possible without losing functionality.
- Any unavoidable warmup is visible as a clear loading state.

Watch for:
- Multi-second delay before message appears sent.
- No visible activity while backend warms up.
- First message much slower than later messages without explanation.

### C03 Send while backend or chat socket reconnects

Steps:
1. Open a chat.
2. Stop or kill the local backend process using the repo terminal or Task Manager.
3. Try to send a message.
4. Restart backend and observe recovery.

Expected:
- User sees a clear offline, reconnecting, or queued message.
- User can cancel or retry.
- No run is lost silently.

Watch for:
- Endless Thinking state.
- Stop button stuck.
- Message looks sent but never runs.

### C04 Stale or deleted chat becomes unavailable

Steps:
1. Open an existing chat.
2. Delete or clear that session from another window/device if possible, or force stale session state.
3. Return to the original window and send a message.

Expected:
- App explains the chat is no longer available.
- User can recover by choosing another chat or starting a new one.

Watch for:
- Typed message appears, then the whole chat disappears into New Chat.
- No explanation of what happened.

### C05 Send while attachment upload is in progress

Steps:
1. Open a chat.
2. Attach a large file.
3. Press Send before upload finishes.

Expected:
- Send waits for upload or is disabled until upload completes.
- User sees clear upload progress.

Watch for:
- Message sends without the attachment.
- Run starts with partial attachment state.
- Upload fails after message has already started.

### C06 Attachment upload with no API key

Steps:
1. Sign into or create an account with no provider API key.
2. Attach a file before sending a message.
3. Try to send.

Expected:
- Either attachment is allowed but sending is blocked with a useful no-key message, or attachment itself is blocked with a useful message.
- No new run starts.

Watch for:
- App creates a ready-looking chat and then fails awkwardly.
- App starts Thinking or generating despite no key.

### C07 Binary attachment usability

Steps:
1. Attach a binary file such as an image, PDF, or archive.
2. Send a message asking about the file.
3. Check attachment preview and tool behavior.

Expected:
- Attachment remains available in the correct form.
- App does not convert it to an empty text shell.

Watch for:
- File size becomes zero.
- Preview exists but model cannot access file content.
- Attachment silently becomes text-only.

### C08 Failed attachment from new draft

Steps:
1. Start from New Chat.
2. Attach a file that will fail upload, such as an unsupported or unavailable file.
3. Observe the sidebar and draft chat after failure.

Expected:
- Failed upload does not leave behind an empty chat.
- User can retry or remove the attachment.

Watch for:
- Empty chat appears in sidebar.
- Draft gets stuck with failed attachment.

### C09 Attachment scope in later messages

Steps:
1. Attach a file and send a message about it.
2. Send a later unrelated message in the same chat.
3. Check whether the old attachment still affects the model.

Expected:
- Attachment scope is clear.
- User can tell whether the attachment is still active and can remove it if needed.

Watch for:
- Old file silently influences later messages.
- No control to detach or inspect active attachments.

### C10 Queued message during active run

Steps:
1. Start a long response.
2. While it is still running, type and send another message.
3. Try canceling or editing the queued message if controls exist.

Expected:
- Queued message is obvious.
- User can cancel it or see that it will send after the run.

Watch for:
- Queued message disappears.
- Stop button controls the wrong thing.
- Second message is stuck forever.

### C11 Unsent composer text survives navigation

Steps:
1. Type a draft message in a chat but do not send it.
2. Switch to another chat.
3. Return to the original chat.
4. Try the same with New Chat.

Expected:
- Draft text is preserved per chat or user is warned before losing it.

Watch for:
- Composer clears silently.
- Draft from one chat appears in the wrong chat.

### C12 Stop and send controls resist spam clicking

Steps:
1. Send a message.
2. Rapidly click Stop, Send, and related controls during state changes.
3. Observe run state and message history.

Expected:
- Controls remain consistent.
- Only valid actions are accepted.

Watch for:
- Duplicate runs.
- Stuck stop button.
- Message appears sent twice or not at all.

### C13 Delete chat confirmation

Steps:
1. Select a non-important test chat.
2. Press Delete or remove chat.

Expected:
- User is asked to confirm before deletion.
- Confirmation names the chat or action clearly.

Watch for:
- Chat deletes immediately.
- Deletion is easy to trigger accidentally.

### C14 Sidebar search outside-click behavior

Steps:
1. Open sidebar search.
2. Type a query.
3. Click outside the search UI.

Expected:
- Search closes or clears predictably.
- Sidebar returns to normal state.

Watch for:
- Search overlay remains stuck.
- Query remains filtering without visible search UI.

### C15 Search modal on empty account

Steps:
1. Sign into an account with no chats.
2. Open chat search.

Expected:
- User sees an empty-state message.
- Modal is not blank.

Watch for:
- Blank panel.
- Search input opens but no explanation appears.

### C16 Sidebar sessions loading vs empty folders

Steps:
1. Sign into an account with folders/projects and chats.
2. Watch sidebar during the first seconds of loading.

Expected:
- Loading state appears until sessions and folders are known.
- Empty folders are not shown as final state before load completes.

Watch for:
- Empty folders flash and then fill in later.
- User believes chats are missing.

### C17 Sidebar folders and projects are account-scoped

Steps:
1. In account A, create folders/projects and move chats into them.
2. Sign out and sign into account B.
3. Check sidebar folders/projects.

Expected:
- Account B only sees its own folders/projects.

Watch for:
- Account A folders appear in account B.
- Moving account B chats affects account A folders.

### C18 Folder rename UX

Steps:
1. Rename a folder/project from the sidebar.

Expected:
- Rename uses the app UI, with validation and cancel/save controls.

Watch for:
- Native browser prompt appears.
- Empty or duplicate names are accepted unexpectedly.

### C19 Removing folder preserves sidebar state

Steps:
1. Create a folder/project with test chats.
2. Remove the folder.
3. Observe where the chats go and whether sidebar remains usable.

Expected:
- App explains whether chats are deleted, moved, or only ungrouped.
- Sidebar remains stable.

Watch for:
- Chats vanish without explanation.
- Sidebar collapses or loses unrelated state.

### C20 Draft branch selection warning

Steps:
1. Open branch selection for a draft or repo-backed chat.
2. Select a different branch while there are unsaved changes or active context.

Expected:
- App warns before switching repo branch.
- User can cancel.

Watch for:
- Branch switches immediately.
- Unsaved draft/context is lost.

### C21 `/reset` and `/forget` behavior clarity

Steps:
1. In a test chat, use `/reset`.
2. Observe visible chat and model context.
3. In another test chat, use `/forget`.
4. Compare behavior.

Expected:
- The app clearly distinguishes resetting model context from deleting or hiding visible chat history.

Watch for:
- User cannot tell what was forgotten.
- Visible history and model context diverge without explanation.

### C22 Unsupported `/tools` and `/run` commands

Steps:
1. Type `/tools` and submit.
2. Type `/run` and submit.

Expected:
- Unsupported commands are rejected with a clear message or hidden from suggestions.

Watch for:
- Command appears accepted but does nothing.
- App starts an unclear action.

### C23 `/restart` confirmation

Steps:
1. Type `/restart` in a chat.
2. Attempt to submit.

Expected:
- App asks for confirmation before restarting local services or app state.

Watch for:
- Restart happens immediately.
- Active work is stopped without warning.

### C24 `/schedule` parser

Steps:
1. Try simple schedules such as `/schedule daily 9am`.
2. Try advanced schedules if the UI suggests them.
3. Inspect the created automation schedule.

Expected:
- Supported schedules parse correctly.
- Unsupported syntax is rejected with a useful message.

Watch for:
- Daily schedule becomes one-time or wrong timezone.
- Advanced placeholder syntax is accepted but not honored.

## Jarvis And Voice

### V01 Jarvis voice with no API key

Steps:
1. Create or sign into an account with no provider API key.
2. Go to Jarvis.
3. Try hold-to-talk.
4. Try always-on voice if available.

Expected:
- Immediate "you have not set an API key" style message.
- No recording loop.
- No generating loop.
- No new run starts.

Watch for:
- Voice starts anyway.
- "Generating" appears.
- Mic or voice state gets stuck.

### V02 Voice message with no TTS installed

Steps:
1. Use an account with a valid API key.
2. Remove or disable local TTS voice support if possible.
3. In Jarvis, send a message via voice.
4. Wait for the response.

Expected:
- Agent works normally and produces a text answer.
- App clearly indicates speech output is unavailable.

Watch for:
- Agent never answers because TTS is missing.
- Run is blocked waiting for speech output.

### V03 Voice websocket failure UX

Steps:
1. Start Jarvis voice.
2. Kill the backend or disconnect network while voice is active.
3. Observe mic, voice, and status UI.

Expected:
- Human-readable error appears.
- Mic/voice state returns to stopped.
- User can restart voice after backend recovers.

Watch for:
- Vague "voice socket error" only.
- Silent toggle changes.
- Voice state stuck active.

### V04 Voice setup unavailable local paths

Steps:
1. Open voice setup.
2. Choose or type a local model/path that does not exist.
3. Try saving or starting voice.

Expected:
- Invalid/unavailable paths are blocked before use.
- Message explains what is missing.

Watch for:
- Save succeeds but voice fails later.
- App loops trying to load missing files.

### V05 Voice pack install and remove overlap

Steps:
1. Start installing a voice pack.
2. Before it finishes, try removing it or installing another pack.
3. Repeat with multiple packs if available.

Expected:
- In-flight pack operations are serialized or clearly disabled.
- Final installed state is correct.

Watch for:
- Pack appears both installed and missing.
- Progress indicators conflict.
- Local files are left half-installed.

### V06 Voice path switching guard

Steps:
1. Start voice model load or pack install.
2. Switch voice path/model while operation is in progress.

Expected:
- App blocks the switch or safely cancels/restarts the operation.

Watch for:
- Old path and new path race.
- UI says one model is active while backend uses another.

### V07 Jarvis Open Setup goes to Voice tab

Steps:
1. Go to Jarvis.
2. Trigger the Open Setup action from a voice-related warning or button.

Expected:
- Setup opens directly to the Voice tab or relevant voice settings.

Watch for:
- Generic setup opens and user must hunt for the right setting.

### V08 Realtime and STT saved key consistency

Steps:
1. Save a provider API key in settings/cloud.
2. Test realtime voice.
3. Test speech-to-text/hold-to-talk.
4. Restart app and test again.

Expected:
- Both realtime and STT read the same saved active key.

Watch for:
- One voice mode works and another says no key.
- Restart loses key for voice only.

## Fleet And Automations

### F01 Fleet stale or duplicate manager identities

Steps:
1. Open Fleet and note manager identities.
2. Switch accounts.
3. Open Fleet immediately and after refresh.

Expected:
- No stale duplicate manager identities appear.
- Deleted/old managers do not return.

Watch for:
- Duplicate manager from a previous account.
- Old manager flashes during loading.

### F02 Individual Fleet Stop scope

Steps:
1. Start multiple fleet workers or tasks if available.
2. Press Stop on one individual item.

Expected:
- App confirms or makes scope obvious.
- Only the intended worker/task stops.

Watch for:
- All workers stop unexpectedly.
- User cannot tell what will be stopped.

### F03 Fleet group creation worker choice

Steps:
1. Open Fleet group creation.
2. Create a group when multiple workers are available.

Expected:
- User can choose workers.
- Default choice is visible before creation.

Watch for:
- App silently selects the first worker.
- Group is created with unexpected members.

### F04 Fleet Preview visible result

Steps:
1. Open Fleet Preview for a group/task.
2. Trigger preview.

Expected:
- Preview output or result is visible in the UI.

Watch for:
- Preview button does nothing visible.
- Result exists only in logs.

### F05 Fleet queued or local messages

Steps:
1. Start a fleet task.
2. Queue or send another local/fleet message while it is busy.

Expected:
- Queued messages are visible and cancelable.

Watch for:
- Messages disappear.
- Queue cannot be canceled.

### F06 Automation Specific chat target

Steps:
1. Create an automation.
2. Select Specific chat as the target.
3. Choose a known chat.
4. Run the automation.

Expected:
- Automation posts/runs in the selected chat.

Watch for:
- Automation ignores selected chat.
- Automation runs in current/default chat instead.

### F07 Automation chat target picker beyond first 20 chats

Steps:
1. Use an account with more than 20 chats.
2. Create/edit an automation and open the chat target picker.
3. Try selecting a chat outside the first 20.

Expected:
- User can search or paginate to any eligible chat.

Watch for:
- Picker only exposes first 20 chats.
- Target cannot be selected.

### F08 Automation double-click duplicate guard

Steps:
1. Rapidly double-click Create, Run, Pause, and Delete automation controls.
2. Observe automation list and backend state.

Expected:
- Duplicate clicks are ignored or safely debounced.
- Only one intended action happens.

Watch for:
- Duplicate automations.
- Pause/run state flips unpredictably.
- Delete fires twice and errors.

### F09 Pending confirmation approve/deny race

Steps:
1. Trigger an automation or tool action that asks for confirmation.
2. Rapidly click Approve and Deny, or double-click one of them.

Expected:
- Only one final decision is accepted.
- UI clearly shows the final state.

Watch for:
- Both approve and deny seem accepted.
- Action runs after denial.
- Confirmation remains pending forever.

### F10 Automation advanced schedule placeholder

Steps:
1. Open automation schedule creation.
2. Look at advanced schedule examples/placeholders.
3. Enter the shown syntax and save.

Expected:
- Placeholder only shows syntax that is actually supported.
- Saved schedule behaves as described.

Watch for:
- Placeholder suggests unsupported syntax.
- Schedule saves but never runs.

### F11 Automation permissions, tool packs, and identities

Steps:
1. Create an automation with specific permission, tool pack, or identity selections.
2. Run it.
3. Compare runtime behavior with selected settings.

Expected:
- Live run honors selected permissions, tools, and identity.

Watch for:
- Automation uses default permissions or identity.
- UI selection has no runtime effect.

### F12 Automation Run Now feedback

Steps:
1. Create or select an automation.
2. Press Run Now.
3. Watch UI for up to 60 seconds.

Expected:
- App immediately shows running, queued, or failed state.
- Long runs show progress or a clear waiting state.

Watch for:
- UI appears hung.
- Nothing changes until a later refresh.

### F13 Automation output cap and full output path

Steps:
1. Run an automation that produces long output.
2. Open the output/result UI.

Expected:
- Truncated output clearly says it is truncated.
- User can view more or open full output/log.

Watch for:
- Important output is silently cut off.
- No way to inspect full result.

### F14 Automation status and validation messages persist

Steps:
1. Create an invalid automation or trigger a validation message.
2. Wait for background refresh.
3. Change tabs and return.

Expected:
- Validation/status messages remain until resolved or dismissed.

Watch for:
- Refresh erases messages.
- User cannot tell why save/run failed.

## Recovery, Artifacts, And Lifecycle

### R01 Artifact preview after rapid clicks

Steps:
1. Open a chat with multiple artifacts.
2. Rapidly click different artifact entries.
3. Use preview/action buttons.

Expected:
- Preview and actions always match the currently selected artifact.

Watch for:
- Preview shows one artifact while actions affect another.
- Download/open uses stale selection.

### R02 Pending confirmations cap

Steps:
1. Trigger enough pending confirmations to exceed any visible list cap.
2. Open the pending confirmations UI.

Expected:
- Important approvals remain reachable.
- UI indicates there are more confirmations if capped.

Watch for:
- Older or important approvals vanish.
- User cannot approve/deny hidden confirmations.

### R03 Recovery older archived items

Steps:
1. Create or identify many archived recovery items.
2. Open Recovery.
3. Try finding older items.

Expected:
- Recovery supports pagination, search, or "load more".

Watch for:
- Only newest items are visible.
- No path to older archived items.

### R04 Restore archived item confirmation

Steps:
1. Open Recovery.
2. Select an archived item.
3. Press Restore.

Expected:
- App confirms before restore.
- Confirmation explains what will be restored and where.

Watch for:
- Restore happens immediately.
- Existing files/chats are overwritten without warning.

### R05 Restore Workspace Files scope

Steps:
1. Open Recovery.
2. Choose Restore Workspace Files.
3. Read the confirmation/details.

Expected:
- App explains exact scope, target paths, and overwrite behavior.
- User can cancel before any file changes.

Watch for:
- Scope is vague.
- Restore can affect broad workspace files without clear warning.

### R06 Long-term Memory unsaved edits

Steps:
1. Open Long-term Memory.
2. Edit memory content.
3. Navigate away, close modal, or switch account without saving.

Expected:
- User gets an unsaved changes warning.

Watch for:
- Edits are lost silently.
- Memory appears saved but reverts later.

### R07 Active local work lifecycle warnings

Steps:
1. Start an active chat run, fleet task, automation, or long local operation.
2. Try Top Stop, app close, logout, and update install.

Expected:
- App warns before stopping active local work.
- Warning explains what will be stopped or preserved.

Watch for:
- Work stops silently.
- Logout/update kills runs without explanation.

## Quick Regression Pack

Use this shorter pack after fixes to catch the highest-risk regressions:

1. Signup OTP enforcement: new email account cannot sign in before valid OTP.
2. Google saved-key login: setup never flashes when a key already exists.
3. Tool-call final answer: tool result is followed by final assistant text.
4. Jarvis no-key voice: no recording/generating loop starts.
5. Jarvis no-TTS voice: text answer still appears.
6. Backend killed while sending: user sees offline/retry/cancel state.
7. Account switch: no old setup, fleet, recovery, secret, or chat data flashes.
8. Fleet manager identities: no duplicate/stale manager from previous account.
9. Chat loading: sidebar shows loader until chats are loaded.
10. Cloud/local chat recovery: chats refound after logout/login according to backup setting.
11. Attachment no-key behavior: attach/send is clearly blocked or allowed-with-send-block.
12. Queued message during active run: queued item is visible and cancelable.
