from importlib.metadata import version

import audio_engine


def test_package_version_matches_distribution() -> None:
    assert audio_engine.__version__ == version("personalized-audio-episode-engine")
