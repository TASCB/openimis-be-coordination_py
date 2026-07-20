"""Coordination management models.

An ``Activity`` is a departmental event placed on the coordination calendar. It moves
through a multi-level maker-checker approval workflow (see ``services.STATUS_TRANSITIONS``
and ``docs``/the FE ``STATUS_ACTIONS``). ``Department`` is the department/unit an activity
belongs to.
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import HistoryModel, UUIDModel, ObjectMutation, MutationLog
from core.fields import DateTimeField
from location.models import Location


class ActivityStatus(models.TextChoices):
    DRAFT = 'DRAFT', _('Draft')
    SUBMITTED = 'SUBMITTED', _('Submitted')                      # -> manager
    MANAGER_APPROVED = 'MANAGER_APPROVED', _('Manager approved')  # -> coordination officer
    OFFICER_APPROVED = 'OFFICER_APPROVED', _('Officer approved')  # -> coordination manager
    APPROVED = 'APPROVED', _('Approved')
    REJECTED = 'REJECTED', _('Rejected')
    CANCELLED = 'CANCELLED', _('Cancelled')


# States in which an activity is settled and should not appear as an open item.
TERMINAL_STATUSES = (ActivityStatus.APPROVED, ActivityStatus.REJECTED, ActivityStatus.CANCELLED)


class Department(HistoryModel):
    """Department / unit an activity belongs to (configurable, seedable)."""
    code = models.CharField(max_length=255, blank=False, null=False)
    name = models.CharField(max_length=255, blank=False, null=False)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=['code']), models.Index(fields=['is_active'])]

    def __str__(self):
        return f'{self.code} - {self.name}'


class CoordinationActivity(HistoryModel):
    """A coordination calendar activity with a multi-level approval workflow.

    Named ``CoordinationActivity`` (not ``Activity``) to avoid a reverse-accessor clash
    with ``social_protection.Activity`` on the shared ``User`` audit FKs. The GraphQL
    query field is still ``activity`` (see schema.py), so the frontend is unaffected.
    """
    code = models.CharField(max_length=255, blank=False, null=False)
    title = models.CharField(max_length=255, blank=False, null=False)
    description = models.TextField(blank=True, null=True)
    department = models.ForeignKey(
        Department, on_delete=models.DO_NOTHING, blank=True, null=True,
        related_name='activities')
    start_datetime = DateTimeField(blank=False, null=False)
    end_datetime = DateTimeField(blank=False, null=False)
    location = models.ForeignKey(
        Location, on_delete=models.DO_NOTHING, blank=True, null=True,
        related_name='coordination_activities')
    venue = models.CharField(max_length=255, blank=True, null=True)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING, blank=True, null=True,
        related_name='coordination_activities')
    status = models.CharField(
        max_length=20, choices=ActivityStatus.choices, default=ActivityStatus.DRAFT)

    class Meta:
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['status']),
            models.Index(fields=['start_datetime']),
            models.Index(fields=['end_datetime']),
            models.Index(fields=['department']),
            models.Index(fields=['location']),
            models.Index(fields=['responsible']),
        ]

    def __str__(self):
        return f'{self.code} - {self.title}'


class ActivityCodeSequence(UUIDModel):
    prefix = models.CharField(max_length=16, unique=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'tblCoordinationActivityCodeSequence'

    def __str__(self):
        return f'{self.prefix}{self.last_number:08}'


class CoordinationActivityMutation(UUIDModel, ObjectMutation):
    activity = models.ForeignKey(CoordinationActivity, models.DO_NOTHING, related_name='mutations')
    mutation = models.ForeignKey(MutationLog, models.DO_NOTHING, related_name='coordination_activities')


class DepartmentMutation(UUIDModel, ObjectMutation):
    department = models.ForeignKey(Department, models.DO_NOTHING, related_name='mutations')
    mutation = models.ForeignKey(MutationLog, models.DO_NOTHING, related_name='coordination_departments')
