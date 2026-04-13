"""
Pydantic models — validación de input/output de la API.

Input: las 23 features del modelo.
Output: predicción + probabilidad.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Feature names — deben coincidir exactamente con el orden en features_v4.parquet
# ---------------------------------------------------------------------------
FEATURE_NAMES = [
    "url_length",
    "url_query_length",
    "content_length",
    "method_is_get",
    "method_is_post",
    "method_is_put",
    "url_pct27",
    "url_pct3c",
    "url_pct20",
    "url_dashdash",
    "url_script",
    "url_select",
    "url_union",
    "url_or",
    "url_and",
    "content_param_count",
    "content_param_density",
    "content_pct27",
    "content_pct3c",
    "content_pct20",
    "content_dashdash",
    "content_script",
    "url_pct_density",
]

FEATURE_NAMES_SET = set(FEATURE_NAMES)


class PredictRequest(BaseModel):
    """Payload del POST /predict."""

    url_length: Annotated[float, Field(ge=0, description="Longitud de la URL")]
    url_query_length: Annotated[float, Field(ge=0, description="Longitud del query string")]
    content_length: Annotated[float, Field(ge=0, description="Longitud del body (0 para GET)")]
    method_is_get: Annotated[int, Field(ge=0, le=1, description="1 si GET, 0 si no")]
    method_is_post: Annotated[int, Field(ge=0, le=1, description="1 si POST, 0 si no")]
    method_is_put: Annotated[int, Field(ge=0, le=1, description="1 si PUT, 0 si no")]
    url_pct27: Annotated[int, Field(ge=0, le=1, description="Indicador %27 en URL")]
    url_pct3c: Annotated[int, Field(ge=0, le=1, description="Indicador %3C en URL")]
    url_pct20: Annotated[int, Field(ge=0, le=1, description="Indicador %20 en URL")]
    url_dashdash: Annotated[int, Field(ge=0, le=1, description="Indicador -- en URL")]
    url_script: Annotated[int, Field(ge=0, le=1, description="Indicador 'script' en URL")]
    url_select: Annotated[int, Field(ge=0, le=1, description="Indicador 'select' en URL")]
    url_union: Annotated[int, Field(ge=0, le=1, description="Indicador 'union' en URL")]
    url_or: Annotated[int, Field(ge=0, le=1, description="Indicador 'or' en URL")]
    url_and: Annotated[int, Field(ge=0, le=1, description="Indicador 'and' en URL")]
    content_param_count: Annotated[float, Field(ge=0, description="Count de '=' en body")]
    content_param_density: Annotated[float, Field(ge=0, description="param_count / content_length")]
    content_pct27: Annotated[int, Field(ge=0, le=1, description="Indicador %27 en body")]
    content_pct3c: Annotated[int, Field(ge=0, le=1, description="Indicador %3C en body")]
    content_pct20: Annotated[int, Field(ge=0, le=1, description="Indicador %20 en body")]
    content_dashdash: Annotated[int, Field(ge=0, le=1, description="Indicador -- en body")]
    content_script: Annotated[int, Field(ge=0, le=1, description="Indicador 'script' en body")]
    url_pct_density: Annotated[float, Field(ge=0, description="Densidad de '%' en URL")]

    @field_validator("method_is_get", "method_is_post", "method_is_put")
    @classmethod
    def method_sum_check(cls, v: int, info) -> int:
        return v

    def to_array(self) -> list[float]:
        """Convierte el request a un array ordered de features."""
        return [getattr(self, f) for f in FEATURE_NAMES]


class PredictResponse(BaseModel):
    """Respuesta del POST /predict."""

    prediction: Annotated[int, Field(description="0 = normal, 1 = attack")]
    probability: Annotated[float, Field(ge=0, le=1, description="P(attack) según el modelo")]
    threshold: Annotated[float, Field(description="Threshold usado para la decisión")]
    model_version: Annotated[str, Field(description="Versión/tag del modelo cargado")]


class HealthResponse(BaseModel):
    """Respuesta del GET /health."""

    status: str
    model_loaded: bool
    model_version: str | None
