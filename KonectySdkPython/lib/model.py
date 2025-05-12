from typing import Any, Dict, List, Optional, Type, TypeVar, cast

from pydantic import BaseModel, Field, create_model
from pydantic.fields import FieldInfo

from .types import (
    Address,
    KonectyDateTime,
    KonectyEmail,
    KonectyLookup,
    KonectyPersonName,
    KonectyPhone,
)

T = TypeVar("T")
ModelType = TypeVar("ModelType", bound=BaseModel)


class KonectyModelGenerator:
    def __init__(self, schema: Dict[str, Any]):
        self.schema = schema
        self.type_mapping: Dict[str, Type[Any]] = {
            "json": dict,
            "richText": str,
            "lookup": KonectyLookup,
            "picklist": str,
            "url": str,
            "boolean": bool,
            "text": str,
            "dateTime": KonectyDateTime,
            "address": Address,
            "email": KonectyEmail,
            "phone": KonectyPhone,
            "personName": KonectyPersonName,
        }

    def generate_model(self, language: str = "en") -> Type[BaseModel]:
        fields: Dict[str, tuple[Type[Any], FieldInfo]] = {}
        for field in self.schema["fields"]:
            field_name = field["name"]
            field_raw_type = field["type"]
            description = (
                field["help"].get(language, field["help"].get("en", ""))
                if "help" in field
                else field["label"].get(language, field["label"].get("en", ""))
            )

            base_type = self._get_field_type(field_raw_type)
            current_type = base_type

            if field.get("isList"):
                current_type = List[base_type]  # type: ignore

            if field.get("minSelected", 1) > 1 or field.get("maxSelected", 1) > 1:
                current_type = List[base_type]  # type: ignore

            is_required = (
                field.get("isRequired", False) or field.get("minSelected", 0) > 0
            )

            if not is_required and "defaultValue" not in field:
                current_type = Optional[base_type]  # type: ignore

            field_params = {
                "alias": field_name,
                "description": description,
            }

            if "defaultValue" in field:
                field_params["default"] = field["defaultValue"]

            if not is_required and "defaultValue" not in field:
                field_params["default"] = None

            fields[self._clean_name_for_pydantic(field_name)] = (
                current_type,
                Field(**field_params),
            )

        model_name = self.schema["name"]
        return create_model(model_name, **fields)

    def _clean_name_for_pydantic(self, name: str) -> str:
        return name.replace("_", "")

    def _get_field_type(self, field_type: str) -> Type[Any]:
        result = self.type_mapping.get(field_type, Any)
        return cast(Type[Any], result)
