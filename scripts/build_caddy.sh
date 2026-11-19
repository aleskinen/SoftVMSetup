#!/bin/sh
set -eu

export GOPATH=${GOPATH:-/var/lib/caddy-build}
export GOCACHE=${GOCACHE:-/var/cache/caddy-build}
install -d -o root -g root "$GOPATH" "$GOCACHE"

tmpdir=$(mktemp -d)
backup=/usr/local/bin/caddy-custom.previous
staged=/usr/local/bin/caddy-custom.new
cleanup() {
    rm -rf "$tmpdir"
    rm -f "$staged"
}
trap cleanup EXIT

GOBIN="$tmpdir/bin" go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest
"$tmpdir/bin/xcaddy" build \
    --with github.com/mholt/caddy-ratelimit \
    --with github.com/WeidiDeng/caddy-cloudflare-ip \
    --output "$tmpdir/caddy-custom"

"$tmpdir/caddy-custom" list-modules | grep -qx 'http.handlers.rate_limit'
"$tmpdir/caddy-custom" list-modules | grep -qx 'http.ip_sources.cloudflare'
"$tmpdir/caddy-custom" validate --config /etc/caddy/Caddyfile

install -o root -g root -m 0755 "$tmpdir/caddy-custom" "$staged"
if [ -x /usr/local/bin/caddy-custom ]; then
    install -o root -g root -m 0755 /usr/local/bin/caddy-custom "$backup"
fi
mv "$staged" /usr/local/bin/caddy-custom
systemctl daemon-reload

if ! systemctl restart caddy; then
    if [ -x "$backup" ]; then
        mv "$backup" /usr/local/bin/caddy-custom
        systemctl restart caddy || true
    fi
    echo "Caddy restart failed; previous binary restored when available" >&2
    exit 1
fi
rm -f "$backup"
