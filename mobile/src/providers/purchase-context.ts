import { createContext, useContext } from 'react';
import type { StoreOffer, StoreStatus } from '../lib/store-purchases';

export interface PurchaseContextValue {
  loading: boolean;
  busy: boolean;
  available: boolean;
  error: string | null;
  notice: string | null;
  status?: StoreStatus;
  offers: { offer: StoreOffer; price: string }[];
  buy: (offer: StoreOffer) => Promise<void>;
  restore: () => Promise<void>;
  manage: () => Promise<void>;
}
export const PurchaseContext = createContext<PurchaseContextValue>({
  loading: false, busy: false, available: false, error: null, notice: null, offers: [],
  buy: async () => {}, restore: async () => {}, manage: async () => {},
});
export const useStorePurchases = () => useContext(PurchaseContext);
