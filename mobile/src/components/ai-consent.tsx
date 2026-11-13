import { useState } from 'react';
import { Linking, Switch } from 'react-native';
import { Body, Button, Card, Label, colors } from './ui';

// Screen- and account-scoped. Never carries permission over to another account or report.
export function useAiConsent(scope: string) {
  const [acceptedScope, setAcceptedScope] = useState<string | null>(null);
  return { accepted: !!scope && acceptedScope === scope, setAccepted: (value: boolean) => setAcceptedScope(value ? scope : null) };
}

export function AiConsent({ accepted, setAccepted, busy = false }: { accepted: boolean; setAccepted: (value: boolean) => void; busy?: boolean }) {
  return <Card>
    <Label>Choose whether to use AI</Label>
    <Body>Vesquiri sends data to OpenAI to help analyse it and answer questions. This can include column names, values and summaries from your files, your instructions, questions and conversation history. Remove private information you do not want to share.</Body>
    <Body>You can leave this off and still view saved reports, compare groups and export them. Turning it off stops new AI requests from this screen; it cannot undo a request already sent. We ask again when you open another screen.</Body>
    <Switch accessibilityLabel="I agree to share this data with OpenAI for AI analysis and answers" value={accepted} onValueChange={setAccepted} disabled={busy} trackColor={{ true: colors.blue }} />
    <Body>{accepted ? 'I agree to share this data with OpenAI.' : 'Sharing with OpenAI is off.'}</Body>
    <Button title="Read privacy policy" variant="secondary" onPress={() => void Linking.openURL('https://vesquiri.com/privacy')} />
  </Card>;
}
