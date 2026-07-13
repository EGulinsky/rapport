# rapport – Deployment Concept: Public Web Hosting

> **Status: planning document, not yet implemented.** Captures the requirements and open decisions for moving rapport from the current local OrbStack/Docker Compose setup (a single Mac, `*.orb.local` routing, self-hosted CI runner on the same machine) to a real internet-facing server. Written 2026-07-13, based on the codebase as of that date (see [ARCHITECTURE.md](ARCHITECTURE.md) for the current implementation). No code changes have been made based on this document yet — treat every "required change" below as a future task, not a completed one.

## 1. Motivation / Context

rapport currently runs exclusively on the developer's own Mac via OrbStack + Docker Compose, with `docker-compose.yml` wired to OrbStack-specific routing (`*.rapport.orb.local` DNS, a custom static-IP subnet) and a GitHub Actions self-hosted runner on the same machine handling CI/deploy. This document captures what changes if the app instead runs on a real, publicly reachable Linux web server.

`docker-compose.yml` has already been partially prepared for this move (`host.docker.internal` now resolves via an explicit `extra_hosts: host-gateway` entry instead of relying on Docker Desktop/OrbStack magic, and the OrbStack-specific static-IP subnet/external-volume config has been removed in favor of plain Docker networking) — this document builds on that baseline rather than starting from the original OrbStack-only compose file.

## 2. Current State (Baseline)

- **Frontend container**: nginx serves the built SPA and proxies `/api/*` internally to `http://backend:8000/api/` (`frontend/nginx.conf`). The frontend itself only ever calls relative `/api/...` paths (`frontend/src/api/client.ts: const BASE = '/api'`) — no hardcoded host anywhere.
- **Backend container**: FastAPI on port 8000, SQLite (WAL) at `/app/data/jobtracker.db` in a named Docker volume, Fernet key + JWT secret auto-generated into the same volume on first start if not supplied via env var.
- **Seq**: structured logging, ports 8088 (UI) and 5341 (ingest), started with `SEQ_FIRSTRUN_NOAUTHENTICATION=true`.
- **Rapport Agent**: a separate native macOS app (menu-bar, launchd-managed), *not* part of the Docker stack, listening on port 9996 on the same Mac. Backend reaches it via `AGENT_URL` (default `http://host.docker.internal:9996`).
- **CI/CD**: `.github/workflows/ci.yml`'s `deploy` job is `runs-on: self-hosted`, hardcoded to this Mac via the `DEPLOY_PATH` repository variable, and health-checks against the OrbStack-local `*.rapport.orb.local` domains.

**Practical implication**: because the frontend already proxies all API traffic internally, a real deployment needs only **one public HTTPS entry point** (in front of the frontend container) — the backend port never needs to be exposed to the internet directly.

## 3. Requirements by Category

### 3.1 Server / Infrastructure
- Linux VPS (Ubuntu/Debian recommended), Docker + Docker Compose v2 installed
- Minimum **2 vCPU / 4 GB RAM** — headless Chromium (Playwright, used by the LinkedIn scraper and company-enrichment sync) is memory-hungry; 2 GB is tight
- ~20+ GB disk (Docker images, SQLite DB, attachments, backups, Seq log storage)

### 3.2 Domain, TLS, Reverse Proxy
- A real domain with an A record pointing at the server's IP
- A reverse proxy terminating TLS (Let's Encrypt) in front of the `frontend` container only — candidates: **Caddy** (near-zero config, automatic certs) or **Traefik** (Docker-label-based routing, better if more services get added later)
- `docker-compose.yml`'s `ports: "3000:80"` mapping on `frontend` becomes internal-only once the reverse proxy takes over the public port

### 3.3 Security — required before real public exposure

| Item | Current state | Required change |
|---|---|---|
| CORS | `allow_origins=["*"]` (`backend/app/main.py`) | Restrict to the real production origin |
| Rate limiting | None exists on auth endpoints (register/login/password-reset) | Add before going public — currently no protection against brute-force or registration spam |
| Seq (log viewer, ports 8088/5341) | `SEQ_FIRSTRUN_NOAUTHENTICATION=true` | Must **not** be publicly reachable — do not map these ports externally, or put behind auth/VPN |
| Firewall | — | Only 80/443 inbound; block everything else (backend 8000, Seq 8088/5341); SSH key-only + fail2ban |
| `JWT_SECRET_KEY` | Auto-generated into `data/jwt_secret.key` if unset | No code change needed, but this file must be included in backups — losing it invalidates every user's session on volume loss |

### 3.4 External Integrations — configuration/code changes needed
- **Google OAuth**: `REDIRECT_URI` is currently a hardcoded constant in `backend/app/routers/sync_google.py:41` (`http://localhost:8000/api/sync/google/callback`) — not an env var. Needs a code change to parametrize it, plus registering the new URI as an authorized redirect in the Google Cloud Console OAuth client.
- **LinkedIn scraper**: Playwright login from a datacenter/VPS IP is more likely to trigger LinkedIn's bot-detection than from a residential IP — expect more frequent 2FA/checkpoint challenges, possibly account flags. Not a blocker, but a real operational risk to budget for.
- **SMTP**: real credentials (Resend or similar) must be set via `.env` (`SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM`) — without them, registration/password-reset fail with `502 EmailNotConfigured`.

### 3.5 Rapport Agent Connectivity (open architectural decision)

This is the most significant open question. The Agent (local documents/notes/calls/backup sync) runs natively on the Mac; the backend currently reaches it via `host.docker.internal:9996`, which only resolves to "the machine Docker is running on." Once the backend runs on a remote server, the Mac is no longer reachable that way. Options, not yet decided:

1. **VPN/tunnel between server and Mac** (e.g. Tailscale) — set `AGENT_URL` to the Mac's Tailscale IP. Keeps all Agent-dependent features working.
2. **Accept the feature gap** — local documents/notes/calls/backup sync stop working once the backend moves off the Mac; everything else (Gmail/Google Calendar/iCloud/LinkedIn sync, AI assessment, core tracking) is unaffected since those don't depend on the Agent.

### 3.6 Deploy Pipeline

The current `deploy` job (`runs-on: self-hosted`) is hardcoded to this Mac (`vars.DEPLOY_PATH`, health checks against `*.rapport.orb.local`). Options for the new server, not yet decided:

1. Register a **new self-hosted GitHub Actions runner directly on the target server** — smallest change to the existing workflow structure.
2. Switch to **SSH-based deployment** — CI builds/pushes images to a registry, then connects via SSH to run `docker compose pull && up -d` on the server.
3. Move to a **managed platform** (Hetzner + CapRover, Fly.io, Railway, etc.) with its own deploy mechanism, replacing the custom `ci.yml` deploy job entirely.

Health-check URLs in the deploy job would need to point at the real domain regardless of which option is chosen.

### 3.7 Database & Backups
- SQLite (WAL) is fine for single-server operation at moderate load, but has no built-in replication — server failure with no backup means total data loss.
- The backup feature already exists in-app (Settings → Backup), but backups stored on the same server don't protect against total server/disk failure — need an **off-server** copy (e.g. automated upload to S3/Backblaze, or rsync to a second host).
- `jobtracker-data`/`seq-data` are now plain (unnamed-external) Docker volumes — a first deploy on a new server starts with an empty database; there is no automatic data migration path from the current Mac.

### 3.8 Environment Variables Checklist (`.env` on the new server)
- `JWT_SECRET_KEY` — optional, auto-generated if omitted
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` — required for registration/password-reset to work
- `BUILD_NUMBER` — set by CI, not needed manually
- (New, pending 3.4) whatever env var the parametrized Google OAuth `REDIRECT_URI` ends up using
- (New, pending 3.5) `AGENT_URL` — only relevant if the VPN/tunnel option is chosen

## 4. Suggested Priority When This Is Picked Up

1. Parametrize `REDIRECT_URI` (Google OAuth) + restrict CORS — small, low-risk code changes, needed regardless of which deploy strategy is chosen later
2. Decide the Rapport Agent question (§3.5) — affects whether local-file/notes/calls/backup features ship at all in the hosted version
3. Decide the deploy-pipeline approach (§3.6) — affects how much of `ci.yml` needs rewriting
4. Stand up server + reverse proxy + TLS
5. Add rate limiting to auth endpoints
6. Set up off-server backups
7. Go live, then lock down Seq/firewall as a final hardening pass

## 5. Explicitly Out of Scope for Now

- Moving off SQLite to a networked database (Postgres) — not required for a single-server deployment at the current/expected scale; revisit only if concurrency or replication needs actually materialize.
- Multi-region / high-availability setup.
- Any specific choice of VPS provider, reverse proxy, or deploy mechanism — all left as open options above until this work is actually picked up.
