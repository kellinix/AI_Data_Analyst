# Native store purchases

Implementation is local and disabled by default. No purchase release or backend deployment has been approved for this work. Store transactions still require tests on signed store-distributed builds.

## Offers

| Offer | Apple product | Google product / base plan | UK price |
| --- | --- | --- | --- |
| Monthly Pro | `com.zephyr.analytics.pro.monthly` (auto-renewable, ONE_MONTH) | `vesquiri_pro_monthly` / `monthly` (P1M auto-renewing) | £19/month |
| Seven-day Pro | `com.zephyr.analytics.pro.seven_day` (non-renewing subscription) | `vesquiri_pro_seven_day` / `seven-days` (P1W prepaid, no automatic renewal) | £5.99 once |

Both grant the existing `starter` plan: 20 analyses, 100 follow-up questions per calendar month, 1 GB storage. Purchase, renewal and restore never reset usage counters. The website remains on Stripe; mobile uses StoreKit 2 and Google Play Billing through `expo-iap`.

The Apple products were created as drafts on 6 November 2026 in app `6829941087`, bundle `com.zephyr.analytics`: group `22553537`, monthly `6831753107`, pass `6831753132`. English (UK) descriptions and pricing are saved. Monthly equalized prices: UK GBP19, US USD19, Canada CAD25, Australia AUD29. The pass uses GBP5.99 as its automatic equalization base. Availability is limited to those four countries, with new territories disabled. Neither product is submitted; review screenshots and the corresponding app release remain required.

Google Developer API returned `403 SERVICE_DISABLED` in project `visaatlas-da025` (1070654439987). The existing EAS Firebase admin credential was used only to audit access, not installed as a backend credential. Google catalogue creation and dedicated verification permissions remain pending.

Chrome confirmed Vesquiri's Play subscription page has no subscriptions and displays **Upload a new APK**, rather than Create subscription. The existing uploaded binary predates the billing module. A billing-enabled signed Android build must be uploaded to unlock that console flow; the Developer API is a separate configuration prerequisite.

## Server verification and account ownership

Migration `010_native_store_purchases` creates a separate purchase ledger and purchase reservation fields. A verified opaque backend User UUID is passed as Apple `appAccountToken` or Google `obfuscatedAccountId`. The backend requires that verified store value to match the signed-in account. Product IDs, base plans, duration, ownership, environment and expiry are checked server-side.

Apple JWS signatures use the official Apple library and public Apple certificate roots, including online certificate checks. A current App Store Server API lookup is required even for a valid older JWS; monthly transactions also require current subscription status. Google subscriptions use `purchases/subscriptionsv2.get`. Active purchases are acknowledged only after ownership, product and environment checks. Google tokens are encrypted at rest with a dedicated Fernet key; evidence is never returned in the status API.

Duplicate delivery is serialized by the account row lock and store/environment/purchase uniqueness. Older verification attempts cannot overwrite a later refund check. Each paid source is independent, so a store refund cannot remove a different valid Stripe pass/subscription or another store purchase. Every authenticated request enforces ledger expiry; provider outages cannot extend a verified deadline. A 15-minute reservation prevents concurrent purchase attempts, and pending payments or auto-renewing subscriptions awaiting recovery block another purchase. The app supports restore and subscription management. Only backend-confirmed results are finished.

Account deletion leaves the store ownership hash and transaction identity as a tombstone, with `user_id` set to NULL. Store notifications never recreate deleted users or transfer purchases. Account deletion does not cancel a store subscription; the app explains this before deletion.

Sandbox transactions grant access only when the backend User UUID is explicitly in `STORE_SANDBOX_USER_IDS`. This includes TestFlight and Play license-test purchases against the shared production backend. Never permit arbitrary sandbox evidence for public users.

## Backend-only configuration

All defaults are disabled/empty. Do not place any private key in `EXPO_PUBLIC_*` variables or a mobile bundle.

| Setting | Purpose |
| --- | --- |
| `APP_STORE_BILLING_ENABLED` | Enable only after Apple credentials, notifications and catalogue are ready |
| `PLAY_STORE_BILLING_ENABLED` | Enable only after Play credentials, notifications and catalogue are ready |
| `STORE_BUNDLE_ID` | `com.zephyr.analytics` |
| `APP_STORE_APP_ID` | `6829941087` |
| `APP_STORE_KEY_ID`, `APP_STORE_ISSUER_ID`, `APP_STORE_PRIVATE_KEY` | Dedicated Apple **In-App Purchase** key for the Server API; do not assume the EAS submission key supports this API |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` | Dedicated verification service account, limited to Vesquiri in Play Console; do not reuse the shared Firebase admin key |
| `STORE_TOKEN_ENCRYPTION_KEY` | Dedicated Fernet key; back it up securely before deployment and retain it when redeploying |
| `STORE_SANDBOX_USER_IDS` | JSON list of explicitly approved test-account backend UUIDs |
| `GOOGLE_PLAY_NOTIFICATION_AUDIENCE` | Exact HTTPS Google notification URL |
| `GOOGLE_PLAY_NOTIFICATION_EMAIL` | Dedicated Pub/Sub push identity email |

Store keys and encryption keys belong in the hosting provider's protected secrets. Creation of persistent access through the Windows UI requires explicit confirmation under the computer-use skill. Any hosting secret update, deployment or cloud build requires separate approval under AGENTS.md.

## Notifications and reconciliation

Apple App Store Server Notifications **V2** (production and sandbox) endpoint:
`https://zephyr-backend-staging.up.railway.app/api/v1/store-billing/apple/notifications`

Google RTDN Pub/Sub authenticated HTTPS push endpoint:
`https://zephyr-backend-staging.up.railway.app/api/v1/store-billing/google/notifications`

The Apple handler verifies the signed envelope then checks current transaction state. Google validates OIDC audience, verified identity email and package, then re-fetches purchase state; unauthenticated pushes never access provider verification or the ledger. Grant Google Play's publisher identity publish access only to the dedicated topic. Grant the Pub/Sub service agent token-creation access only to the push identity, not across the project.

Celery Beat schedules `reconcile_native_store_purchases` every 15 minutes. Worker and Beat must be running in production. Reconciliation checks active/pending/suspended receipts and recently expired monthly receipts. Watch successful notification responses and reconciliation counts; investigate repeated provider failures without logging receipts. Missing notifications can delay renewals/refunds until reconciliation but cannot extend the original verified deadline.

## Release gates

1. Complete dedicated credentials, Google API activation and catalogue setup. Check paid-app agreements and the app's financial/purchase-history disclosures in both consoles. Do not accept legal agreements on the account holder's behalf.
2. Finish local validation, create a scoped release candidate and obtain explicit deployment approval. Deploy migration 010 and backend/worker code before enabling either store; publish updated terms/privacy pages with separate approval.
3. Obtain explicit approval for signed iOS/Android cloud builds and test uploads. A JavaScript export is not a signed native build. `expo-iap` needs a fresh native binary and does not run in Expo Go.
4. Test each offer on TestFlight and a Play testing track with allowlisted accounts: purchase, customer cancellation, pending payment, restore/reinstall, sign-out/account switch, cross-device access, renewal, expiration, refund/revocation and unchanged usage. Test subscription management and account deletion without transferring ownership.
5. Capture genuine review screenshots from the tested paywall; submit purchases with the required app review. Remove testing-only access when testing ends. Public activation is a separately approved release.

## Local validation on 6 November 2026

- Isolated release-candidate backend suite: **792 passed, 17 skipped**. Following the final receipt-log and confirmation-contract checks, **66 focused native store checks** pass, including real PostgreSQL locking/idempotence, pending-payment settlement, restore, refunds, expiry, cross-provider access, tombstones, encrypted tokens, signed-notification guards and Apple/Google evidence handling.
- Migration 010: empty-database upgrade, downgrade to 009 and re-upgrade passed on an isolated loopback PostgreSQL cluster, using synthetic accounts only.
- Mobile: lint, TypeScript and **23 tests** passed; local Android, iOS and web exports passed. These do not verify StoreKit/Play billing on a signed binary.
- Website: **18 tests**, TypeScript and production build passed; lint has no errors and nine existing warnings. Updated privacy/terms and store-access wording remain local.

## Primary references

- [Expo purchase guide](https://docs.expo.dev/guides/in-app-purchases/)
- [OpenIAP purchase confirmation](https://www.openiap.dev/docs/features/validation)
- [Apple Server Library](https://github.com/apple/app-store-server-library-python)
- [Apple review guidelines](https://developer.apple.com/app-store/review/guidelines/)
- [Google billing security](https://developer.android.com/google/play/billing/security)
- [Google subscription management](https://support.google.com/googleplay/android-developer/answer/140504?hl=en)
