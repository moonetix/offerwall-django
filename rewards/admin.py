from django.contrib import admin

from .models import MoonetixTransaction, Wallet


@admin.register(MoonetixTransaction)
class MoonetixTransactionAdmin(admin.ModelAdmin):
    list_display = ["transaction_id", "wall_user_id", "reward_micro", "status", "offer_name", "created_at"]
    search_fields = ["transaction_id", "wall_user_id"]
    list_filter = ["status"]

    # The ledger is written by postbacks only.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ["user", "balance_micro", "age_confirmed_at"]
