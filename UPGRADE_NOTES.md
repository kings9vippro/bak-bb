# ALB Forge — Upgrade Notes

## Render
Set `BOT_TOKEN` as a **Secret Environment Variable**. The token is intentionally
not stored in `render.yaml` or source code.

## QR / Zalo
The project previously contained two different QR implementations and a
custom `zalologin://...` payload. That payload is not proof of a valid Zalo
login session. Keep QR/session handling behind the supported login flow and
store only an opaque session reference.

## Anti-abuse / rate control
`SafetyController` is a defensive circuit breaker. It enforces minimum
intervals, hourly caps, exponential cooldowns and stops after platform
enforcement responses (401/403/429). It is not an anti-ban/evasion layer.

## Credential handling
Do not put cookies, access tokens, IMEI values, passwords or bot tokens into
Telegram messages, source code, logs or public repositories.


## Forge UI 10.0
- Modern control-center menu with overview, health, ping, file pipeline, guard and emoji entry.
- `/ping` measures Bot API latency and process uptime.
- `/health` reports active tasks and defensive guard state.
- Numbered `.txt/.log/.csv` upload mode keeps only `N. text`, strips `N.`, previews first, then sends at most 30 lines with a 3-second minimum interval into the current Telegram chat.
- `/filestop` cancels the file sender.
- Expert Guard is defensive: per-account/target pacing, 120/hour cap, exponential cooldown and circuit-breaker behavior for 401/403/429. It is not a ban-evasion mechanism.
- QR success messages no longer echo raw Zalo cookies back into Telegram.
- Bot token remains an environment secret; rotate the exposed token and set the replacement in Render as `BOT_TOKEN`.
- The supplied Telegram emoji set is exposed as a link because bots cannot silently install an emoji set into a user's account.
