# Plane-in-CRM Iframe — Security Review & Mitigation Options

## Overview

The security team has raised four concerns about Plane being embedded
as an iframe inside the CRM ops dashboard. This document states each
issue and lists the mitigation options we identified during analysis,
with the benefits and challenges of each.

| # | Concern                                     |
|---|---------------------------------------------|
| 1 | CRM logout does not end the Plane session   |
| 2 | Plane reachable directly via URL / IP / curl|
| 3 | Unauthenticated users see Plane login / signup |
| 4 | Webhook endpoint exposure (SSRF risk)       |

---

## 1. CRM Logout Does Not End the Plane Session

### Issue

When a user logs out of the CRM, their Plane session remains valid for
up to 7 days. If the user (or someone else with access to their machine
or cookie) subsequently opens Plane directly in another browser tab,
they are still signed in. The CRM logout is therefore cosmetic from
Plane's perspective.

This matters because:
- Shared-device scenarios (support desks, shift-based ops teams) leak
  access between users.
- An exfiltrated session cookie stays valid long after the user has
  "logged out".
- Compliance posture: "log out" should mean logged out everywhere.

A complicating factor: the Plane iframe is only mounted while the user
is on the support-tickets tab. Other iframes in CRM (such as LIA) stay
mounted always via a persistent-iframe pool; Plane does not. So any
postMessage-based logout signal cannot reach Plane from other CRM tabs.

### Solution Options

#### Option 1.A — postMessage on logout, re-embed iframe if needed

When the user clicks logout, if the Plane iframe is not currently
mounted, briefly mount it (hidden), wait for it to finish its SSO boot,
send a sign-out message, await acknowledgement, then proceed with CRM
logout.

- **Benefits**
  - No change to Plane-side code needed.
  - No ongoing background resource use from Plane.
  - Works from any CRM tab, not just support tickets.
- **Challenges**
  - Logout becomes visibly slower when the iframe has to be remounted
    (a few seconds of SSO round-trip). This lag sits squarely on the
    user's critical path.
  - If Plane is unreachable at that moment, we must choose: block CRM
    logout, or let it proceed with a silent failure. Either option has
    trade-offs.

#### Option 1.B — Keep the Plane iframe alive at all times

Migrate Plane to CRM's persistent-iframe pool (the same mechanism LIA
uses). The iframe stays mounted always; visibility is toggled with CSS.
Logout broadcasts reach Plane without any special handling.

- **Benefits**
  - Consistent with LIA and other persistent iframes — one mental model
    to maintain.
  - No logout lag.
  - Side benefit: faster tab-switch back to support tickets; no re-SSO.
- **Challenges**
  - Plane keeps running background pollers, timers, and (if applicable)
    websockets even when the user is not using it. Extra CPU, memory,
    and Plane API load per active user.
  - Plane components were written assuming they mount fresh at route
    entry. Keeping them long-lived may expose stale-data bugs or memory
    leaks.
  - Larger change — touches CRM architecture, not a surgical fix.

#### Option 1.C — End Plane session on every tab switch

Whenever the user navigates away from the support-tickets tab, send a
sign-out message in the cleanup phase before the iframe is destroyed.

- **Benefits**
  - Smallest session lifetime — security-ideal.
  - Minimal code change.
- **Challenges**
  - Forces a full re-SSO every time the user returns to support
    tickets. For users who multitask between modules, this is a
    significant productivity hit.
  - The in-Plane navigation context is lost on return.

#### Option 1.D — Server-to-server logout (CRM backend → Plane backend)

CRM's logout handler calls Plane's `/auth/sign-out/` endpoint directly,
with the user's session cookie. Requires unblocking CORS between the
two origins.

- **Benefits**
  - Works even when no iframe is mounted — the only option that
    handles the "logout from a different tab" case cleanly.
  - Complements any of the options above.
- **Challenges**
  - Requires Plane backend configuration changes (CORS allow-list,
    credentials, CSRF handshake).
  - Still subject to browser cross-origin cookie rules, which are
    tightening industry-wide.
  - Does not protect against a cookie that was exfiltrated before
    logout.

---

## 2. Plane Reachable Directly via URL / IP / curl

### Issue

Plane's URLs (`https://planedev.shipsy.io/...`, and by IP) are reachable
from any browser tab and from command-line tools. The CRM iframe is not
enforcing any security boundary — it is only a UI layer. Any user who
holds a valid Plane session can:

1. Copy the URL into a new browser tab and access Plane outside CRM.
2. Copy the session cookie from DevTools and replay requests via curl
   or any HTTP client.
3. (In the case of a cookie stolen via XSS or malware) operate Plane
   indefinitely without ever touching CRM.

Because Plane is open-source, API endpoints are publicly documented —
hiding them in the UI does not hide them from a knowledgeable attacker.

### Solution Options

#### Option 2.A — CRM-proxied Plane (all traffic through CRM backend)

Introduce a CRM backend route that forwards all Plane API calls. The
iframe loads Plane from a CRM-origin URL; Plane backend rejects any
request not carrying a CRM service identity.

- **Benefits**
  - Strongest isolation. If Plane's ingress is further IP-restricted to
    CRM backend servers, direct access becomes impossible at the
    network layer.
  - Single chokepoint for audit logging, rate limiting, and policy.
- **Challenges**
  - Large engineering effort. Every Plane feature that uses websockets,
    long-polling, file uploads, or streaming must be proxied.
  - Adds latency and a new point of failure.
  - CRM backend absorbs Plane's request volume.
  - Non-trivial operational handover.

#### Option 2.B — CRM-issued short-lived access tokens

CRM issues a signed, short-lived (~30 second) token that travels with
every Plane request. Plane middleware validates the token on each
request against CRM's public keys.

- **Benefits**
  - Very short replay window — stolen tokens expire in seconds.
  - Session lifetime is implicitly controlled by CRM; when CRM stops
    issuing tokens, Plane access stops.
- **Challenges**
  - CRM must continuously inject the token into the iframe via
    postMessage for every navigation. Complex, many moving parts.
  - CRM becomes the sole identity authority — a CRM outage locks all
    Plane users out.
  - A user watching their own DevTools can still copy a live token
    and replay within the TTL.

#### Option 2.C — Partitioned cookies (CHIPS)

Configure Plane's session cookie with the `Partitioned` attribute. The
browser keys the cookie by (Plane origin, top-level CRM site). The
cookie is only sent when Plane is loaded under the CRM top-level
context.

- **Benefits**
  - Defeats "copy URL into a new tab" at the browser layer, with no
    Plane code change beyond a cookie attribute.
  - Very low blast radius — one configuration change.
  - Aligns with the industry direction for third-party cookies.
- **Challenges**
  - Does not stop curl or any non-browser client — curl ignores
    partitioning.
  - Requires a modern browser (Chrome-based, recent versions). Users
    on older browsers may lose access.
  - Requires Plane's session middleware to emit the `Partitioned`
    attribute (not yet native in the framework).

#### Option 2.D — Server-to-server liveness heartbeat

CRM's backend sends a signed "user X is active" heartbeat to Plane's
backend every ~30 seconds. Plane stores the last-seen timestamp per
user and rejects any Plane API request if the heartbeat has gone stale
(e.g. > 60 seconds old).

- **Benefits**
  - Resists both cookie-copy-to-new-tab and curl replay — neither
    attack path refreshes the heartbeat.
  - No per-request token injection into the iframe; user experience
    is unchanged.
  - Naturally mitigates concern #1 too: when the user leaves CRM,
    Plane sessions die within the heartbeat window.
- **Challenges**
  - New endpoint, new middleware, new secret to manage on Plane side.
  - Operational load: one heartbeat per active user per interval. At
    large user counts this is a tunable concern.
  - A brief CRM slowdown could cause false rejections — the rejection
    window needs careful calibration.

### Approaches considered and ruled out

- **Origin / Referer / Sec-Fetch headers:** Plane's own internal
  navigation issues same-origin requests from the Plane origin itself,
  so these headers cannot distinguish legitimate iframe traffic from
  malicious direct-tab traffic. Also trivially forgeable from curl.
- **Frontend-only gates** (e.g. `window.top !== window.self`): purely
  cosmetic; API endpoints bypass them entirely.
- **Session tagging** (flag inside session saying "came from CRM"):
  the tag travels with the cookie, so cookie replay carries the tag.

---

## 3. Unauthenticated Users See Plane's Login / Signup Pages

### Issue

A stranger hitting Plane's URL directly sees Plane's built-in sign-in
form, and from `/sign-up` can self-service an account with Plane-issued
credentials — entirely outside CRM's identity system. The same applies
to forgot-password, reset-password, and set-password flows.

This creates:
- An identity-pollution risk (Plane accounts that CRM doesn't know
  about).
- A second authentication surface subject to credential-stuffing and
  account-takeover.

Even after the UI pages are hidden, the underlying authentication API
endpoints (`/auth/sign-up/`, `/auth/sign-in/`, `/auth/forgot-password/`,
OAuth callbacks, etc.) remain reachable directly via curl. Because
Plane is open-source, an attacker can read the endpoint paths from the
public source code.

### Solution Options

#### Option 3.A — Disable the UI pages (return 404)

Replace the sign-in, sign-up, forgot-password, reset-password, and
set-password pages with a 404 response.

- **Benefits**
  - Closes the casual-user / browser-walk-in path.
  - Very small code change; trivial to roll back.
- **Challenges**
  - UI hide only. A knowledgeable attacker can still hit the
    underlying API endpoints directly via curl.

#### Option 3.B — Disable unused auth endpoints at the URL router

Comment out the auth-related URL includes in the Plane backend, keeping
only the four endpoints the CRM SSO flow actually needs:
`magic-generate`, `magic-sign-in`, `sign-out`, and `get-csrf-token`.

- **Benefits**
  - Surgically closes the account-creation and password-reset
    attack surfaces at the API layer, not just the UI.
  - Matches the pattern already used elsewhere (familiar to
    reviewers).
- **Challenges**
  - If any internal test or admin script uses one of these endpoints
    (e.g. QA using `email-check`), it will break silently.
  - Partial rollback (reactivating one flow) requires uncommenting
    individual routes.

#### Option 3.C — Feature-flag the auth endpoints

Wrap each auth endpoint with a Django setting (defaulting to "off").
Rollback is via an environment variable.

- **Benefits**
  - Instant on/off switch without code deploy.
  - Preserves all source code in working order.
- **Challenges**
  - More code to write and maintain than commenting out URLs.
  - Adds a permanent toggle to the ops runbook ("must stay off").

#### Option 3.D — Rely on backend enforcement from concern #2

If concern #2 is addressed (partitioned cookies + heartbeat, or
equivalent), these auth endpoints become unreachable from outside the
CRM context by construction.

- **Benefits**
  - Single mitigation covers everything.
- **Challenges**
  - Depends on concern #2 being solved first. Not a standalone
    solution.

---

## 4. Webhook Endpoint Exposure & SSRF Risk

### Issue

Plane's webhook system lets users register URLs that Plane's backend
will POST to on workspace events. The URL validator only rejects
localhost addresses. It does **not** reject:

- Private internal networks (10.x.x.x, 172.16–31.x.x, 192.168.x.x)
- Link-local addresses (169.254.x.x — includes AWS metadata endpoints)
- Cloud metadata services (169.254.169.254)

An attacker who is a workspace administrator can register a webhook
pointing at an internal service. Plane's backend will POST to it; the
response is captured and visible via Plane's webhook logs. This is a
classic server-side request forgery (SSRF) with read-back — usable to
probe internal infrastructure, read cloud instance metadata, or reach
other internal APIs.

Two distinct surfaces allow webhook creation:
- The **admin UI API** (session-authenticated, exposed to workspace
  administrators).
- The **public API** (`/api/v1/...`, token-authenticated, used by
  internal teams for programmatic provisioning).

Existing webhook records already in the database may also point at
private IPs.

### Solution Options

#### Option 4.A — Disable the admin UI and its API route

Remove the webhooks UI pages and the session-authenticated webhook
URL include. Workspace administrators can no longer create or manage
webhooks through Plane's UI.

- **Benefits**
  - Closes the largest attack surface (any workspace admin) in a
    small, auditable change.
  - No impact on internal provisioning (which uses the public API).
- **Challenges**
  - Does not address the public API — an attacker with a leaked API
    token can still exploit the validator weakness.
  - The validator weakness remains in source; re-enabling the admin
    route in the future brings the vulnerability back.

#### Option 4.B — Harden the URL validator (at creation and at delivery)

Update the validator to resolve the URL to IP addresses and reject if
any IP is private, loopback, link-local, multicast, or a known cloud
metadata endpoint. Re-check at delivery time too (to defeat DNS
rebinding attacks).

- **Benefits**
  - Fixes the root cause. Both the admin API and the public API are
    protected simultaneously.
  - Survives any future re-enablement of the admin UI.
  - Matches industry practice (GitHub, GitLab use this pattern).
- **Challenges**
  - Adds a DNS lookup at delivery time — small latency cost per
    webhook call.
  - Developers using localhost or tunnels (ngrok) for webhook testing
    need an explicit dev-mode bypass.


#### Option 4.C — Restrict public webhook API by network and token scope

Keep the public API live but restrict it to specific source IPs (CRM
backend range) and to API tokens with a dedicated `webhooks:write`
scope held only by a single service principal.

- **Benefits**
  - Preserves the existing internal workflow.
  - Reduces the attack surface from "anyone with any workspace-admin
    token" to "the one service principal from the allowed IP range".
- **Challenges**
  - Requires token scoping to exist in Plane (may need to be built).
  - Requires coordination with ingress/load-balancer configuration.

#### Option 4.D — One-off audit of existing webhook records

Run a database scan over current webhook rows. For each, resolve the
URL and classify by IP range. Disable any row whose URL resolves to a
private or link-local IP; notify the workspace owner.

- **Benefits**
  - Mitigates risk from data already in the system — not just from
    future inserts.
  - Quick and informational; low operational risk.
- **Challenges**
  - Point-in-time only; must be combined with a hardened validator
    (Option 4.B) to prevent new bad rows.
