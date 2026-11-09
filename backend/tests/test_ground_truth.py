import pytest

from backend.app.eval.ground_truth import DETECTOR_CHECKS, LABELS, expected
from backend.app.scoring import CHECKS
from store.flaws import FLAW_KEYS


def test_every_store_flaw_has_ground_truth_and_vice_versa():
    assert set(LABELS) == set(FLAW_KEYS)
    for checks in LABELS.values():
        assert set(checks) <= set(DETECTOR_CHECKS) <= set(CHECKS)


def test_flaw_without_ground_truth_cannot_be_evaluated():
    with pytest.raises(ValueError, match="made_up"):
        expected({"made_up"}, checkout=True)


def test_single_flaws_trigger_their_labels():
    for flaw, labels in LABELS.items():
        t = expected({flaw}, checkout=True)
        assert t.all_expected == set(labels), flaw
        assert t.all_masked == set()


def test_price_as_image_masks_price_comparisons():
    t = expected({"price_as_image", "price_mismatch"}, checkout=False)
    assert t.expected["price_as_image"] == {"price_in_text"}
    assert "price_mismatch" not in t.expected  # nothing visible in a browse run
    assert t.masked["price_mismatch"] == {"price_consistent"}


def test_sold_out_text_keeps_stock_readable_without_jsonld():
    t = expected({"no_structured_data", "oos_buyable"}, checkout=False)
    assert t.expected["no_structured_data"] == {"structured_data"}
    assert t.masked["no_structured_data"] == {"stock_readable"}


def test_currency_with_nothing_readable_is_masked():
    t = expected({"currency_missing", "price_as_image", "no_structured_data"}, checkout=False)
    assert "currency_missing" not in t.expected
    assert t.masked["currency_missing"] == {"currency_stated"}


def test_no_guest_checkout_label_is_accepted():
    t = expected({"no_guest_checkout"}, checkout=True)
    assert t.all_expected == set() and t.all_masked == set()
