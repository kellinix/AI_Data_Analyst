import { createElement, useMemo, useState } from 'react';
import type { ChartConfig } from '../generated/contracts';
import runtime from '../generated/echarts';
import { chartDocument } from '../lib/chart-document';
import { Body, Button, Card, Label, colors } from './ui';

export function Chart({ chart, defaultExpanded = false }: { chart: ChartConfig; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const categoryAxis = chart.echarts_option.yAxis as { type?: string; data?: unknown[] } | undefined;
  const horizontalBar = (chart.type === 'bar' || chart.type === 'histogram') && categoryAxis?.type === 'category';
  const chartHeight = horizontalBar ? Math.max(320, (categoryAxis?.data?.length ?? 0) * 34 + 80) : 320;
  const html = useMemo(() => expanded ? chartDocument(runtime, chart.echarts_option, chart.currency) : '', [chart, expanded]);
  return <Card>{createElement('div', { style: { height: 4, borderRadius: 4, backgroundColor: colors.teal } })}<Label>{chart.title}</Label>{chart.description && <Body>{chart.description}</Body>}
    <Button title={expanded ? 'Hide chart' : 'View chart'} variant="secondary" onPress={() => setExpanded(!expanded)} />
    {expanded && createElement('iframe', { title: chart.title, srcDoc: html, sandbox: 'allow-scripts', style: { border: 0, width: '100%', height: chartHeight, borderRadius: 10 } })}
  </Card>;
}
