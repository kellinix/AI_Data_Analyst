# Pro billing preparation

Vesquiri's web checkout is implemented for one Pro plan: **£19 GBP per month** (20 analyses, 100 follow-up questions and 1 GB of saved files). `starter` is the existing internal plan key for Pro. The public site keeps checkout closed until `STRIPE_BILLING_ENABLED=true` and all Stripe settings below are present. A successful browser redirect never grants Pro access; only a signed webhook reflecting an active or trialing subscription with the configured Pro price does.

## Configure in Stripe test mode first

1. Create a recurring monthly GBP price of exactly **1900 pence** for Pro. Record its `price_...` ID.
2. Create a dedicated Vesquiri customer portal configuration for payment-method updates, invoice history and cancellation at the end of the billing period. Set its privacy and terms links to Vesquiri's public policy pages. Record its `bpc_...` ID; do not change a shared Stripe account's default portal for other apps. Leave plan switching off while Vesquiri sells only one paid tier.
3. Add a Stripe webhook destination at `https://<backend-host>/api/v1/billing/webhook` for `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid` and `invoice.payment_failed`. Copy the destination's `whsec_...` signing secret.
4. Set these **backend-only** variables: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`, `STRIPE_PORTAL_CONFIGURATION_ID`, `FRONTEND_URL` and `APP_NAME=Vesquiri`. Keep `STRIPE_BILLING_ENABLED=false` until the test checklist passes. Use a dedicated application key for deployed billing; Stripe CLI login keys expire, and a local listener's webhook secret is different from a hosted destination's secret. The web client does not need a publishable key because checkout and the portal are Stripe-hosted.
5. Ensure the configured `FRONTEND_URL` is the public HTTPS website. The backend constructs return URLs from this setting; clients cannot supply their own redirect URL.
6. Configure a valid terms-of-service URL in the Stripe account before creating Checkout Sessions. Checkout requires consent and displays Vesquiri's own policy links and name through per-session settings. Check the legal business name, receipts and support details separately: a session display name does not change the Stripe account's business identity.

## Deploy the backend after approval

The staging backend must include the billing router and migration `008_billing_checkout_session`. Verify its Railway pre-deploy command is `alembic upgrade head`, with root directory `/backend`, before the approved deployment. Migration 008 adds two nullable columns to `subscriptions` and was exercised against a fresh disposable PostgreSQL database. The staging process launcher does not run migrations itself.

Use a release branch scoped to the backend so the website is not redeployed accidentally. Include the guarded checkout implementation, subscription reconciliation, cancellation before account deletion, and Vesquiri's checkout/portal settings. Configure the hosted Stripe test destination for `/api/v1/billing/webhook`, using that destination's signing secret. After deployment, verify backend health and billing availability, then repeat the signed-in website journey through payment, Pro allowances, portal and cancellation. Local harness results do not replace this staging check.

If the deployment fails, restore the previous backend release and keep checkout disabled. The nullable columns can remain during an application rollback; do not drop subscription data to roll back the application. Obtain approval before any rollback or configuration change that triggers another deployment.

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

This used a loopback-only test harness with a synthetic authenticated user and a disposable database. It verifies real Stripe checkout, webhook signatures and persisted subscription changes, but does not verify deployed Supabase authentication or the complete signed-in staging website journey. The staging billing endpoint was still absent when checked; live billing remains unconfigured. Do not turn on live billing based only on these local checks.

## Mobile stores

The Stripe checkout button exists on the **website only**. Do not add a mobile button that opens this web checkout without reviewing the applicable store rules. The [Apple App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) and [Google Play Payments policy](https://support.google.com/googleplay/android-developer/answer/9858738?hl=en) govern in-app purchases of digital features. Native store billing and receipt reconciliation remain separate launch work if Pro will be sold inside the iOS or Play-distributed app.

Every change to a deployed billing variable can trigger a redeployment. Follow `AGENTS.md`: get explicit approval for each staging or production deployment before changing cloud variables or pushing to an auto-deploy branch.
