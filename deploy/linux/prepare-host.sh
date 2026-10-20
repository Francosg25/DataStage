#!/usr/bin/env bash
# Run once by IT after installing Python, Nginx, unixODBC/Driver 18 and trusted CAs.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run as root through the approved administration process.' >&2; exit 1; }
for account in datastage datastage-migrate; do
    if ! getent passwd "$account" >/dev/null; then
        useradd --system --user-group --no-create-home --shell /usr/sbin/nologin "$account"
    fi
done
install -d -o root -g root -m 0755 /opt/datastage /opt/datastage/releases /var/lib/datastage
install -d -o root -g root -m 0700 /etc/datastage
install -d -o datastage -g datastage -m 0750 /var/lib/datastage/documents
install -d -o root -g datastage -m 0750 /var/lib/datastage/reference
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for file in runtime migration; do
    if [[ ! -e /etc/datastage/$file.env ]]; then
        install -o root -g root -m 0600 "$source_dir/$file.env.example" "/etc/datastage/$file.env"
    fi
done
install -o root -g root -m 0644 "$source_dir"/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable datastage-api datastage-worker
printf '%s\n' 'Services installed but NOT started. Complete settings, TLS, SQL permissions and reference files first.'
