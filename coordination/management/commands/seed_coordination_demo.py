"""Seed (or purge) demonstration coordination activities.

Every row carries ``json_ext['_seed'] = 'demo'`` so ``--purge`` removes exactly this set.
Activities are written straight to their status: demo data, not a test of the approval chain.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import User
from location.models import Location
from coordination.models import CoordinationActivity, Department
from coordination.services import ActivityService

DEMO = {'_seed': 'demo'}

# (title, department, status, district, start offset in days (negative = past), days, venue,
#  responsible login, description, reject reason)
DEMO_ACTIVITIES = [
    ('Quarterly Programme Coordination Meeting', 'COORD', 'APPROVED', 'Dodoma CC', 5, 1,
     'TASAF HQ Boardroom', 'tz_coord_manager',
     'All departments report progress against the quarterly workplan.', None),
    ('Targeting Update Planning Workshop', 'TARGETING', 'SUBMITTED', 'Dodoma CC', 12, 2,
     'Dodoma Hotel', 'tz_coord_officer',
     'Plan the household targeting update and agree the field calendar.', None),
    ('Enrollment Verification Mission - Mwanza', 'ENROLLMENT', 'MANAGER_APPROVED', 'Mwanza CC', 18, 4,
     'Mwanza Region PAAs', 'tz_coord_officer',
     'Joint verification of newly enrolled households with council staff.', None),
    ('Payment Cycle Readiness Review', 'PAYMENT', 'OFFICER_APPROVED', 'Dodoma CC', 9, 1,
     'TASAF HQ', 'tz_coord_offapprover',
     'Check paylists, FSP readiness and MUSE settings before the next cycle.', None),
    ('GRM Refresher Training for PAA Staff', 'GRIEVANCE', 'DRAFT', 'Arusha CC', 30, 3,
     'Arusha Regional Office', 'tz_coord_officer',
     'Refresher on grievance intake, categories and response timelines.', None),
    ('Public Works Site Inspection - Iringa', 'PUBLIC_WORKS', 'APPROVED', 'Iringa MC', -20, 3,
     'Iringa District sites', 'tz_coord_linemgr',
     'Inspect road and water sub-projects before the next payment.', None),
    ('Livelihoods Savings Groups Review', 'LIVELIHOODS', 'APPROVED', 'Njombe', -45, 2,
     'Njombe Town Hall', 'tz_coord_manager',
     'Review savings-group performance and livelihood grant uptake.', None),
    ('M&E Data Quality Audit', 'MONITORING', 'REJECTED', 'Ilala MC', 25, 5,
     'Ilala Municipal Office', 'tz_coord_officer',
     'Spot-check registry and payment data against source documents.',
     'Clashes with the payment cycle; resubmit after the cycle closes.'),
    ('Communications Calendar Alignment', 'COMMS', 'CANCELLED', 'Dodoma CC', 3, 1,
     'TASAF HQ', 'tz_coord_officer',
     'Align department events with the communications calendar.', None),
    ('Annual Workplan Validation', 'GENERAL_ADMIN', 'APPROVED', 'Dodoma CC', -90, 2,
     'Dodoma Convention Centre', 'tz_coord_manager',
     'Validate the annual workplan and budget with all departments.', None),
]


class Command(BaseCommand):
    help = 'Seed (or purge) demonstration coordination activities.'

    def add_arguments(self, parser):
        parser.add_argument('--purge', action='store_true', help='Delete every demo-tagged activity.')

    def handle(self, *args, **options):
        if options['purge']:
            n = CoordinationActivity.objects.filter(json_ext___seed='demo').delete()[0]
            self.stdout.write(self.style.SUCCESS(f'Purged demo activities: {n}'))
            return
        user = User.objects.filter(username='Admin').first() or User.objects.order_by('id').first()
        if not user:
            self.stderr.write('No user available to attribute the seed to.')
            return
        with transaction.atomic():
            created = self._seed(user)
        self.stdout.write(self.style.SUCCESS(f'Activities created: {created}'))

    def _seed(self, user):
        service = ActivityService(user)
        departments = {d.code: d for d in Department.objects.filter(is_deleted=False)}
        today = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
        created = 0
        for (title, dept, status, district, offset, days, venue, login,
             description, reject_reason) in DEMO_ACTIVITIES:
            if CoordinationActivity.objects.filter(title=title, is_deleted=False).exists():
                continue
            start = today + timedelta(days=offset)
            loc = Location.objects.filter(type='D', name__iexact=district, validity_to__isnull=True).first()
            responsible = User.objects.filter(username=login).first()
            json_ext = dict(DEMO)
            if reject_reason:
                json_ext['reject_reason'] = reject_reason
            res = service.create({
                'title': title, 'status': status, 'description': description,
                'department_id': departments[dept].id if dept in departments else None,
                'start_datetime': start, 'end_datetime': start + timedelta(days=days, hours=-1),
                'location_id': loc.id if loc else None, 'venue': venue,
                'responsible_id': responsible.id if responsible else None,
                'json_ext': json_ext,
            })
            if res['success']:
                created += 1
            else:
                self.stderr.write(f'{title}: {res.get("message")} {res.get("detail", "")}')
        return created
