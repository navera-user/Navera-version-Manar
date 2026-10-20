# Copyright 2017 Open Source Robotics Foundation, Inc.
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
"""flake8 over this package, with the repository's lint configuration (/.flake8)."""
import os

from ament_flake8.main import main_with_errors
import pytest

_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_CONFIG = os.path.join(os.path.dirname(_PKG), '.flake8')


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8():
    # Lint this package whatever the working directory (pytest from the repository root
    # would otherwise lint every directory), with the repository's settings when present.
    argv = ['--config', _REPO_CONFIG] if os.path.isfile(_REPO_CONFIG) else []
    rc, errors = main_with_errors(argv=argv + [_PKG])
    assert rc == 0, \
        'Found %d code style errors / warnings:\n' % len(errors) + \
        '\n'.join(errors)
