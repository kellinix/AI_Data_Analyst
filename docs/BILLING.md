# Pro billing preparation

Zephyr's web checkout is implemented for one Pro plan: **£19 GBP per month** (20 analyses, 100 follow-up questions and 1 GB of saved files). `starter` is the existing internal plan key for Pro. The public site keeps checkout closed until `STRIPE_BILLING_ENABLED=true` and all Stripe settings below are present. A successful browser redirect never grants Pro access; only a signed webhook reflecting an active or trialing subscription with the configured Pro price does.

## Configure in Stripe test mode first

1. Create a recurring monthly GBP price of exactly **1900 pence** for Pro. Record its `price_...` ID.
2. Configure the customer portal for payment-method updates, invoice history and cancellation at the end of the billing period. Leave plan switching off while Zephyr sells only one paid tier.
3. Add a Stripe webhook destination at `https://<backend-host>/api/v1/billing/webhook` for `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid` and `invoice.payment_failed`. Copy the destination's `whsec_...` signing secret.
4. Set these **backend-only** variables: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`, `FRONTEND_URL`. Keep `STRIPE_BILLING_ENABLED=false` until the test checklist passes. The web client does not need a publishable key because checkout and the portal are Stripe-hosted.
5. Ensure the configured `FRONTEND_URL` is the public HTTPS website. The backend constructs return URLs from this setting; clients cannot supply their own redirect URL.

## Test before enabling purchases

- In Stripe test mode, sign in as a new Free user. Open the pricing page. With billing disabled, it must say Pro is closed and must not start checkout.
- Enable billing **only in an isolated local or approved test environment** with test keys, then start checkout twice. Both requests must reuse the same open session. Confirm Stripe displays £19 per month before using a test card.
- After test payment, verify `/api/v1/users/me` shows Pro allowances (20 analyses, 100 questions, 1 GB) and Settings opens the Stripe billing portal.
- Test cancellation at period end: access remains Pro until the period ends, then returns to Free when Stripe reports cancellation. Test a failed renewal: status moves to `past_due` or `unpaid` and access returns to Free. Verify duplicate and delayed webhook deliveries do not restore stale access.
- Test account deletion with an active subscription: Zephyr must cancel the Stripe subscription immediately before deleting the account. If Stripe cancellation fails, account deletion must stop so billing can be retried safely.
- Test a bad webhook signature and a signature older than five minutes; both must return HTTP 400. Verify a wrong Stripe price is rejected before checkout and cannot grant Pro access.
- Check taxes, customer-facing terms, refund policy, support contact and receipt wording before charging real customers. These depend on the business and Stripe account setup.

The local automated suite covers checkout creation and reuse, wrong price, duplicate subscriptions, billing portal ownership, signed webhook delivery, cancellation, payment failure and stale-event handling. A **real Stripe test-mode payment** has not been run until a test account, price and webhook destination are configured. Do not turn on live billing based only on mocked tests.

## Mobile stores

The Stripe checkout button exists on the **website only**. Do not add a mobile button that opens this web checkout without reviewing the applicable store rules. The [Apple App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) and [Google Play Payments policy](https://support.google.com/googleplay/android-developer/answer/9858738?hl=en) govern in-app purchases of digital features. Native store billing and receipt reconciliation remain separate launch work if Pro will be sold inside the iOS or Play-distributed app.

Every change to a deployed billing variable can trigger a redeployment. Follow `AGENTS.md`: get explicit approval for each staging or production deployment before changing cloud variables or pushing to an auto-deploy branch.
