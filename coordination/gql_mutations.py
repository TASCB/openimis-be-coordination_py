"""

GraphQL mutations for the Coordination module.

"""
import graphene
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _

from core.gql.gql_mutations.base_mutation import (
    BaseHistoryModelCreateMutationMixin, BaseHistoryModelUpdateMutationMixin,
    BaseHistoryModelDeleteMutationMixin, BaseMutation,
)
from core.schema import OpenIMISMutation

from coordination.apps import CoordinationConfig
from coordination.models import (
    CoordinationActivity, Department, CoordinationActivityMutation, DepartmentMutation, ActivityStatus,
)
from coordination.services import ActivityService, DepartmentService


# --- graphene enums (exposed in inputs) ------------------------------------
def _gql_enum(name, choices_cls):
    return graphene.Enum(name, [(c.value, c.value) for c in choices_cls])


ActivityStatusEnum = _gql_enum('CoordinationActivityStatusInput', ActivityStatus)


def _strip_client(data):
    data.pop('client_mutation_id', None)
    data.pop('client_mutation_label', None)


def _journal(mutation_model, fk_name, user, client_mutation_id, obj):
    if client_mutation_id and obj is not None:
        mutation_model.object_mutated(user, client_mutation_id=client_mutation_id, **{fk_name: obj})


# ===========================================================================
# Activity
# ===========================================================================
class CreateCoordinationActivityInput(OpenIMISMutation.Input):
    code = graphene.String(required=False)
    title = graphene.String(required=True)
    description = graphene.String(required=False)
    department_id = graphene.UUID(required=False)
    start_datetime = graphene.DateTime(required=True)
    end_datetime = graphene.DateTime(required=True)
    location_id = graphene.Int(required=False)
    venue = graphene.String(required=False)
    responsible_id = graphene.UUID(required=False)   # core User pk is a UUID
    status = graphene.Field(ActivityStatusEnum, required=False)


class UpdateCoordinationActivityInput(CreateCoordinationActivityInput):
    id = graphene.UUID(required=True)


class CreateCoordinationActivityMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_module = 'coordination'
    _mutation_class = 'CreateCoordinationActivityMutation'

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        if not user.has_perms(CoordinationConfig.gql_activity_create_perms):
            raise PermissionDenied(_('unauthorized'))

    @classmethod
    def _mutate(cls, user, **data):
        client_mutation_id = data.get('client_mutation_id')
        _strip_client(data)
        res = ActivityService(user).create(data)
        if res['success']:
            obj = CoordinationActivity.objects.get(id=res['data']['id'])
            _journal(CoordinationActivityMutation, 'activity', user, client_mutation_id, obj)
        return res if not res['success'] else None

    class Input(CreateCoordinationActivityInput):
        pass


class UpdateCoordinationActivityMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_module = 'coordination'
    _mutation_class = 'UpdateCoordinationActivityMutation'
    _model = CoordinationActivity

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        if not user.has_perms(CoordinationConfig.gql_activity_update_perms):
            raise PermissionDenied(_('unauthorized'))

    @classmethod
    def _mutate(cls, user, **data):
        client_mutation_id = data.get('client_mutation_id')
        _strip_client(data)
        res = ActivityService(user).update(data)
        if res['success']:
            obj = CoordinationActivity.objects.get(id=data['id'])
            _journal(CoordinationActivityMutation, 'activity', user, client_mutation_id, obj)
        return res if not res['success'] else None

    class Input(UpdateCoordinationActivityInput):
        pass


class DeleteCoordinationActivityMutation(BaseHistoryModelDeleteMutationMixin, BaseMutation):
    _mutation_module = 'coordination'
    _mutation_class = 'DeleteCoordinationActivityMutation'
    _model = CoordinationActivity

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        if not user.has_perms(CoordinationConfig.gql_activity_delete_perms):
            raise PermissionDenied(_('unauthorized'))

    @classmethod
    def _mutate(cls, user, **data):
        _strip_client(data)
        service = ActivityService(user)
        for identifier in data.get('ids', []):
            res = service.delete({'id': identifier})
            if not res['success']:
                return res
        return None

    class Input(OpenIMISMutation.Input):
        ids = graphene.List(graphene.UUID)


# --- status workflow (multi-level approval) --------------------------------
class CoordinationTransitionInput(OpenIMISMutation.Input):
    id = graphene.UUID(required=True)
    reason = graphene.String(required=False)


# action -> the CoordinationConfig permission-list attribute controlling that hop.
_ACTION_PERMS = {
    'submit': 'gql_activity_update_perms',
    'revise': 'gql_activity_update_perms',
    'cancel': 'gql_activity_update_perms',
    'managerApprove': 'gql_activity_manager_approve_perms',
    'officerApprove': 'gql_activity_officer_approve_perms',
    'deptApprove': 'gql_activity_dept_approve_perms',
    # rejection is available to any approval level; the from-state check in the service
    # bounds who can reject at which stage.
    'reject': 'gql_activity_manager_approve_perms',
}


class _TransitionLogic:
    """Plain (non-graphene) mixin shared by the status-workflow mutations.

    Must NOT be a graphene mutation itself — subclassing a processed graphene mutation
    that already carries an ``Input`` triggers an InputObjectType MRO error.
    """
    _action = None

    @classmethod
    def _validate_mutation(cls, user, **data):
        # NB: do NOT call super()._validate_mutation — the only base in the MRO is
        # BaseMutation whose _validate_mutation is abstract (raises NotImplementedError).
        perms = getattr(CoordinationConfig, _ACTION_PERMS[cls._action])
        if not user.has_perms(perms):
            raise PermissionDenied(_('unauthorized'))

    @classmethod
    def _mutate(cls, user, **data):
        _strip_client(data)
        res = ActivityService(user).transition(
            data.get('id'), cls._action, reason=data.get('reason'))
        return res if not res['success'] else None


class SubmitCoordinationActivityMutation(_TransitionLogic, BaseMutation):
    _mutation_module = 'coordination'
    _mutation_class = 'SubmitCoordinationActivityMutation'
    _action = 'submit'

    class Input(CoordinationTransitionInput):
        pass


class ManagerApproveCoordinationActivityMutation(_TransitionLogic, BaseMutation):
    _mutation_module = 'coordination'
    _mutation_class = 'ManagerApproveCoordinationActivityMutation'
    _action = 'managerApprove'

    class Input(CoordinationTransitionInput):
        pass


class OfficerApproveCoordinationActivityMutation(_TransitionLogic, BaseMutation):
    _mutation_module = 'coordination'
    _mutation_class = 'OfficerApproveCoordinationActivityMutation'
    _action = 'officerApprove'

    class Input(CoordinationTransitionInput):
        pass


class DeptApproveCoordinationActivityMutation(_TransitionLogic, BaseMutation):
    _mutation_module = 'coordination'
    _mutation_class = 'DeptApproveCoordinationActivityMutation'
    _action = 'deptApprove'

    class Input(CoordinationTransitionInput):
        pass


class RejectCoordinationActivityMutation(_TransitionLogic, BaseMutation):
    _mutation_module = 'coordination'
    _mutation_class = 'RejectCoordinationActivityMutation'
    _action = 'reject'

    class Input(CoordinationTransitionInput):
        pass


class ReviseCoordinationActivityMutation(_TransitionLogic, BaseMutation):
    _mutation_module = 'coordination'
    _mutation_class = 'ReviseCoordinationActivityMutation'
    _action = 'revise'

    class Input(CoordinationTransitionInput):
        pass


class CancelCoordinationActivityMutation(_TransitionLogic, BaseMutation):
    _mutation_module = 'coordination'
    _mutation_class = 'CancelCoordinationActivityMutation'
    _action = 'cancel'

    class Input(CoordinationTransitionInput):
        pass


# ===========================================================================
# Department CRUD
# ===========================================================================
class CreateCoordinationDepartmentInput(OpenIMISMutation.Input):
    code = graphene.String(required=True)
    name = graphene.String(required=True)
    description = graphene.String(required=False)
    is_active = graphene.Boolean(required=False)


class UpdateCoordinationDepartmentInput(CreateCoordinationDepartmentInput):
    id = graphene.UUID(required=True)


class CreateCoordinationDepartmentMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_module = 'coordination'
    _mutation_class = 'CreateCoordinationDepartmentMutation'

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        if not user.has_perms(CoordinationConfig.gql_department_manage_perms):
            raise PermissionDenied(_('unauthorized'))

    @classmethod
    def _mutate(cls, user, **data):
        client_mutation_id = data.get('client_mutation_id')
        _strip_client(data)
        res = DepartmentService(user).create(data)
        if res['success']:
            obj = Department.objects.get(id=res['data']['id'])
            _journal(DepartmentMutation, 'department', user, client_mutation_id, obj)
        return res if not res['success'] else None

    class Input(CreateCoordinationDepartmentInput):
        pass


class UpdateCoordinationDepartmentMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_module = 'coordination'
    _mutation_class = 'UpdateCoordinationDepartmentMutation'
    _model = Department

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        if not user.has_perms(CoordinationConfig.gql_department_manage_perms):
            raise PermissionDenied(_('unauthorized'))

    @classmethod
    def _mutate(cls, user, **data):
        client_mutation_id = data.get('client_mutation_id')
        _strip_client(data)
        res = DepartmentService(user).update(data)
        if res['success']:
            obj = Department.objects.get(id=data['id'])
            _journal(DepartmentMutation, 'department', user, client_mutation_id, obj)
        return res if not res['success'] else None

    class Input(UpdateCoordinationDepartmentInput):
        pass


class DeleteCoordinationDepartmentMutation(BaseHistoryModelDeleteMutationMixin, BaseMutation):
    _mutation_module = 'coordination'
    _mutation_class = 'DeleteCoordinationDepartmentMutation'
    _model = Department

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        if not user.has_perms(CoordinationConfig.gql_department_manage_perms):
            raise PermissionDenied(_('unauthorized'))

    @classmethod
    def _mutate(cls, user, **data):
        _strip_client(data)
        service = DepartmentService(user)
        for identifier in data.get('ids', []):
            res = service.delete({'id': identifier})
            if not res['success']:
                return res
        return None

    class Input(OpenIMISMutation.Input):
        ids = graphene.List(graphene.UUID)
