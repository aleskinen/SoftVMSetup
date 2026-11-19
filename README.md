# SoftVM Debian cloud-init setup

This project provisions a minimal Debian 13 (trixie) arm64 VM with Caddy,
nftables, unattended Debian security updates, and scheduled Cloudflare IP-set
refreshes. It is designed for first-boot cloud-init user-data.

## Prepare user-data

Review and edit `configs/Caddyfile` before deploying: replace
`yourdomain.example` with the domain served through Cloudflare and set the
reverse-proxy upstream to your application. This firewall intentionally allows
ports 80 and 443 only from Cloudflare address ranges. SSH on port 22 remains
available from any address; ensure you can reach the VM over SSH before
deployment.

Render the separate project files into a cloud-init payload:

```sh
python3 render_user_data.py > user-data.yaml
```

Attach `user-data.yaml` to the VM as cloud-init user-data in SoftVM. Cloud-init
runs this setup once per VM instance. To repeat a deployment, use a fresh VM or
clean cloud-init state before booting again.

## What is installed

- Debian packages: Caddy, Go and Git (for the Caddy build), nftables, Python 3,
  curl, CA certificates, locales, and unattended-upgrades.
- A custom Caddy binary with the rate-limit and Cloudflare IP-source modules.
  The build script validates both modules and the Caddyfile before replacing
  the binary. A weekly systemd timer rebuilds it from the latest upstream
  module releases and rolls back if Caddy cannot restart.
- An nftables input policy that permits established traffic, essential
  ICMPv6, SSH, and HTTP/HTTPS only from Cloudflare IP ranges. Other inbound
  traffic is dropped.
- A daily Cloudflare feed updater. It validates both official CIDR feeds and
  applies the new sets in a single nftables transaction, preserving the
  previous sets if fetching or validation fails.
- Daily unattended Debian package/security updates.
- `en_US.UTF-8`, `fi_FI.UTF-8`, and `sv_SE.UTF-8` locales, with `en_US.UTF-8`
  as the system default.

Cloudflare IP ranges are downloaded from the official `ips-v4` and `ips-v6`
endpoints over HTTPS. The updater intentionally fails closed on empty,
truncated, malformed, or unexpected-family feeds. If a scheduled refresh
fails, the last successfully installed ranges remain active.

The SSH rate limit bans an address for one hour after repeated new connection
attempts. A client behind shared NAT could be affected; change the rule in
`configs/nftables.conf` if that is unsuitable. The firewall is not applied
until cloud-init has installed and validated its configuration.

The original notes also contained interactive or VM-specific tuning for GRUB,
discard/TRIM, LVM, SSH environment forwarding, and a placeholder user account.
Those are not applied automatically because SoftVM device/discard behavior and
the VM's actual login account need to be verified first.

## Updating

Debian updates run daily through unattended-upgrades. Cloudflare ranges refresh
daily. The custom Caddy binary is rebuilt weekly; its build uses the current
latest upstream versions, so review upstream module changes and run the tests
before deploying project changes. To update manually on the VM:

```sh
sudo apt update && sudo apt full-upgrade
sudo /usr/local/sbin/update-cloudflare-nft.py
sudo /usr/local/sbin/build-caddy.sh
```

## Tests

The tests use only the Python standard library and do not require root, network
access, nftables, or a running VM:

```sh
python3 -m unittest discover -s tests -v
```

They cover malformed and incomplete feed rejection, the transactional update
sequence (validation before apply), and inclusion of the separate configuration
files in rendered cloud-init user-data. For a live VM, check service state with
`systemctl status nftables caddy cloudflare-nft-update.timer caddy-rebuild.timer`
and inspect updater logs using `journalctl -u cloudflare-nft-update.service`.
