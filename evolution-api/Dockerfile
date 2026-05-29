FROM atendai/evolution-api:latest

# Baileys 6.7.12 ships with Evolution API v2.2.3 and gets 405 Connection Failure
# from WhatsApp servers due to an outdated protocol version.
# 
# Fix 1: Upgrade to Baileys 6.7.18 (latest CJS-compatible version)
# Note: 6.7.19+ are ESM-only (type: module) which breaks v2.2.3's CommonJS build.
#
# Fix 2: Update baileys-version.json to the latest WhatsApp client version
# from @whiskeysockets/baileys@7.0.0-rc13 (the current upstream).
# The tertiary version 1035194821 is required — the old 1023223821 gets 405 rejected.

RUN apk add --no-cache git && \
    cd /evolution && \
    npm install baileys@6.7.18 --save --legacy-peer-deps && \
    apk del git && \
    echo '{"version": [2, 3000, 1035194821]}' > /evolution/node_modules/baileys/lib/Defaults/baileys-version.json