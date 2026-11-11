from django.conf import settings
from django.db import models


class Wallet(models.Model):
    """The coin balance of one user, kept next to your user model."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True)
    # Millionths of a coin. Exact on every database. Signed: a reversal of coins
    # the user already spent may take it below zero.
    balance_micro = models.BigIntegerField(default=0)
    # Set when the user confirms they are 16 or older. No offerwall link before that.
    age_confirmed_at = models.DateTimeField(null=True, blank=True)


class MoonetixTransaction(models.Model):
    """The rewards ledger: one row per Moonetix transaction_id."""

    CREDITED = 1
    REVERSED = 2
    STATUS_CHOICES = [(CREDITED, "Credited"), (REVERSED, "Reversed")]

    # The primary key is what makes a retried or duplicated postback harmless.
    transaction_id = models.CharField(max_length=191, primary_key=True)
    # The user_id from the postback. Not a foreign key, so a reversal for an
    # unknown or deleted user can still be recorded. Named so nobody takes it for one.
    wall_user_id = models.CharField(max_length=100, db_index=True)
    reward_micro = models.BigIntegerField()
    # Empty only inside the database transaction that inserted the row.
    status = models.PositiveSmallIntegerField(choices=STATUS_CHOICES, null=True)
    offer_name = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
