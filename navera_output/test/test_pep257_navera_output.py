# Copyright 2015 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""pep257 over this package, with the repository's docstring convention (/.flake8 [pydocstyle])."""
import configparser
import os

from ament_pep257.main import main
import pytest

_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_CONFIG = os.path.join(os.path.dirname(_PKG), '.flake8')


def _convention_args():
    """Return the ament_pep257 options of the repository config ([] = ament's defaults)."""
    cfg = configparser.ConfigParser()
    if not cfg.read(_REPO_CONFIG) or not cfg.has_section('pydocstyle'):
        return []
    sect = cfg['pydocstyle']
    args = ['--convention', sect.get('convention', 'ament')]
    ignore = [c.strip() for c in sect.get('add-ignore', '').split(',') if c.strip()]
    return args + (['--add-ignore'] + ignore if ignore else [])


@pytest.mark.linter
@pytest.mark.pep257
def test_pep257():
    rc = main(argv=_convention_args() + ['--', _PKG])
    assert rc == 0, 'Found code style errors / warnings'
