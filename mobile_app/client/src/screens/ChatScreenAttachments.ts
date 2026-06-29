import { requestJson } from '../../lib/appHttp';

import {
  loadDocumentPickerModule,
  loadImagePickerModule,
} from './ChatScreen.helpers';

export type ChatAttachmentKind = 'camera' | 'gallery' | 'document';

type UploadChatAttachmentOptions = {
  requireChatConnection: () => boolean;
  setStatus: (value: string) => void;
  ensureSessionForSend: () => Promise<string | null | undefined>;
  apiBaseUrl: string;
  token: string;
  sessionIdRef: { current: string | undefined };
  setSessionId: (value: string | undefined) => void;
  appendLog: (entry: string) => void;
  refreshSidebarData: () => Promise<void>;
  showChatError: (error: unknown, fallback?: string) => void;
};

type PickedAsset = {
  uri: string;
  name: string;
  mimeType?: string | null;
};

async function pickAttachmentAsset(
  kind: ChatAttachmentKind,
  setStatus: (value: string) => void,
): Promise<PickedAsset | null> {
  if (kind === 'camera') {
    const ImagePicker = await loadImagePickerModule();
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      setStatus('camera denied');
      return null;
    }
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.8,
    });
    if (result.canceled || !result.assets?.length) return null;
    const picked = result.assets[0];
    return { uri: picked.uri, name: picked.fileName || `camera-${Date.now()}.jpg`, mimeType: picked.mimeType };
  }

  if (kind === 'gallery') {
    const ImagePicker = await loadImagePickerModule();
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setStatus('gallery denied');
      return null;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.8,
    });
    if (result.canceled || !result.assets?.length) return null;
    const picked = result.assets[0];
    return { uri: picked.uri, name: picked.fileName || `gallery-${Date.now()}.jpg`, mimeType: picked.mimeType };
  }

  const DocumentPicker = await loadDocumentPickerModule();
  const result = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true, multiple: false });
  if (result.canceled || !result.assets?.length) return null;
  const picked = result.assets[0];
  return { uri: picked.uri, name: picked.name, mimeType: picked.mimeType };
}

export async function uploadChatAttachment(
  kind: ChatAttachmentKind,
  options: UploadChatAttachmentOptions,
) {
  const {
    requireChatConnection,
    setStatus,
    ensureSessionForSend,
    apiBaseUrl,
    token,
    sessionIdRef,
    setSessionId,
    appendLog,
    refreshSidebarData,
    showChatError,
  } = options;

  if (!requireChatConnection()) return;

  try {
    const asset = await pickAttachmentAsset(kind, setStatus);
    if (!asset) return;

    const uploadSessionId = await ensureSessionForSend();
    if (!uploadSessionId) return;

    const form = new FormData();
    form.append('file', {
      uri: asset.uri,
      name: asset.name,
      type: asset.mimeType || 'application/octet-stream',
    } as any);
    form.append('session_id', uploadSessionId);

    const data = await requestJson<{ filename?: string; session_id?: string }>({
      scope: 'chat.upload',
      url: `${apiBaseUrl}/api/app/upload`,
      init: {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      },
    });
    if (data.session_id) {
      sessionIdRef.current = String(data.session_id);
      setSessionId(String(data.session_id));
    }
    appendLog(`Attached: ${data.filename}`);
    setStatus('attachment ready');
    void refreshSidebarData();
  } catch (error) {
    showChatError(error, 'Attachment was not added.');
  }
}
