FROM atendai/evolution-api:latest

# Evolution API v2.2.3 has TWO issues that prevent WhatsApp QR code generation:
#
# 1. Baileys 6.7.12 (bundled) gets 405 Connection Failure from WhatsApp servers
#    due to an outdated client version. Fix: upgrade to 6.7.18 and patch
#    baileys-version.json with version [2, 3000, 1035194821] from upstream.
#    Note: Baileys 6.7.19+ are ESM-only ("type": "module") and crash v2.2.3's
#    CommonJS build with ERR_REQUIRE_ESM.
#
# 2. The .env file inside the container sets CONFIG_SESSION_PHONE_VERSION to
#    an outdated version (2.3000.1015901307) which OVERRIDES baileys-version.json.
#    This env var must also be updated. We set it via docker-compose.yml environment.
#
# 3. LOG_LEVEL must be a comma-separated list of log levels (e.g., "DEBUG,LOG"),
#    not a single value, because Evolution API's logger expects an array.

RUN apk add --no-cache git && \
    cd /evolution && \
    npm install baileys@6.7.18 --save --legacy-peer-deps && \
    apk del git && \
    echo '{"version": [2, 3000, 1035194821]}' > /evolution/node_modules/baileys/lib/Defaults/baileys-version.json