"""Service layer for the Coordination module.

Per-entity CRUD services extend ``core.services.BaseService`` (uniform
``{success, data, error}`` contract + service signals). Status transitions live in
``ActivityService.transition`` — the single chokepoint for the multi-level maker-checker
workflow. ``STATUS_TRANSITIONS`` is the whole state machine; the per-level permission
gating lives in ``gql_mutations._ACTION_PERMS``.
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.translation import gettext as _

from core.services import BaseService
from core.services.utils import output_exception, model_representation, check_authentication
from core.signals import register_service_signal

from coordination.models import CoordinationActivity, Department, ActivityStatus, ActivityCodeSequence
from coordination.validations import ActivityValidation, DepartmentValidation

logger = logging.getLogger(__name__)
S = ActivityStatus
COORDINATION_CODE_PREFIX = 'COO'


# Allowed status transitions: action -> (from-states, to-state).
# The action name matches the GraphQL mutation service name and the FE STATUS_ACTIONS key.
STATUS_TRANSITIONS = {
    'submit':         ((S.DRAFT, S.REJECTED),                                     S.SUBMITTED),
    'managerApprove': ((S.SUBMITTED,),                                            S.MANAGER_APPROVED),
    'officerApprove': ((S.MANAGER_APPROVED,),                                     S.OFFICER_APPROVED),
    'deptApprove':    ((S.OFFICER_APPROVED,),                                     S.APPROVED),
    'reject':         ((S.SUBMITTED, S.MANAGER_APPROVED, S.OFFICER_APPROVED),     S.REJECTED),
    'revise':         ((S.REJECTED,),                                             S.DRAFT),
    'cancel':         ((S.DRAFT, S.SUBMITTED, S.MANAGER_APPROVED,
                        S.OFFICER_APPROVED, S.APPROVED),                          S.CANCELLED),
}


class DepartmentService(BaseService):
    OBJECT_TYPE = Department

    def __init__(self, user, validation_class=DepartmentValidation):
        super().__init__(user, validation_class)

    @register_service_signal('coordination_department_service.create')
    def create(self, obj_data):
        return super().create(obj_data)

    @register_service_signal('coordination_department_service.update')
    def update(self, obj_data):
        return super().update(obj_data)

    @register_service_signal('coordination_department_service.delete')
    def delete(self, obj_data):
        return super().delete(obj_data)


class ActivityService(BaseService):
    OBJECT_TYPE = CoordinationActivity

    def __init__(self, user, validation_class=ActivityValidation):
        super().__init__(user, validation_class)

    @register_service_signal('coordination_activity_service.create')
    @transaction.atomic
    def create(self, obj_data):
        self._assign_code(obj_data)
        return super().create(obj_data)

    @register_service_signal('coordination_activity_service.update')
    def update(self, obj_data):
        return super().update(obj_data)

    @staticmethod
    def _assign_code(obj_data):
        sequence = ActivityCodeSequence.objects.select_for_update().get(prefix=COORDINATION_CODE_PREFIX)
        sequence.last_number += 1
        sequence.save()
        obj_data['code'] = f'{COORDINATION_CODE_PREFIX}{sequence.last_number:08}'

    @register_service_signal('coordination_activity_service.delete')
    def delete(self, obj_data):
        return super().delete(obj_data)

    @register_service_signal('coordination_activity_service.transition')
    def transition(self, activity_id, action, **ctx):
        """Guarded status transition. Returns the BaseService ``{success, ...}`` shape.

        This is the ONLY place an activity's status changes — the multi-level approval
        chain is entirely ``STATUS_TRANSITIONS`` (legal from->to) plus the per-action
        permission check performed by the mutation before we get here.
        """
        try:
            if action not in STATUS_TRANSITIONS:
                return {'success': False, 'message': _('coordination.validation.unknown_action'),
                        'detail': str(action)}
            activity = CoordinationActivity.objects.filter(id=activity_id, is_deleted=False).first()
            if not activity:
                return {'success': False, 'message': _('coordination.validation.not_found'),
                        'detail': str(activity_id)}
            from_states, to_state = STATUS_TRANSITIONS[action]
            if activity.status not in from_states:
                return {'success': False,
                        'message': _('coordination.validation.invalid_status_transition'),
                        'detail': f'{activity.status} -> {to_state} ({action})'}
            if action in ('reject', 'revise') and ctx.get('reason'):
                key = 'reject_reason' if action == 'reject' else 'revise_reason'
                activity.json_ext = {**(activity.json_ext or {}), key: ctx['reason']}
            activity.status = to_state
            activity.save(username=self.user.username)
            return {'success': True, 'message': _('coordination.transition.success'),
                    'data': model_representation(activity)}
        except Exception as exc:
            return output_exception(model_name=self.OBJECT_TYPE.__name__, method='transition', exception=exc)


class CoordinationSummaryService:
    """Read service for the (optional) dashboard KPIs."""

    def __init__(self, user):
        self.user = user

    @check_authentication
    def get_summary(self, *, date_from=None, date_to=None, department_id=None):
        now = timezone.now()
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

        qs = CoordinationActivity.objects.filter(is_deleted=False)
        if department_id:
            qs = qs.filter(department_id=department_id)
        if date_from:
            qs = qs.filter(start_datetime__gte=date_from)
        if date_to:
            qs = qs.filter(start_datetime__lte=date_to)

        pending = [ActivityStatus.SUBMITTED, ActivityStatus.MANAGER_APPROVED, ActivityStatus.OFFICER_APPROVED]
        by_status = list(qs.values('status').order_by('status').annotate(count=Count('id')))
        return {
            'total_activities': qs.count(),
            'activities_this_week': qs.filter(start_datetime__gte=week_start, start_datetime__lt=week_end).count(),
            'pending_approval': qs.filter(status__in=pending).count(),
            'approved_activities': qs.filter(status=ActivityStatus.APPROVED).count(),
            'by_status': [{'status': r['status'], 'count': r['count']} for r in by_status],
        }
