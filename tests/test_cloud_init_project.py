import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


updater = load_module(
    "update_cloudflare_nft", ROOT / "scripts" / "update_cloudflare_nft.py"
)
renderer = load_module("render_user_data", ROOT / "render_user_data.py")


class CloudflareFeedTests(unittest.TestCase):
    def test_parses_expected_network_families(self):
        v4 = updater.parse_networks(
            "\n".join(
                [
                    "192.0.2.0/24",
                    "198.51.100.0/24",
                    "203.0.113.0/24",
                    "192.0.2.0/25",
                    "198.51.100.0/25",
                ]
            ),
            4,
            5,
        )
        self.assertEqual(len(v4), 5)
        self.assertEqual(
            updater.parse_networks(
                "2001:db8::/32\n2001:db9::/32\n", 6, 2
            ),
            ["2001:db8::/32", "2001:db9::/32"],
        )

    def test_rejects_truncated_malformed_wrong_family_and_duplicate_feeds(self):
        bad_feeds = [
            ("192.0.2.0/24\n", 4, 5),
            ("not-a-cidr\n", 4, 1),
            ("2001:db8::/32\n", 4, 1),
            ("192.0.2.0/24\n192.0.2.0/24\n", 4, 1),
        ]
        for contents, version, minimum in bad_feeds:
            with self.subTest(contents=contents, version=version):
                with self.assertRaises(ValueError):
                    updater.parse_networks(contents, version, minimum)

    def test_nft_sets_are_replaced_in_one_validated_transaction(self):
        batch = updater.build_nft_batch(
            ["192.0.2.0/24"], ["2001:db8::/32"]
        )
        calls = []

        def fake_runner(command, check):
            calls.append((command[1], check))

        updater.apply_nft_batch(batch, runner=fake_runner)
        self.assertEqual(calls, [("-c", True), ("-f", True)])

    def test_failed_validation_does_not_apply_firewall_update(self):
        calls = []

        def fake_runner(command, check):
            calls.append(command[1])
            if command[1] == "-c":
                raise RuntimeError("invalid nft batch")

        with self.assertRaisesRegex(RuntimeError, "invalid nft batch"):
            updater.apply_nft_batch("invalid batch", runner=fake_runner)
        self.assertEqual(calls, ["-c"])

    def test_failed_feed_does_not_replace_existing_sets(self):
        with patch.object(
            updater,
            "fetch_networks",
            side_effect=[
                ["192.0.2.0/24"] * 5,
                RuntimeError("feed unavailable"),
            ],
        ):
            with patch.object(updater, "apply_nft_batch") as apply_batch:
                with self.assertRaisesRegex(RuntimeError, "feed unavailable"):
                    updater.main()
                apply_batch.assert_not_called()

    def test_empty_address_family_is_rejected(self):
        with self.assertRaises(ValueError):
            updater.build_nft_batch([], ["2001:db8::/32"])

    def test_feed_rejects_downgrade_redirects(self):
        response = MagicMock()
        response.status = 200
        response.geturl.return_value = "http://www.cloudflare.com/ips-v4"
        response.__enter__.return_value = response
        with patch.object(updater, "urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "untrusted URL"):
                updater.fetch_networks(updater.FEEDS[0][0], 4, 1)


class CloudInitRenderTests(unittest.TestCase):
    def test_user_data_contains_each_separate_file_and_update_jobs(self):
        payload = renderer.build_user_data()
        self.assertTrue(payload["package_update"])
        self.assertTrue(payload["package_upgrade"])
        self.assertIn("nftables", payload["packages"])
        self.assertIn("unattended-upgrades", payload["packages"])

        files = {item["path"]: item for item in payload["write_files"]}
        self.assertEqual(
            files["/etc/nftables.conf"]["content"],
            (ROOT / "configs" / "nftables.conf").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            files["/usr/local/sbin/update-cloudflare-nft.py"]["permissions"],
            "0755",
        )
        self.assertIn(
            "rate_limit",
            files["/etc/caddy/Caddyfile"]["content"],
        )
        command = payload["runcmd"][0][2]
        self.assertIn("update-cloudflare-nft.py", command)
        self.assertIn("build-caddy.sh", command)
        self.assertIn("apt-daily-upgrade.timer", command)

    def test_rendered_payload_is_json_compatible_cloud_config(self):
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir) / "user-data.yaml"
            output_path.write_text(
                json.dumps(renderer.build_user_data()), encoding="utf-8"
            )
            decoded = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(decoded["packages"], renderer.build_user_data()["packages"])


if __name__ == "__main__":
    unittest.main()
