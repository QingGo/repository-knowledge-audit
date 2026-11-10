"""Parameterized convention-sensitive tasks for an outcome-level KB benchmark.

Each task: a single numpy function whose success depends on conventions that are NOT stated in the
prompt. Conventions are supplied by a KB note (useful) or an outdated note (stale). Hidden tests are
generated from the same parameter set. Families × variants ≈ 28 tasks.
"""
from __future__ import annotations

NATURAL = object()


def _t(tid, family, params, prompt, useful, stale, tests, neutral):
    return {"tid": tid, "family": family, "params": params, "prompt": prompt,
            "useful": useful, "stale": stale, "tests": tests, "neutral": neutral}


# ---------------------------------------------------------------- F1 masked_mean
def _f1(name, denom, empty, dtype):
    d = "per-row count of mask=True" if denom == "valid" else ("S (sequence length)" if denom == "S" else "B*S (global elements per feature)")
    empty_s = "return zeros" if empty == "zeros" else "return NaN"
    prompt = ("Implement `masked_mean(x, mask)` in solution.py. x: float32 numpy [B,S,D]; mask: bool "
              "[B,S] (True = keep). Return a [B,D] mean over kept positions per row.")
    useful = [f"Denominator: {d}.", f"For rows with no kept positions: {empty_s}.",
              f"Output dtype: {dtype}.", "mask=True means the position is kept."]
    stale = [f"Denominator: {'B*S (global)' if denom != 'B*S' else 'per-row count' }.",
             f"For rows with no kept positions: {'return NaN' if empty == 'zeros' else 'return zeros'}.",
             f"Output dtype: {'float16' if dtype == 'float32' else 'float32'}.",
             "mask=False means the position is kept."]
    tests = f'''
import numpy as np
import solution as S

def ref(x, mask):
    B, S_, D = x.shape
    cnt = mask.sum(axis=1, keepdims=True)
    denom = cnt if "{denom}" == "valid" else (S_ if "{denom}" == "S" else B * S_)
    out = (x * mask[..., None]).sum(axis=1) / np.maximum(denom, 1)
    out = out.astype(np.{dtype})
    if "{empty}" == "zeros":
        out[(cnt[:, 0] == 0)] = 0
    else:
        out[(cnt[:, 0] == 0)] = np.nan
    return out

def test_random():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(4, 6, 3)).astype(np.float32)
    mask = rng.random((4, 6)) > 0.35
    got = S.masked_mean(x.copy(), mask.copy())
    assert got.shape == (4, 3) and got.dtype == np.{dtype}, (got.shape, got.dtype)
    assert np.allclose(got, ref(x, mask), atol=1e-5, equal_nan=("{empty}" == "nan"))

def test_empty_row():
    x = np.arange(2 * 3 * 2, dtype=np.float32).reshape(2, 3, 2) + 1
    mask = np.zeros((2, 3), dtype=bool); mask[1, 1:] = True
    got = S.masked_mean(x.copy(), mask.copy())
    if "{empty}" == "zeros":
        assert np.all(got[0] == 0), got
    else:
        assert np.all(np.isnan(got[0])), got
    assert np.allclose(got[1], ref(x, mask)[1], atol=1e-5)
'''
    neutral = ["The repo uses black formatting and ruff lint.", "Tests are run with pytest.",
               "Python version is 3.11; CI uses a CPU-only runner."]
    return _t(name, "masked_mean", dict(denom=denom, empty=empty, dtype=dtype), prompt, useful, stale, tests, neutral)


# ---------------------------------------------------------------- F2 shift_ce
def _f2(name, shift, denom, accum):
    pred = "logits[:, :-1] predict ids[:, 1:] (next-token shift)" if shift == "next" else \
           "logits[:, 1:] predict ids[:, :-1] (previous-token shift)"
    den = "number of valid targets" if denom == "valid" else "B*S"
    acc = "float32/float64" if accum == "f32" else "float64 throughout"
    prompt = ("Implement `shift_ce(logits, ids, ignore_index=-100)` in solution.py. logits: float32 "
              "[B,S,V]; ids: int64 [B,S]. Return the scalar mean cross-entropy (np.float32).")
    if denom == "valid":
        ign_line = "Targets equal to ignore_index are excluded from numerator and denominator."
    else:
        ign_line = "Targets equal to ignore_index are excluded from the numerator only; the denominator stays B*S."
    useful = [f"Labels: {pred}; the unused position is excluded.", f"Reduction: sum over valid targets / {den}.",
              ign_line, f"Accumulate log-softmax in {acc}; return np.float32."]
    stale = [f"Labels: {'logits[:, 1:] predict ids[:, :-1] (previous-token)' if shift == 'next' else 'logits[:, :-1] predict ids[:, 1:] (next-token)'}.",
             f"Reduction: always divide by {'B*S' if denom == 'valid' else 'number of valid targets'}.",
             "Ignored positions still contribute to the loss.",
             "Accumulate in float16 for speed; return np.float16."]
    tests = f'''
import numpy as np
import solution as S

def ref(logits, ids):
    B, S_, V = logits.shape
    if "{shift}" == "next":
        lg = logits.astype(np.float64)[:, :-1, :]; tg = ids[:, 1:]
    else:
        lg = logits.astype(np.float64)[:, 1:, :]; tg = ids[:, :-1]
    m = lg.max(-1, keepdims=True)
    lse = np.log(np.exp(lg - m).sum(-1)) + m[..., 0]
    picked = np.take_along_axis(lg, np.clip(tg, 0, V - 1)[..., None], axis=-1)[..., 0]
    ce = lse - picked
    valid = tg != -100
    if "{denom}" == "valid":
        return np.float32(ce[valid].sum() / valid.sum())
    return np.float32(ce.sum() / (logits.shape[0] * logits.shape[1]))

def test_random():
    rng = np.random.default_rng(1)
    for _ in range(2):
        B, S_, V = 2, 6, 9
        logits = rng.normal(size=(B, S_, V)).astype(np.float32)
        ids = rng.integers(0, V, size=(B, S_)).astype(np.int64)
        ids[0, 3:] = -100
        got = S.shift_ce(logits.copy(), ids.copy())
        assert np.asarray(got, dtype=np.float32).dtype == np.float32
        assert abs(float(got) - float(ref(logits, ids))) <= 1e-4, (got, ref(logits, ids))

def test_denominator():
    rng = np.random.default_rng(2)
    B, S_, V = 2, 5, 7
    logits = rng.normal(size=(B, S_, V)).astype(np.float32)
    ids = rng.integers(0, V, size=(B, S_)).astype(np.int64)
    ids[1, 2:] = -100
    got = S.shift_ce(logits, ids)
    exp = ref(logits, ids)
    assert abs(float(got) - float(exp)) <= 1e-4, (got, exp)
'''
    neutral = ["The repo is a research prototype; no external dependencies beyond numpy.",
               "Formatting is black; lint is ruff.", "The CI runs CPU-only unit tests."]
    return _t(name, "shift_ce", dict(shift=shift, denom=denom, accum=accum), prompt, useful, stale, tests, neutral)


# ---------------------------------------------------------------- F3 topk
def _f3(name, tie, order, ret):
    tie_s = "higher index first" if tie == "high" else "lower index first"
    ord_s = "descending value order" if order == "desc" else "ascending value order"
    ret_s = "numpy arrays (values float32, indices int64)" if ret == "np" else "Python lists"
    prompt = ("Implement `topk_logits(logits, k)` in solution.py. logits: 1-D float32 numpy array. "
              "Return (values, indices) for the top-k entries; tie-breaking and output format follow the project convention.")
    useful = [f"Tie-breaking: when values are equal, {tie_s}.", f"Output order: {ord_s}.",
              f"Return {ret_s}.", "Assume 1 <= k <= len(logits)."]
    stale = [f"Tie-breaking: when values are equal, {'lower index first' if tie == 'high' else 'higher index first'}.",
             f"Output order: {'ascending' if order == 'desc' else 'descending'} value order.",
             f"Return {'Python lists' if ret == 'np' else 'numpy arrays'}.",
             "Ties are unspecified; any order is acceptable."]
    tests = f'''
import numpy as np
import solution as S

def ref(logits, k):
    n = len(logits)
    sec = -np.arange(n) if "{tie}" == "high" else np.arange(n)
    order = np.lexsort((sec, (-np.asarray(logits) if "{order}" == "desc" else np.asarray(logits))))
    idx = order[:k].astype(np.int64)
    return np.asarray(logits)[idx].astype(np.float32), idx

def check(x, k):
    vals, idx = S.topk_logits(x.copy(), k)
    rv, ri = ref(x, k)
    if "{ret}" == "np":
        assert np.asarray(idx).dtype == np.int64
        assert np.asarray(vals).dtype == np.float32
    assert list(np.asarray(idx)) == list(ri), (idx, ri)
    assert np.allclose(np.asarray(vals), rv), (vals, rv)

def test_ties():
    check(np.array([1.0, 3.0, 1.0, 3.0, 2.0], dtype=np.float32), 3)

def test_random():
    rng = np.random.default_rng(3)
    for _ in range(3):
        check(rng.normal(size=14).astype(np.float32), 5)
'''
    neutral = ["The repo is a research prototype.", "Use black/ruff for formatting.",
               "No network access is available to tests."]
    return _t(name, "topk", dict(tie=tie, order=order, ret=ret), prompt, useful, stale, tests, neutral)


# ---------------------------------------------------------------- F4 quantize
def _f4(name, mode, vmax, rnd, zero):
    scale_s = "per-tensor (one scale = amax/MAX)" if mode == "tensor" else "per-channel (one scale per element)"
    rnd_s = "round to nearest even (banker's)" if rnd == "rne" else ("truncate toward zero" if rnd == "trunc" else "floor")
    zero_s = "scale=1 and output zeros" if zero == "scale1" else "scale=NaN and output NaN"
    prompt = ("Implement `quantize_fp8(x)` in solution.py. x: 1-D float32 numpy array. Return "
              "`(xq, scale)` after symmetric quantization/dequantization; exact convention is in the KB.")
    useful = [f"Scale mode: {scale_s}.", f"Maximum representable magnitude: {vmax}.",
              f"Rounding: {rnd_s}.", f"All-zero input: {zero_s}.", "Dequantized xq = round(clamp(x/scale, -MAX, MAX)) * scale; return float32 arrays."]
    stale = [f"Scale mode: {'per-channel' if mode == 'tensor' else 'per-tensor (one scale = amax/MAX)'}.",
             f"Maximum representable magnitude: {'127' if vmax == 448 else ('448' if vmax == 127 else '1024')}.",
             f"Rounding: {'truncate toward zero' if rnd == 'rne' else 'round to nearest even'}.",
             f"All-zero input: {'scale=NaN and output NaN' if zero == 'scale1' else 'scale=1 and output zeros'}.",
             "Return float16 arrays instead of float32."]
    tests = f'''
import numpy as np
import solution as S

def ref(x):
    amax = float(np.max(np.abs(x)))
    if "{mode}" == "tensor":
        scale = np.float32(amax / {vmax}) if amax > 0 else np.float32(1.0 if "{zero}" == "scale1" else np.nan)
        q = x / scale if scale != 0 else x
        q = np.{'round' if rnd == 'rne' else ('trunc' if rnd == 'trunc' else 'floor')}(q)
        q = np.clip(q, -{vmax}, {vmax})
        return (q * scale).astype(np.float32), np.float32(scale)
    scales = np.abs(x) / {vmax}
    scales[scales == 0] = 1.0
    q = np.{'round' if rnd == 'rne' else ('trunc' if rnd == 'trunc' else 'floor')}(x / scales)
    q = np.clip(q, -{vmax}, {vmax})
    return (q * scales).astype(np.float32), scales.astype(np.float32)

def test_basic():
    rng = np.random.default_rng(4)
    x = (rng.normal(size=32) * 3).astype(np.float32)
    xq, sc = S.quantize_fp8(x.copy())
    rxq, rsc = ref(x)
    assert np.asarray(xq).dtype == np.float32
    assert np.allclose(xq, rxq, atol=1e-5)
    assert np.allclose(np.asarray(sc), rsc, atol=1e-6, equal_nan=("{zero}" == "nan"))

def test_zero_and_rounding():
    x = np.zeros(5, dtype=np.float32)
    xq, sc = S.quantize_fp8(x)
    if "{mode}" == "channel":
        assert np.all(xq == 0) and np.all(np.asarray(sc) == 1.0)
    elif "{zero}" == "scale1":
        assert np.all(xq == 0) and float(np.asarray(sc)) == 1.0
    else:
        assert np.all(np.isnan(xq)) and np.isnan(float(np.asarray(sc)))
    if "{mode}" == "tensor" and "{rnd}" == "rne" and {vmax} == 448:
        x2 = np.array([448.0, 1.5], dtype=np.float32)
        xq2, sc2 = S.quantize_fp8(x2)
        assert np.isclose(float(np.asarray(xq2)[1]), 2.0), (xq2, sc2)
'''
    neutral = ["The repo uses black/ruff.", "Unit tests run with pytest on CPU.",
               "The project is a research prototype."]
    return _t(name, "quantize", dict(mode=mode, vmax=vmax, rnd=rnd, zero=zero), prompt, useful, stale, tests, neutral)


# ---------------------------------------------------------------- F5 masked softmax
def _f5(name, fill, allmask, dtype):
    fill_s = "-inf" if fill == "inf" else ("-1e4" if fill == "1e4" else "0")
    am_s = "zeros" if allmask == "zeros" else ("uniform 1/S" if allmask == "uniform" else "NaN")
    prompt = ("Implement `masked_softmax(scores, mask)` in solution.py. scores: float32 [B,S]; mask: "
              "bool [B,S] (True = keep). Return [B,S] softmax over S with masked positions handled per convention.")
    useful = [f"Fill masked positions with {fill_s} before softmax.", f"Rows with all positions masked: {am_s}.",
              f"Compute/return {dtype}.", "mask=True means the position is kept."]
    stale = [f"Fill masked positions with {'0' if fill == 'inf' else '-inf'} before softmax.",
             f"Rows with all positions masked: {'NaN' if allmask == 'zeros' else 'zeros'}.",
             f"Return {'float16' if dtype == 'float32' else 'float32'}.",
             "mask=False means keep."]
    tests = f'''
import numpy as np
import solution as S

def ref(scores, mask):
    s = scores.astype(np.float64).copy()
    fill = -np.inf if "{fill}" == "inf" else (-1e4 if "{fill}" == "1e4" else 0.0)
    s[~mask] = fill
    m = s.max(axis=1, keepdims=True)
    e = np.exp(s - m); out = e / e.sum(axis=1, keepdims=True)
    allm = ~mask.any(axis=1)
    if "{allmask}" == "zeros":
        out[allm] = 0
    elif "{allmask}" == "uniform":
        out[allm] = 1.0 / scores.shape[1]
    else:
        out[allm] = np.nan
    return out.astype(np.{dtype})

def test_basic():
    rng = np.random.default_rng(5)
    s = rng.normal(size=(4, 7)).astype(np.float32)
    mask = rng.random((4, 7)) > 0.3
    mask[2, :] = True
    got = S.masked_softmax(s.copy(), mask.copy())
    assert got.shape == s.shape and got.dtype == np.{dtype}
    assert np.allclose(got, ref(s, mask), atol=1e-6, equal_nan=("{allmask}" == "nan"))

def test_all_masked():
    s = np.ones((2, 4), dtype=np.float32)
    mask = np.zeros((2, 4), dtype=bool); mask[1, 1] = True
    got = S.masked_softmax(s, mask)
    if "{allmask}" == "zeros":
        assert np.all(got[0] == 0)
    elif "{allmask}" == "uniform":
        assert np.allclose(got[0], 0.25)
    else:
        assert np.all(np.isnan(got[0]))
'''
    neutral = ["The repo uses pytest and black.", "CPU-only test runner.", "Research prototype code."]
    return _t(name, "masked_softmax", dict(fill=fill, allmask=allmask, dtype=dtype), prompt, useful, stale, tests, neutral)


# ---------------------------------------------------------------- F6 ce_grad
def _f6(name, shift, denom, ignore):
    pred = "logits[:, :-1] correspond to ids[:, 1:] (next-token)" if shift == "next" else \
           "logits[:, 1:] correspond to ids[:, :-1] (previous-token)"
    den = "number of valid targets" if denom == "valid" else "B*S"
    ign = ("zero gradients at ignored positions" if ignore == "zero"
           else "do NOT zero ignored positions: keep the (softmax - one_hot) gradient there")
    prompt = ("Implement `ce_grad(logits, ids, ignore_index=-100)` in solution.py. logits: float32 "
              "[B,S,V]; ids: int64 [B,S]. Return dlogits (float32, same shape) for mean CE.")
    useful = [f"Shift: {pred}.", f"Gradient: (softmax - one_hot) / {den}.",
              f"Handle ignore_index: {ign}.", "Return float32."]
    stale = [f"Shift: {'logits[:, 1:] correspond to ids[:, :-1]' if shift == 'next' else 'logits[:, :-1] correspond to ids[:, 1:]'}.",
             f"Gradient: divide by {'B*S' if denom == 'valid' else 'number of valid targets'}.",
             f"Handle ignore_index: {'keep the softmax gradient at ignored positions' if ignore == 'zero' else 'zero gradients'}.",
             "Return float16."]
    tests = f'''
import numpy as np
import solution as S

def ref(logits, ids):
    B, S_, V = logits.shape
    d = np.zeros_like(logits, dtype=np.float64)
    if "{shift}" == "next":
        lg = logits.astype(np.float64)[:, :-1, :]; tg = ids[:, 1:]
    else:
        lg = logits.astype(np.float64)[:, 1:, :]; tg = ids[:, :-1]
    m = lg.max(-1, keepdims=True)
    e = np.exp(lg - m); p = e / e.sum(-1, keepdims=True)
    valid = tg != -100
    denom = valid.sum() if "{denom}" == "valid" else B * S_
    oh = np.zeros_like(p)
    np.put_along_axis(oh, np.clip(tg, 0, V - 1)[..., None], 1.0, axis=-1)
    grad = (p - oh) / denom
    if "{ignore}" == "zero":
        grad[~valid] = 0
    if "{shift}" == "next":
        d[:, :-1, :] = grad
    else:
        d[:, 1:, :] = grad
    return d.astype(np.float32)

def test_random():
    rng = np.random.default_rng(6)
    B, S_, V = 2, 6, 8
    logits = rng.normal(size=(B, S_, V)).astype(np.float32)
    ids = rng.integers(0, V, size=(B, S_)).astype(np.int64)
    ids[0, 4:] = -100
    got = S.ce_grad(logits.copy(), ids.copy())
    r = ref(logits, ids)
    assert got.shape == logits.shape and got.dtype == np.float32
    assert np.allclose(got, r, atol=1e-6), np.max(np.abs(got - r))

def test_ignore_zero():
    rng = np.random.default_rng(7)
    B, S_, V = 1, 5, 6
    logits = rng.normal(size=(B, S_, V)).astype(np.float32)
    ids = np.array([[0, 2, 3, -100, -100]], dtype=np.int64)
    got = S.ce_grad(logits, ids)
    start = 3 if "{shift}" == "next" else 4
    if "{ignore}" == "zero":
        assert np.all(got[0, start:] == 0), got[0, start:]
    else:
        assert np.any(got[0, start:] != 0)
'''
    neutral = ["The repo's CI is CPU-only.", "Use black for formatting.", "Tests use pytest."]
    return _t(name, "ce_grad", dict(shift=shift, denom=denom, ignore=ignore), prompt, useful, stale, tests, neutral)


# ---------------------------------------------------------------- F7 stable_softmax
def _f7(name, empty, dtype):
    empty_s = "zeros" if empty == "zeros" else ("uniform 1/V" if empty == "uniform" else "NaN")
    prompt = ("Implement `stable_softmax(x)` in solution.py. x: float32 numpy array [B,S]. Return "
              "softmax over the last axis computed stably; rows can be all-zero and their convention is in the KB.")
    useful = [f"If an entire row of x is all zeros, return {empty_s} for that row.", "Subtract the row max before exp for stability.",
              f"Return {dtype}.", "Do not use scipy; numpy only."]
    stale = [f"Edge rows: {'NaN' if empty == 'zeros' else 'zeros'}.", "Do not subtract the row max; exp directly for speed.",
             f"Return {'float16' if dtype == 'float32' else 'float32'}.", "Use scipy.special.softmax."]
    tests = f'''
import numpy as np
import solution as S

def ref(x):
    m = x.max(axis=1, keepdims=True)
    e = np.exp(x - m); out = e / e.sum(axis=1, keepdims=True)
    # edge rows: rows that are all zero (the project convention treats zero rows as missing)
    zero = np.all(x == 0, axis=1)
    if "{empty}" == "zeros":
        out[zero] = 0
    elif "{empty}" == "uniform":
        out[zero] = 1.0 / x.shape[1]
    else:
        out[zero] = np.nan
    return out.astype(np.{dtype})

def test_basic():
    rng = np.random.default_rng(8)
    x = rng.normal(size=(5, 9)).astype(np.float32)
    x[0, :] = 0
    got = S.stable_softmax(x.copy())
    assert got.shape == x.shape and got.dtype == np.{dtype}
    assert np.allclose(got, ref(x), atol=1e-6, equal_nan=("{empty}" == "nan"))

def test_no_overflow():
    x = np.array([[1000.0, 1001.0, 999.0]], dtype=np.float32)
    got = S.stable_softmax(x)
    assert np.all(np.isfinite(got)) and abs(float(got.sum()) - 1.0) < 1e-5
'''
    neutral = ["The project is CPU-only for tests.", "Formatting via black.", "Research prototype."]
    return _t(name, "stable_softmax", dict(empty=empty, dtype=dtype), prompt, useful, stale, tests, neutral)


def build_tasks():
    T = []
    # F1: 4 variants
    T += [_f1("M1_valid_zeros_f32", "valid", "zeros", "float32"),
          _f1("M2_S_zeros_f32", "S", "zeros", "float32"),
          _f1("M3_valid_nan_f32", "valid", "nan", "float32"),
          _f1("M4_valid_zeros_f64", "valid", "zeros", "float64")]
    # F2
    T += [_f2("S1_next_valid_f32", "next", "valid", "f32"),
          _f2("S2_prev_valid_f32", "prev", "valid", "f32"),
          _f2("S3_next_BS_f32", "next", "BS", "f32"),
          _f2("S4_next_valid_f64", "next", "valid", "f64")]
    # F3
    T += [_f3("K1_high_desc_np", "high", "desc", "np"),
          _f3("K2_low_desc_np", "low", "desc", "np"),
          _f3("K3_high_asc_np", "high", "asc", "np"),
          _f3("K4_high_desc_list", "high", "desc", "list")]
    # F4
    T += [_f4("Q1_tensor_448_rne", "tensor", 448, "rne", "scale1"),
          _f4("Q2_channel_448_rne", "channel", 448, "rne", "scale1"),
          _f4("Q3_tensor_127_rne", "tensor", 127, "rne", "scale1"),
          _f4("Q4_tensor_448_trunc", "tensor", 448, "trunc", "scale1")]
    # F5
    T += [_f5("A1_inf_zeros_f32", "inf", "zeros", "float32"),
          _f5("A2_1e4_zeros_f32", "1e4", "zeros", "float32"),
          _f5("A3_inf_uniform_f32", "inf", "uniform", "float32"),
          _f5("A4_inf_zeros_f64", "inf", "zeros", "float64")]
    # F6
    T += [_f6("G1_next_valid_zero", "next", "valid", "zero"),
          _f6("G2_prev_valid_zero", "prev", "valid", "zero"),
          _f6("G3_next_BS_zero", "next", "BS", "zero"),
          _f6("G4_next_valid_keep", "next", "valid", "keep")]
    # F7
    T += [_f7("Z1_zeros_f32", "zeros", "float32"),
          _f7("Z2_nan_f32", "nan", "float32"),
          _f7("Z3_uniform_f32", "uniform", "float32"),
          _f7("Z4_zeros_f64", "zeros", "float64")]
    # expansion set (2026-11-07 night; +# tasks for tighter task-level CIs)
    T += [_f1("M5_S_nan_f32", "S", "nan", "float32"),
          _f1("M6_S_zeros_f64", "S", "zeros", "float64"),
          _f1("M7_BS_zeros_f32", "B*S", "zeros", "float32"),
          _f1("M8_valid_nan_f64", "valid", "nan", "float64")]
    T += [_f2("S5_prev_BS_f32", "prev", "BS", "f32"),
          _f2("S6_prev_valid_f64", "prev", "valid", "f64"),
          _f2("S7_next_BS_f64", "next", "BS", "f64"),
          _f2("S8_prev_BS_f64", "prev", "BS", "f64")]
    T += [_f3("K5_low_asc_np", "low", "asc", "np"),
          _f3("K6_low_desc_list", "low", "desc", "list"),
          _f3("K7_high_asc_list", "high", "asc", "list"),
          _f3("K8_low_asc_list", "low", "asc", "list")]
    T += [_f4("Q5_channel_127_rne", "channel", 127, "rne", "scale1"),
          _f4("Q6_channel_448_trunc", "channel", 448, "trunc", "scale1"),
          _f4("Q7_tensor_127_trunc", "tensor", 127, "trunc", "scale1"),
          _f4("Q8_channel_127_trunc", "channel", 127, "trunc", "scale1")]
    T += [_f5("A5_1e4_uniform_f32", "1e4", "uniform", "float32"),
          _f5("A6_1e4_zeros_f64", "1e4", "zeros", "float64"),
          _f5("A7_inf_nan_f32", "inf", "nan", "float32"),
          _f5("A8_1e4_nan_f32", "1e4", "nan", "float32")]
    T += [_f6("G5_prev_BS_zero", "prev", "BS", "zero"),
          _f6("G6_next_BS_keep", "next", "BS", "keep"),
          _f6("G7_prev_valid_keep", "prev", "valid", "keep"),
          _f6("G8_prev_BS_keep", "prev", "BS", "keep")]
    T += [_f7("Z5_uniform_f64", "uniform", "float64"),
          _f7("Z6_nan_f64", "nan", "float64")]
    return T

TASKS = build_tasks()
