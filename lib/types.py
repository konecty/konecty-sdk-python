import re
from datetime import datetime
from typing import Any, Optional, Self

from pydantic import BaseModel, Field
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema


class KonectyDateTimeError(Exception):
    """Exceção base para erros de data/hora."""

    pass


class KonectyDateTimeFormatError(KonectyDateTimeError):
    """Exceção para erros de formato de data/hora."""

    def __init__(self):
        super().__init__("Data em formato inválido")


class KonectyDateTimeTypeError(KonectyDateTimeError):
    """Exceção para erros de tipo de data/hora."""

    def __init__(self):
        super().__init__("Tipo inválido para KonectyDateTime")


class KonectyDateTime(datetime):
    """Classe personalizada para manipular datetime com o formato {'$date': 'ISO8601 string'}."""

    @classmethod
    def from_datetime(cls, dt: datetime) -> Self:
        return cls(
            dt.year,
            dt.month,
            dt.day,
            dt.hour,
            dt.minute,
            dt.second,
            dt.microsecond,
            dt.tzinfo,
        )

    @classmethod
    def from_json(cls, json: dict[str, Any]) -> Self:
        date_str = json["$date"]
        date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return cls(
            date.year,
            date.month,
            date.day,
            date.hour,
            date.minute,
            date.second,
            date.microsecond,
            date.tzinfo,
        )

    @classmethod
    def from_any(cls, value: Any) -> Self:
        if isinstance(value, dict) and "$date" in value:
            return cls.from_json(value)
        if isinstance(value, datetime):
            return cls.from_datetime(value)
        if isinstance(value, str):
            return cls.from_isoformat(value)
        raise KonectyDateTimeTypeError

    @classmethod
    def from_isoformat(cls, value: str) -> Self:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return cls(
            date.year,
            date.month,
            date.day,
            date.hour,
            date.minute,
            date.second,
            date.microsecond,
            date.tzinfo,
        )

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, dict) and "$date" in v:
            try:
                return datetime.fromisoformat(v["$date"].replace("Z", "+00:00"))
            except Exception as e:
                raise KonectyDateTimeFormatError from e
        elif isinstance(v, datetime):
            return v
        raise KonectyDateTimeTypeError

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> CoreSchema:
        """Define o schema para serialização/deserialização do Pydantic."""
        return core_schema.json_or_python_schema(
            json_schema=core_schema.typed_dict_schema(
                {
                    "$date": core_schema.typed_dict_field(core_schema.str_schema()),
                },
                total=True,
            ),
            python_schema=core_schema.datetime_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: {"$date": x.isoformat()}
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: Any, handler: Any
    ) -> JsonSchemaValue:
        """Define o schema JSON para documentação."""
        json_schema = handler(core_schema)
        json_schema.update(
            examples=["2023-01-01T00:00:00Z"],
            type="string",
            format="date-time",
        )
        return json_schema

    def to_json(self):
        return {"$date": self.isoformat()}


class Address(BaseModel):
    """Representa um endereço completo.

    Esta classe modela informações detalhadas de um endereço, incluindo
    dados geográficos e informações de localização específicas.
    """

    number: str | None = Field(None, description="Número do endereço.")
    postal_code: str | None = Field(
        None, description="Código postal ou CEP do endereço."
    )
    street: str | None = Field(None, description="Nome da rua, avenida ou logradouro.")
    district: str | None = Field(None, description="Bairro ou distrito.")
    city: str | None = Field(None, description="Cidade.")
    state: str | None = Field(None, description="Estado ou província.")
    place_type: str | None = Field(
        None, description="Tipo de logradouro (por exemplo, Rua, Avenida, Praça)."
    )
    complement: str | None = Field(
        None, description="Informações complementares do endereço."
    )
    country: str | None = Field(None, description="País.")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


class KonectyUser(BaseModel):
    """Representa um usuário do Konecty."""

    id: str = Field(alias="_id")
    name: str = Field(alias="name")
    active: bool = Field(alias="active")


class KonectyBaseModel(BaseModel):
    """Modelo base para documentos do Konecty."""

    id: str = Field(alias="_id")
    created_at: KonectyDateTime = Field(alias="_createdAt")
    created_by: KonectyUser = Field(alias="_createdBy")
    updated_at: KonectyDateTime = Field(alias="_updatedAt")
    updated_by: KonectyUser = Field(alias="_updatedBy")
    user: list[KonectyUser] = Field(alias="_user")


class KonectyLabel(BaseModel):
    pt_br: str = Field(alias="pt_BR")
    en: str = Field(alias="en")


class KonectyPhone(BaseModel):
    country_code: Optional[int] = Field(None, ge=1, le=999, alias="countryCode")
    phone_number: Optional[str] = Field(
        None, max_length=11, min_length=8, alias="phoneNumber"
    )
    type: Optional[str] = Field(
        None,
        description="Tipo do telefone (por exemplo, celular, fixo, comercial)",
        alias="type",
    )

    model_config = {
        "populate_by_name": True,
        "extra": "allow",
    }

    @classmethod
    def empty(cls) -> Self:
        return cls(countryCode=None, phoneNumber=None, type=None)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls.model_validate(data)

    @classmethod
    def from_string(cls, value: str) -> Self:
        return cls(
            phoneNumber=re.sub(r"\D", "", value),
            countryCode=55,
            type="mobile",
        )

    @classmethod
    def from_any(cls, value: Any) -> Self | None:
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls.from_string(value)
        if isinstance(value, dict):
            return cls.from_dict(value)
        raise ValueError("Invalid value for KonectyPhone")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


class KonectyLookup(BaseModel):
    """Representa uma referência a outro documento no Konecty."""

    id: str = Field(alias="_id")


class KonectyEmail(BaseModel):
    """Representa um endereço de e-mail."""

    address: Optional[str] = Field(None, description="Endereço de e-mail válido")

    model_config = {
        "populate_by_name": True,
        "extra": "allow",
    }

    @classmethod
    def empty(cls) -> Self:
        return cls(address=None)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls.model_validate(data)

    @classmethod
    def from_string(cls, value: str) -> Self:
        return cls(address=value)

    @classmethod
    def from_any(cls, value: Any) -> Self | None:
        if value is None:
            return None
        if isinstance(value, str):
            return cls.from_string(value)
        if isinstance(value, dict):
            return cls.from_dict(value)
        if isinstance(value, cls):
            return value
        raise ValueError("Invalid value for KonectyEmail")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


class KonectyPersonName(BaseModel):
    """Representa um nome completo de pessoa."""

    first: str | None = Field(None, description="Primeiro nome")
    last: str | None = Field(None, description="Sobrenome")
    full: str = Field(description="Nome completo")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls.model_validate(data)

    @classmethod
    def from_string(cls, value: str) -> Self:
        name = value.split(" ")
        return cls(first=name[0], last=" ".join(name[1:]), full=value)

    @classmethod
    def from_any(cls, value: Any) -> Self:
        if isinstance(value, str):
            return cls.from_string(value)
        if isinstance(value, dict):
            return cls.from_dict(value)
        if isinstance(value, cls):
            return value
        raise ValueError("Invalid value for KonectyPersonName")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)
