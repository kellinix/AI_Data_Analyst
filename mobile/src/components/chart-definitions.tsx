import { useState } from 'react';
import { View } from 'react-native';
import { chartReaderDefinitions } from '../generated/data-guide';
import { Body, Button, Label } from './ui';

export function ChartDefinitions({ option }: { option: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false);
  const definitions = chartReaderDefinitions(option);
  if (definitions.length === 0) return null;
  return <View style={{ gap: 10 }}>
    <Button title={expanded ? 'Hide definitions' : 'What these names mean'} variant="secondary" onPress={() => setExpanded(!expanded)} />
    {expanded && <>
      <Body>From the data guide supplied with this analysis.</Body>
      {definitions.map(definition => <View key={definition.field} style={{ gap: 5 }}>
        <Label>{definition.label}</Label>
        {definition.description && <Body>{definition.description}</Body>}
        {definition.unit && <Body>Measured in {definition.unit}.</Body>}
        {definition.origin && <Body>Days are counted from {definition.origin}.</Body>}
      </View>)}
    </>}
  </View>;
}
