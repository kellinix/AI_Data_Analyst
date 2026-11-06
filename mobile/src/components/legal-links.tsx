import { useState } from 'react';
import * as Linking from 'expo-linking';
import { Body, Button, Card, ErrorNotice, Label } from './ui';

// Public policy pages for the current staging closed test.
const legalPages = [
  { title: 'Privacy policy', url: 'https://zephyr-web-staging.up.railway.app/privacy' },
  { title: 'Terms of use', url: 'https://zephyr-web-staging.up.railway.app/terms' },
  { title: 'Account and data deletion', url: 'https://zephyr-web-staging.up.railway.app/delete-account' },
] as const;

export function LegalLinks() {
  const [error, setError] = useState<string | null>(null);

  async function openPage(url: string) {
    setError(null);
    try {
      await Linking.openURL(url);
    } catch {
      setError('Could not open this page. Please try again or contact visaatlasdigital@gmail.com.');
    }
  }

  return <Card>
    <Label>Privacy and support</Label>
    <Body>Read how Vesquiri handles your information and how to request deletion.</Body>
    {legalPages.map((page) => <Button key={page.url} title={page.title} variant="secondary" onPress={() => void openPage(page.url)} />)}
    {error && <ErrorNotice message={error} />}
  </Card>;
}
