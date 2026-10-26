import { useMemo, useState } from 'react';
import { View } from 'react-native';
import { WebView } from 'react-native-webview';
import type { ChartConfig } from '../generated/contracts';
import runtime from '../generated/echarts';
import { chartDocument } from '../lib/chart-document';
import { Body, Button, Card, Label, colors } from './ui';

export function Chart({ chart, defaultExpanded = false }: { chart: ChartConfig; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [failed, setFailed] = useState(false);
  const rangeAxis = chart.echarts_option.yAxis as { data?: unknown[] } | undefined;
  const chartHeight = chart.type === 'histogram' ? Math.max(320, (rangeAxis?.data?.length ?? 0) * 34 + 80) : 320;
  const html = useMemo(() => expanded ? chartDocument(runtime, chart.echarts_option, chart.currency) : '', [chart, expanded]);
  return <Card><View style={{ height: 4, borderRadius: 4, backgroundColor: colors.teal, marginBottom: 2 }} /><Label>{chart.title}</Label>{chart.description && <Body>{chart.description}</Body>}
    <Button title={expanded ? 'Hide chart' : 'View chart'} variant="secondary" onPress={() => { setExpanded(!expanded); setFailed(false); }} />
    {expanded && <View style={{ height: chartHeight, overflow: 'hidden', borderRadius: 16 }}>
      <WebView source={{ html }} originWhitelist={['*']} onShouldStartLoadWithRequest={({ url }) => url === 'about:blank' || url.startsWith('about:blank#')}
        javaScriptEnabled domStorageEnabled={false} scrollEnabled={false} allowFileAccess={false}
        mixedContentMode="never" setSupportMultipleWindows={false}
        onError={() => setFailed(true)} onMessage={({ nativeEvent }) => { if (nativeEvent.data === 'chart-error') setFailed(true); }}
        style={{ backgroundColor: '#fff' }} />
    </View>}{failed && <Body>This chart could not be displayed. Open the analysis on the website to view it.</Body>}
  </Card>;
}
