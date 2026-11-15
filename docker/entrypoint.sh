#!/bin/sh
# Drop to PUID:PGID so files written to mounted volumes stay owned by the host
# user. Only /config and /downloads are chowned; /music is the user's data.
set -e

: "${PUID:=1000}"
: "${PGID:=1000}"
: "${UMASK:=002}"

if [ "$(id -u)" = "0" ]; then
    if ! getent group "$PGID" >/dev/null 2>&1; then
        groupadd -g "$PGID" app
    fi
    if ! getent passwd "$PUID" >/dev/null 2>&1; then
        useradd -u "$PUID" -g "$PGID" -M -s /usr/sbin/nologin app
    fi

    mkdir -p /config /downloads
    if [ "${CHOWN_ON_START:-true}" = "true" ]; then
        chown -R "$PUID:$PGID" /config /downloads 2>/dev/null || true
    fi

    umask "$UMASK"
    exec gosu "$PUID:$PGID" "$@"
fi

umask "$UMASK"
exec "$@"
