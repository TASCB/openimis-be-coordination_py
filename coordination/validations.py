"""Validation classes for Coordination entities (openIMIS core validation mixins)."""
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from core.validation import BaseModelValidation, UniqueCodeValidationMixin, ObjectExistsValidationMixin
from core.validation.stringFieldValidationMixin import StringFieldValidationMixin

from coordination.models import CoordinationActivity, Department


class _CodedValidation(BaseModelValidation, UniqueCodeValidationMixin,
                       ObjectExistsValidationMixin, StringFieldValidationMixin):
    """Shared create/update validation for entities carrying a unique ``code``."""

    @classmethod
    def validate_create(cls, user, **data):
        code = data.get('code', None)
        cls.validate_empty_string(code)
        cls.validate_unique_code_name(code)

    @classmethod
    def validate_update(cls, user, **data):
        id_ = data.get('id', None)
        cls.validate_object_exists(id_)
        code = data.get('code', None)
        if code:
            cls.validate_unique_code_name(code, id_)


class DepartmentValidation(_CodedValidation):
    OBJECT_TYPE = Department


class ActivityValidation(_CodedValidation):
    OBJECT_TYPE = CoordinationActivity

    @classmethod
    def validate_create(cls, user, **data):
        code = data.get('code', None)
        if code:
            cls.validate_empty_string(code)
            cls.validate_unique_code_name(code)
        cls._validate_dates(data)

    @classmethod
    def validate_update(cls, user, **data):
        id_ = data.get('id', None)
        cls.validate_object_exists(id_)
        if 'code' in data:
            existing = CoordinationActivity.objects.filter(id=id_).only('code').first()
            if existing and data.get('code') != existing.code:
                raise ValidationError(_('coordination.validation.code_immutable'))
            if data.get('code'):
                cls.validate_unique_code_name(data.get('code'), id_)
        cls._validate_dates(data)

    @staticmethod
    def _validate_dates(data):
        start = data.get('start_datetime')
        end = data.get('end_datetime')
        if start and end and end < start:
            raise ValidationError(_('coordination.validation.end_before_start'))
