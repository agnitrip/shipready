"""Tests for the dogfood .traj converter. No network access."""

from __future__ import annotations

import importlib.util
from pathlib import Path

CONVERTER = Path(__file__).resolve().parents[1] / "dogfood" / "traj_to_shipready.py"
_spec = importlib.util.spec_from_file_location("traj_to_shipready", CONVERTER)
conv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conv)

# Shape of step 12 in the beeware__briefcase-2075 calibration run: the old text
# alone runs past the 300-character command cap, so the old converter cut the
# command inside old_str and new_str never reached the grader.
OLD = (
    "# Only custom permissions\n"
    "        (\n"
    "            {\n"
    '                "custom_permission": "Custom message",\n'
    "            },\n"
    "            {\n"
    '                "allow=bluetooth": True,\n'
    "            },\n"
    "            {\n"
    '                "finish_args": {\n'
    '                    "share=ipc": True,\n'
    '                    "socket=x11": True,\n'
    '                    "filesystem=xdg-documents": True,\n'
    '                    "socket=session-bus": True,\n'
    '                    "allow=bluetooth": True,\n'
    "                },\n"
)
NEW = OLD.replace('                    "socket=session-bus": True,\n', "")
EDIT = (
    "str_replace_editor str_replace /testbed/tests/platforms/linux/flatpak/test_create.py"
    f"   --old_str '{OLD}' --new_str '{NEW}'"
)


def test_edit_command_keeps_new_text():
    assert len(EDIT) > conv.ACTION_CAP
    [call] = conv.build_tool_calls([{"action": EDIT, "observation": "edited"}])
    args = call["args"]
    assert call["tool"] == "str_replace_editor"
    assert args["command"].endswith("test_create.py")
    assert args["old_str"] == OLD
    assert args["new_str"] == NEW
    assert '"socket=session-bus": True' in args["old_str"]
    assert '"socket=session-bus": True' not in args["new_str"]


def test_long_edit_field_is_capped_with_marker():
    long_new = "x" * (conv.EDIT_FIELD_CAP + 50)
    action = f"str_replace_editor create /testbed/a.py --file_text '{long_new}'"
    [call] = conv.build_tool_calls([{"action": action, "observation": ""}])
    assert call["args"]["file_text"].endswith("...[truncated 50 chars]")


def test_plain_command_is_capped_with_marker():
    action = "grep -rn " + "a" * 400
    [call] = conv.build_tool_calls([{"action": action, "observation": ""}])
    assert set(call["args"]) == {"command"}
    assert "...[truncated" in call["args"]["command"]


def test_unparseable_edit_falls_back_to_plain_cap():
    action = "str_replace_editor str_replace /a.py --old_str 'unterminated"
    [call] = conv.build_tool_calls([{"action": action, "observation": ""}])
    assert set(call["args"]) == {"command"}
