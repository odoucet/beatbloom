from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from beatbloom.cli import build_parser, main
from beatbloom.errors import BeatBloomError
from beatbloom.models import RenderOptions, RenderResult
from beatbloom.preview import play_preview


def test_preview_defaults_and_rational_fps() -> None:
    args = build_parser().parse_args(["preview", "video.mp4", "--audio", "mix.wav"])
    assert args.duration == 8.0
    assert args.size == (960, 540)
    assert args.fps == Fraction(15)
    assert (args.crf, args.preset) == (26, "ultrafast")
    assert args.output is None
    render = build_parser().parse_args(
        ["render", "video.mp4", "--audio", "mix.wav", "-o", "out.mp4", "--fps", "30000/1001"]
    )
    assert render.fps == Fraction(30000, 1001)


def test_no_play_requires_output() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["preview", "video.mp4", "--audio", "mix.wav", "--no-play"])
    assert exc.value.code == 2


def test_missing_player_fails_before_render(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("beatbloom.preview.shutil.which", lambda _name: None)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("player discovery must precede processing")

    monkeypatch.setattr("beatbloom.render.engine.render_video", forbidden)
    assert main(["preview", "video.mp4", "--audio", "mix.wav"]) == 1
    assert "Missing ffplay" in caplog.text


@pytest.mark.parametrize("interrupt", [False, True])
def test_temporary_preview_exists_during_playback_and_is_cleaned(
    monkeypatch: pytest.MonkeyPatch, interrupt: bool
) -> None:
    played: list[Path] = []
    monkeypatch.setattr("beatbloom.preview.require_player", lambda: None)

    def render(options: RenderOptions, **_kwargs: object) -> RenderResult:
        options.output.write_bytes(b"encoded preview")
        return RenderResult(options.output, 30, Fraction(15))

    def play(path: Path) -> None:
        assert path.read_bytes() == b"encoded preview"
        played.append(path)
        if interrupt:
            raise KeyboardInterrupt

    monkeypatch.setattr("beatbloom.render.engine.render_video", render)
    monkeypatch.setattr("beatbloom.preview.play_preview", play)
    assert main(["preview", "video.mp4", "--audio", "mix.wav"]) == (130 if interrupt else 0)
    assert len(played) == 1 and not played[0].exists()
    assert not played[0].parent.exists()


def test_saved_preview_survives_player_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "saved.mp4"
    monkeypatch.setattr("beatbloom.preview.require_player", lambda: None)

    def render(options: RenderOptions, **_kwargs: object) -> RenderResult:
        options.output.write_bytes(b"successful render")
        return RenderResult(options.output, 30, Fraction(15))

    def play(_path: Path) -> None:
        raise BeatBloomError("player failed")

    monkeypatch.setattr("beatbloom.render.engine.render_video", render)
    monkeypatch.setattr("beatbloom.preview.play_preview", play)
    assert main(["preview", "video.mp4", "--audio", "mix.wav", "-o", str(output)]) == 1
    assert output.read_bytes() == b"successful render"


def test_player_is_reaped_on_interrupt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "preview with spaces.mp4"
    monkeypatch.setattr("beatbloom.preview.require_player", lambda: None)
    calls: list[str] = []

    class Player:
        stdin = None
        stdout = None
        stopped = False

        def wait(self, **_kwargs: object) -> int:
            if not self.stopped:
                raise KeyboardInterrupt
            calls.append("reaped")
            return -15

        def poll(self) -> int | None:
            return -15 if self.stopped else None

        def terminate(self) -> None:
            self.stopped = True
            calls.append("terminated")

    def start(command: list[str], **_kwargs: object) -> Player:
        assert command[-1] == str(path)
        assert command[0] == "ffplay" and "-autoexit" in command
        return Player()

    monkeypatch.setattr("beatbloom.preview.subprocess.Popen", start)
    with pytest.raises(KeyboardInterrupt):
        play_preview(path)
    assert calls == ["terminated", "reaped"]
