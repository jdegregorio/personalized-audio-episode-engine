import pytest


@pytest.mark.smoke
def test_installed_package_imports() -> None:
    import audio_engine

    assert audio_engine.__version__
