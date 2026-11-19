#!/usr/bin/env python3
"""Render the project's separate configuration files as cloud-init user-data."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FILES = (
    ("configs/nftables.conf", "/etc/nftables.conf", "0644"),
    (
        "scripts/update_cloudflare_nft.py",
        "/usr/local/sbin/update-cloudflare-nft.py",
        "0755",
    ),
    ("scripts/build_caddy.sh", "/usr/local/sbin/build-caddy.sh", "0755"),
    (
        "configs/Caddyfile",
        "/etc/caddy/Caddyfile",
        "0644",
    ),
    (
        "configs/caddy-service-override.conf",
        "/etc/systemd/system/caddy.service.d/override.conf",
        "0644",
    ),
    (
        "configs/cloudflare-nft-update.service",
        "/etc/systemd/system/cloudflare-nft-update.service",
        "0644",
    ),
    (
        "configs/cloudflare-nft-update.timer",
        "/etc/systemd/system/cloudflare-nft-update.timer",
        "0644",
    ),
    (
        "configs/caddy-rebuild.service",
        "/etc/systemd/system/caddy-rebuild.service",
        "0644",
    ),
    (
        "configs/caddy-rebuild.timer",
        "/etc/systemd/system/caddy-rebuild.timer",
        "0644",
    ),
    (
        "configs/20auto-upgrades",
        "/etc/apt/apt.conf.d/20auto-upgrades",
        "0644",
    ),
)


def build_user_data(root=ROOT):
    """Return a cloud-init configuration containing the project's source files."""
    write_files = []
    for source, destination, permissions in FILES:
        content = (root / source).read_text(encoding="utf-8")
        write_files.append(
            {
                "path": destination,
                "owner": "root:root",
                "permissions": permissions,
                "content": content,
            }
        )

    return {
        "package_update": True,
        "package_upgrade": True,
        "packages": [
            "ca-certificates",
            "caddy",
            "curl",
            "git",
            "golang-go",
            "locales",
            "nftables",
            "python3",
            "unattended-upgrades",
        ],
        "write_files": write_files,
        "runcmd": [
            [
                "bash",
                "-lc",
                "set -eu; "
                "locale-gen en_US.UTF-8 fi_FI.UTF-8 sv_SE.UTF-8; "
                "update-locale LANG=en_US.UTF-8; "
                "nft -c -f /etc/nftables.conf; "
                "systemctl enable nftables; "
                "systemctl restart nftables; "
                "/usr/local/sbin/update-cloudflare-nft.py; "
                "systemctl daemon-reload; "
                "/usr/local/sbin/build-caddy.sh; "
                "systemctl enable --now caddy; "
                "systemctl enable --now cloudflare-nft-update.timer; "
                "systemctl enable --now caddy-rebuild.timer; "
                "systemctl enable --now apt-daily.timer apt-daily-upgrade.timer",
            ]
        ],
    }


def main():
    print("#cloud-config")
    print(json.dumps(build_user_data(), indent=2))


if __name__ == "__main__":
    main()
