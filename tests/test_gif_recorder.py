"""The Python half of the GIF scripting interface.

These tests assert the command protocol -- what is sent, when, and with what
payload -- against a visualizer whose transport is captured. The browser half
of the same protocol is covered in test_recorder_js.py; between them, both
sides of ``class_start_gif`` / ``class_stop_gif`` are pinned to the same
command names and payload keys.
"""

import asyncio

import pytest

from bme590 import visualizer_ext
from bme590.visualizer_ext import (
    GifRecorder,
    gif_recorder,
    gif_recording,
    set_step_delay,
    step,
)


@pytest.fixture(autouse=True)
def fast_steps():
    """Run pacing at zero so tests measure protocol, not wall-clock pauses.

    Restored afterwards because the delay is module-global: leaking a zero
    would silently disable pacing for any test that cares about it.
    """
    original = visualizer_ext._step_delay
    set_step_delay(0)
    yield
    set_step_delay(original)


# --- construction ----------------------------------------------------------


def test_rejects_a_non_visualizer():
    """The most likely student mistake is passing `lh` instead of `lh.vis`;
    that has to fail with a type error, not an AttributeError deep in start()."""
    with pytest.raises(TypeError, match="expected a Visualizer"):
        GifRecorder("not a visualizer")  # type: ignore[arg-type]


def test_gif_recorder_defaults_match_the_documented_signature(connected):
    rec = gif_recorder(connected.vis)
    assert rec.name == "plr-protocol.gif"
    assert rec.frame_interval == 8
    assert rec.max_duration == 60.0


# --- the command protocol --------------------------------------------------


async def test_start_sends_the_frame_interval(connected):
    await gif_recorder(connected.vis, frame_interval=12).start()
    assert connected.events == ["class_start_gif"]
    assert connected.data_for("class_start_gif") == {"frame_interval": 12}


async def test_stop_sends_the_download_filename(connected):
    rec = gif_recorder(connected.vis, name="exercise_1.gif", max_duration=None)
    await rec.start()
    await rec.stop()
    assert connected.events == ["class_start_gif", "class_stop_gif"]
    assert connected.data_for("class_stop_gif") == {"filename": "exercise_1.gif"}


@pytest.mark.parametrize(
    "name",
    [
        "out/subdir.gif",       # relative path
        "subdir/../out.gif",    # relative with traversal
        "/abs/path/out.gif",    # POSIX absolute path
        r"C:\out\subdir.gif",   # Windows absolute path
    ],
)
async def test_stop_sends_a_path_bearing_filename_verbatim(connected, name):
    """Absolute and relative paths reach the browser untouched.

    The recorder never touches the filename: whatever the student passed is the
    ``filename`` payload. Where to put the file (or which part of a path the
    browser keeps as the download name) is the browser's business, and is
    pinned on the JS side in test_recorder_js.py.
    """
    rec = gif_recorder(connected.vis, name=name, max_duration=None)
    await rec.start()
    await rec.stop()
    assert connected.data_for("class_stop_gif") == {"filename": name}


async def test_stop_is_idempotent(connected):
    """Notebooks re-run cells. A second stop() must not emit a second
    class_stop_gif, which would re-download a stale (or empty) recording."""
    rec = gif_recorder(connected.vis, max_duration=None)
    await rec.start()
    await rec.stop()
    await rec.stop()
    assert connected.events.count("class_stop_gif") == 1


async def test_a_recording_spans_calls(connected):
    """The reason gif_recorder exists alongside gif_recording: start and stop
    are plain calls, so a recording can cross notebook cell boundaries."""
    rec = gif_recorder(connected.vis, max_duration=None)
    await rec.start()
    await asyncio.sleep(0)  # stand-in for "another cell ran"
    await rec.stop()
    assert connected.events == ["class_start_gif", "class_stop_gif"]


# --- the watchdog ----------------------------------------------------------


async def test_watchdog_finalizes_a_forgotten_recording(connected, capsys):
    """A forgotten stop() should cost a short GIF, not the whole recording."""
    rec = gif_recorder(connected.vis, name="forgotten.gif", max_duration=0.05)
    await rec.start()
    await asyncio.sleep(0.4)

    assert connected.events == ["class_start_gif", "class_stop_gif"]
    assert connected.data_for("class_stop_gif") == {"filename": "forgotten.gif"}
    assert "stopped automatically" in capsys.readouterr().out


async def test_watchdog_does_not_cancel_its_own_stop(connected):
    """stop() cancels the watchdog, and the watchdog calls stop(). If it did
    not detach itself first it would cancel the very task sending the command,
    and the recording would be lost -- the bug the detach guards against."""
    rec = gif_recorder(connected.vis, max_duration=0.05)
    await rec.start()
    await asyncio.sleep(0.4)
    assert "class_stop_gif" in connected.events
    assert rec._watchdog is None


async def test_explicit_stop_cancels_the_watchdog(connected):
    """After a normal stop the timer must be gone, or a later auto-stop would
    fire a second download long after the protocol finished."""
    rec = gif_recorder(connected.vis, max_duration=0.05)
    await rec.start()
    await rec.stop()
    await asyncio.sleep(0.3)
    assert connected.events.count("class_stop_gif") == 1


async def test_max_duration_none_disables_the_watchdog(connected):
    rec = gif_recorder(connected.vis, max_duration=None)
    await rec.start()
    assert rec._watchdog is None
    await asyncio.sleep(0.2)
    assert connected.events == ["class_start_gif"]


# --- waiting for the browser ----------------------------------------------


async def test_start_waits_for_the_browser_tab(disconnected):
    """Recording into a page nobody opened produces an empty GIF, so start()
    blocks until the tab connects."""
    rec = GifRecorder(disconnected.vis, browser_timeout=5.0)
    task = asyncio.create_task(rec.start())
    await asyncio.sleep(0.3)

    assert disconnected.events == [], "started before the browser connected"

    disconnected.connected = True
    await asyncio.wait_for(task, timeout=2)
    assert disconnected.events == ["class_start_gif"]


async def test_start_times_out_with_an_actionable_message(disconnected):
    rec = GifRecorder(disconnected.vis, browser_timeout=0.2)
    with pytest.raises(TimeoutError, match="Open the printed URL"):
        await rec.start()


async def test_wait_for_browser_false_skips_the_check(disconnected):
    rec = GifRecorder(disconnected.vis, wait_for_browser=False, max_duration=None)
    await rec.start()
    assert disconnected.events == ["class_start_gif"]


# --- the context-manager form ---------------------------------------------


async def test_gif_recording_brackets_the_block(connected):
    async with gif_recording(connected.vis, name="ctx.gif", max_duration=None):
        assert connected.events == ["class_start_gif"]
    assert connected.events == ["class_start_gif", "class_stop_gif"]
    assert connected.data_for("class_stop_gif") == {"filename": "ctx.gif"}


async def test_gif_recording_stops_when_the_protocol_raises(connected):
    """A failed protocol should still yield the partial GIF -- that recording
    is usually the most useful thing a student has for debugging."""
    with pytest.raises(RuntimeError):
        async with gif_recording(connected.vis, max_duration=None):
            raise RuntimeError("aspirate failed")
    assert "class_stop_gif" in connected.events


# --- pacing ---------------------------------------------------------------


async def test_step_uses_the_configured_delay(monkeypatch):
    """Asserted on what was asked for, not on the wall clock.

    asyncio fires a timer once it is within one clock-resolution tick of its
    deadline -- about 15ms on Windows -- so timing a 0.1s sleep and asserting
    the elapsed time reached 0.1 fails intermittently. Capturing the sleep
    request tests the same thing (delay times multiplier) and cannot flake.
    """
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(visualizer_ext.asyncio, "sleep", fake_sleep)

    set_step_delay(0.05)
    await step()
    await step(2)
    assert slept == [pytest.approx(0.05), pytest.approx(0.1)]


async def test_set_step_delay_clamps_negatives():
    """A negative delay would make asyncio.sleep raise mid-protocol."""
    set_step_delay(-5)
    assert visualizer_ext._step_delay == 0.0
    await step()
