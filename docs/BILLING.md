# Web billing

Native Apple/Google purchases are implemented separately; see [store purchase setup and release gates](STORE_PURCHASES.md). They remain disabled until credentials, store setup and signed sandbox tests are complete.

Vesquiri offers **£19 GBP per month**, renewing until canceled, and **£5.99 once for seven days of Pro**. The seven-day pass never creates a subscription or renews. Both use Pro's existing calendar-month allowances: 20 analyses, 100 follow-up questions and 1 GB of saved files. Buying either option does not reset usage counts. `starter` is the internal plan key for Pro.

Checkout remains closed until `STRIPE_BILLING_ENABLED=true` and the corresponding price, secret key and webhook secret are configured. A browser redirect never grants access. Monthly access follows verified Stripe subscription state; a pass follows a verified, captured payment for the configured one-time price.

## Seven-day pass behavior

- Checkout uses `mode=payment`, GBP 599 pence, one line item and quantity one. The configured price must be `one_time`, not a weekly recurring price. Checkout displays the duration, lack of renewal and unchanged usage counts, and creates an invoice for the purchase.
- Access starts at the captured charge's original timestamp and ends exactly 168 hours later. The `pro_passes` table retains unique Checkout Session and PaymentIntent IDs. Duplicate or concurrent webhooks cannot create another pass or extend its deadline. A delayed event arriving after the deadline cannot start a fresh week.
- Authentication enforces expiry before protected operations and quota checks. A scheduler or a visit to Settings is not required. After expiry, Free allowances apply; saved files are not deleted automatically. Expiring or refunding a pass does not remove a valid monthly entitlement.
- A full refund or dispute revokes the pass. The webhook handler refetches current payment state, so a late success event cannot restore refunded access. Partial refunds do not automatically revoke it. An existing revocation is not automatically reversed by later event delivery.
- An active pass or an existing recurring subscription blocks another checkout. Switching an unpaid checkout between durations expires the old payable link. A completed payment awaiting its webhook blocks another charge.

## Payment methods

Set backend-only `STRIPE_PAYMENT_METHOD_CONFIGURATION_ID` to a dedicated, nondefault Stripe payment-method configuration for Vesquiri. The backend passes this configuration to Checkout instead of forcing `payment_method_types=card`. If the setting is empty, Checkout remains card-only; it never inherits a shared account's default configuration.

The live configuration is `pmc_1UXnCzEt6mZEzRhBpzhlM1ln` (Vesquiri web checkout). Chrome's live Stripe dashboard confirmed Cards, PayPal, Klarna, Pay by Bank and Stripe's default Link wallet enabled, with zero methods requiring action. Existing shared configurations were not changed. After explicit approval, backend deployment `9fa9e624-7751-44a0-b73c-6430f7efc3d8` activated this setting with release `edd2c8a668ae7a176a613c790f35a9300a7be041`.

Stripe selects eligible methods based on the purchase mode, currency, amount and customer location. PayPal and Klarna are configured for both offers, subject to provider eligibility. UK Pay by Bank is for the one-time seven-day pass: Stripe Checkout does not support it in subscription mode. Bacs Direct Debit is not enabled. See [payment-method configurations](https://docs.stripe.com/payments/payment-method-configurations) and [Pay by Bank support](https://docs.stripe.com/payments/pay-by-bank).

An existing open Checkout Session is reused only when its offer and payment-method configuration match. Otherwise it is expired before a replacement is created. A completed, unpaid session permits a fresh checkout only after Stripe reports its PaymentIntent as `requires_payment_method` or `canceled`; processing, action-required and unconfirmed successful payments continue to block another purchase. Starting or returning from checkout never grants Pro. Verified successful payment and signed webhook processing remain required.

## Configure in Stripe test mode first

1. Create a recurring monthly GBP price of exactly **1900 pence**, and a separate one-time GBP price of exactly **599 pence** for the pass. Record both `price_...` IDs.
2. Create a dedicated Vesquiri customer portal configuration for payment-method updates, invoice history and cancellation at the end of the billing period. Set its privacy and terms links to Vesquiri's public policy pages. Record its `bpc_...` ID; do not change a shared Stripe account's default portal for other apps. Leave plan switching off while Vesquiri sells only one paid tier.
3. Add a Stripe webhook destination at `https://<backend-host>/api/v1/billing/webhook` for `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`, `charge.refunded` and `charge.dispute.created`. Copy that destination's `whsec_...` signing secret.
4. Set these **backend-only** variables: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`, `STRIPE_WEEKLY_PRICE_ID`, `STRIPE_PORTAL_CONFIGURATION_ID`, optionally `STRIPE_PAYMENT_METHOD_CONFIGURATION_ID` as described above, `STRIPE_LIVE_MODE=false`, `FRONTEND_URL` and `APP_NAME=Vesquiri`. Keep `STRIPE_BILLING_ENABLED=false` until the test checklist passes. Use a dedicated application key for deployed billing; Stripe CLI login keys expire, and a local listener's webhook secret is different from a hosted destination's secret. The web client does not need a publishable key because checkout and the portal are Stripe-hosted.
5. Ensure the configured `FRONTEND_URL` is the public HTTPS website. The backend constructs return URLs from this setting; clients cannot supply their own redirect URL.
6. Configure a valid terms-of-service URL in the Stripe account before creating Checkout Sessions. Checkout requires consent and displays Vesquiri's own policy links and name through per-session settings. Check the legal business name, receipts and support details separately: a session display name does not change the Stripe account's business identity.

## Deploy the backend after approval

The backend must include the billing router and migration `009_weekly_pro_pass`. Verify its Railway pre-deploy command is `alembic upgrade head`, with root directory `/backend`, before the approved deployment. Migration 009 adds the pass ledger, nullable user entitlement fields and billing-mode fields; it tags the earlier deployed sandbox entitlements explicitly. Its fresh upgrade, downgrade, and upgrade with an existing sandbox subscriber were verified in a disposable PostgreSQL database. The process launcher does not run migrations itself.

Use a release branch scoped to the backend so the website is not redeployed accidentally. Include the guarded checkout implementation, subscription reconciliation, cancellation before account deletion, and Vesquiri's checkout/portal settings. Configure the hosted Stripe test destination for `/api/v1/billing/webhook`, using that destination's signing secret. After deployment, verify backend health and billing availability, then repeat the signed-in website journey through payment, Pro allowances, portal and cancellation. Local harness results do not replace this staging check.

If the deployment fails, restore the previous backend release and keep checkout disabled. The nullable columns can remain during an application rollback; do not drop subscription data to roll back the application. Obtain approval before any rollback or configuration change that triggers another deployment.

## Promoting the existing Railway website to live billing

The selected public website remains `https://zephyr-web-staging.up.railway.app`; the hostname alone does not select Stripe mode. Use a dedicated live server key, live monthly and one-time prices, a live portal configuration and a live webhook destination, with `STRIPE_LIVE_MODE=true` and `APP_ENV=production`. The key prefix must match the selected billing mode. Never deploy the temporary CLI credential as the production server key.

Subscription customer records and paid entitlements carry their Stripe mode. Earlier sandbox Pro access is removed when the same site is promoted; it is not treated as a live purchase. Live checkout creates a live customer instead of reusing a test customer ID. A sandbox deployment cannot overwrite live customer records or delete an account while leaving its live recurring billing running. Cross-mode webhook events are ignored. These safeguards do not themselves enable live payments.

The live catalogue, dedicated portal and live webhook are configured. The backend uses a dedicated restricted application key, with catalogue read access and the customer, checkout, subscription and portal permissions needed at runtime. Catalogue writes and webhook administration are not granted to that key. Keys must stay outside Git and chat, and only in the backend's private deployment configuration.

## Test before enabling purchases

- In Stripe test mode, sign in as a new Free user. Open the pricing page. With billing disabled, it must say Pro is closed and must not start checkout.
- Enable billing **only in an isolated local or approved test environment** with test keys, then start checkout twice. Both requests must reuse the same open session. Confirm Stripe displays £19 per month before using a test card.
- After test payment, verify `/api/v1/users/me` shows Pro allowances (20 analyses, 100 questions, 1 GB) and Settings opens the Stripe billing portal.
- Test cancellation at period end: access remains Pro until the period ends, then returns to Free when Stripe reports cancellation. Test a failed renewal: status moves to `past_due` or `unpaid` and access returns to Free. Verify duplicate and delayed webhook deliveries do not restore stale access.
- Test account deletion with an active subscription: Vesquiri must cancel the Stripe subscription immediately before deleting the account. If Stripe cancellation fails, account deletion must stop so billing can be retried safely.
- Test a bad webhook signature and a signature older than five minutes; both must return HTTP 400. Verify a wrong Stripe price is rejected before checkout and cannot grant Pro access.
- Check taxes, customer-facing terms, refund policy, support contact and receipt wording before charging real customers. These depend on the business and Stripe account setup.

The local automated suite covers checkout creation and reuse, wrong price, duplicate subscriptions, billing portal ownership and configuration, signed webhook delivery, cancellation, payment failure and stale-event handling.

On 3 November 2026, an actual Stripe test-mode card payment completed for Vesquiri's £19 monthly test price. Signed Stripe events delivered through the CLI listener changed an isolated PostgreSQL user from Free to Pro, cleared the pending checkout, and retained Pro when cancellation was scheduled at period end. Immediate cancellation then changed that user back to Free. A Stripe-hosted portal session was also created successfully. No live payment was made, and the synthetic subscription was canceled after testing.

The first test used a loopback-only harness with a synthetic authenticated user and a disposable database. The 42 billing and account-deletion checks passed, including the PostgreSQL lifecycle test; that database test also passed when repeated, and Ruff passed for the changed backend files.

### Approved staging verification, 3 November 2026

Railway deployment `e8b2b7fc-d5a7-4c33-9874-0b755f0f6285` deployed commit `65c2d8443adc9e62c2c04be14d5b9f739455ae24` from `staging/vesquiri-billing-2026-11-03`. Its logs confirmed migration 007 to 008 ran. Backend health returned `healthy` with database `ok`; billing availability returned `enabled: true`. Unsigned webhook requests returned HTTP 400 and unauthenticated checkout requests returned HTTP 401.

Using the existing signed-in `visaatlasdigital@gmail.com` browser session, Settings opened an actual Stripe sandbox checkout for Vesquiri Pro at £19 monthly. The synthetic card payment completed, Stripe reported `paid`, and the hosted signing destination delivered the subscription events. Returning to Settings showed Pro with 20 analyses and 100 follow-up questions, while the account's existing usage remained unchanged.

Manage billing opened the dedicated Stripe customer portal, showing Vesquiri Pro, its paid invoice and payment-method controls. Cancellation through that portal scheduled the subscription to end at period end; the delivered update left Pro active in Vesquiri. Immediate cancellation of that same verified test subscription then delivered the cancellation event, and refreshing Settings showed Free with its original allowances. No live payment was made and no test subscription was left renewing. This used an existing authenticated session; it did not repeat a fresh Google sign-in flow.

That staging test used a CLI-issued sandbox credential. The subsequently approved live release replaced it with a dedicated restricted live application key, live prices and a live webhook destination. The sandbox checks above establish the earlier test-mode lifecycle; live verification below used unpaid sessions only.

### Weekly release verification, 3 November 2026

The weekly release was deployed after approval as commit `9326785c1d6440e9314c42452fb1febb4c6dee96`. Backend deployment `a46833ac-030d-4ce9-a0a5-31fce813dbc4` and frontend deployment `64258576-e1ea-4cdf-a353-1f8bd8446694` succeeded. Backend logs confirmed migration 009 and production mode. Health reported a healthy database and both billing offers enabled. All **79 backend checks**, including PostgreSQL persistence, concurrent delivery, refunds, disputes, expiry, mode transition and account-deletion safeguards, passed before release. The **17 frontend tests**, TypeScript check and local production build passed. Backend Ruff passed. Frontend lint reported no errors and the pre-existing payment-confirmation effect warning.

An actual £5.99 Stripe sandbox checkout completed with the synthetic test card. It created no subscription. Signed webhook delivery granted the isolated test account Pro until exactly seven days after the captured charge timestamp. A full sandbox refund succeeded, and its signed webhook restored Free and cleared pass expiry. The checkout also reused the existing open session when requested twice. This payment used a loopback-only harness and disposable database with synthetic authentication; it did not run the new weekly flow on the deployed website. The existing monthly flow was separately verified on staging above.

On the deployed website, the signed-in Google test account opened a live £5.99 one-time checkout with the expected seven-day and nonrenewal wording. Owner/customer bindings were checked and the session was expired unpaid. Separate unpaid live sessions verified both offer prices, and a live portal session was created. Unsigned webhooks returned 400, unauthenticated checkout returned 401, and a correctly signed no-op webhook returned 200. No live payment was attempted.

### Additional payment-method verification, 3 November 2026

The new backend changes pass **72 targeted billing and account-deletion tests** plus Ruff. These cover selecting the scoped method configuration, retaining the card fallback, replacing older card-only sessions, safe checkout reuse, retry after a failed bank payment and preventing another purchase while payment confirmation is pending.

Actual unpaid Stripe sandbox sessions using the scoped test configuration `pmc_1UXn2VEt6mZEzRhB8nFDLF6f` returned `card`, `paypal`, `klarna` and `pay_by_bank` for GBP 599 one-time checkout, and `card`, `paypal` and `klarna` for GBP 1900 monthly checkout. Both sessions were expired and their temporary customer deleted. These checks verify provider eligibility and session creation; they do not establish successful PayPal, Klarna or bank-payment settlement. The live configuration's enabled methods were verified separately in Chrome. A later CLI recheck returned an invalid CLI API key; the deployed dedicated application key was not changed.

Following the approved backend deployment, Railway reported deployment successful and production application startup complete. Public health returned `healthy` with database `ok`; both billing offers remained enabled. The existing signed-in Google test account opened the actual website's live £5.99 checkout, which displayed Card, Pay by Bank, PayPal and Klarna. Switching to the £19 monthly offer opened live checkout displaying Card, PayPal and Klarna, with monthly renewal wording and no Pay by Bank option. Both checkout pages were left through their return links without entering payment details or attempting a charge. The weekly session was replaced when switching offers; the final monthly session was left unpaid. Successful live settlement was not tested.

## Mobile stores

The Stripe checkout button exists on the **website only**. Do not add a mobile button that opens this web checkout without reviewing the applicable store rules. The [Apple App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) and [Google Play Payments policy](https://support.google.com/googleplay/android-developer/answer/9858738?hl=en) govern in-app purchases of digital features. Native store billing and receipt reconciliation remain separate launch work if Pro will be sold inside the iOS or Play-distributed app.

Every change to a deployed billing variable can trigger a redeployment. Follow `AGENTS.md`: get explicit approval for each staging or production deployment before changing cloud variables or pushing to an auto-deploy branch.
