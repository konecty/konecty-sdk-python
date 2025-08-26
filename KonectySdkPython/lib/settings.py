"""Módulo para gerenciar configurações do Konecty."""

import json
import os
from typing import Any, Type, TypeVar

from pydantic import BaseModel

from .client import KonectyClient

T = TypeVar("T", bound=BaseModel)


def _convert_value(value: str, field_type: Type[Any] | None) -> Any:
    """Converte um valor string para o tipo correto.

    Args:
        value: Valor string a ser convertido
        field_type: Tipo para converter o valor

    Returns:
        Valor convertido para o tipo correto
    """
    if field_type is None:
        return value

    try:
        if field_type is bool:
            return value.lower() == "true"
        elif field_type is int:
            return int(value)
        elif field_type is float:
            return float(value)
        elif field_type is list:
            return [item.strip() for item in value.split(",")]
        elif field_type is dict:
            return json.loads(value)
        else:
            return value
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


async def fill_settings(settings_class: Type[T]) -> T:
    """Preenche as configurações de uma classe com valores do Konecty.

    Args:
        settings_class: Classe de configurações que herda de BaseModel.

    Returns:
        Instância da classe de configurações preenchida com valores do Konecty.
    """
    client = KonectyClient(
        base_url=os.getenv("KONECTY_URL", "http://localhost:3000"),
        token=os.getenv("KONECTY_TOKEN", "invalid_key"),
    )

    settings_dict = {}
    fields_to_fetch = []

    # Primeiro verifica variáveis de ambiente e coleta campos que precisam ser buscados no Konecty
    for field_name in settings_class.model_fields.keys():
        env_value = os.getenv(field_name.upper())
        if env_value is not None and env_value.strip():
            field_type = settings_class.model_fields[field_name].annotation
            converted_value = _convert_value(env_value, field_type)
            if converted_value is not None:
                settings_dict[field_name] = converted_value
        else:
            fields_to_fetch.append(field_name)

    # Busca todas as configurações do Konecty de uma vez
    if fields_to_fetch:
        konecty_settings = await client.get_settings(
            [field.upper() for field in fields_to_fetch]
        )

        for field_name, value in konecty_settings.items():
            if value is not None and value.strip():
                field_type = settings_class.model_fields[field_name].annotation
                converted_value = _convert_value(value, field_type)
                if converted_value is not None:
                    settings_dict[field_name] = converted_value

    return settings_class.model_construct(**settings_dict)


def fill_settings_sync(settings_class: Type[T]) -> T:
    """Versão síncrona de fill_settings.

    Args:
        settings_class: Classe de configurações que herda de BaseModel.

    Returns:
        Instância da classe de configurações preenchida com valores do Konecty.
    """
    client = KonectyClient(
        base_url=os.getenv("KONECTY_URL", "http://localhost:3000"),
        token=os.getenv("KONECTY_TOKEN", "invalid_key"),
    )

    settings_dict = {}
    fields_to_fetch = []

    # Primeiro verifica variáveis de ambiente e coleta campos que precisam ser buscados no Konecty
    for field_name in settings_class.model_fields.keys():
        env_value = os.getenv(field_name.upper())
        if env_value is not None and env_value.strip():
            field_type = settings_class.model_fields[field_name].annotation
            converted_value = _convert_value(env_value, field_type)
            if converted_value is not None:
                settings_dict[field_name] = converted_value
        else:
            # Se não encontrou na variável de ambiente, adiciona à lista para buscar no Konecty
            fields_to_fetch.append(field_name)

    # Busca todas as configurações do Konecty de uma vez
    if fields_to_fetch:
        konecty_settings = client.get_settings_sync(
            [field.upper() for field in fields_to_fetch]
        )

        for field_name, value in konecty_settings.items():
            if value is not None and value.strip():
                field_type = settings_class.model_fields[field_name].annotation
                converted_value = _convert_value(value, field_type)
                if converted_value is not None:
                    settings_dict[field_name] = converted_value

    return settings_class.model_construct(**settings_dict)
