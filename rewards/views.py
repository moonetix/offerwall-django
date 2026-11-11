import logging
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import moonetix
from .models import MoonetixTransaction, Wallet

log = logging.getLogger("moonetix")
User = get_user_model()


def _wallet(user):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet


@login_required
@never_cache
def earn(request):
    """The Earn page. The link is signed here, for the signed-in user only."""
    wallet = _wallet(request.user)
    # Users must be 16 or older. No link is built before they confirm it.
    wall_url = moonetix.wall_url(request.user.pk) if wallet.age_confirmed_at else None
    recent = MoonetixTransaction.objects.filter(wall_user_id=str(request.user.pk), status__isnull=False)[:10]
    return render(request, "rewards/earn.html", {
        "wall_url": wall_url,
        "balance": moonetix.format_micro(wallet.balance_micro),
        "recent": [(row, moonetix.format_micro(row.reward_micro)) for row in recent],
    })


@login_required
@require_POST
def confirm_age(request):
    if request.POST.get("age_16_or_older") != "1":
        return render(request, "rewards/earn.html", {
            "wall_url": None,
            "balance": moonetix.format_micro(_wallet(request.user).balance_micro),
            "recent": [],
            "age_error": True,
        }, status=400)
    _wallet(request.user)
    Wallet.objects.filter(user=request.user, age_confirmed_at__isnull=True).update(age_confirmed_at=timezone.now())
    return redirect("earn")


def _answer(status, body):
    response = HttpResponse(body, status=status, content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "no-store"
    return response


def _one(query, key):
    # Exactly one value, as it arrived. A repeated key gives "" and fails the hash.
    values = query.getlist(key)
    return values[0] if len(values) == 1 else ""


@csrf_exempt  # GET is never CSRF-checked; this keeps it working if the route ever takes POST.
@require_GET
def moonetix_postback(request):
    """
    GET /moonetix/postback/?tx={transaction_id}&user={user_id}&reward={reward}&status={status}&hash={hash}

    Answers 200 only after the change is committed. Any exception rolls back and
    Django answers 500, so Moonetix retries the event later.
    """
    q = request.GET
    tx, user_id, reward, status = (_one(q, k) for k in ("tx", "user", "reward", "status"))

    # 1. The hash first, in constant time. Nothing else runs before this check.
    if not moonetix.valid_postback_hash(tx, user_id, reward, status, _one(q, "hash")):
        return _answer(403, "Invalid hash")

    # 2. Signed values, now check their shape.
    reward_micro = moonetix.to_micro(reward)
    if not tx or len(tx) > 191 or len(user_id) > 100 or reward_micro is None or status not in ("1", "2"):
        return _answer(400, "Bad parameters")

    # 3. Tests from the dashboard always have a transaction_id that starts with test_.
    if tx.startswith("test_"):
        log.info("Moonetix test postback: hash OK, nothing credited tx=%s user=%s status=%s", tx, user_id, status)
        return _answer(200, "Test postback: hash OK, nothing credited")

    # 4. Apply it in one database transaction.
    offer = _one(q, "offer")[:200]
    result = apply_postback(tx, user_id, reward_micro, int(status), offer)
    log.info("Moonetix postback tx=%s user=%s reward=%s status=%s result=%s", tx, user_id, reward, status, result)

    # 5. Committed. 200 also for repeats and ignored events, so Moonetix stops retrying.
    return _answer(200, result)


def _find_user_pk(user_id):
    """The user_id in the link is our user's pk. Anything else (for example test_user) is not ours.
    Using UUID keys? Change the pattern and the int() call."""
    if not re.fullmatch(r"[1-9][0-9]{0,17}", user_id):
        return None
    pk = int(user_id)
    return pk if User.objects.filter(pk=pk).exists() else None


def _add_to_wallet(user_pk, micro):
    Wallet.objects.bulk_create([Wallet(user_id=user_pk)], ignore_conflicts=True)
    Wallet.objects.filter(user_id=user_pk).update(balance_micro=F("balance_micro") + micro)


@transaction.atomic
def apply_postback(tx, user_id, reward_micro, status, offer):
    user_pk = _find_user_pk(user_id)
    if status == MoonetixTransaction.CREDITED and user_pk is None:
        log.warning("Moonetix credit for an unknown user tx=%s user=%s", tx, user_id)
        return "Unknown user, nothing credited"

    # Insert the row, or skip silently if this transaction_id exists. bulk_create is used
    # instead of create(), because an IntegrityError inside atomic() breaks the transaction.
    MoonetixTransaction.objects.bulk_create(
        [MoonetixTransaction(transaction_id=tx, wall_user_id=user_id, reward_micro=reward_micro,
                             status=None, offer_name=offer)],
        ignore_conflicts=True,
    )
    # Lock the row, so two copies of one event wait for each other (PostgreSQL, MySQL).
    row = MoonetixTransaction.objects.select_for_update().get(pk=tx)

    if row.status is None:
        # This request inserted the row: it is the first event for this transaction_id.
        if status == MoonetixTransaction.CREDITED:
            _add_to_wallet(user_pk, reward_micro)
            result = "Credited"
        else:
            # Never credited: remember it, so a late credit for this transaction is never paid.
            result = "Not credited before, nothing taken back"
        row.status = status
        row.save(update_fields=["status", "updated_at"])
        return result

    if status == MoonetixTransaction.REVERSED and row.status == MoonetixTransaction.CREDITED:
        # Take back exactly what was credited, from the user who got it.
        credited_pk = _find_user_pk(row.wall_user_id)
        if credited_pk is not None:
            _add_to_wallet(credited_pk, -row.reward_micro)
        row.status = MoonetixTransaction.REVERSED
        row.save(update_fields=["status", "updated_at"])
        return "Reversed"

    return "Already processed"
