"""Fixtures compartilhadas. Os fakes em si vivem em tests/helpers.py."""
import pytest

from tests.helpers import feed_item


@pytest.fixture
def make_feed_item():
    return feed_item
