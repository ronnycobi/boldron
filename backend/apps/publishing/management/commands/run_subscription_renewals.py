"""Open the next billing cycle for every subscription whose period has ended (spec §24).

The scheduler is the OS — run this from cron / a systemd timer, e.g. hourly:

    0 * * * * cd /app/backend && python manage.py run_subscription_renewals

It is deterministic and idempotent: a cycle order is opened only when the period
has ended and no cycle order is still outstanding, so running it repeatedly never
double-bills. Each opened cycle is a REAL, payable order — nothing is auto-charged
or faked.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.publishing import subscriptions


class Command(BaseCommand):
    help = "Open due subscription billing cycles as real orders (for cron/systemd)."

    def handle(self, *args, **options):
        opened = subscriptions.renew_due()
        self.stdout.write(self.style.SUCCESS(f"Opened {opened} subscription cycle(s)."))
        return f"opened={opened}"
