import cv2
import numpy as np

from src.preprocessing.cleaner import clean_page


def _page_with_text():
    img = np.full((600, 400, 3), 255, np.uint8)
    cv2.putText(img, "VISION 6/6", (50, 100), cv2.FONT_HERSHEY_SIMPLEX,
                1.0, (0, 0, 0), 2)
    cv2.rectangle(img, (30, 150), (370, 200), (0, 0, 0), 2)
    return img


def test_clean_page_not_blank_and_survives():
    out, flags = clean_page(_page_with_text())
    assert not flags["blank"]
    assert out.shape[0] > 100 and out.shape[1] > 100


def test_blank_page_flagged_untouched():
    blank = np.full((600, 400, 3), 255, np.uint8)
    out, flags = clean_page(blank)
    assert flags["blank"]
    assert (out == blank).all()