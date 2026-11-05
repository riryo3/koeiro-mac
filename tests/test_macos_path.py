import os
import sys

import app


def test_a_finder_launched_app_gets_the_homebrew_folders_on_its_path(monkeypatch=None):
    if sys.platform != 'darwin' or not os.path.isdir('/opt/homebrew/bin'):
        return
    saved = os.environ.get('PATH')
    try:
        os.environ['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
        app.extend_path_for_macos()
        parts = os.environ['PATH'].split(os.pathsep)
        assert parts[:4] == ['/usr/bin', '/bin', '/usr/sbin', '/sbin']   # system tools stay first
        assert '/opt/homebrew/bin' in parts
        app.extend_path_for_macos()
        assert os.environ['PATH'].split(os.pathsep).count('/opt/homebrew/bin') == 1
    finally:
        os.environ['PATH'] = saved
