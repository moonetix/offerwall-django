"""Link signing and amount helpers, checked against links made by the Moonetix code."""

import json
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from rewards import moonetix

VECTORS = json.loads((Path(__file__).parent / "moonetix_vectors.json").read_text())
KEYS = {
    "MOONETIX_APP_ID": VECTORS["app_id"],
    "MOONETIX_LINK_SALT": VECTORS["link_salt"],
    "MOONETIX_POSTBACK_KEY": VECTORS["postback_key"],
}


@override_settings(**KEYS)
class WallUrlTests(SimpleTestCase):
    def test_links_match_the_moonetix_links(self):
        for user_id, link in VECTORS["links"].items():
            with self.subTest(user_id=user_id):
                self.assertEqual(moonetix.wall_url(user_id), link)

    def test_integer_ids_are_signed_as_strings(self):
        self.assertEqual(moonetix.wall_url(42), VECTORS["links"]["42"])

    def test_sub_ids_are_appended_and_invalid_ones_dropped(self):
        url = moonetix.wall_url("42", {"sub1": "earn_page", "sub2": "bad value!", "sub9": "x", "sub3": "a~b"})
        self.assertEqual(url, VECTORS["links"]["42"] + "&sub1=earn_page&sub3=a~b")

    def test_user_ids_the_offerwall_rejects_raise(self):
        for bad in ("", "has space", "x" * 101, "café"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                moonetix.wall_url(bad)

    @override_settings(MOONETIX_LINK_SALT="")
    def test_missing_salt_raises_instead_of_signing_with_an_empty_key(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "MOONETIX_LINK_SALT is not set"):
            moonetix.wall_url("1")

    def test_non_ascii_hash_is_a_clean_mismatch(self):
        self.assertFalse(moonetix.valid_postback_hash("tx", "1", "1", "1", "é" * 64))


class AmountTests(SimpleTestCase):
    def test_amounts_are_exact(self):
        self.assertEqual(moonetix.to_micro("150"), 150_000_000)
        self.assertEqual(moonetix.to_micro("0.75"), 750_000)
        self.assertEqual(moonetix.to_micro("1.23456"), 1_234_560)
        for bad in ("-1", "1e3", "1.", "", " 1", "1.1234567", "١"):
            with self.subTest(bad=bad):
                self.assertIsNone(moonetix.to_micro(bad))
        self.assertEqual(moonetix.format_micro(151_984_560), "151.98456")
        self.assertEqual(moonetix.format_micro(-250_000), "-0.25")
        self.assertEqual(moonetix.format_micro(0), "0")
