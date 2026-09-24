"""Satellite integration regressions. Synthetic fixtures are NOT model accuracy validation."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("PRAHARI_DB_PATH", str(ROOT / "qa" / "prahari_test.db"))
os.environ["PRAHARI_AUTH_REQUIRED"] = "false"
import main
import satellite_l4s as l4s
import satellite_preprocess as prep
import satellite_jobs as jobs
import satellite_engine as engine
import satellite_worker as worker


@pytest.fixture
def meta():
    crs, transform = prep.target_grid(27.3314, 88.6138)
    return {"patch_id": "a" * 32, "crs": crs.to_string(), "transform": list(transform)[:6],
            "scene": {"id": "SYNTHETIC_TEST_ONLY", "datetime": "2026-01-01T00:00:00Z"},
            "terrain": {"source": "COPERNICUS_DEM_GLO30_DERIVED_SLOPE"}}


@pytest.fixture
def configured_model(monkeypatch, tmp_path):
    torch = pytest.importorskip("torch")
    torch.set_num_threads(2)
    model = l4s.LandslideUNet()
    state = model.state_dict()
    for value in state.values():
        value.zero_()
    state["outc.conv.bias"][1] = 2
    path = tmp_path / "UNTRAINED_STRUCTURAL_FIXTURE.pth"
    torch.save(state, path)
    monkeypatch.setattr(l4s, "WEIGHTS_PATH", path)
    monkeypatch.setattr(l4s, "EXPECTED_SHA256", "")
    monkeypatch.setattr(l4s, "DEVICE_PREF", "cpu")
    monkeypatch.setattr(l4s, "_MODEL_SIGNATURE", None)
    yield path
    l4s._MODEL = None
    l4s._MODEL_SIGNATURE = None


def test_missing_runtime_cannot_be_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(l4s, "TORCH_AVAILABLE", False)
    monkeypatch.setattr(l4s, "WEIGHTS_PATH", tmp_path)
    status = l4s.status()
    assert status["status"] == "NOT_CONFIGURED"
    assert not status["verified"]
    assert "weights_path" not in status


def test_directory_is_not_a_checkpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(l4s, "WEIGHTS_PATH", tmp_path)
    assert not l4s.status()["weights_present"]


def test_corrupt_checkpoint_fails_closed(monkeypatch, tmp_path):
    path = tmp_path / "broken.pth"
    path.write_bytes(b"not a model")
    monkeypatch.setattr(l4s, "WEIGHTS_PATH", path)
    monkeypatch.setattr(l4s, "_MODEL_SIGNATURE", None)
    assert l4s.status()["status"] == "LOAD_FAILED"


def test_verified_checkpoint_and_actual_forward_pass(configured_model):
    status = l4s.status()
    assert status["verified"] is True
    assert status["checkpoint_sha256"] == hashlib.sha256(configured_model.read_bytes()).hexdigest()
    assert "not trained-model quality" in status["verification_scope"]
    result = l4s.infer_patch(np.broadcast_to(l4s.MEAN, (128, 128, 14)))
    assert result["mask_rle"] == [[0, 16384, 1]]
    assert result["candidate_pixel_pct"] == 100
    assert result["mean_softmax_landslide_score_pct"] == pytest.approx(88.08, abs=.01)
    assert result["checkpoint_sha256"] == status["checkpoint_sha256"]


def test_checksum_mismatch(configured_model, monkeypatch):
    monkeypatch.setattr(l4s, "EXPECTED_SHA256", "0" * 64)
    assert l4s.status()["status"] == "LOAD_FAILED"


@pytest.mark.parametrize("value", [np.zeros((1, 14)), np.full((128, 128, 14), np.nan)])
def test_bad_patch_rejected(value):
    with pytest.raises(ValueError):
        l4s._prepare_patch(value)


def test_raw_elevation_is_not_benchmark_input():
    patch = np.broadcast_to(l4s.MEAN, (128, 128, 14)).copy()
    patch[:, :, 13] = 1650
    with pytest.raises(ValueError, match="Raw DEM"):
        l4s._prepare_patch(patch)


def test_npy_header_is_checked_before_allocating():
    buffer = io.BytesIO()
    np.lib.format.write_array_header_1_0(buffer, {"descr": "<f4", "fortran_order": False, "shape": (10**9, 10**9, 14)})
    with pytest.raises(ValueError, match="float32 values"):
        l4s.read_patch_bytes(buffer.getvalue())


def test_npy_valid_and_truncated_payload():
    buffer = io.BytesIO()
    value = np.zeros((128, 128, 14), dtype=np.float32)
    np.save(buffer, value, allow_pickle=False)
    assert l4s.read_patch_bytes(buffer.getvalue()).shape == value.shape
    with pytest.raises(ValueError, match="truncated"):
        l4s.read_patch_bytes(buffer.getvalue()[:-4])


@pytest.mark.parametrize("rle", [[], [[1, 16383, 0]], [[0, -1, 0]], [[0, 16385, 1]], [[0, 16384, 2]], [[0, 100, 1], [99, 16284, 0]]])
def test_malformed_mask_rejected(rle):
    with pytest.raises(ValueError):
        prep._mask_from_rle(rle)


def test_polygon_area_subtracts_holes_and_scores_component(meta):
    mask = np.zeros((128, 128), dtype=np.uint8)
    mask[4:8, 4:8] = 1
    mask[5:7, 5:7] = 0
    scores = np.where(mask, .8, .1)
    result = prep.candidate_geojson(l4s._rle(mask), meta, scores=scores)
    assert len(result["features"]) == 1
    candidate = result["features"][0]
    assert candidate["properties"]["area_m2"] == 1200
    assert candidate["properties"]["mean_softmax_score_pct"] == pytest.approx(80)
    assert len(candidate["geometry"]["coordinates"]) == 2
    assert result["properties"]["total_area_m2"] == 1200


def test_zero_candidates_and_small_components(meta):
    mask = np.zeros((128, 128), dtype=np.uint8)
    assert prep.candidate_geojson(l4s._rle(mask), meta)["features"] == []
    mask[0, 0] = 1
    assert prep.candidate_geojson(l4s._rle(mask), meta)["features"] == []
    assert prep.candidate_geojson(l4s._rle(mask), meta, min_pixels=1)["properties"]["total_area_m2"] == 100


def test_overlay_has_geographic_bounds(meta):
    result = prep.mask_overlay([[0, 16384, 0]], meta)
    assert result["image_url"].startswith("data:image/png;base64,iVBOR")
    south, west = result["bounds"][0]
    north, east = result["bounds"][1]
    assert south < 27.3314 < north and west < 88.6138 < east


def test_windowed_read_preserves_nodata(tmp_path):
    from rasterio.transform import from_origin
    transform = from_origin(0, 1280, 10, 10)
    path = tmp_path / "test.tif"
    data = np.ones((128, 128), dtype=np.float32)
    data[:10] = -999
    with prep.rasterio.open(path, "w", driver="GTiff", width=128, height=128, count=1,
                            dtype="float32", crs="EPSG:32645", transform=transform, nodata=-999) as dst:
        dst.write(data, 1)
    result, missing = prep._read_to_grid(str(path), "EPSG:32645", transform, resampling=prep.Resampling.nearest)
    assert np.isnan(result[:10]).all()
    assert missing == pytest.approx(10 / 128 * 100)


def test_incomplete_patch_never_imputed(monkeypatch):
    scene = {"id": "SYNTHETIC", "assets": {asset: {"href": "test.tif"} for _, asset in prep.S2_BANDS}}
    monkeypatch.setattr(prep, "find_l1c_scene", lambda *a, **k: scene)
    band = np.ones((128, 128), dtype=np.float32)
    band[0, 0] = np.nan
    monkeypatch.setattr(prep, "_read_to_grid", lambda *a, **k: (band, 1))
    monkeypatch.setattr(prep, "_terrain", lambda *a: (band, band, {}))
    with pytest.raises(RuntimeError, match="incomplete"):
        prep.prepare_patch(27.3314, 88.6138, persist=False)


def test_zero_cloud_is_preferred_and_null_is_allowed(monkeypatch):
    assets = {asset: {} for _, asset in prep.S2_BANDS}
    scenes = [{"id": str(v), "assets": assets, "properties": {"datetime": "2026-01-01T00:00:00Z", "eo:cloud_cover": v}} for v in [None, 10, 0]]
    monkeypatch.setattr(prep, "_stac_search", lambda *a, **k: scenes)
    assert prep.find_l1c_scene(27, 88)["id"] == "0"


def test_input_profile_binds_checkpoint_and_terrain(monkeypatch, tmp_path, meta):
    path = tmp_path / "profile.json"
    profile = {"channel_order": prep.CHANNEL_ORDER, "scales": [1] * 14, "offsets": [0] * 14,
               "checkpoint_sha256": "a" * 64, "terrain_source": meta["terrain"]["source"], "provenance": "SYNTHETIC TEST ONLY"}
    path.write_text(json.dumps(profile))
    monkeypatch.setattr(prep, "INPUT_PROFILE_PATH", str(path))
    monkeypatch.setattr(prep, "ALLOW_EXPERIMENTAL", True)
    patch = np.zeros((128, 128, 14), dtype=np.float32)
    assert prep.model_input(patch, meta, "a" * 64).shape == patch.shape
    with pytest.raises(RuntimeError, match="different model"):
        prep.model_input(patch, meta, "b" * 64)
    meta["terrain"]["source"] = "ALOS_LOCAL_SLOPE_DEM"
    with pytest.raises(RuntimeError, match="terrain"):
        prep.model_input(patch, meta, "a" * 64)
    monkeypatch.setattr(prep, "ALLOW_EXPERIMENTAL", False)
    assert not prep.status()["live_inference_ready"]


def test_worker_auth_and_size_limit(monkeypatch):
    monkeypatch.setenv("PRAHARI_L4S_SERVICE_TOKEN", "s" * 32)
    client = TestClient(worker.app)
    assert client.get("/v1/status").status_code == 401
    monkeypatch.setattr(worker, "status", lambda: {"status": "NOT_CONFIGURED"})
    headers = {"Authorization": "Bearer " + "s" * 32}
    assert client.get("/v1/status", headers=headers).json()["status"] == "NOT_CONFIGURED"
    assert client.post("/v1/infer", headers=headers, content=b"x" * (2 * 1024 * 1024 + 1)).status_code == 413


def test_remote_config_refuses_insecure_tokens(monkeypatch):
    monkeypatch.setenv("PRAHARI_L4S_SERVICE_URL", "http://remote.example")
    monkeypatch.setenv("PRAHARI_L4S_SERVICE_TOKEN", "s" * 32)
    assert engine.status()["status"] == "UNAVAILABLE"
    monkeypatch.setenv("PRAHARI_L4S_SERVICE_URL", "https://remote.example")
    monkeypatch.setenv("PRAHARI_L4S_SERVICE_TOKEN", "short")
    assert engine.status()["status"] == "UNAVAILABLE"


def test_missing_model_rejected_before_scene_download(monkeypatch):
    monkeypatch.setattr(main, "l4s_status", lambda: {"status": "NOT_CONFIGURED"})
    monkeypatch.setattr(main, "satprep_prepare_patch", lambda *a, **k: pytest.fail("Should not download scenes"))
    with pytest.raises(RuntimeError, match="not verified"):
        main._satellite_work(1, "infer")


def test_pipeline_reuses_patch_but_refuses_wrong_location(monkeypatch, meta):
    main._SATELLITE_PATCHES.clear()
    patch = np.zeros((128, 128, 14), dtype=np.float32)
    calls = []
    def prepare(*args, **kwargs):
        calls.append(1)
        return patch, meta
    monkeypatch.setattr(main, "satprep_prepare_patch", prepare)
    result = main._satellite_work(1, "prepare")
    monkeypatch.setattr(main, "l4s_status", lambda: {"status": "READY", "verified": True, "checkpoint_sha256": "a" * 64})
    monkeypatch.setattr(main, "satprep_status", lambda: {"live_inference_ready": True, "profile_checkpoint_sha256": "a" * 64})
    monkeypatch.setattr(main, "satprep_model_input", lambda p, m, s: p)
    monkeypatch.setattr(main, "l4s_infer_patch", lambda p: {"checkpoint_sha256": "a" * 64, "mask_rle": [[0, 16384, 0]], "score_grid": np.zeros((128, 128)).tolist()})
    output = main._satellite_work(1, "infer", patch_id=result["patch_id"])
    assert len(calls) == 1
    assert output["candidate_polygons"]["features"] == []
    assert "score_grid" not in output["inference"]
    with pytest.raises(ValueError, match="another location"):
        main._satellite_work(2, "infer", patch_id=result["patch_id"])
    main._SATELLITE_PATCHES.clear()


def test_job_access_requires_admin_and_consent(monkeypatch):
    client = TestClient(main.app)
    main.app.dependency_overrides[main.resolve_role] = lambda: "PUBLIC"
    try:
        assert client.post("/api/satellite/jobs/1", json={"operation": "prepare", "confirm_experimental": True}).status_code == 403
        assert client.get("/api/satellite/jobs/status/unknown").status_code == 403
        main.app.dependency_overrides[main.resolve_role] = lambda: "ADMIN"
        assert client.post("/api/satellite/jobs/1", json={"operation": "prepare"}).status_code == 400
        assert client.get("/api/satellite/jobs/status/unknown").status_code == 404
        monkeypatch.setattr(jobs, "submit", lambda *a: {"status": "QUEUED", "job_id": "test"})
        assert client.post("/api/satellite/jobs/1", json={"operation": "prepare", "confirm_experimental": True}).status_code == 202
    finally:
        main.app.dependency_overrides.clear()


def test_queue_serializes_work_and_reports_progress():
    jobs._JOBS.clear()
    started, release, complete = Event(), Event(), Event()
    def work(progress):
        progress("Reading bands")
        started.set()
        assert release.wait(5)
        complete.set()
        return {"status": "PATCH_READY"}
    try:
        first = jobs.submit(1, "prepare", work)
        assert started.wait(5)
        assert jobs.get(first["job_id"])["stage"] == "Reading bands"
        with pytest.raises(RuntimeError, match="busy"):
            jobs.submit(2, "prepare", work)
    finally:
        release.set()
    assert complete.wait(5)
    deadline = time.monotonic() + 5
    while jobs.get(first["job_id"])["status"] == "RUNNING" and time.monotonic() < deadline:
        time.sleep(.01)
    assert jobs.get(first["job_id"])["status"] == "SUCCEEDED"


def test_blank_paths_use_defaults():
    env = {**os.environ, "PYTHONPATH": str(ROOT / "backend"), "PRAHARI_L4S_WEIGHTS_PATH": "", "PRAHARI_SATELLITE_PATCH_DIR": ""}
    result = subprocess.run([sys.executable, "-c", "import satellite_l4s as l, satellite_preprocess as p; assert l.WEIGHTS_PATH == l.DEFAULT_WEIGHTS; assert p.PATCH_DIR == p.BASE / 'satellite_patches'"], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
