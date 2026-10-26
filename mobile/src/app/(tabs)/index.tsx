import { useState } from 'react';
import { FlatList, Pressable, Text, View } from 'react-native';
import { router } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { api, messageOf } from '../../lib/api';
import { useAuth } from '../../providers/auth';
import { count, date } from '../../lib/format';
import type { AnalysisListItem, PaginatedResponse } from '../../generated/contracts';
import { Badge, Body, Button, Card, ErrorNotice, Field, Heading, Loading, Screen, colors, styles } from '../../components/ui';

export default function Analyses() {
  const { session } = useAuth();
  const [search, setSearch] = useState('');
  const [submitted, setSubmitted] = useState('');
  const [page, setPage] = useState(1);
  const result = useQuery({
    queryKey: ['analyses', session?.user.id, page, submitted],
    queryFn: ({ signal }) => api<PaginatedResponse<AnalysisListItem>>(`/analyses?page=${page}&limit=20&search=${encodeURIComponent(submitted)}`, { signal }),
    refetchInterval: (query) => query.state.data?.items.some((item) => ['pending', 'processing'].includes(item.status)) ? 3000 : false,
  });
  return <Screen scroll={false}><FlatList data={result.data?.items ?? []} keyExtractor={(item) => item.id}
    contentContainerStyle={styles.content} refreshing={result.isRefetching} onRefresh={() => void result.refetch()}
    ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
    ListHeaderComponent={<View style={{ gap: 18, marginBottom: 18 }}>
      <View style={{ borderRadius: 28, backgroundColor: '#302056', padding: 24, overflow: 'hidden', gap: 12 }}>
        <View style={{ position: 'absolute', width: 170, height: 170, borderRadius: 85, backgroundColor: '#613DA1', right: -45, top: -80 }} />
        <View style={{ position: 'absolute', width: 130, height: 130, borderRadius: 65, backgroundColor: '#177E7B', right: -60, bottom: -72 }} />
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}><Ionicons name="sparkles" color="#ACF1DB" size={16} /><Text style={{ color: '#ACF1DB', fontSize: 12, fontWeight: '800', letterSpacing: 2 }}>YOUR DATA WORKSPACE</Text></View>
        <Text style={{ color: '#fff', fontSize: 29, fontWeight: '800', letterSpacing: -1, maxWidth: 300 }}>Find the story in your data.</Text>
        <Text style={{ color: '#DDD1F2', fontSize: 14, lineHeight: 21, maxWidth: 300 }}>Your analyses and answers, ready wherever you are.</Text>
        <View style={{ marginTop: 8 }}><Button title="Create a new analysis" icon="add-circle-outline" onPress={() => router.push('/(tabs)/upload')} /></View>
      </View>
      <Heading title="Your analyses" subtitle={result.data ? `${count(result.data.total)} analyses in your workspace` : 'Explore your recent work.'} />
      <Field label="Search analyses" value={search} onChangeText={setSearch} returnKeyType="search" onSubmitEditing={() => { setSubmitted(search.trim()); setPage(1); }} />
      <Button title="Search" variant="secondary" onPress={() => { setSubmitted(search.trim()); setPage(1); }} />
      {result.error && <ErrorNotice message={messageOf(result.error)} retry={() => void result.refetch()} />}
    </View>}
    ListEmptyComponent={result.isPending ? <Loading /> : result.error ? null : <Card><Ionicons name="analytics-outline" color={colors.blue} size={38} /><Heading title={submitted ? 'No matching analyses' : 'Your next insight starts here'} subtitle={submitted ? 'Try another search.' : 'Choose a file to create your first dashboard.'} /></Card>}
    renderItem={({ item }) => <Pressable accessibilityRole="button" accessibilityLabel={`Open ${item.name}`} onPress={() => router.push({ pathname: '/analysis/[id]', params: { id: item.id } })}>
      <Card><View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}><View style={{ width: 42, height: 42, borderRadius: 14, backgroundColor: colors.pale, alignItems: 'center', justifyContent: 'center' }}><Ionicons name="bar-chart" size={20} color={colors.blue} /></View><Text style={{ fontSize: 18, fontWeight: '700', color: colors.ink, flex: 1 }} numberOfLines={2}>{item.name}</Text><Ionicons name="arrow-forward" size={20} color={colors.blue} /></View><View style={{ flexDirection: 'row', alignItems: 'center', gap: 9 }}><Badge status={item.status} /><Text style={{ color: colors.muted, fontSize: 12 }}>{date(item.created_at)}</Text></View><Body>{count(item.row_count)} rows · {item.filename}</Body></Card>
    </Pressable>}
    ListFooterComponent={result.data && result.data.pages > 1 ? <View style={{ gap: 12, marginTop: 16 }}><Body>Page {page} of {result.data.pages}</Body><View style={{ flexDirection: 'row', gap: 12 }}><View style={{ flex: 1 }}><Button title="Previous" variant="secondary" disabled={page <= 1} onPress={() => setPage(page - 1)} /></View><View style={{ flex: 1 }}><Button title="Next" variant="secondary" disabled={page >= result.data.pages} onPress={() => setPage(page + 1)} /></View></View></View> : null}
  /></Screen>;
}
