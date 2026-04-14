"""
Pydantic models — validación de input/output de la API.

Input: las 23 features del modelo.
Output: predicción + probabilidad.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Feature names — orden y nombres exactos de features_v4.parquet
# ---------------------------------------------------------------------------
FEATURE_NAMES = [
    "method_is_get",
    "method_is_post",
    "method_is_put",
    "url_length",
    "url_param_count",
    "url_pct_density",
    "url_path_depth",
    "url_query_length",
    "url_has_query",
    "url_has_pct27",
    "url_has_pct3c",
    "url_has_dashdash",
    "url_has_script",
    "url_has_select",
    "content_length",
    "content_pct_density",
    "content_param_count",
    "content_param_density",
    "content_has_pct27",
    "content_has_pct3c",
    "content_has_dashdash",
    "content_has_script",
    "content_has_select",
]

FEATURE_NAMES_SET = set(FEATURE_NAMES)


class PredictRequest(BaseModel):
    """Payload del POST /predict."""

    method_is_get: Annotated[int, Field(ge=0, le=1, description="1 si GET, 0 si no")]
    method_is_post: Annotated[int, Field(ge=0, le=1, description="1 si POST, 0 si no")]
    method_is_put: Annotated[int, Field(ge=0, le=1, description="1 si PUT, 0 si no")]
    url_length: Annotated[float, Field(ge=0, description="Longitud de la URL")]
    url_param_count: Annotated[float, Field(ge=0, description="Cantidad de parámetros en la URL")]
    url_pct_density: Annotated[float, Field(ge=0, description="Densidad de '%' en la URL")]
    url_path_depth: Annotated[float, Field(ge=0, description="Profundidad del path")]
    url_query_length: Annotated[float, Field(ge=0, description="Longitud del query string")]
    url_has_query: Annotated[int, Field(ge=0, le=1, description="1 si la URL tiene query string")]
    url_has_pct27: Annotated[int, Field(ge=0, le=1, description="Indicador %27 en URL")]
    url_has_pct3c: Annotated[int, Field(ge=0, le=1, description="Indicador %3C en URL")]
    url_has_dashdash: Annotated[int, Field(ge=0, le=1, description="Indicador -- en URL")]
    url_has_script: Annotated[int, Field(ge=0, le=1, description="Indicador 'script' en URL")]
    url_has_select: Annotated[int, Field(ge=0, le=1, description="Indicador 'select' en URL")]
    content_length: Annotated[float, Field(ge=0, description="Longitud del body (0 para GET)")]
    content_pct_density: Annotated[float, Field(ge=0, description="Densidad de '%' en el body")]
    content_param_count: Annotated[float, Field(ge=0, description="Count de '=' en body")]
    content_param_density: Annotated[float, Field(ge=0, description="param_count / content_length")]
    content_has_pct27: Annotated[int, Field(ge=0, le=1, description="Indicador %27 en body")]
    content_has_pct3c: Annotated[int, Field(ge=0, le=1, description="Indicador %3C en body")]
    content_has_dashdash: Annotated[int, Field(ge=0, le=1, description="Indicador -- en body")]
    content_has_script: Annotated[int, Field(ge=0, le=1, description="Indicador 'script' en body")]
    content_has_select: Annotated[int, Field(ge=0, le=1, description="Indicador 'select' en body")]

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
