import os

import pytest
from PySide6.QtWidgets import QApplication

from src.utils.single_instance import SingleInstance, instance_key


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def key_for(name):
    # Unique per test process so a leftover pipe from a crashed run cannot interfere.
    return f'koeiro-test-{name}-{os.getpid()}'


def test_key_follows_the_data_directory(tmp_path):
    assert instance_key(tmp_path / 'a') == instance_key(tmp_path / 'A')
    assert instance_key(tmp_path / 'a') != instance_key(tmp_path / 'b')


def test_second_instance_hands_over_and_the_first_is_told(app):
    first = SingleInstance(key_for('handover'))
    try:
        assert first.acquire() is True
        raised = []
        first.on_activate(lambda: raised.append(True))

        second = SingleInstance(key_for('handover'))
        assert second.acquire() is False
        assert first.server.waitForNewConnection(2000)
        app.processEvents()
        assert raised == [True]
    finally:
        first.close()


def test_key_is_reusable_after_the_owner_closes(app):
    key = key_for('reuse')
    first = SingleInstance(key)
    assert first.acquire() is True
    first.close()
    second = SingleInstance(key)
    try:
        assert second.acquire() is True
    finally:
        second.close()


def test_distinct_keys_do_not_collide(app):
    other = SingleInstance(key_for('other'))
    try:
        assert other.acquire() is True
    finally:
        other.close()
