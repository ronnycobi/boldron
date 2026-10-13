# Mobile client (`frontend/`)

A Flutter client of the platform — a first-class consumer of the same backend
API the web app uses (see [`../docs/MOBILE_API.md`](../docs/MOBILE_API.md)). It
owns presentation, local state and mobile interaction only; all business logic
stays server-side.

## Architecture

```
UI (screens)  →  Riverpod controllers/providers  →  repositories  →  ApiClient  →  secure token storage
```

- `lib/config/` — compile-time config: branding + API base (all via `--dart-define`).
- `lib/core/` — `ApiClient` (dio: Bearer auth, single-flight token refresh on 401,
  typed `ApiException`), `TokenStorage` (Keychain/Keystore), the Riverpod graph.
- `lib/features/<area>/` — one folder per area: models, repository, provider(s), screens.
- `lib/routing/` — `go_router` with an auth-gated redirect; detail/area screens are
  pushed full-screen on the root navigator and are deep-linkable.

Nothing hard-codes a product name; branding comes from `AppConfig` (spec §43).

## Run

The app is **brand-agnostic by default** (`APP_NAME` falls back to "Application",
spec §43). Supply a brand at build time. The simplest way is a dart-defines
file (brand configs live under `dart_defines/` and are gitignored like the web
`.env`; copy `dart_defines/example.json`):

```bash
flutter pub get
flutter run --dart-define-from-file=dart_defines/boldron.json
```

Or pass defines individually:

```bash
flutter run \
  --dart-define=APP_NAME=Boldron \
  --dart-define=API_BASE_URL=http://localhost:8020/api/v1/
```

- iOS simulator reaches the host at `localhost`.
- Android emulator must use `API_BASE_URL=http://10.0.2.2:8020/api/v1/`.
- The API base should end with a trailing slash (the client normalizes it anyway).

### Branding (per white-label build)

```bash
flutter build apk \
  --dart-define=APP_NAME="Acme Studio" \
  --dart-define=API_BASE_URL=https://api.acme.com/api/v1 \
  --dart-define=APP_SUPPORT_EMAIL=help@acme.com
```

Also change the native bundle id / `DEVELOPMENT_TEAM` (iOS) and `applicationId`
(Android) for a real release; `flutter create` stamped local defaults.

## Test & analyze

```bash
flutter analyze
flutter test
```

`ApiClient` refresh/retry/expiry and the model serialization layer are covered;
run both before committing (CI runs them too).
