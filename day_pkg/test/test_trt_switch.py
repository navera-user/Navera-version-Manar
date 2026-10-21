"""navera_common.trt_engine: the NAVERA_TRT switch and the engine lookup (no GPU needed)."""
import os

from navera_common import trt_engine


def test_switch(monkeypatch):
    monkeypatch.delenv("NAVERA_TRT", raising=False)
    assert trt_engine.trt_enabled(True) and not trt_engine.trt_enabled(False)
    for v in ("1", "on", "true"):
        monkeypatch.setenv("NAVERA_TRT", v)
        assert trt_engine.trt_enabled(False)
    for v in ("0", "off", "false"):
        monkeypatch.setenv("NAVERA_TRT", v)
        assert not trt_engine.trt_enabled(True)


def test_no_engine_in_an_empty_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(trt_engine, "TRT_DIR", str(tmp_path))
    assert trt_engine.find_engine("sthn") is None


def test_engine_lookup_by_precision(monkeypatch, tmp_path):
    trt = trt_engine.import_tensorrt()
    if trt is None:
        return
    monkeypatch.setattr(trt_engine, "TRT_DIR", str(tmp_path))
    f16 = tmp_path / f"disk_abc_fp16_trt{trt.__version__}.engine"
    f32 = tmp_path / f"disk_abc_fp32_trt{trt.__version__}.engine"
    f16.write_bytes(b"x")
    f32.write_bytes(b"x")
    (tmp_path / "disk_abc_fp16_trt0.0.engine").write_bytes(b"x")       # another TensorRT: ignored
    assert trt_engine.find_engine("disk", fp16=True) == str(f16)
    assert trt_engine.find_engine("disk", fp16=False) == str(f32)
    assert trt_engine.find_engine("sthn") is None
    assert os.path.basename(trt_engine.engine_path("disk", str(f16), True)).endswith(
        f"_fp16_trt{trt.__version__}.engine")
