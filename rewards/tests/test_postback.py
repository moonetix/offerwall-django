"""Every postback here was produced and signed by the Moonetix postback code (moonetix_vectors.json)."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, TestCase, override_settings

from rewards import moonetix
from rewards.models import MoonetixTransaction, Wallet

from .test_moonetix import KEYS, VECTORS

PB = VECTORS["postbacks"]
User = get_user_model()


@override_settings(**KEYS)
class PostbackTests(TestCase):
    def setUp(self):
        self.u1 = User.objects.create_user("one", password="x", pk=1)
        self.u2 = User.objects.create_user("two", password="x", pk=2)

    def get(self, path, client=None):
        return (client or self.client).get(path)

    def balance(self, user):
        wallet = Wallet.objects.filter(user=user).first()
        return moonetix.format_micro(wallet.balance_micro if wallet else 0)

    def assert_ok(self, path, text):
        response = self.get(path)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn(text, response.content.decode())
        return response

    def test_credit_is_applied_once(self):
        self.assert_ok(PB["credit_150"], "Credited")
        self.assertEqual(self.balance(self.u1), "150")

        self.assert_ok(PB["credit_150"], "Already processed")
        self.assertEqual(self.balance(self.u1), "150")

        row = MoonetixTransaction.objects.get(pk="tx_1001")
        self.assertEqual((row.wall_user_id, row.status, row.offer_name), ("1", 1, 'Bigo Live & "Friends"'))

    def test_decimal_rewards_add_up_exactly(self):
        for name in ("credit_150", "credit_decimal", "credit_five_decimals", "credit_user2", "credit_large"):
            self.assert_ok(PB[name], "Credited")
        self.assertEqual(self.balance(self.u1), "151.98456")
        self.assertEqual(self.balance(self.u2), "1234607.125")

    def test_reversal_takes_back_exactly_what_was_credited_once(self):
        self.assert_ok(PB["credit_150"], "Credited")
        self.assert_ok(PB["credit_decimal"], "Credited")

        self.assert_ok(PB["reverse_150"], "Reversed")
        self.assertEqual(self.balance(self.u1), "0.75")

        self.assert_ok(PB["reverse_150"], "Already processed")
        self.assert_ok(PB["credit_150"], "Already processed")
        self.assertEqual(self.balance(self.u1), "0.75")

    def test_reversal_can_take_the_balance_below_zero(self):
        self.assert_ok(PB["credit_150"], "Credited")
        Wallet.objects.filter(user=self.u1).update(balance_micro=50_000_000)  # the user spent 100 coins
        self.assert_ok(PB["reverse_150"], "Reversed")
        self.assertEqual(self.balance(self.u1), "-100")

    def test_reversal_without_credit_changes_nothing_and_blocks_a_late_credit(self):
        self.assert_ok(PB["reverse_never_credited"], "Not credited before")
        self.assert_ok(PB["late_credit_after_reverse"], "Already processed")
        self.assertEqual(self.balance(self.u1), "0")
        self.assertEqual(MoonetixTransaction.objects.get(pk="tx_9001").status, 2)

    def test_dashboard_test_postbacks_are_verified_but_not_credited(self):
        self.assert_ok(PB["test_credit"], "Test postback")
        self.assert_ok(PB["test_reverse"], "Test postback")
        self.assertEqual(self.balance(self.u1), "0")
        self.assertFalse(MoonetixTransaction.objects.exists())

    def test_unknown_users_get_200_and_nothing_is_stored(self):
        self.assert_ok(PB["unknown_user"], "Unknown user")
        self.assert_ok(PB["not_an_account_id"], "Unknown user")
        self.assertFalse(MoonetixTransaction.objects.exists())

    def test_wrong_key_is_rejected(self):
        self.assertEqual(self.get(PB["wrong_key"]).status_code, 403)
        self.assertEqual(self.balance(self.u1), "0")

    def test_tampered_values_are_rejected(self):
        url = PB["credit_150"]
        for old, new in (("reward=150&", "reward=1500&"), ("user=1&", "user=2&"),
                         ("tx=tx_1001&", "tx=tx_1002&"), ("status=1&", "status=2&")):
            with self.subTest(change=new):
                self.assertEqual(self.get(url.replace(old, new)).status_code, 403)
        self.assertEqual(self.balance(self.u1), "0")
        self.assertEqual(self.balance(self.u2), "0")

    def test_malformed_requests_are_rejected(self):
        url = PB["credit_150"]
        good = url.rsplit("hash=", 1)[1]
        cases = [
            url.replace(good, good.upper()),
            url.replace("&hash=" + good, ""),
            url + "&hash=" + good,  # repeated parameter
            url.replace("tx=tx_1001&", "tx=tx_1001&tx=tx_1001&"),
            "/moonetix/postback/",
        ]
        for path in cases:
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code, 403)
        self.assertEqual(self.balance(self.u1), "0")

    def test_only_get_is_allowed_and_no_cookie_is_set(self):
        self.assertEqual(self.client.post(PB["credit_150"]).status_code, 405)
        response = self.assert_ok(PB["credit_150"], "Credited")
        self.assertEqual(len(response.cookies), 0)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_url_without_trailing_slash_redirects(self):
        # Shows why the postback URL must end in /moonetix/postback/ on the Postback page.
        self.assertEqual(self.get(PB["credit_150"].replace("/postback/?", "/postback?")).status_code, 301)

    @override_settings(MOONETIX_POSTBACK_KEY="")
    def test_missing_postback_key_answers_500_so_moonetix_retries(self):
        client = Client(raise_request_exception=False)
        self.assertEqual(self.get(PB["credit_150"], client).status_code, 500)

    def test_failure_after_insert_rolls_back_the_whole_credit(self):
        client = Client(raise_request_exception=False)
        with mock.patch("rewards.views._add_to_wallet", side_effect=RuntimeError("database went away")):
            self.assertEqual(self.get(PB["credit_150"], client).status_code, 500)
        self.assertFalse(MoonetixTransaction.objects.exists())
        self.assertEqual(self.balance(self.u1), "0")

        # Moonetix retries later, and the credit goes through once.
        self.assert_ok(PB["credit_150"], "Credited")
        self.assertEqual(self.balance(self.u1), "150")


class MissingKeyTests(TestCase):
    @override_settings(MOONETIX_POSTBACK_KEY="")
    def test_helper_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            moonetix.valid_postback_hash("a", "b", "c", "d", "e")
