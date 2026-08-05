import logging
import uuid

from django.apps import AppConfig
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)

MODULE_NAME = 'coordination'

IMIS_ADMINISTRATOR_SYSTEM = 64

DEFAULT_DEPARTMENTS = [
    ('COORD', 'Coordination Department'),
    ('TARGETING', 'Targeting / Registry'),
    ('ENROLLMENT', 'Enrollment'),
    ('PAYMENT', 'Payment'),
    ('GRIEVANCE', 'Grievance'),
    ('PUBLIC_WORKS', 'Public Works'),
    ('LIVELIHOODS', 'Livelihoods'),
    ('MONITORING', 'Monitoring and Evaluation'),
    ('COMMS', 'Communications'),
    ('GENERAL_ADMIN', 'General Administration'),
]

DEFAULT_CONFIG = {
    # --- Activity ---
    'gql_activity_search_perms': ['251101'],
    'gql_activity_create_perms': ['251102'],
    'gql_activity_update_perms': ['251103'],
    'gql_activity_delete_perms': ['251104'],
    # --- Approval chain (one right per hop) ---
    'gql_activity_manager_approve_perms': ['251110'],
    'gql_activity_officer_approve_perms': ['251111'],
    'gql_activity_dept_approve_perms': ['251112'],
    # --- Department / unit ---
    'gql_department_search_perms': ['251201'],
    'gql_department_manage_perms': ['251202'],
    # --- Dashboard / calendar ---
    'gql_dashboard_view_perms': ['251601'],
    'gql_unified_calendar_view_perms': ['251602'],
    # --- Settings (visibility matrix) ---
    'gql_coordination_admin_perms': ['251901'],
    # --- Seeding ---
    'seed_departments': True,
}

# All right codes managed by this module (granted to the admin role on migrate).
ALL_RIGHTS = [
    251101, 251102, 251103, 251104,
    251110, 251111, 251112,
    251201, 251202,
    251601, 251602,
    251901,
]


class CoordinationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = MODULE_NAME

    # rights
    gql_activity_search_perms = []
    gql_activity_create_perms = []
    gql_activity_update_perms = []
    gql_activity_delete_perms = []
    gql_activity_manager_approve_perms = []
    gql_activity_officer_approve_perms = []
    gql_activity_dept_approve_perms = []
    gql_department_search_perms = []
    gql_department_manage_perms = []
    gql_dashboard_view_perms = []
    gql_unified_calendar_view_perms = []
    gql_coordination_admin_perms = []
    # behaviour
    seed_departments = True

    def ready(self):
        from core.models import ModuleConfiguration
        cfg = ModuleConfiguration.get_or_default(MODULE_NAME, DEFAULT_CONFIG)
        self.__load_config(cfg)
        post_migrate.connect(on_post_migrate, sender=self)

    @classmethod
    def __load_config(cls, cfg):
        for field in cfg:
            if hasattr(CoordinationConfig, field):
                setattr(CoordinationConfig, field, cfg[field])


def on_post_migrate(sender, **kwargs):
    """Idempotent seeding run after this app's tables exist."""
    apps = kwargs.get('apps')
    try:
        _seed_admin_rights(apps)
    except Exception as exc:  # never break the migrate of other apps
        logger.warning('coordination: rights seeding skipped (%s)', exc)
    try:
        if CoordinationConfig.seed_departments:
            _seed_departments(apps)
    except Exception as exc:
        logger.warning('coordination: department seeding skipped (%s)', exc)


def _seed_admin_rights(apps):
    Role = apps.get_model('core', 'Role')
    RoleRight = apps.get_model('core', 'RoleRight')
    role = Role.objects.filter(is_system=IMIS_ADMINISTRATOR_SYSTEM, validity_to__isnull=True).first()
    if not role:
        return
    for right_id in ALL_RIGHTS:
        if not RoleRight.objects.filter(role=role, right_id=right_id, validity_to__isnull=True).exists():
            RoleRight.objects.create(role=role, right_id=right_id, audit_user_id=1)


def _seed_departments(apps):
    # Seed via the migration-state model, which lacks HistoryModel.save(); so the UUID
    # PK and the (NOT NULL) audit FKs must be supplied explicitly.
    Department = apps.get_model('coordination', 'Department')
    User = apps.get_model('core', 'User')
    admin = User.objects.order_by('id').first()
    if not admin:
        return  # no user yet (fresh bootstrap) — departments can be created later
    for code, name in DEFAULT_DEPARTMENTS:
        if not Department.objects.filter(code=code).exists():
            Department.objects.create(
                id=uuid.uuid4(), code=code, name=name, is_active=True, version=1,
                user_created_id=admin.id, user_updated_id=admin.id,
            )
