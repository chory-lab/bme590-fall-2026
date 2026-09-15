"""`bme590 start` must repair the editor config, not just the installer.

The searchability work shipped as part of the installer, which is fine for
anyone installing after it landed and useless for everyone already mid-semester:
`bme590.code-workspace` is gitignored and generated per machine, so no `git pull`
can deliver it, and `.vscode/settings.json` is merged into rather than replaced,
so an older install keeps the file and misses the keys added since.

These tests pin the self-heal that closes that: what counts as out of date, that
repairing it is idempotent, and that the content has exactly one definition in
the tree -- a second copy of the Pylance depths would drift, and the drift would
reach students as "labware autocomplete works on my machine".
"""

import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import install  # noqa: E402

from bme590 import cli  # noqa: E402

FOUR_OLD_KEYS = {
    "python.defaultInterpreterPath": "${workspaceFolder}\\.venv\\Scripts\\python.exe",
    "python.terminal.activateEnvironment": True,
    "jupyter.kernels.filter": [],
    "jupyter.askForKernelSelection": False,
}


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    """A class folder the problem check can be pointed at."""
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    return tmp_path


def current_workspace_settings(root):
    """What the installer would put in the workspace file's settings block."""
    return install.class_settings(root, str(install.venv_python(root)))


def current_vscode_settings(root):
    """What the installer would put in .vscode/settings.json."""
    return install.class_settings(root, install.interpreter_path())


def write_workspace_file(root, folder_path, settings=None):
    (root / "bme590.code-workspace").write_text(
        json.dumps({
            "folders": [
                {"path": "."},
                {"name": "pylabrobot (library source - read only)", "path": folder_path},
            ],
            "settings": current_workspace_settings(root) if settings is None else settings,
        }),
        encoding="utf-8",
    )


def write_settings_file(root, settings):
    (root / ".vscode").mkdir(exist_ok=True)
    (root / ".vscode/settings.json").write_text(json.dumps(settings), encoding="utf-8")


def test_a_checkout_that_never_ran_the_installer_reports_both_files(fake_root):
    problems = cli.editor_config_problems()
    assert any("code-workspace" in p for p in problems)
    assert any("settings.json" in p for p in problems)


def test_the_mid_semester_case_is_the_missing_pylance_keys(fake_root):
    """An older install: the files exist, the newer keys do not.

    This is the shape the class is actually in, and the one a `git pull` cannot
    fix on its own.
    """
    target = fake_root / "pylabrobot"
    target.mkdir()
    write_workspace_file(fake_root, "pylabrobot")
    write_settings_file(fake_root, dict(FOUR_OLD_KEYS))

    problems = cli.editor_config_problems()
    assert len(problems) == 1, problems
    assert problems[0].startswith(".vscode/settings.json is older than this checkout")
    assert "python.analysis.packageIndexDepths" in problems[0]
    assert "python.analysis.autoImportCompletions" in problems[0]


def test_a_workspace_root_that_no_longer_exists_is_a_problem(fake_root):
    """Reinstalling pylabrobot at a new version moves that path.

    A workspace whose second root is gone is worse than no workspace: VS Code
    greys the folder out and searches nothing, with no error a student can act
    on.
    """
    write_workspace_file(fake_root, "lib/python3.99/site-packages/pylabrobot")
    write_settings_file(fake_root, current_vscode_settings(fake_root))

    problems = cli.editor_config_problems()
    assert any("points at a missing" in p for p in problems), problems


def test_unreadable_json_is_reported_not_raised(fake_root):
    """Half-written config is a support case, not a traceback."""
    (fake_root / "bme590.code-workspace").write_text("{ not json", encoding="utf-8")
    write_settings_file(fake_root, dict(FOUR_OLD_KEYS))
    (fake_root / ".vscode/settings.json").write_text("{ not json", encoding="utf-8")

    problems = cli.editor_config_problems()
    assert any("code-workspace is not readable" in p for p in problems), problems
    assert any("settings.json is not readable" in p for p in problems), problems


def test_a_current_config_reports_nothing(fake_root):
    target = fake_root / "pylabrobot"
    target.mkdir()
    write_workspace_file(fake_root, "pylabrobot")
    write_settings_file(fake_root, current_vscode_settings(fake_root))

    assert cli.editor_config_problems() == []


def test_a_downgraded_index_depth_is_noticed(fake_root):
    """The state the first version of this check called current.

    Pylance replaces `packageIndexDepths` wholesale, so an older install can
    carry the key with pylabrobot at depth 1 -- named, and useless. Asking only
    whether the name appears passed this; comparing values does not.
    """
    (fake_root / "pylabrobot").mkdir()
    write_workspace_file(fake_root, "pylabrobot")
    settings = current_vscode_settings(fake_root)
    settings["python.analysis.packageIndexDepths"] = [
        {"name": "pylabrobot", "depth": 1} if entry["name"] == "pylabrobot" else entry
        for entry in settings["python.analysis.packageIndexDepths"]
    ]
    write_settings_file(fake_root, settings)

    problems = cli.editor_config_problems()
    assert any("packageIndexDepths" in p for p in problems), problems


def test_a_removed_key_is_noticed(fake_root):
    (fake_root / "pylabrobot").mkdir()
    write_workspace_file(fake_root, "pylabrobot")
    settings = current_vscode_settings(fake_root)
    del settings["python.analysis.autoImportCompletions"]
    write_settings_file(fake_root, settings)

    problems = cli.editor_config_problems()
    assert any("autoImportCompletions" in p for p in problems), problems


def test_a_stale_workspace_settings_block_is_noticed(fake_root):
    """The workspace copy matters most: it is the file `bme590 start` opens."""
    (fake_root / "pylabrobot").mkdir()
    write_workspace_file(fake_root, "pylabrobot", settings={"editor.fontSize": 15})
    write_settings_file(fake_root, current_vscode_settings(fake_root))

    problems = cli.editor_config_problems()
    assert any(p.startswith("bme590.code-workspace is older") for p in problems), problems


def test_a_setting_added_later_needs_no_second_list(fake_root, monkeypatch):
    """The point of comparing against the writer.

    A key added to `class_settings` must go stale on its own, with nothing in
    the CLI to update in step -- that is what makes this propagate on the day it
    lands rather than the next time someone remembers.
    """
    (fake_root / "pylabrobot").mkdir()
    write_workspace_file(fake_root, "pylabrobot")
    write_settings_file(fake_root, current_vscode_settings(fake_root))
    assert cli.editor_config_problems() == []

    real = install.class_settings
    monkeypatch.setattr(
        install, "class_settings",
        lambda root, interpreter: {**real(root, interpreter), "python.analysis.newKey": True},
    )

    problems = cli.editor_config_problems()
    assert any("python.analysis.newKey" in p for p in problems), problems


def test_write_settings_keeps_what_the_student_set(tmp_path):
    """The repair runs on every `bme590 start`, so it must not be destructive."""
    write_settings_file(tmp_path, {**FOUR_OLD_KEYS, "editor.fontSize": 15})

    install.write_settings(tmp_path)

    settings = json.loads((tmp_path / ".vscode/settings.json").read_text(encoding="utf-8"))
    assert settings["editor.fontSize"] == 15
    indexed = {entry["name"] for entry in settings["python.analysis.packageIndexDepths"]}
    assert "pylabrobot" in indexed
    # Pylance replaces the array wholesale, so its own defaults have to survive.
    assert {"scipy", "matplotlib", "sklearn"} <= indexed


def test_write_settings_is_idempotent(tmp_path):
    install.write_settings(tmp_path)
    first = (tmp_path / ".vscode/settings.json").read_text(encoding="utf-8")
    install.write_settings(tmp_path)
    assert (tmp_path / ".vscode/settings.json").read_text(encoding="utf-8") == first


def test_the_pylance_depths_are_defined_once():
    """One definition, or the two copies drift.

    `bme590 start` writes this file through scripts/install.py rather than
    carrying its own copy of the content; this is the test that keeps it that
    way.
    """
    defining = [
        path for path in (*(REPO / "scripts").glob("*.py"), *(REPO / "bme590").glob("*.py"))
        if "PYLANCE_PACKAGE_DEPTHS = [" in path.read_text(encoding="utf-8")
    ]
    assert [p.name for p in defining] == ["install.py"], defining


def test_start_and_check_both_repair():
    """The propagation route. `start` is what students run every session."""
    source = (REPO / "bme590/cli.py").read_text(encoding="utf-8")
    for command in ("def cmd_start", "def cmd_check"):
        body = source.split(command, 1)[1].split("\ndef ", 1)[0]
        assert "repair_editor_config()" in body, f"{command} does not repair the editor config"


@pytest.mark.skipif(
    not (REPO / ".venv").exists() or not (REPO / ".vscode/settings.json").exists(),
    reason="this checkout has not been installed, so there is no editor config to check",
)
def test_this_installed_checkout_is_current():
    """An installed checkout should need no repair -- CI installs before it runs."""
    assert cli.editor_config_problems() == []
