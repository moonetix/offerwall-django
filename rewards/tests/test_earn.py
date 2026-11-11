from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from rewards.models import Wallet

from .test_moonetix import KEYS, VECTORS

User = get_user_model()


@override_settings(**KEYS)
class EarnPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("one", password="right-password", pk=1)
        User.objects.create_user("two", password="x", pk=2)

    def test_guests_are_sent_to_sign_in(self):
        response = self.client.get("/earn/")
        self.assertRedirects(response, "/accounts/login/?next=/earn/", fetch_redirect_response=False)

    def test_no_link_before_the_user_confirms_16_or_older(self):
        self.client.force_login(self.user)
        response = self.client.get("/earn/")
        self.assertContains(response, "I am 16 or older")
        self.assertNotContains(response, "wall.moonetix.com")

        response = self.client.post("/earn/age/", {})
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(Wallet.objects.get(user=self.user).age_confirmed_at)

    def test_signed_link_for_the_signed_in_user_only(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.post("/earn/age/", {"age_16_or_older": "1"}), "/earn/")

        # A user ID sent by the client is ignored.
        response = self.client.get("/earn/?user_id=2&user=2")
        expected = VECTORS["links"]["1"].replace("&", "&amp;")
        self.assertContains(response, f'src="{expected}"')
        self.assertNotContains(response, "user_id=2")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        html = response.content.decode()
        self.assertNotIn(KEYS["MOONETIX_LINK_SALT"], html)
        self.assertNotIn(KEYS["MOONETIX_POSTBACK_KEY"], html)

    def test_balance_and_recent_rewards_are_shown(self):
        self.client.get(VECTORS["postbacks"]["credit_150"])
        self.client.get(VECTORS["postbacks"]["credit_decimal"])
        self.client.force_login(self.user)
        response = self.client.get("/earn/")
        self.assertContains(response, "150.75 coins")
        self.assertContains(response, "Bigo Live &amp; &quot;Friends&quot;")

    def test_demo_sign_in_works(self):
        response = self.client.post("/accounts/login/", {"username": "one", "password": "wrong"})
        self.assertContains(response, "did not match")
        response = self.client.post("/accounts/login/", {"username": "one", "password": "right-password"})
        self.assertRedirects(response, "/earn/", fetch_redirect_response=False)
