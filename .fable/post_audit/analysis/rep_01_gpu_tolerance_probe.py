# -*- coding: utf-8 -*-
"""REP-01 — sonda de tolerâncias GPU/CUDA (fecha BLK-GPU-TOLERANCES).

Mede, por família de op realmente usada pelo sistema (conv3d/interpolate ~
segmentação; matmul/softmax/layernorm ~ embeddings; reduções):
  (1) run-to-run na GPU com flags determinísticas LIGADAS;
  (2) run-to-run na GPU em modo PADRÃO de produção (flags default);
  (3) GPU vs CPU em float32 (máx |delta| absoluto e relativo).
Seeds fixas, 3 repetições. MEDIÇÃO pura — nada de produção muda.
"""
import json
import os
from pathlib import Path

SAIDA = Path(r"C:/Users/profurg/Desktop/sander/argos-main/.fable/post_audit/evidence/REP-01")

# necessario ANTES de qualquer op CUDA para o modo deterministico de cublas
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import torch  # noqa: E402


def _ops(seed: int, device: str) -> dict[str, torch.Tensor]:
    """Executa as familias de ops com entradas geradas por seed fixa."""
    g = torch.Generator(device="cpu").manual_seed(seed)
    resultados: dict[str, torch.Tensor] = {}

    # matmul (embeddings/classificador)
    a = torch.randn(512, 1152, generator=g)
    b = torch.randn(1152, 1152, generator=g)
    resultados["matmul"] = a.to(device) @ b.to(device)

    # softmax + layernorm (atencao/normalizacao de embedder)
    x = torch.randn(256, 1152, generator=g)
    xd = x.to(device)
    resultados["softmax"] = torch.softmax(xd, dim=-1)
    resultados["layernorm"] = torch.nn.functional.layer_norm(xd, (1152,))

    # conv3d (segmentacao nnU-Net-like)
    vol = torch.randn(1, 8, 48, 64, 64, generator=g)
    peso = torch.randn(16, 8, 3, 3, 3, generator=g)
    resultados["conv3d"] = torch.nn.functional.conv3d(vol.to(device), peso.to(device), padding=1)

    # interpolate trilinear (resample de mascaras/volumes)
    resultados["interpolate_trilinear"] = torch.nn.functional.interpolate(
        vol.to(device), scale_factor=1.5, mode="trilinear", align_corners=False
    )

    # reducoes (contagens/medias)
    resultados["sum_reduction"] = resultados["conv3d"].sum(dim=(2, 3, 4))
    resultados["mean_reduction"] = resultados["interpolate_trilinear"].mean(dim=(2, 3, 4))
    return resultados


def _compara(r1: dict, r2: dict) -> dict[str, dict]:
    saida = {}
    for nome in r1:
        t1, t2 = r1[nome].double(), r2[nome].double()
        delta = (t1 - t2).abs()
        max_abs = float(delta.max())
        escala = t1.abs().clamp_min(1e-30)
        max_rel = float((delta / escala).max())
        saida[nome] = {
            "bitwise_igual": bool(torch.equal(r1[nome], r2[nome])),
            "max_abs": max_abs,
            "max_rel": max_rel,
        }
    return saida


def _regime(deterministico: bool, seed: int) -> dict:
    torch.backends.cudnn.deterministic = deterministico
    torch.backends.cudnn.benchmark = not deterministico
    if deterministico:
        torch.use_deterministic_algorithms(True, warn_only=True)
    else:
        torch.use_deterministic_algorithms(False)
    execucoes = [_ops(seed, "cuda") for _ in range(3)]
    torch.cuda.synchronize()
    par_12 = _compara(execucoes[0], execucoes[1])
    par_13 = _compara(execucoes[0], execucoes[2])
    pior = {}
    for nome in par_12:
        pior[nome] = {
            "bitwise_igual_3runs": par_12[nome]["bitwise_igual"] and par_13[nome]["bitwise_igual"],
            "max_abs": max(par_12[nome]["max_abs"], par_13[nome]["max_abs"]),
            "max_rel": max(par_12[nome]["max_rel"], par_13[nome]["max_rel"]),
        }
    return pior


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    assert torch.cuda.is_available(), "GPU indisponivel"
    seed = 20260824

    resultado = {
        "ambiente": {
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "cudnn": torch.backends.cudnn.version(),
            "device": torch.cuda.get_device_name(0),
            "cublas_workspace": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
        },
        "seed": seed,
        "repeticoes": 3,
    }

    # (1) run-to-run com determinismo LIGADO
    resultado["gpu_run_to_run_deterministico"] = _regime(True, seed)
    # (2) run-to-run em modo PADRAO de producao
    resultado["gpu_run_to_run_padrao_producao"] = _regime(False, seed)

    # (3) GPU vs CPU (regime padrao)
    torch.use_deterministic_algorithms(False)
    torch.backends.cudnn.deterministic = False
    r_gpu = {k: v.cpu() for k, v in _ops(seed, "cuda").items()}
    r_cpu = _ops(seed, "cpu")
    resultado["gpu_vs_cpu_float32"] = _compara(r_gpu, r_cpu)

    destino = SAIDA / "gpu_tolerance_probe_2026-08-24.json"
    destino.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
