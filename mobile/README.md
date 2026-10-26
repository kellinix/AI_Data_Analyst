# Zephyr mobile

Android and iOS app built with Expo SDK 57, React Native and Expo Router. It uses
the existing FastAPI API and Supabase accounts.

## Included

Email and Google sign-in, registration and password recovery; analysis search and status
polling; single-file uploads with progress; dashboards with offline-rendered
interactive charts, KPIs and recommendations; recommendation feedback; AI chat;
PDF/Excel export and sharing; profile updates, sign-out and account deletion.
Native sessions use encrypted SecureStore storage. API calls read the current
access token. Missing configuration shows setup instructions.

Multi-file analysis, live dashboard filters, other social providers, push notifications
and offline data synchronization are not included in this first version.

## Local development

Use Node 22.13 or newer. From this directory:

```powershell
npm ci
Copy-Item .env.example .env # only when .env does not already exist
npm start
```

Fill in the three `EXPO_PUBLIC_*` values in `.env`. These values are public and
are bundled into the app. Never use a Supabase service-role key or server API key.
The working tree has an ignored local `.env` configured for the Android emulator
and the existing public Supabase settings.

For Android emulator testing, the computer's API URL is
`http://10.0.2.2:8000`. For a physical Android/iPhone device, use the computer's
LAN IP, for example `http://192.168.1.20:8000`, on the same Wi-Fi. An iOS simulator
on a Mac uses the API host reachable from that Mac. Replace local Supabase host
addresses the same way. Start the existing backend and its database/worker
dependencies, binding the API to `0.0.0.0`; allow the ports through the firewall.
From the repository root, start all services required for analysis processing:

```powershell
docker compose up -d postgres redis backend celery_worker
```

The backend can accept uploads while `celery_worker` is stopped, but those
analyses remain queued at 0% until the worker starts. Keep it running during testing.

For browser preview, set `EXPO_PUBLIC_WEB_API_URL=http://localhost:8000`. The
browser uses this override while native builds continue to use
`EXPO_PUBLIC_API_URL`. Allow the preview origin (normally ports 8081 or 8082) in
`BACKEND_CORS_ORIGINS` and recreate the backend container after changing it.

Install a development build before running `npm start -- --dev-client`.
For a physical Android connected through USB debugging, authorize the computer
on the phone and use USB port forwarding:

```powershell
adb reverse tcp:8000 tcp:8000
adb reverse tcp:8081 tcp:8081
$env:EXPO_PUBLIC_API_URL = 'http://127.0.0.1:8000'
npm start -- --dev-client --lan --port 8081
```

Open the development client with server URL `http://127.0.0.1:8081`.
If relaunching the app shows the Zephyr Development Build launcher, select its
recent Zephyr server (or enter that URL) and wait for Metro to finish bundling
before testing sign-in. A previously loaded screen can still use an older
JavaScript bundle and an outdated OAuth redirect.
Keep USB connected. `--lan` lets Metro accept IPv4 USB-forwarded requests;
on this Windows setup `--localhost` bound only to IPv6 and failed over USB.
The environment override above applies to that development-server process.
If Metro reports `UnexpectedServerError` while requesting the Android manifest
because the Expo account API is unavailable, start it with
`$env:EXPO_OFFLINE = '1'` in the same PowerShell session. Confirm that
`EXPO_PUBLIC_API_URL` resolves to `http://127.0.0.1:8000` for this USB setup;
`10.0.2.2` works only for an Android emulator. Re-run `adb reverse` after
unplugging or reconnecting the phone, since those routes may disappear.

Use `npm start -- --web` for a browser preview. Browser testing additionally
needs the preview origin in the backend CORS configuration. Full native callback
testing uses the development build's `zephyr` URL scheme.

Enable the Google provider in Supabase Auth and add `zephyr://auth/callback`
to the Supabase redirect allow list. Google sign-in uses the same Supabase
account as the website and returns through this deep link. Also allow the
recovery variant `zephyr://auth/callback?type=recovery`. Email confirmation and
recovery use PKCE and must open on the device where they were initiated. Configure
the existing backend with the same Supabase project. Account deletion requires
the backend service-role configuration and migration `004_completion_exports`.
For local website auth in the same project, also allow
`http://localhost:3000/auth/callback` and
`http://localhost:3000/auth/callback?redirectTo=**`; the latter covers the
requested page after sign-in. Use HTTPS callback URLs for deployments.

If Google sign-in on a phone ends at `localhost:3000` with “This site can’t be
reached”, Supabase has fallen back to the website Site URL instead of the native
callback. Check **Authentication → URL Configuration → Redirect URLs** in the
project named by `EXPO_PUBLIC_SUPABASE_URL`, add the exact
`zephyr://auth/callback` URL, and retry Google sign-in. The website Site URL can
remain `http://localhost:3000` for local web testing.

## Builds

The app is linked to [its EAS project](https://expo.dev/accounts/visaatlasdigital/projects/zephyr-mobile).
Builds run in the cloud; Windows can request both platforms.

```powershell
npx eas-cli@latest build --platform android --profile development
npx eas-cli@latest build --platform ios --profile simulator
```

Android development builds are installable APKs. The `simulator` profile produces
an iOS simulator app that runs on a Mac, not an iPhone. An iPhone development build
uses `--platform ios --profile development` and requires Apple signing credentials
and registered devices. Development builds load the app from your local Metro
server; restart Metro after changing `.env`.

Before a standalone preview or store build, configure the public environment
values in EAS, use a deployed HTTPS API/Supabase server and choose owned bundle
identifiers using `ZEPHYR_ANDROID_PACKAGE` and `ZEPHYR_IOS_BUNDLE_IDENTIFIER`.
Runtime release configuration requires HTTPS. `.easignore` deliberately excludes
local `.env` files, backend code, datasets and generated output. Only the mobile
app and canonical frontend type source are uploaded. Production builds are not
automatically submitted to either store.

## Verification

```powershell
npm run type-check
npm run lint
npm test
npm run doctor
npm run export
```

Eleven focused tests cover encrypted session integrity/concurrency, fresh tokens,
API errors/timeouts, chart serialization and KPI formatting. All passed, along
with type checking, lint, Expo Doctor and Android/iOS/web JavaScript exports.
Exported bundles alone are not native binaries.

`node tests/ui-smoke.mjs` tests the app served on port 8082, using the frontend's
existing Playwright installation. Start that preview with API URL
`http://127.0.0.1:8000`, Supabase URL `https://mobile-fixture.invalid` and anon key
`fixture-public-key`. It intercepts every auth/API request and verifies login,
dashboard chart rendering, feedback, PDF download, chat, upload, profile and
sign-out. Its screenshots in `artifacts/` contain fixture data. Real device,
email callback and live backend validation remain necessary before release.

Shared API contracts and the installed ECharts runtime are generated by
`scripts/prepare-assets.mjs` during installation, start and export. The generated
directory is ignored. The mobile CI workflow checks types, lint, tests,
dependency alignment and cross-platform exports. Upstream Expo dependencies
still report npm audit advisories; review those before a production release.
