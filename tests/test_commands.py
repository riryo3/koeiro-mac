import pytest

from src.asr.commands import CommandMatcher, VoiceCommand, label


@pytest.mark.parametrize("text,kind", [
    ("コエイロ止めて", "stop"),
    ("こえいろ、ストップ！", "stop"),
    ("Koeiro スタート", "start"),
    ("コエイロ、次の声", "next_voice"),
    ("こえいろ 前の声にして", "prev_voice"),
    ("コエイロ地声", "original"),
    ("こえいろAIボイス", "ai_voice"),
    ("ＫＯＥＩＲＯ 止まって", "stop"),
])
def test_recognised_commands(text, kind):
    result = CommandMatcher().match(text, now=0.0)
    assert result is not None and result.kind == kind


@pytest.mark.parametrize("text", ["止めて", "スタート", "次の声", "", None, 42, "こんにちは"])
def test_requires_the_wake_word(text):
    assert CommandMatcher().match(text, now=0.0) is None


def test_wake_word_without_a_command_is_not_a_command():
    assert CommandMatcher().match("コエイロ、今日はいい天気だね", now=0.0) is None
    assert CommandMatcher().wake_present("コエイロ")


def test_cooldown_absorbs_repeats_but_not_other_commands():
    matcher = CommandMatcher(cooldown=1.5)
    assert matcher.match("コエイロ止めて", now=10.0).kind == "stop"
    assert matcher.match("こえいろ止めて", now=10.4) is None
    # A different command is never swallowed by the cooldown.
    assert matcher.match("コエイロ次の声", now=10.5).kind == "next_voice"
    # The same command is accepted again once the window has passed.
    assert matcher.match("コエイロ止めて", now=12.0).kind == "stop"


def test_reset_clears_the_cooldown():
    matcher = CommandMatcher(cooldown=10.0)
    assert matcher.match("コエイロ止めて", now=1.0).kind == "stop"
    assert matcher.match("コエイロ止めて", now=2.0) is None
    matcher.reset()
    assert matcher.match("コエイロ止めて", now=2.0).kind == "stop"


def test_command_carries_the_matched_phrase_and_a_label():
    command = VoiceCommand("stop", "止めて")
    assert label(command) == "変換を停止"
    result = CommandMatcher().match("コエイロ止めて", now=0.0)
    assert result == VoiceCommand("stop", "止めて")


def test_voice_commands_flag_defaults_off_and_validates():
    from src.prosody.parameters import ProsodyParameters
    assert ProsodyParameters().voice_commands is False
    assert ProsodyParameters.from_dict({"voice_commands": True}).voice_commands is True
    assert ProsodyParameters.from_dict({"voice_commands": "yes"}).voice_commands is False


def test_asr_bridge_text_path_is_wanted_for_commands():
    from src.asr.bridge import ASRBridge
    from src.prosody.parameters import ProsodyParameters
    # Prosody off and commands off: the text path stays idle.
    assert ASRBridge(ProsodyParameters())._text_wanted is False
    # Turned on only for commands: the ASR path runs without Auto Intonation.
    assert ASRBridge(ProsodyParameters(enabled=False, engine="rule_v2",
                                       voice_commands=True))._text_wanted is True
    assert ASRBridge(ProsodyParameters(enabled=True, engine="text_v3"))._text_wanted is True


def test_asr_bridge_take_command_consumes_once():
    from src.asr.bridge import ASRBridge
    from src.prosody.parameters import ProsodyParameters
    bridge = ASRBridge(ProsodyParameters(voice_commands=True))
    bridge.last_command = VoiceCommand("next_voice", "次の声")
    assert bridge.take_command() == VoiceCommand("next_voice", "次の声")
    assert bridge.take_command() is None
