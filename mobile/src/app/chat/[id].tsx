import { useRef, useState } from 'react';
import { Platform, ScrollView, Text, View } from 'react-native';
import { useHeaderHeight } from 'expo-router/react-navigation';
import { router, useLocalSearchParams } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, messageOf } from '../../lib/api';
import { useAuth } from '../../providers/auth';
import type { ChatMessage, ChatSession } from '../../generated/contracts';
import { Chart } from '../../components/chart';
import { Body, Button, ErrorNotice, Field, Loading, Screen, colors, styles } from '../../components/ui';

function MessageText({ content }: { content: string }) {
  const plain = content.replace(/(^|\n)#{1,6}\s+/g, '$1');
  return <Text selectable style={{ color: colors.ink, fontSize: 15, lineHeight: 24 }}>
    {plain.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
      part.startsWith('**') && part.endsWith('**')
        ? <Text key={index} style={{ fontWeight: '700' }}>{part.slice(2, -2)}</Text>
        : part,
    )}
  </Text>;
}

export default function ChatScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const headerHeight = useHeaderHeight();
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const [chosenSession, setActive] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [pendingText, setPendingText] = useState<string | null>(null);
  const scroll = useRef<ScrollView>(null);
  const sessions = useQuery({ queryKey: ['chat-sessions', session?.user.id, id], queryFn: ({ signal }) => api<ChatSession[]>(`/chat/sessions?analysis_id=${encodeURIComponent(id)}`, { signal }) });
  const active = chosenSession ?? sessions.data?.[0]?.id ?? null;
  const messages = useQuery({ queryKey: ['messages', session?.user.id, active], queryFn: ({ signal }) => api<ChatMessage[]>(`/chat/sessions/${active}/messages`, { signal }), enabled: !!active });
  const send = useMutation({ mutationFn: async (content: string) => {
    let chatId = active;
    if (!chatId) {
      const created = await api<ChatSession>('/chat/sessions', { method: 'POST', body: { analysis_id: id } });
      chatId = created.id; setActive(chatId);
      void queryClient.invalidateQueries({ queryKey: ['chat-sessions', session?.user.id, id] });
    }
    await api<ChatMessage>(`/chat/sessions/${chatId}/messages`, { method: 'POST', body: { content }, timeout: 120_000 });
    await queryClient.invalidateQueries({ queryKey: ['messages', session?.user.id, chatId] });
    void queryClient.invalidateQueries({ queryKey: ['profile', session?.user.id] });
  }, onSuccess: () => setInput(''), onSettled: async () => {
    setPendingText(null);
    if (active) await queryClient.invalidateQueries({ queryKey: ['messages', session?.user.id, active] });
  } });

  function submit(content = input.trim()) {
    if (!content || send.isPending || sessions.isPending || sessions.isError) return;
    setPendingText(content); send.mutate(content);
  }
  return <Screen scroll={false} keyboardAvoidingBehavior={Platform.OS === 'android' ? 'height' : 'padding'} keyboardVerticalOffset={headerHeight}><ScrollView ref={scroll} style={{ flex: 1 }} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: true })}>
    <Body>Ask questions grounded in this analysis.</Body>
    {sessions.isPending && <Loading label="Opening conversation…" />}
    {sessions.error && <ErrorNotice message={messageOf(sessions.error)} retry={() => void sessions.refetch()} />}
    {(messages.data ?? []).map((message) => <View key={message.id} style={{ gap: 12 }}><View style={{ backgroundColor: message.role === 'user' ? colors.pale : '#fff', padding: 18, borderRadius: 18, borderWidth: 1, borderColor: colors.line }}><Text style={{ color: colors.blue, fontWeight: '600', marginBottom: 8 }}>{message.role === 'user' ? 'You' : 'Zephyr'}</Text><MessageText content={message.content} />{message.comparison && <View style={{ gap: 10, marginTop: 12 }}><Body>Figures behind this answer</Body>{message.comparison.groups.map((group, index) => <Button key={index} title={`View entries: ${group.group ?? 'this result'}`} variant="secondary" onPress={() => router.push({ pathname: '/entries/[id]', params: { id, request: JSON.stringify({ kind: 'comparison', comparison: message.comparison!.plan, evidence_revision: message.comparison!.evidence_revision, group_value: group.group_value }) } })} />)}</View>}</View>{message.chart_config && <Chart chart={message.chart_config} />}</View>)}
    {!messages.data?.length && !sessions.isPending && !sessions.error && !send.isPending && <View style={{ gap: 10 }}>{['Summarise the key findings', 'What should we focus on next?', 'What unusual patterns can you see?'].map((question) => <Button key={question} title={question} variant="secondary" onPress={() => submit(question)} />)}</View>}
    {send.isPending && <><Body>You: {pendingText}</Body><Loading label="Zephyr is checking your data…" /></>}
    {messages.error && <ErrorNotice message={messageOf(messages.error)} retry={() => void messages.refetch()} />}
    {send.error && <ErrorNotice message={`${messageOf(send.error)} Refresh the conversation before retrying; your message may already have reached the server.`} retry={() => void messages.refetch()} />}
  </ScrollView><View style={{ paddingHorizontal: 20, paddingTop: 12, paddingBottom: 10, gap: 10, borderTopWidth: 1, borderColor: colors.line, backgroundColor: '#fff' }}><Field label="Your question" value={input} onChangeText={setInput} multiline maxLength={4000} editable={!send.isPending} /><Button title="Send question" icon="send-outline" loading={send.isPending} disabled={!input.trim() || sessions.isPending || sessions.isError} onPress={() => submit()} /></View></Screen>;
}
