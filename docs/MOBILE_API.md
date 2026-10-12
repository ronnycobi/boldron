# Mobile / API layer (`/api/v1/`)

The platform's mobile client (Flutter) and any other non-browser client consume
this JSON API. It is the **same backend and the same business services** the web
app uses — one source of truth. The web app authenticates with session cookies;
API clients authenticate with JWT. Nothing here duplicates business logic: every
endpoint wraps an existing service.

## Conventions

- **Auth**: `Authorization: Bearer <access>`. Obtain tokens at `auth/token/`.
  JWT is first in the authentication chain, so an **invalid or expired token
  returns 401** (the signal to refresh); an unauthenticated API request also
  returns 401.
- **Tenancy**: every resource is scoped to the user's organizations. Reads
  require membership; writes require owner/admin. A resource outside the user's
  orgs returns **404** (never leaks existence).
- **Honesty**: statuses reflect reality. Store connections, push, custom-domain
  SSL, and live store submission are **gated** until real credentials exist —
  never faked.
- **Confidentiality**: no agent, model-routing, framework, or infrastructure
  detail is exposed; build/step language is customer-friendly.

## Endpoints

### Auth & account
| Method | Path | Purpose |
|---|---|---|
| POST | `auth/register/` | Sign up → onboard (org+owner+free credits+verify email) → tokens |
| POST | `auth/token/` | Email+password → access, refresh, user |
| POST | `auth/token/refresh/` · `auth/token/verify/` | Rotate / verify tokens |
| POST | `auth/logout/` | Blacklist a refresh token |
| POST | `auth/verify-email/` · `auth/resend-verification/` | Email verification |
| POST | `auth/password-reset/` · `auth/password-reset/confirm/` | Password reset |
| GET | `me/` · `account/` | Current user / profile |
| PATCH | `account/` | Edit name/email/language/timezone |
| POST | `account/password/` | Change password (revokes other sessions, reissues) |
| POST | `account/logout-all/` | Sign out everywhere (reissues to caller) |
| POST/DELETE | `account/avatar/` | Upload / remove profile photo |

### Organizations & teams
`organizations/` (list/create) · `organizations/<id>/` (detail/rename) ·
`organizations/<id>/members/` · `organizations/<id>/members/<uid>/` (role/remove) ·
`organizations/<id>/leave/` · `organizations/<id>/invitations/` (+ `<id>/revoke`,
`<id>/resend`) · `invitations/accept/`.

### Projects & build
`projects/` · `projects/<id>/` · `build/` (describe → create → run pipeline) ·
`projects/<id>/build-status/` (state, progress, steps, credits, demo-mode) ·
`projects/<id>/workspaces/`.

### Changes
`projects/<id>/changes/` (list / create+plan) · `changes/<id>/` ·
`changes/<id>/approve|implement|rollback/`.

### Deployments
`projects/<id>/deployments/` (list/create) · `projects/<id>/environments/` ·
`deployments/<id>/` · `deployments/<id>/approve|run/`.

### Backups
`projects/<id>/backups/` (list/create) · `backups/<id>/restore/` (code only).

### Websites
`projects/<id>/website/` · `.../publish/` · `.../versions/` · `.../rollback/` ·
`.../domains/` · `website/domains/<id>/verify|ssl/` (gated) · `website/domains/<id>/`
(DELETE) · `.../leads/` · `.../monitoring/` · `.../analytics/`.

### Commerce (merchant console — shared engine)
`projects/<id>/commerce/products/` (+ `<id>/`, `<id>/variants/`) ·
`.../inventory/` · `.../orders/` (+ `<id>/`, `<id>/refund`, `<id>/cancel`) ·
`.../discounts/` · `.../sales/`. Public storefront (shopper) stays at
`stores/<subdomain>/...`.

### Billing & usage
`orgs/<id>/billing/` · `orgs/<id>/usage/` · `orgs/<id>/usage/summary/` ·
`orgs/<id>/invoices/` · `orgs/<id>/upgrade-request/` (opens a billing ticket).

### Mobile release
`release/providers/` (gated) · `projects/<id>/mobile-apps/` · `mobile-apps/<id>/` ·
`orgs/<id>/store-connections/`.

### Support
`support/tickets/` (list/create) · `support/tickets/<id>/` ·
`support/tickets/<id>/reply/` · `support/meta/`.

### Cross-cutting
`notifications/` (activity feed; `push_available:false`) · `integrations/`
(connector inventory) · `search/?q=` (projects/products/orders/tickets/apps).

## Feature parity matrix (§46)

Backend/API column reflects this layer. Flutter column is the remaining client
work (the API it needs is ready).

| Capability | Web | Shared Backend/API | Flutter |
|---|---|---|---|
| Authentication | YES | YES | pending |
| Organizations / teams | YES | YES | pending |
| Projects | YES | YES | pending |
| Build | YES | YES | pending |
| Change requests | YES | YES | pending |
| Deployments | YES | YES | pending |
| Backups / restore | YES | YES | pending |
| Websites (publish/versions/rollback) | YES | YES | pending |
| Domains (verify/SSL — gated) | YES | YES | pending |
| Commerce (products/inventory/orders/refunds/sales) | YES | YES | pending |
| Billing / usage / invoices | YES | YES | pending |
| Analytics | YES | YES | pending |
| Monitoring | YES | YES | pending |
| Notifications (feed) | YES | YES | pending |
| Push delivery | — | gated (no provider) | gated |
| Mobile releases | YES | YES | pending |
| Store submission (live) | gated | gated | gated |
| Team / permissions | YES | YES | pending |
| Settings | YES | YES | pending |
| Support | YES | YES | pending |
| Integrations | YES | YES | pending |
| Search | YES | YES | pending |
