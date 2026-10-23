"""The day pipeline restarts a crashed node alone (B23): the day node and the live camera are
respawned by the launch, so the other one goes on (the camera keeps its stream open, the day node
dead-reckons) instead of systemd restarting the whole pipeline (25 s in flight, the copter landed).
"""
import importlib.util
import os

import pytest
from launch.actions import IncludeLaunchDescription
from launch_ros.actions import Node

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCH = os.path.join(HERE, 'simulation_web', 'launch', 'day_pipeline.launch.py')
LIVE = os.path.join(os.path.dirname(HERE), 'camera_pkg', 'camera_pkg', 'launch', 'live.launch.py')


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def entities(monkeypatch):
    pytest.importorskip('ament_index_python')
    from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
    try:
        get_package_share_directory('camera_pkg')
    except PackageNotFoundError:
        pytest.skip('camera_pkg not built')
    monkeypatch.setenv('NAVERA_CAMERA', 'live')
    return _load(LAUNCH, 'day_pipeline_launch').generate_launch_description().entities


def test_the_day_node_is_respawned_alone(entities):
    day = [e for e in entities if isinstance(e, Node) and 'day_subscriber' in str(e.node_executable)]
    assert len(day) == 1
    keys = ('__respawn', '__respawn_delay', '__on_exit')
    a = {k.split('__')[-1]: v for k, v in vars(day[0]).items() if k.endswith(keys)}
    assert a['respawn'] is True and 0 < float(a['respawn_delay']) <= 1.0
    assert a['on_exit'] is None                               # no Shutdown of the whole pipeline


def test_the_live_camera_is_respawned_alone(entities):
    inc = [e for e in entities if isinstance(e, IncludeLaunchDescription)]
    assert len(inc) == 1
    args = {k if isinstance(k, str) else k[0].text: v if isinstance(v, str) else v[0].text
            for k, v in inc[0].launch_arguments}
    assert args.get('respawn') == 'true'


def test_the_live_launch_respawns_only_when_asked():
    from launch import LaunchContext
    from launch.actions import DeclareLaunchArgument
    mod = _load(LIVE, 'live_launch')
    src = open(LIVE).read()
    assert "respawn=True" in src and "on_exit=Shutdown(reason='live camera exited')" in src
    decl = {e.name: e.default_value for e in mod.generate_launch_description().entities
            if isinstance(e, DeclareLaunchArgument)}
    ctx = LaunchContext()
    assert decl['respawn'][0].perform(ctx) == 'false'                    # default: as before
    assert float(decl['respawn_delay_s'][0].perform(ctx)) > 0
