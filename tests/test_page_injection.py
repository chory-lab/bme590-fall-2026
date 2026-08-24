"""What the file server actually puts in the page.

RecordingVisualizer overrides `_run_file_server` to inject the recorder script
and, conditionally, the declutter style. These tests fetch the real served page
over HTTP rather than inspecting the module's string constants, so they cover
the handler's branching and the `</body>` splice together.
"""

import os
import urllib.request

import pytest

from pylabrobot.visualizer import visualizer as plr_visualizer

from bme590.visualizer_ext import _DECLUTTER_CSS, _RECORDER_JS

FLAG = "window.__CLASS_DECLUTTER_KWARG = true"


def get(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


# --- the upstream assumptions this override rests on ----------------------


def test_upstream_index_html_still_has_the_body_anchor():
    """The injection splices on `</body>`. If a PyLabRobot upgrade reflows
    index.html, every other test here would still pass while students silently
    got a page with no recorder in it -- so assert the anchor directly."""
    index = os.path.join(os.path.dirname(plr_visualizer.__file__), "index.html")
    with open(index, "r", encoding="utf-8") as f:
        content = f.read()
    assert content.count("</body>") == 1


def test_upstream_still_exposes_the_elements_declutter_hides():
    """The declutter CSS targets the stock page by id. An upstream rename
    would leave the rules matching nothing and the page fully cluttered."""
    index = os.path.join(os.path.dirname(plr_visualizer.__file__), "index.html")
    with open(index, "r", encoding="utf-8") as f:
        content = f.read()
    for element in ('id="sidepanel"', 'id="home-button"', "<aside"):
        assert element in content, f"stock page no longer has {element}"


# --- the recorder script ---------------------------------------------------


def test_recorder_script_is_always_injected(serve):
    _, url = serve()
    assert _RECORDER_JS in get(url)


def test_placeholders_are_still_substituted(serve):
    """The override reimplements upstream's templating, so a new placeholder
    upstream would ship to students unreplaced."""
    vis, url = serve()
    page = get(url)
    assert "{{" not in page
    assert str(vis.ws_port) in page and str(vis.fs_port) in page


def test_static_assets_still_come_from_the_stock_handler(serve):
    """Only `/` is overridden; everything else must fall through to upstream,
    or the page loads with no visualizer code at all."""
    _, url = serve()
    assert "function" in get(f"{url}/vis.js")


# --- declutter: the kwarg --------------------------------------------------


def test_declutter_kwarg_injects_style_and_flag(serve):
    _, url = serve(declutter=True)
    page = get(url)
    assert _DECLUTTER_CSS in page
    assert FLAG in page


def test_flag_precedes_the_declutter_script(serve):
    """The declutter script reads __CLASS_DECLUTTER_KWARG at parse time, so
    injecting it after would leave the flag permanently unread. Ordering is
    load-bearing and invisible in any single-string assertion."""
    _, url = serve(declutter=True)
    page = get(url)
    assert page.index(FLAG) < page.index(_DECLUTTER_CSS)


def test_declutter_kwarg_applies_without_a_query_string(serve):
    """The kwarg is the always-on form: it must not need ?minimal=1 too."""
    _, url = serve(declutter=True)
    assert _DECLUTTER_CSS in get(f"{url}/")


def test_declutter_closes_machine_tool_popups(make_visualizer):
    """Popups are part of the clutter, and they are a constructor kwarg rather
    than something CSS can reach."""
    assert make_visualizer(declutter=True)._show_machine_tools_at_start is False


def test_declutter_does_not_override_an_explicit_popup_choice(make_visualizer):
    """setdefault, not assignment: someone who asks for popups gets them."""
    vis = make_visualizer(declutter=True, show_machine_tools_at_start=True)
    assert vis._show_machine_tools_at_start is True


def test_popups_are_untouched_by_default(make_visualizer):
    assert make_visualizer()._show_machine_tools_at_start is True


# --- declutter: the query string ------------------------------------------


@pytest.mark.parametrize("query", ["minimal=1", "clean=1", "deck-only=1"])
def test_documented_query_aliases_all_declutter(serve, query):
    _, url = serve()
    assert _DECLUTTER_CSS in get(f"{url}/?{query}")


def test_query_declutter_does_not_set_the_kwarg_flag(serve):
    """The flag means "always minimal". A per-load query must not set it, or
    the distinction between the two mechanisms collapses."""
    _, url = serve()
    page = get(f"{url}/?minimal=1")
    assert _DECLUTTER_CSS in page
    assert FLAG not in page


def test_query_alias_works_without_a_value(serve):
    """`?minimal` with no `=1` is what people actually type."""
    _, url = serve()
    assert _DECLUTTER_CSS in get(f"{url}/?minimal")


def test_unrelated_query_strings_do_not_declutter(serve):
    _, url = serve()
    assert _DECLUTTER_CSS not in get(f"{url}/?zoom=2")


def test_no_declutter_by_default(serve):
    """The default page is the full stock UI; students need the side panel."""
    _, url = serve()
    page = get(url)
    assert _DECLUTTER_CSS not in page
    assert FLAG not in page
