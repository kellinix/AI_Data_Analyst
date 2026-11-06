import { useCallback, useEffect, useMemo, useRef, useState, type PropsWithChildren } from 'react';
import { AppState, Linking, Platform } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createPurchaseFlow, deepLinkToSubscriptions, describePurchaseFlowStatus, ErrorCode, toPurchaseConfirmationRequest, useIAP, type Purchase, type PurchaseConfirmation } from 'expo-iap';
import { api, messageOf } from '../lib/api';
import { createApi } from '../lib/api-core';
import { config } from '../lib/config';
import { basePlanOffer, purchaseGuidance, subscriptionOfferToken, type PurchaseIntent, type Store, type StoreOffer, type StoreStatus } from '../lib/store-purchases';
import { useAuth } from './auth';
import { PurchaseContext, type PurchaseContextValue } from './purchase-context';

const store: Store = Platform.OS === 'ios' ? 'apple' : 'google';

export function PurchaseProvider({ children }: PropsWithChildren) {
  const { session } = useAuth();
  const status = useQuery({ queryKey: ['store-status', session?.user.id], enabled: !!session,
    queryFn: ({ signal }) => api<StoreStatus>('/store-billing/status', { signal }), retry: false });
  const fallback = useMemo<PurchaseContextValue>(() => ({ loading: status.isFetching, busy: false, available: false,
    error: status.error ? messageOf(status.error) : null, notice: null, offers: [], status: status.data,
    buy: async () => {}, restore: async () => {}, manage: async () => {},
  }), [status.data, status.error, status.isFetching]);
  if (!session || !status.data?.available[store]) return <PurchaseContext.Provider value={fallback}>{children}</PurchaseContext.Provider>;
  return <ConnectedPurchases key={session.user.id} status={status.data} accessToken={session.access_token} accountId={session.user.id}>{children}</ConnectedPurchases>;
}

function ConnectedPurchases({ children, status, accessToken, accountId }: PropsWithChildren<{ status: StoreStatus; accessToken: string; accountId: string }>) {
  const queryClient = useQueryClient();
  const { session } = useAuth();
  const currentAccount = useRef(session?.user.id);
  useEffect(() => {
    currentAccount.current = session?.user.id;
    return () => { currentAccount.current = undefined; };
  }, [session?.user.id]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intent = useRef<string | null>(null);
  const capturedApi = useMemo(() => createApi(config.apiUrl, async () => accessToken), [accessToken]);
  const refresh = useCallback(async () => {
    await Promise.all([queryClient.invalidateQueries({ queryKey: ['profile'] }), queryClient.invalidateQueries({ queryKey: ['store-status'] })]);
  }, [queryClient]);
  const confirmWithBackend = useCallback(async (purchase: Purchase) => {
      if (currentAccount.current !== accountId) throw new Error('Account changed. Restore purchases after signing in again.');
      const result = await capturedApi<PurchaseConfirmation>('/store-billing/confirm', { method: 'POST', body: toPurchaseConfirmationRequest(purchase) });
      if (result.status === 'entitled') intent.current = null;
      await refresh();
      return result;
  }, [accountId, capturedApi, refresh]);
  // The SDK factory stores this callback; it never invokes it during render.
  // eslint-disable-next-line react-hooks/refs
  const flow = useMemo(() => createPurchaseFlow({ isConsumable: () => false, confirmWithBackend }), [confirmWithBackend]);
  useEffect(() => () => flow.dispose(), [flow]);

  const cancelIntent = useCallback(async () => {
    const id = intent.current;
    if (!id) return;
    await capturedApi('/store-billing/cancel-intent', { method: 'POST', body: { intent: id } });
    intent.current = null;
    await refresh();
  }, [capturedApi, refresh]);

  const iap = useIAP({ purchaseFlow: flow,
    onPurchaseFlowOutcome: ({ status: outcome }) => {
      setBusy(false);
      setNotice(purchaseGuidance(describePurchaseFlowStatus(outcome).key));
      if (outcome.status === 'entitled') void refresh();
    },
    onPurchaseError: (failure) => {
      setBusy(false);
      if (failure.code === ErrorCode.UserCancelled) {
        setNotice('Purchase cancelled.');
        void cancelIntent().catch(() => setError('Cancellation is still being confirmed. Try again shortly.'));
      } else setError('The store could not finish this purchase. Use Restore purchases before trying to pay again.');
    },
    onError: (failure) => setError(messageOf(failure)),
  });
  const { connected, fetchProducts, restorePurchases } = iap;
  const products = status.products[store];
  useEffect(() => {
    if (!connected) return;
    void fetchProducts({ skus: [products.monthly, ...(store === 'google' ? [products.weekly] : [])], type: 'subs' })
      .then(() => store === 'apple' ? fetchProducts({ skus: [products.weekly], type: 'in-app' }) : undefined)
      .catch(() => setError('Store prices are unavailable. Try again later.'));
  }, [connected, fetchProducts, products.monthly, products.weekly]);
  useEffect(() => {
    const listener = AppState.addEventListener('change', state => {
      if (state === 'active' && connected) void flow.recoverPurchases().then(refresh).catch(() => setNotice(purchaseGuidance('try_again_later')));
    });
    return () => listener.remove();
  }, [connected, flow, refresh]);

  const allProducts = [...iap.subscriptions, ...iap.products];
  const offers = (['monthly', 'weekly'] as const).flatMap(offer => {
    const product = allProducts.find(item => item.id === products[offer]);
    if (!product) return [];
    try {
      const price = store === 'google'
        ? basePlanOffer(iap.subscriptions.find(item => item.id === product.id)?.subscriptionOffers ?? [], status.basePlans[offer]).displayPrice
        : product.displayPrice;
      return [{ offer, price }];
    } catch { return []; }
  });
  async function buy(offer: StoreOffer) {
    if (!connected || busy) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      // Validate the selected store offer before reserving a purchase on the server.
      const googleToken = store === 'google' ? subscriptionOfferToken(
        iap.subscriptions.find(item => item.id === products[offer])?.subscriptionOffers ?? [], status.basePlans[offer]) : null;
      const prepared = await capturedApi<PurchaseIntent>('/store-billing/prepare', { method: 'POST', body: { store, offer } });
      intent.current = prepared.intent;
      if (store === 'apple') {
        await iap.requestPurchase({ type: offer === 'monthly' ? 'subs' : 'in-app', request: { apple: {
          sku: prepared.productId, appAccountToken: prepared.accountToken, andDangerouslyFinishTransactionAutomatically: false,
        } } });
      } else {
        await iap.requestPurchase({ type: 'subs', request: { google: {
          skus: [prepared.productId], obfuscatedAccountId: prepared.accountToken,
          subscriptionOffers: [{ sku: prepared.productId, offerToken: googleToken! }],
        } } });
      }
    } catch (failure) {
      setBusy(false);
      if (typeof failure === 'object' && failure && 'code' in failure && failure.code === ErrorCode.UserCancelled) {
        await cancelIntent().catch(() => {}); setNotice('Purchase cancelled.');
      } else setError(messageOf(failure));
    }
  }
  async function restore() {
    setBusy(true); setError(null); setNotice(null);
    try { await restorePurchases(); await refresh(); setNotice('Purchases checked. Your plan reflects the access confirmed by the store.'); }
    catch { setError('We could not confirm all purchases yet. Try Restore purchases again later; please do not buy again.'); }
    finally { setBusy(false); }
  }
  async function manage() {
    try {
      if (store === 'apple') await Linking.openURL('https://apps.apple.com/account/subscriptions');
      else await deepLinkToSubscriptions({ packageNameAndroid: 'com.zephyr.analytics', skuAndroid: products.monthly });
    } catch { setError('Your store subscriptions could not be opened. Open subscriptions in your store account.'); }
  }
  return <PurchaseContext.Provider value={{ loading: !connected, busy, available: connected, error, notice, status, offers, buy, restore, manage }}>{children}</PurchaseContext.Provider>;
}
