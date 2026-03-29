import { useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';

const API_BASE = process.env.EXPO_PUBLIC_EMPLOAI_APP_URL || 'http://127.0.0.1:8765';

type ChatEvent = {
  type: string;
  session_id?: string;
  payload?: Record<string, any>;
};

type ChatMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
};

export default function ChatScreen() {
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [toolLogs, setToolLogs] = useState<string[]>([]);
  const [status, setStatus] = useState('disconnected');
  const wsRef = useRef<WebSocket | null>(null);

  const token = useMemo(() => process.env.EXPO_PUBLIC_EMPLOAI_APP_TOKEN || '', []);

  const uploadAttachment = async (kind: 'camera' | 'gallery' | 'document') => {
    if (!token) {
      setStatus('missing token');
      return;
    }

    try {
      let asset: { uri: string; name: string; mimeType?: string | null } | null = null;

      if (kind === 'camera') {
        const permission = await ImagePicker.requestCameraPermissionsAsync();
        if (!permission.granted) {
          setStatus('camera denied');
          return;
        }
        const result = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.8 });
        if (result.canceled || !result.assets?.length) return;
        const picked = result.assets[0];
        asset = { uri: picked.uri, name: picked.fileName || `camera-${Date.now()}.jpg`, mimeType: picked.mimeType };
      } else if (kind === 'gallery') {
        const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
        if (!permission.granted) {
          setStatus('gallery denied');
          return;
        }
        const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.8 });
        if (result.canceled || !result.assets?.length) return;
        const picked = result.assets[0];
        asset = { uri: picked.uri, name: picked.fileName || `gallery-${Date.now()}.jpg`, mimeType: picked.mimeType };
      } else {
        const result = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true, multiple: false });
        if (result.canceled || !result.assets?.length) return;
        const picked = result.assets[0];
        asset = { uri: picked.uri, name: picked.name, mimeType: picked.mimeType };
      }

      if (!asset) return;

      const form = new FormData();
      form.append('file', {
        uri: asset.uri,
        name: asset.name,
        type: asset.mimeType || 'application/octet-stream',
      } as any);
      if (sessionId) form.append('session_id', sessionId);

      const response = await fetch(`${API_BASE}/api/app/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const data = await response.json();
      if (!response.ok) throw new Error('upload failed');
      if (data.session_id) setSessionId(String(data.session_id));
      setToolLogs((prev) => [`Attached: ${data.filename}`, ...prev].slice(0, 40));
      setStatus('attachment ready');
    } catch {
      setStatus('upload error');
    }
  };

  useEffect(() => {
    if (!token) {
      setStatus('missing token');
      return;
    }

    const ws = new WebSocket(`${API_BASE.replace(/^http/, 'ws')}/ws/app/chat?token=${encodeURIComponent(token)}`);
    wsRef.current = ws;

    ws.onopen = () => setStatus('connected');
    ws.onclose = () => setStatus('closed');
    ws.onerror = () => setStatus('error');
    ws.onmessage = (event) => {
      const data: ChatEvent = JSON.parse(event.data);
      if (data.session_id) {
        setSessionId(data.session_id);
      }
      if (data.type === 'assistant_delta') {
        const delta = String(data.payload?.delta || '');
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === 'assistant') {
            last.content += delta;
            return [...next];
          }
          return [...next, { role: 'assistant', content: delta }];
        });
      } else if (data.type === 'assistant_final') {
        const text = String(data.payload?.text || '');
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === 'assistant') {
            last.content = text || last.content;
            return [...next];
          }
          return [...next, { role: 'assistant', content: text }];
        });
      } else if (data.type === 'tool_event') {
        setToolLogs((prev) => [JSON.stringify(data.payload), ...prev].slice(0, 40));
      } else if (data.type === 'status' || data.type === 'log') {
        const msg = String(data.payload?.message || '');
        if (msg) setToolLogs((prev) => [msg, ...prev].slice(0, 40));
      }
    };

    return () => ws.close();
  }, [token]);

  const send = () => {
    const trimmed = input.trim();
    if (!trimmed || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    setMessages((prev) => [...prev, { role: 'user', content: trimmed }]);
    wsRef.current.send(JSON.stringify({ text: trimmed, session_id: sessionId }));
    setInput('');
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>EmploAI Chat</Text>
        <Text style={styles.meta}>Status: {status}</Text>
        <Text style={styles.meta}>Session: {sessionId || 'none'}</Text>
      </View>
      <ScrollView style={styles.messages} contentContainerStyle={styles.messagesContent}>
        {messages.map((message, index) => (
          <View key={`${message.role}-${index}`} style={[styles.bubble, message.role === 'user' ? styles.userBubble : styles.assistantBubble]}>
            <Text style={styles.bubbleRole}>{message.role}</Text>
            <Text style={styles.bubbleText}>{message.content}</Text>
          </View>
        ))}
      </ScrollView>
      <View style={styles.logsCard}>
        <Text style={styles.logsTitle}>Tool / status feed</Text>
        {toolLogs.length === 0 ? <Text style={styles.logsEmpty}>No events yet.</Text> : toolLogs.slice(0, 6).map((entry, index) => <Text key={`${entry}-${index}`} style={styles.logLine}>{entry}</Text>)}
      </View>
      <View style={styles.attachRow}>
        <Pressable style={styles.secondaryButton} onPress={() => uploadAttachment('camera')}>
          <Text style={styles.buttonText}>Camera</Text>
        </Pressable>
        <Pressable style={styles.secondaryButton} onPress={() => uploadAttachment('gallery')}>
          <Text style={styles.buttonText}>Gallery</Text>
        </Pressable>
        <Pressable style={styles.secondaryButton} onPress={() => uploadAttachment('document')}>
          <Text style={styles.buttonText}>Document</Text>
        </Pressable>
      </View>
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Send a message"
          placeholderTextColor="#7f8aa3"
        />
        <Pressable style={styles.button} onPress={send}>
          <Text style={styles.buttonText}>Send</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0b1020', padding: 16, gap: 12 },
  header: { gap: 4 },
  title: { color: '#fff', fontSize: 24, fontWeight: '700' },
  meta: { color: '#9aa9c7', fontSize: 13 },
  messages: { flex: 1 },
  messagesContent: { gap: 10, paddingBottom: 10 },
  bubble: { borderRadius: 14, padding: 12, gap: 6 },
  userBubble: { backgroundColor: '#21406b', alignSelf: 'flex-end', maxWidth: '86%' },
  assistantBubble: { backgroundColor: '#172038', alignSelf: 'flex-start', maxWidth: '92%' },
  bubbleRole: { color: '#7cc7ff', fontWeight: '700', fontSize: 12 },
  bubbleText: { color: '#e8eefc', fontSize: 15 },
  logsCard: { backgroundColor: '#141c33', borderRadius: 16, padding: 12, gap: 8 },
  logsTitle: { color: '#fff', fontWeight: '700' },
  logsEmpty: { color: '#9aa9c7' },
  logLine: { color: '#c9d7f3', fontSize: 12 },
  attachRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  secondaryButton: { backgroundColor: '#223153', borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10 },
  inputRow: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  input: { flex: 1, backgroundColor: '#141c33', color: '#fff', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12 },
  button: { backgroundColor: '#3b82f6', borderRadius: 12, paddingHorizontal: 18, paddingVertical: 12 },
  buttonText: { color: '#fff', fontWeight: '700' },
});
