import type { PropsWithChildren } from 'react';

// Web uses its existing Stripe pricing page; native store code is never loaded.
export function PurchaseProvider({ children }: PropsWithChildren) { return children; }
