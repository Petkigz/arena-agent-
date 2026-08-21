"""PackageInstaller tests — read paths (real pip), validation, and gated writes."""

import shutil

from app.tools.package_installer import PackageInstaller

HAS_PIP = shutil.which("pip") is not None


def test_list_packages_pip():
    if not HAS_PIP:
        import pytest
        pytest.skip("pip not available")
    res = PackageInstaller.list_packages("pip")
    assert res["success"] is True
    assert res["count"] >= 1


def test_list_packages_unsupported():
    assert PackageInstaller.list_packages("bogus")["success"] is False


def test_check_package_installed():
    if not HAS_PIP:
        import pytest
        pytest.skip("pip not available")
    res = PackageInstaller.check_package("pip")
    assert res["success"] is True
    assert res["installed"] is True


def test_check_package_missing():
    if not HAS_PIP:
        import pytest
        pytest.skip("pip not available")
    res = PackageInstaller.check_package("this_package_does_not_exist_xyz")
    assert res["success"] is False
    assert res["installed"] is False


def test_check_package_requires_name():
    assert PackageInstaller.check_package("")["success"] is False


def test_install_rejects_invalid_input():
    assert PackageInstaller.install_package("")["success"] is False
    assert PackageInstaller.install_package("--user")["success"] is False
    assert PackageInstaller.install_package("x; rm -rf /")["success"] is False
    assert PackageInstaller.install_package("x && echo hi")["success"] is False
    assert PackageInstaller.install_package("x\npip install y")["success"] is False


def test_uninstall_rejects_invalid_input():
    assert PackageInstaller.uninstall_package("")["success"] is False
    assert PackageInstaller.uninstall_package("pkg --force")["success"] is False


def test_validate_whitelist():
    ok, err = PackageInstaller._validate("numpy>=1.0")
    assert err is None and ok == "numpy>=1.0"
    # Scoped npm package is allowed.
    ok, err = PackageInstaller._validate("@scope/name")
    assert err is None
    # Spaces are rejected.
    _, err = PackageInstaller._validate("numpy >= 1.0")
    assert err is not None
