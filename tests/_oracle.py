"""Differential-testing helpers: the upstream package plus explicit tolerances.

Every parity assertion in this suite names the reference it was checked
against. Two references exist and neither is optional:

* the installed upstream ``hpack`` 4.2.0 package, loaded from site-packages, and
* upstream's own published vectors (RFC 7541 Appendix C, which upstream
  ``hpack`` itself asserts in its test suite).

No assertion in this suite relies on a value the port invented.
"""

import importlib.util
import os
import sys

import pytest

# HPACK is a byte format: for every public function the upstream output and the
# port output must agree on every byte, so the tolerance is zero bytes.
BYTES_ATOL = 0
# Integer quantities (lengths, indices, offsets) agree exactly.
COUNTS_ATOL = 0


def _upstream_package_path():
    env_root = os.path.dirname(sys.executable)
    return os.path.join(
        os.path.dirname(env_root),
        "lib",
        f"python{sys.version_info.major}.{sys.version_info.minor}",
        "site-packages",
        "hpack",
    )


def load_upstream(module_name="_upstream_hpack"):
    """Import the installed upstream package under a private module name.

    The name must differ from ``hpack`` because ``PYTHONPATH=python`` makes the
    checkout's package shadow the installed one.
    """
    package = _upstream_package_path()
    init = os.path.join(package, "__init__.py")
    if not os.path.exists(init):
        pytest.skip("upstream hpack is not installed")
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        module_name, init, submodule_search_locations=[package]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def assert_same_bytes(actual, expected, context=""):
    """Byte-exact comparison with an explicit tolerance of ``BYTES_ATOL``."""
    assert len(actual) == len(expected), (context, actual, expected)
    for index, (left, right) in enumerate(zip(actual, expected)):
        assert abs(left - right) <= BYTES_ATOL, (
            f"{context}: byte {index} {left} != {right}"
        )


def assert_same_count(actual, expected, context=""):
    assert abs(actual - expected) <= COUNTS_ATOL, (context, actual, expected)


def outcome(function, *args, **kwargs):
    """Run ``function`` and capture either its value or its exception type.

    Used to compare behaviour on degenerate input, where "raises the same class"
    is the contract and the message text is not.
    """
    try:
        return ("returned", function(*args, **kwargs))
    except Exception as error:  # noqa: BLE001 - the exception class is the datum
        return ("raised", type(error))


UPSTREAM = None


def upstream():
    """The loaded upstream package, shared across tests."""
    global UPSTREAM
    if UPSTREAM is None:
        UPSTREAM = load_upstream()
    return UPSTREAM


def upstream_submodule(name):
    """Load e.g. ``_upstream_hpack.hpack`` next to the package."""
    load_upstream()
    return importlib.import_module(f"_upstream_hpack.{name}")
