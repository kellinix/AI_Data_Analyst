import { useQuery } from '@tanstack/react-query';
import { Platform } from 'react-native';
import type { UserProfile } from '../generated/contracts';
import { Body, Button, Card, ErrorNotice, Heading, Label, Loading, Screen } from '../components/ui';
import { LegalLinks } from '../components/legal-links';
import { api } from '../lib/api';
import { offerCopy } from '../lib/store-purchases';
import { useAuth } from '../providers/auth';
import { useStorePurchases } from '../providers/purchase-context';

export default function Purchases() {
  const { session } = useAuth();
  const purchase = useStorePurchases();
  const profile = useQuery({ queryKey: ['profile', session?.user.id], queryFn: ({ signal }) => api<UserProfile>('/users/me', { signal }) });
  const paid = !!profile.data && profile.data.plan !== 'free';
  return <Screen><Heading title="Vesquiri Pro" subtitle="More room for your data and questions." />
    <Card><Label>Included with Pro</Label><Body>20 analyses and 100 follow-up questions each calendar month, with 1 GB of saved files.</Body>
      <Body>Buying access does not reset your usage. The seven-day pass uses these same calendar-month allowances.</Body></Card>
    {purchase.loading && <Loading label="Loading store options…" />}
    {purchase.error && <ErrorNotice message={purchase.error} />}
    {purchase.notice && <Body>{purchase.notice}</Body>}
    {paid ? <Card><Label>Your account already has paid access</Label><Body>You can use the same access on the website and your other devices when you sign in to this account. Manage any subscription with the provider where you bought it.</Body></Card>
      : purchase.offers.map(({ offer, price }) => <Card key={offer}><Label>{offerCopy(offer).title}</Label>
        <Body>{price}{offer === 'monthly' ? ' per month' : ' once'}</Body><Body>{offerCopy(offer).terms}</Body>
        <Button title={offer === 'monthly' ? `Subscribe for ${price} per month` : `Buy seven days for ${price}`}
          loading={purchase.busy} disabled={!purchase.available || purchase.busy || purchase.status?.pending || !profile.data}
          onPress={() => void purchase.buy(offer)} /></Card>)}
    {!purchase.loading && !purchase.available && <Body>Store purchases are not available yet. Your current account access continues to work.</Body>}
    {purchase.status?.pending && <Body>A purchase is awaiting confirmation or an existing subscription may still renew. Restore purchases or manage that subscription before buying again.</Body>}
    {purchase.available && <><Button title="Restore purchases" variant="secondary" loading={purchase.busy} onPress={() => void purchase.restore()} />
      {purchase.status?.purchases.some(item => item.autoRenew && item.store === (Platform.OS === 'ios' ? 'apple' : 'google')) && <Button title="Manage store subscriptions" variant="secondary" disabled={purchase.busy} onPress={() => void purchase.manage()} />}</>}
    <Body>Monthly subscriptions renew automatically unless cancelled through your Apple or Google account. A seven-day pass does not renew. The store confirms the final price before payment.</Body>
    <LegalLinks />
  </Screen>;
}
