from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from beatbloom.cli import build_parser, main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "0.2.0" in capsys.readouterr().out


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--start", "-1"),
        ("--start", "nan"),
        ("--duration", "0"),
        ("--duration", "inf"),
        ("--size", "1279x720"),
        ("--size", "bad"),
        ("--crf", "52"),
        ("--crf", "-1"),
        ("--fps", "0"),
        ("--fps", "nan"),
        ("--fps", "30/0"),
        ("--fps", "-24"),
    ],
)
def test_invalid_cli_values(flag: str, value: str) -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(
            ["render", "video.mp4", "--audio", "mix.wav", "-o", "out.mp4", flag, value]
        )
    assert exc.value.code == 2


def test_validate_does_not_require_media_files(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = tmp_path / "project.json"
    config.write_text(json.dumps({"schema_version": 2, "signals": {"x": {"source": "absent.wav"}}}))
    caplog.set_level(logging.INFO)
    assert main(["validate", str(config)]) == 0
    assert "Valid configuration" in caplog.text


def test_invalid_config_returns_nonzero(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    config = tmp_path / "project.json"
    config.write_text('{"schema_version":2,"signals":{"x":{"gamma":0}}}')
    assert main(["validate", str(config)]) == 1
    assert "Invalid configuration" in caplog.text


def test_missing_ffmpeg_is_actionable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("beatbloom.media.shutil.which", lambda _: None)
    assert main(["render", "video.mp4", "--audio", "mix.wav", "-o", str(tmp_path / "out.mp4")]) == 1
    assert "Install FFmpeg" in caplog.text
