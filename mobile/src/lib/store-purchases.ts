export type Store = 'apple' | 'google';
export type StoreOffer = 'monthly' | 'weekly';
export interface StoreStatus {
  available: Record<Store, boolean>;
  products: Record<Store, Record<StoreOffer, string>>;
  basePlans: Record<StoreOffer, string>;
  pending: boolean;
  purchases: { store: Store; offer: StoreOffer; status: string; expiresAt: string | null; autoRenew: boolean; active: boolean }[];
}
export interface PurchaseIntent { intent: string; accountToken: string; productId: string; basePlanId: string }

export function offerCopy(offer: StoreOffer) {
  return offer === 'monthly'
    ? { title: 'Pro monthly', terms: 'Renews monthly until cancelled in your store account.' }
    : { title: 'Seven-day Pro pass', terms: 'One payment for seven days. Does not renew automatically.' };
}

/** Only the configured, undiscounted base plan is offered in this first release. */
export function basePlanOffer<T extends { id: string; basePlanIdAndroid?: string | null; offerTokenAndroid?: string | null }>(offers: T[], basePlanId: string): T {
  // OpenIAP maps a base-plan-only offer's id to basePlanId; promotional
  // offers instead carry Google's offerId. Never select an arbitrary offer.
  const matches = offers.filter(offer => offer.basePlanIdAndroid === basePlanId && offer.id === basePlanId && offer.offerTokenAndroid);
  if (matches.length !== 1) throw new Error('This purchase option is not available from the store yet.');
  return matches[0];
}

export function subscriptionOfferToken(offers: Parameters<typeof basePlanOffer>[0], basePlanId: string): string {
  return basePlanOffer(offers, basePlanId).offerTokenAndroid!;
}

export function purchaseGuidance(key: string): string {
  const text: Record<string, string> = {
    payment_pending: 'Your store is still confirming payment. Access starts after confirmation. Please do not buy again.',
    change_pending: 'Your store is still confirming the change. Your current access continues.',
    verification_delayed: 'Confirmation is delayed. Use Restore purchases later; please do not buy again.',
    owned_by_another_account: 'This purchase belongs to another Vesquiri account. Sign in to the account used to buy it.',
    test_purchase_not_accepted: 'This test purchase is not enabled for this account.',
    purchase_not_valid: 'The store reports that this purchase does not currently grant access.',
    access_pending: 'The store purchase is being linked to your account. Try Restore purchases shortly.',
    access_granted: 'Your Pro access is confirmed.',
    try_again_later: 'We could not confirm this purchase yet. Try Restore purchases later; please do not buy again.',
  };
  return text[key] ?? text.try_again_later;
}
