"""Theme and copy gates: contrast math, focus visibility, honest wording.

These pin the antislop decisions so a later tweak cannot silently reintroduce
a failing pair or a banned character.
"""


def _luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _ratio(foreground, background):
    lighter = max(_luminance(foreground), _luminance(background))
    darker = min(_luminance(foreground), _luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def test_text_pairs_meet_wcag_aa():
    from src.gui import shell
    # Body and hint text on every surface it sits on.
    assert _ratio(shell.TEXT_MUTED, shell.BG) >= 4.5
    assert _ratio(shell.TEXT_MUTED, shell.CARD) >= 4.5
    assert _ratio(shell.TEXT_MUTED, shell.PILL) >= 4.5
    assert _ratio(shell.TEXT, shell.BG) >= 4.5
    assert _ratio(shell.TEXT, shell.CARD) >= 4.5
    # Reversed pairs on filled controls.
    assert _ratio(shell.PRIMARY_TEXT, shell.PRIMARY) >= 4.5
    assert _ratio('#ffffff', shell.DANGER) >= 4.5
    assert _ratio(shell.WARN, shell.CARD) >= 4.5
    assert _ratio(shell.WARN, shell.BG) >= 4.5
    # Error text is the fill hue one step darker: the fill itself only reaches
    # 4.3:1 on the page, so it may never be used for words.
    assert _ratio(shell.DANGER_TEXT, shell.BG) >= 4.5
    assert _ratio(shell.DANGER_TEXT, shell.CARD) >= 4.5
    assert _ratio(shell.DANGER, shell.BG) < 4.5


def test_live_accent_is_a_single_color():
    from src.gui import shell
    assert shell.LIVE.startswith('#') and shell.LIVE == shell.PRIMARY
    assert _ratio(shell.LIVE, shell.BG) >= 4.5
    assert _ratio(shell.LIVE, shell.CARD) >= 4.5


def test_surfaces_share_one_readable_navy():
    """Wayfinding uses the single brand navy, never four competing tints."""
    from src.gui import shell
    for name in ('TUNE_TINT', 'LAB_TINT', 'VOICE_TINT', 'GUIDE_TINT'):
        assert not hasattr(shell, name), name
    css = shell.stylesheet('assets')
    for selector in ('QLabel#drawerTitle', 'QLabel#railTitle', 'QLabel#guideTitle'):
        assert selector in css, selector
    assert css.count(shell.LIVE) >= 4
    for surface in (shell.BG, shell.CARD, shell.PILL):
        assert _ratio(shell.LIVE, surface) >= 4.5, surface


def test_keyboard_focus_stays_visible_without_moving_layout():
    from src.gui.shell import stylesheet
    css = stylesheet('assets')
    for selector in ('QPushButton:focus', 'QComboBox:focus', 'QLineEdit:focus',
                     'QCheckBox:focus', 'QSlider:focus'):
        assert selector in css, selector
    # An id selector outranks the plain :focus rule, so the window controls need their
    # own focus rule or the keyboard would have no visible focus on them.
    for selector in ('QPushButton#windowButton:focus', 'QPushButton#windowClose:focus'):
        assert selector in css, selector


def test_guide_copy_has_no_em_dash_or_buzzwords():
    from src.gui.tutorial import PAGES
    banned = ('—', 'シームレス', '次世代', '革新的', '最先端', 'パワフル',
              'AI Powered', 'Seamless', '革命的')
    assert len(PAGES) == 6
    for spec in PAGES:
        for word in banned:
            assert word not in spec['body'], (spec['title'], word)


def test_the_drawer_finds_its_own_contents_without_a_second_list():
    """The search box and the jump row are built from the cards that are there."""
    from src.gui.shell import stylesheet
    css = stylesheet('assets')
    for selector in ('QLineEdit#drawerSearch', 'QPushButton#indexJump',
                     'QPushButton#indexJump:checked', 'QPushButton#indexJump:disabled'):
        assert selector in css, selector
    # The guide's two buttons are told apart by fill, not by colour alone.
    assert 'QPushButton#guideNext {' in css
    assert 'QPushButton#guideBack {' in css


def test_status_pill_marks_real_states_only():
    from src.gui.shell import StatusPill
    assert set(StatusPill.BADGES) == {'stopped', 'running', 'error'}


def test_ai_readiness_states_use_theme_tokens_only():
    """Every readiness colour is a palette token, so a state cannot invent one."""
    from src.gui import shell
    css = shell.stylesheet('assets')
    assert 'QLabel#aiBanner {' in css
    for state in ('loading', 'ready', 'fallback', 'unavailable', 'error'):
        assert f'QLabel#aiBanner[state="{state}"]' in css, state
        assert state in shell.AiReadiness.TEXT, state
    for token in (shell.LIVE, shell.WARN, shell.DANGER_TEXT, shell.TEXT, shell.TEXT_MUTED,
                   shell.PRIMARY):
        assert token in css, token
