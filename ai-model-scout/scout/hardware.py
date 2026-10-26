"""Estimate whether a model will run on the configured machine."""

from __future__ import annotations

from .models import ModelCandidate

# Approximate bytes per parameter for common formats (weights only).
BYTES = {"FP16": 2.0, "Q8": 1.07, "Q4": 0.61}
CONTEXT_OVERHEAD_GB = 1.5   # KV cache for a modest context window + runtime buffers


def weights_gb(params_b: float, fmt: str) -> float:
    return params_b * BYTES[fmt] * 1.05 + CONTEXT_OVERHEAD_GB


def assess(c: ModelCandidate, machine: dict) -> None:
    vram = float(machine.get("gpu_vram_gb", 0))
    ram = float(machine.get("system_ram_gb", 0))
    if machine.get("unified_memory"):
        # Apple Silicon: roughly 75% of unified memory is usable by the GPU.
        vram, ram = ram * 0.75, 0.0

    if c.params_b is None:
        if c.source == "github":
            c.fit, c.fit_detail = "check", "Tool/library: size not published; most run on any modern GPU or CPU"
        else:
            c.fit, c.fit_detail = "check", "Size not published; check the model card"
        return

    p = c.params_b
    if c.category != "llm":
        # Audio models are usually run unquantised in PyTorch; allow for activations.
        need = p * 2.0 * 1.3 + 2.0
        if need <= vram:
            c.fit, c.fit_detail = "gpu", f"~{need:.0f} GB VRAM at FP16"
        elif need <= vram + ram * 0.5:
            c.fit, c.fit_detail = "offload", f"~{need:.0f} GB at FP16; needs CPU offload or 8-bit loading"
        else:
            c.fit, c.fit_detail = "too_big", f"~{need:.0f} GB at FP16"
        return

    for fmt in ("FP16", "Q8", "Q4"):
        need = weights_gb(p, fmt)
        if need <= vram:
            c.fit, c.fit_detail = "gpu", f"Fully on GPU at {fmt} (~{need:.0f} GB)"
            return

    q4 = weights_gb(p, "Q4")
    if q4 <= (vram + ram) * 0.9:
        if c.is_moe and (c.active_params_b or 0) <= 40:
            active = f"{c.active_params_b:g}B active" if c.active_params_b else "few active params"
            c.fit = "offload"
            c.fit_detail = f"Q4 ~{q4:.0f} GB: GPU + system RAM. MoE ({active}), so speed is usable"
        else:
            c.fit = "offload_slow"
            c.fit_detail = f"Q4 ~{q4:.0f} GB: GPU + system RAM, dense model so expect a few tokens/s"
        return
    c.fit, c.fit_detail = "too_big", f"Q4 needs ~{q4:.0f} GB; more than this machine has"


FIT_LABEL = {
    "gpu": "Runs on GPU",
    "offload": "Runs (GPU+RAM)",
    "offload_slow": "Runs slowly",
    "too_big": "Too big",
    "check": "Check card",
}
