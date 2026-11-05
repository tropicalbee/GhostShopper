from backend.app.agent.guards import ABORT, OK, WARN, LoopDetector


def test_same_action_on_same_page_warns_then_aborts():
    d = LoopDetector()
    args = {"element_id": "e5"}
    assert d.check("click", args, "http://s/p") == OK
    assert d.check("click", args, "http://s/p") == WARN
    assert d.check("click", args, "http://s/p") == ABORT


def test_same_action_on_different_pages_is_not_a_loop():
    d = LoopDetector()
    for url in ("http://s/a", "http://s/b", "http://s/c"):
        assert d.check("click", {"element_id": "e5"}, url) == OK


def test_finish_and_screenshots_never_count():
    d = LoopDetector()
    for _ in range(5):
        assert d.check("take_screenshot", {}, "http://s/p") == OK


def test_repeats_outside_the_window_are_forgotten():
    d = LoopDetector(window=3)
    assert d.check("read_text", {}, "http://s/p") == OK
    d.check("click", {"element_id": "e1"}, "http://s/p")
    d.check("click", {"element_id": "e2"}, "http://s/p")
    d.check("click", {"element_id": "e3"}, "http://s/p")
    assert d.check("read_text", {}, "http://s/p") == OK  # the first read_text fell out of the window


def test_leaving_the_page_and_coming_back_is_exploration_not_a_loop():
    d = LoopDetector()
    for _ in range(3):
        assert d.check("find_elements", {}, "http://s/product") != ABORT
        d.check("click", {"element_id": "e5"}, "http://s/product")
        d.check("open_page", {"url": "/product"}, "http://s/other")  # went somewhere else, came back


def test_argument_order_and_url_fragment_do_not_hide_a_loop():
    d = LoopDetector()
    d.check("fill_form", {"a": 1, "b": 2}, "http://s/p#top")
    assert d.check("fill_form", {"b": 2, "a": 1}, "http://s/p") == WARN
