import gpubench


def test_package_exposes_version() -> None:
    assert gpubench.__version__ == "0.1.0"
