"""Registro fechado de variantes de configuração da qualificação OpenSwissHCC."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.core import PipelineError


MULTIPHASE_KEY = "multiphase_rgb"
FALLBACK_KEY = "venous_single_phase_fallback"
_EXTRA_KEY = re.compile(r"^venous_single_phase_fallback_[a-z0-9_]+$")


def parse_extra_configs(values: Iterable[str] | None) -> dict[str, Path]:
    """Converta argumentos KEY=PATH, rejeitando chaves ambíguas ou duplicadas."""
    result: dict[str, Path] = {}
    for raw in values or ():
        key, separator, value = str(raw).partition("=")
        key = key.strip()
        value = value.strip()
        if not separator or not key or not value:
            raise PipelineError("--extra-config exige KEY=PATH.")
        if key in result:
            raise PipelineError(f"Configuração adicional duplicada: {key!r}.")
        result[key] = Path(value)
    return result


def authorized_config_paths(
    *,
    multiphase_config: Path,
    fallback_config: Path,
    additional_configs: Mapping[str, Path] | None = None,
) -> dict[str, Path]:
    """Retorne somente as configurações pré-declaradas e com chaves fechadas."""
    paths = {
        MULTIPHASE_KEY: Path(multiphase_config).resolve(),
        FALLBACK_KEY: Path(fallback_config).resolve(),
    }
    for key, value in dict(additional_configs or {}).items():
        key = str(key)
        if key in paths or not _EXTRA_KEY.fullmatch(key):
            raise PipelineError(f"Chave de configuração adicional não autorizada: {key!r}.")
        paths[key] = Path(value).resolve()
    resolved = list(paths.values())
    if len(resolved) != len(set(resolved)):
        raise PipelineError("Configurações autorizadas não podem apontar para o mesmo arquivo.")
    return paths


def resolve_candidate_config(
    candidate: Mapping[str, Any], config_paths: Mapping[str, Path]
) -> tuple[str, Path]:
    """Selecione por tipo e hash bruto, nunca por caminho vindo do candidato."""
    kind = str(candidate.get("candidate_kind", MULTIPHASE_KEY))
    if kind == MULTIPHASE_KEY:
        allowed = {MULTIPHASE_KEY}
    elif kind == FALLBACK_KEY:
        allowed = {key for key in config_paths if key == FALLBACK_KEY or key.startswith(FALLBACK_KEY + "_")}
    else:
        raise PipelineError(f"Tipo de candidato não autorizado: {kind!r}.")
    expected_hash = str(candidate.get("config_sha256", ""))
    matches = [
        (key, Path(path).resolve())
        for key, path in config_paths.items()
        if key in allowed and _sha256(Path(path).resolve()) == expected_hash
    ]
    if len(matches) != 1:
        raise PipelineError("Configuração do candidato não corresponde exatamente ao registro autorizado.")
    return matches[0]
