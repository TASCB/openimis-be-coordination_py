"""GraphQL schema (Query + Mutation) for the Coordination module.

Concatenated into the global openIMIS schema by the assembly (same mechanism as
``training`` / ``payment_cycle``). openIMIS merges every module's ``Query``/``Mutation``
by multiple inheritance (``class Query(*queries, ObjectType)``), and GraphQL type names
are global — so ALL fields, types and inputs here are ``coordination``-prefixed to avoid
colliding with ``social_protection`` (which owns ``activity`` / ``ActivityGQLType``),
``training`` (``TransitionInput``), etc.
"""
import graphene
import graphene_django_optimizer as gql_optimizer
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils.translation import gettext as _

from core.schema import OrderedDjangoFilterConnectionField
from core.services import wait_for_mutation

from coordination.apps import CoordinationConfig
from coordination.models import CoordinationActivity, Department
from coordination.gql_queries import (
    CoordinationActivityGQLType, CoordinationDepartmentGQLType,
    UnifiedCalendarEventGQLType, CoordinationSummaryGQLType, CoordinationStatusCountGQLType,
)
from coordination.services import CoordinationSummaryService
from coordination.gql_mutations import (
    CreateCoordinationActivityMutation, UpdateCoordinationActivityMutation, DeleteCoordinationActivityMutation,
    SubmitCoordinationActivityMutation, ManagerApproveCoordinationActivityMutation,
    OfficerApproveCoordinationActivityMutation, DeptApproveCoordinationActivityMutation,
    RejectCoordinationActivityMutation, ReviseCoordinationActivityMutation, CancelCoordinationActivityMutation,
    CreateCoordinationDepartmentMutation, UpdateCoordinationDepartmentMutation, DeleteCoordinationDepartmentMutation,
)


def _check(user, perms):
    if type(user) is AnonymousUser or not user.id or not user.has_perms(perms):
        raise PermissionDenied(_('unauthorized'))


def _overlap(qs, date_from, date_to):
    """Rows whose [start, end] interval overlaps the [date_from, date_to] window."""
    return qs.filter(start_datetime__lt=date_to, end_datetime__gt=date_from)


class Query(graphene.ObjectType):
    coordination_activity = OrderedDjangoFilterConnectionField(
        CoordinationActivityGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        client_mutation_id=graphene.String(),
        show_deleted=graphene.Boolean(),
    )
    coordination_department = OrderedDjangoFilterConnectionField(
        CoordinationDepartmentGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        client_mutation_id=graphene.String(),
        show_deleted=graphene.Boolean(),
    )

    coordination_activity_calendar = graphene.List(
        CoordinationActivityGQLType,
        date_from=graphene.DateTime(required=True),
        date_to=graphene.DateTime(required=True),
        status=graphene.String(),
        department_id=graphene.UUID(),
        location_id=graphene.Int(),
    )

    # Cross-module aggregation: Coordination + Training + Communications events.
    coordination_unified_calendar = graphene.List(
        UnifiedCalendarEventGQLType,
        date_from=graphene.DateTime(required=True),
        date_to=graphene.DateTime(required=True),
        department_id=graphene.UUID(),
        status=graphene.String(),
        sources=graphene.List(graphene.String),
    )

    coordination_summary = graphene.Field(
        CoordinationSummaryGQLType,
        date_from=graphene.DateTime(),
        date_to=graphene.DateTime(),
        department_id=graphene.UUID(),
    )

    # -- resolvers ----------------------------------------------------------
    def resolve_coordination_activity(self, info, **kwargs):
        _check(info.context.user, CoordinationConfig.gql_activity_search_perms)
        filters = [] if kwargs.get('show_deleted') else [Q(is_deleted=False)]
        client_mutation_id = kwargs.get('client_mutation_id')
        if client_mutation_id:
            wait_for_mutation(client_mutation_id)
            filters.append(Q(mutations__mutation__client_mutation_id=client_mutation_id))
        return gql_optimizer.query(CoordinationActivity.objects.filter(*filters).distinct(), info)

    def resolve_coordination_department(self, info, **kwargs):
        _check(info.context.user, CoordinationConfig.gql_department_search_perms)
        filters = [] if kwargs.get('show_deleted') else [Q(is_deleted=False)]
        client_mutation_id = kwargs.get('client_mutation_id')
        if client_mutation_id:
            wait_for_mutation(client_mutation_id)
            filters.append(Q(mutations__mutation__client_mutation_id=client_mutation_id))
        return gql_optimizer.query(Department.objects.filter(*filters), info)

    def resolve_coordination_activity_calendar(self, info, date_from, date_to, **kwargs):
        _check(info.context.user, CoordinationConfig.gql_dashboard_view_perms)
        qs = _overlap(CoordinationActivity.objects.filter(is_deleted=False), date_from, date_to)
        if kwargs.get('status'):
            qs = qs.filter(status=kwargs['status'])
        if kwargs.get('department_id'):
            qs = qs.filter(department_id=kwargs['department_id'])
        if kwargs.get('location_id'):
            qs = qs.filter(location_id=kwargs['location_id'])
        # NB: apply the settings visibility matrix here (scope by viewer department/group)
        # once the CoordinationSetting store is wired — see docs / SettingsPage.
        return gql_optimizer.query(qs.distinct().order_by('start_datetime'), info)

    def resolve_coordination_unified_calendar(self, info, date_from, date_to, **kwargs):
        _check(info.context.user, CoordinationConfig.gql_dashboard_view_perms)
        status = kwargs.get('status')
        department_id = kwargs.get('department_id')
        sources = set(kwargs.get('sources') or ['COORDINATION', 'TRAINING', 'COMMUNICATIONS'])
        events = []

        # --- Coordination activities ---
        if 'COORDINATION' in sources:
            qs = _overlap(CoordinationActivity.objects.filter(is_deleted=False), date_from, date_to)
            if status:
                qs = qs.filter(status=status)
            if department_id:
                qs = qs.filter(department_id=department_id)
            for a in qs.select_related('department'):
                events.append(UnifiedCalendarEventGQLType(
                    id=str(a.id), code=a.code, title=a.title, status=a.status,
                    start_datetime=a.start_datetime, end_datetime=a.end_datetime,
                    source='COORDINATION',
                    department=a.department.name if a.department_id else None))

        # --- Training events (optional module: import lazily, degrade gracefully) ---
        if 'TRAINING' in sources and not department_id:
            try:
                from training.models import Training
                tqs = _overlap(Training.objects.filter(is_deleted=False), date_from, date_to)
                if status:
                    tqs = tqs.filter(status=status)
                for t in tqs:
                    events.append(UnifiedCalendarEventGQLType(
                        id=str(t.id), code=t.code, title=t.title, status=t.status,
                        start_datetime=t.start_datetime, end_datetime=t.end_datetime,
                        source='TRAINING', department=None))
            except Exception:
                pass

        # --- Communications activities (optional module) ---
        if 'COMMUNICATIONS' in sources and not department_id:
            try:
                from communications.models import CommunicationActivity
                cqs = _overlap(CommunicationActivity.objects.filter(is_deleted=False), date_from, date_to)
                if status:
                    cqs = cqs.filter(status=status)
                for c in cqs:
                    events.append(UnifiedCalendarEventGQLType(
                        id=str(c.id), code=getattr(c, 'code', None), title=c.title, status=c.status,
                        start_datetime=c.start_datetime, end_datetime=c.end_datetime,
                        source='COMMUNICATIONS', department=None))
            except Exception:
                pass

        events.sort(key=lambda e: e.start_datetime)
        return events

    def resolve_coordination_summary(self, info, **kwargs):
        _check(info.context.user, CoordinationConfig.gql_dashboard_view_perms)
        data = CoordinationSummaryService(info.context.user).get_summary(
            date_from=kwargs.get('date_from'), date_to=kwargs.get('date_to'),
            department_id=kwargs.get('department_id'))
        return CoordinationSummaryGQLType(
            total_activities=data['total_activities'],
            activities_this_week=data['activities_this_week'],
            pending_approval=data['pending_approval'],
            approved_activities=data['approved_activities'],
            by_status=[CoordinationStatusCountGQLType(**r) for r in data['by_status']],
        )


class Mutation(graphene.ObjectType):
    # Activity CRUD
    create_coordination_activity = CreateCoordinationActivityMutation.Field()
    update_coordination_activity = UpdateCoordinationActivityMutation.Field()
    delete_coordination_activity = DeleteCoordinationActivityMutation.Field()
    # Activity approval chain (FE action == mutation == STATUS_TRANSITIONS key)
    submit_coordination_activity = SubmitCoordinationActivityMutation.Field()
    manager_approve_coordination_activity = ManagerApproveCoordinationActivityMutation.Field()
    officer_approve_coordination_activity = OfficerApproveCoordinationActivityMutation.Field()
    dept_approve_coordination_activity = DeptApproveCoordinationActivityMutation.Field()
    reject_coordination_activity = RejectCoordinationActivityMutation.Field()
    revise_coordination_activity = ReviseCoordinationActivityMutation.Field()
    cancel_coordination_activity = CancelCoordinationActivityMutation.Field()
    # Department
    create_coordination_department = CreateCoordinationDepartmentMutation.Field()
    update_coordination_department = UpdateCoordinationDepartmentMutation.Field()
    delete_coordination_department = DeleteCoordinationDepartmentMutation.Field()
