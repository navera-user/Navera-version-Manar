"""navera_common.camera_model.mount_identity: what a learned mount calibration belongs to (F33 item 4)."""
from navera_common.camera_model import mount_identity


def test_the_identity_changes_with_the_mount_angles_the_lens_and_the_crop(tmp_path):
    base = mount_identity((0.0, 0.0, 0.0), "", 84.0)
    assert base == mount_identity((0.0, 0.0, 0.0), "", 84.0) and len(base["mount_id"]) == 12
    ids = {base["mount_id"]}
    for other in (mount_identity((1.0, 0.0, 0.0), "", 84.0), mount_identity((0.0, -2.0, 0.0), "", 84.0),
                  mount_identity((0.0, 0.0, 90.0), "", 84.0), mount_identity((0.0, 0.0, 0.0), "", 70.0),
                  mount_identity((0.0, 0.0, 0.0), "", 84.0, (0, 0, 640, 480))):
        ids.add(other["mount_id"])
    assert len(ids) == 6


def test_a_recalibrated_lens_file_is_another_lens(tmp_path):
    f = tmp_path / "lens.yaml"
    f.write_text("K: [1, 2, 3]\n")
    a = mount_identity((0.0, 0.0, 0.0), str(f))
    assert a["lens"].startswith("lens.yaml ")
    f.write_text("K: [1, 2, 4]\n")                      # same name, new calibration
    assert mount_identity((0.0, 0.0, 0.0), str(f))["mount_id"] != a["mount_id"]
    assert mount_identity((0.0, 0.0, 0.0), str(tmp_path / "missing.yaml"))["lens"] == "missing.yaml"
