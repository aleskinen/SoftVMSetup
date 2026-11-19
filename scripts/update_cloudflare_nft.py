#!/usr/bin/env python3
"""Refresh nftables Cloudflare sets without discarding the last good ranges."""

import ipaddress
import subprocess
import tempfile
from urllib.parse import urlparse
from urllib.request import urlopen


FEEDS = (
    ("https://www.cloudflare.com/ips-v4", 4, 5),
    ("https://www.cloudflare.com/ips-v6", 6, 2),
)
MAX_NETWORKS = 100
MAX_FEED_BYTES = 65536


def parse_networks(contents, version, minimum_count):
    networks = []
    for line in contents.splitlines():
        value = line.strip()
        if not value:
            continue
        network = ipaddress.ip_network(value, strict=True)
        if network.version != version:
            raise ValueError("Cloudflare feed contains an address of the wrong family")
        networks.append(str(network))

    if len(networks) < minimum_count or len(networks) > MAX_NETWORKS:
        raise ValueError(
            f"Cloudflare IPv{version} feed has unexpected range count: {len(networks)}"
        )
    if len(set(networks)) != len(networks):
        raise ValueError(f"Cloudflare IPv{version} feed contains duplicate ranges")
    return networks


def fetch_networks(url, version, minimum_count):
    with urlopen(url, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"Cloudflare feed returned HTTP {response.status}: {url}")
        final_url = urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != "www.cloudflare.com":
            raise RuntimeError(f"Cloudflare feed redirected to an untrusted URL: {url}")
        contents = response.read(MAX_FEED_BYTES + 1)
    if len(contents) > MAX_FEED_BYTES:
        raise ValueError("Cloudflare feed exceeds the maximum permitted size")
    contents = contents.decode("ascii")
    return parse_networks(contents, version, minimum_count)


def build_nft_batch(v4_networks, v6_networks):
    if not v4_networks or not v6_networks:
        raise ValueError("Both Cloudflare address families must be present")
    v4_networks = parse_networks("\n".join(v4_networks), 4, 1)
    v6_networks = parse_networks("\n".join(v6_networks), 6, 1)
    commands = [
        "flush set inet filter cloudflare_v4",
        "flush set inet filter cloudflare_v6",
        "add element inet filter cloudflare_v4 { " + ", ".join(v4_networks) + " }",
        "add element inet filter cloudflare_v6 { " + ", ".join(v6_networks) + " }",
        "",
    ]
    return "\n".join(commands)


def apply_nft_batch(batch, runner=subprocess.run):
    with tempfile.NamedTemporaryFile(mode="w", encoding="ascii") as batch_file:
        batch_file.write(batch)
        batch_file.flush()
        runner(["nft", "-c", "-f", batch_file.name], check=True)
        runner(["nft", "-f", batch_file.name], check=True)


def main():
    v4_networks = fetch_networks(*FEEDS[0])
    v6_networks = fetch_networks(*FEEDS[1])
    apply_nft_batch(build_nft_batch(v4_networks, v6_networks))


if __name__ == "__main__":
    main()
