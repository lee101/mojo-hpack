import importlib.util
import os
import sys

import pytest


@pytest.fixture(scope="session")
def upstream_hpack():
    env_root = os.path.dirname(sys.executable)
    package = os.path.join(
        os.path.dirname(env_root), "lib", f"python{sys.version_info.major}.{sys.version_info.minor}",
        "site-packages", "hpack",
    )
    init = os.path.join(package, "__init__.py")
    if not os.path.exists(init):
        pytest.skip("upstream hpack is not installed")
    spec = importlib.util.spec_from_file_location(
        "_upstream_hpack", init, submodule_search_locations=[package]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
