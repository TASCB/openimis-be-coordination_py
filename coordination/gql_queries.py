"""GraphQL object types for the Coordination module."""
import graphene
from graphene_django import DjangoObjectType

from core import ExtendedConnection
from coordination.models import CoordinationActivity, Department


class CoordinationDepartmentGQLType(DjangoObjectType):
    uuid = graphene.String(source='uuid')

    class Meta:
        model = Department
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            'id': ['exact'],
            'code': ['exact', 'istartswith', 'icontains', 'iexact'],
            'name': ['exact', 'istartswith', 'icontains', 'iexact'],
            'is_active': ['exact'],
            'is_deleted': ['exact'],
            'date_created': ['exact', 'lt', 'lte', 'gt', 'gte'],
            'version': ['exact'],
        }
        connection_class = ExtendedConnection


class CoordinationActivityGQLType(DjangoObjectType):
    uuid = graphene.String(source='uuid')

    class Meta:
        model = CoordinationActivity
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            'id': ['exact'],
            'code': ['exact', 'istartswith', 'icontains', 'iexact'],
            'title': ['exact', 'istartswith', 'icontains', 'iexact'],
            'status': ['exact', 'in'],
            'venue': ['exact', 'icontains'],
            'department_id': ['exact'],
            'location_id': ['exact'],
            'responsible_id': ['exact'],
            'start_datetime': ['exact', 'lt', 'lte', 'gt', 'gte'],
            'end_datetime': ['exact', 'lt', 'lte', 'gt', 'gte'],
            'is_deleted': ['exact'],
            'date_created': ['exact', 'lt', 'lte', 'gt', 'gte'],
            'version': ['exact'],
        }
        connection_class = ExtendedConnection


# --- Non-model types -------------------------------------------------------
class UnifiedCalendarEventGQLType(graphene.ObjectType):
    """A calendar event aggregated from any source module (Coordination, Training,
    Communications). Presentational — matches the FE calendar event shape."""
    id = graphene.String()
    code = graphene.String()
    title = graphene.String()
    status = graphene.String()
    start_datetime = graphene.DateTime()
    end_datetime = graphene.DateTime()
    source = graphene.String()      # 'COORDINATION' | 'TRAINING' | 'COMMUNICATIONS'
    department = graphene.String()


class CoordinationStatusCountGQLType(graphene.ObjectType):
    status = graphene.String()
    count = graphene.Int()


class CoordinationSummaryGQLType(graphene.ObjectType):
    total_activities = graphene.Int()
    activities_this_week = graphene.Int()
    pending_approval = graphene.Int()
    approved_activities = graphene.Int()
    by_status = graphene.List(CoordinationStatusCountGQLType)
