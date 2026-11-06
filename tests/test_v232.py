"""2.3.2: scrolling settings, her voice in every language, ElevenLabs 400s, the new sitting pose."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (QApplication, QComboBox, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget)

app = QApplication.instance() or QApplication([])


def _wheel(widget, down=True):
    delta = QPoint(0, -120 if down else 120)
    ev = QWheelEvent(QPointF(5, 5), QPointF(widget.mapToGlobal(QPoint(5, 5))), QPoint(0, 0), delta,
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)


def test_scrolling_the_settings_page_never_changes_a_setting():
    from capri.ui.wheel_guard import guard
    page = QWidget()
    v = QVBoxLayout(page)
    combo, spin, slider = QComboBox(), QSpinBox(), QSlider(Qt.Orientation.Horizontal)
    combo.addItems(["a", "b", "c"])
    spin.setRange(0, 10)
    slider.setRange(0, 10)
    for w in (combo, spin, slider):
        v.addWidget(w)
    for _ in range(40):
        v.addWidget(QSpinBox())                        # a long page
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(page)
    area.resize(300, 200)
    area.show()
    assert guard(area) >= 43
    bar = area.verticalScrollBar()
    for w in (combo, spin, slider):
        _wheel(w)
    assert (combo.currentIndex(), spin.value(), slider.value()) == (0, 0, 0)
    assert bar.value() > 0                             # the page scrolled instead
    spin.setFocus()
    app.processEvents()
    if spin.hasFocus():                                # clicked into it: then the wheel is for it
        _wheel(spin, down=False)
        assert spin.value() == 1
    assert guard(area) == 0                            # not twice
    area.close()


def _http_error(code, body):
    import io
    import urllib.error
    return urllib.error.HTTPError("https://api.elevenlabs.io", code, "x", {}, io.BytesIO(body.encode()))


def test_elevenlabs_pasted_voice_links_and_names_become_the_id():
    from capri.speech.engines import ElevenLabsEngine as E
    vid = "21m00Tcm4TlvDq8ikWAM"
    assert E.voice_from(vid) == vid
    assert E.voice_from(f" {vid} ") == vid
    assert E.voice_from(f"https://elevenlabs.io/app/voice-library?voiceId={vid}") == vid
    assert E.voice_from(f"https://elevenlabs.io/app/voice-lab/share/abc/{vid}") == vid
    assert E.voice_from(f"Rachel - {vid}") == vid


def test_elevenlabs_fixes_a_400_by_itself():
    from capri.speech.engines import ElevenLabsEngine
    seen = []

    def fetch(url, body, headers):
        seen.append((url, dict(body), dict(body.get("voice_settings") or {})))
        if "voice_settings" in body and "speed" in body["voice_settings"]:
            raise _http_error(400, '{"detail": {"status": "invalid_voice_settings", "message": "speed"}}')
        return b"\x01\x00" * 4000
    ElevenLabsEngine.key = staticmethod(lambda: "k")
    ElevenLabsEngine.voice_id = staticmethod(lambda: "https://elevenlabs.io/app/voice-library?voiceId=AAAAAAAAAAAAAAAAAAAA")
    try:
        audio = ElevenLabsEngine(fetch=fetch).synthesize("hello there", "", 0.6)
    finally:
        ElevenLabsEngine.voice_id = staticmethod(lambda: "")
    assert audio is not None and len(seen) == 2
    assert "/AAAAAAAAAAAAAAAAAAAA?" in seen[0][0]
    assert "speed" not in seen[1][2]


def test_elevenlabs_400_that_never_works_says_why():
    import pytest
    from capri.speech.engines import ElevenLabsEngine

    def fetch(url, body, headers):
        raise _http_error(400, '{"detail": [{"loc": ["body", "text"], "msg": "field required"}]}')
    ElevenLabsEngine.key = staticmethod(lambda: "k")
    with pytest.raises(RuntimeError) as err:
        ElevenLabsEngine(fetch=fetch).synthesize("hi", "", 0.6)
    assert "field required" in str(err.value)


def test_elevenlabs_voice_the_plan_cant_use_falls_back_to_the_default_voice():
    from capri.speech.engines import ElevenLabsEngine
    urls = []

    def fetch(url, body, headers):
        urls.append(url)
        if ElevenLabsEngine.DEFAULT_VOICE not in url:
            raise _http_error(400, '{"detail": {"status": "voice_not_fine_tuned", "message": "not fine_tuned"}}')
        return b"\x01\x00" * 4000
    ElevenLabsEngine.key = staticmethod(lambda: "k")
    ElevenLabsEngine.voice_id = staticmethod(lambda: "BBBBBBBBBBBBBBBBBBBB")
    try:
        ElevenLabsEngine(fetch=fetch).synthesize("hi", "", 0.6)
    finally:
        ElevenLabsEngine.voice_id = staticmethod(lambda: "")
    assert ElevenLabsEngine.DEFAULT_VOICE in urls[-1] and len(urls) == 2


# -- her new sitting pose: her own figure on the window's edge -------------------------------------------------
def _companion(**kw):
    from capri.app import asset_root
    from capri.controller import CompanionController
    from capri.settings import Settings
    from capri.ui.art import CharacterArt
    from capri.ui.companion import Companion
    from capri.ui.sprites import SpriteArt
    c = Companion(CompanionController(), CharacterArt.load(asset_root() / "capri"), Settings(**kw),
                  SpriteArt.load(asset_root() / "capri_v2"))
    c.show()
    app.processEvents()
    return c


def test_she_sits_on_the_window_with_her_own_figure():
    import numpy as np
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from capri.ui import looks
    c = _companion()
    a = QGuiApplication.primaryScreen().availableGeometry()
    win = QRect(a.left() + 100, a.top() + 420, 600, 300)
    assert c.perch_on(win)
    app.processEvents()
    sit = c.sit_window
    assert sit._geo is not None                                  # her rig, not the old picture
    seat = sit.pos() + sit.seat_point()
    assert abs(seat.y() - win.top()) <= 6 and win.left() < seat.x() < win.right()
    img = QImage(sit.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    sit.render(img)
    alpha = looks.to_array(img)[..., 3] > 128
    edge = sit.seat_point().y()
    above, below = alpha[:edge].sum(), alpha[edge:].sum()
    assert above > 0 and below > 0                               # her body above the edge, her shins over it
    rows = np.flatnonzero(alpha.any(1))
    assert rows[-1] - edge > 0.15 * sit.height()                 # her legs really hang down
    box = sit.content_rect()
    assert sit.rect().contains(box) and box.height() > 100


def test_her_shins_swing_out_of_step_and_stay_on_her_knees():
    c = _companion()
    sit = c.sit_window
    import numpy as np
    kicks = [sit.kicks(t) for t in np.linspace(0, 2, 40)]
    black, red = [k[0] for k in kicks], [k[1] for k in kicks]
    assert max(black) > 0.6 and min(black) < -0.6 and max(abs(r) for r in red) > 0.2
    assert black.index(max(black)) != red.index(max(red))
    rig = c.character.full_rig()
    for side in ("left", "right"):                               # each shin's top is at its knee
        assert rig.shins[side].height() == rig.h and rig.knees[side].y() > rig.hip_joints[side].y()


def test_sitting_follows_her_size():
    c = _companion()
    sit = c.sit_window
    h100 = sit.height()
    sit.set_compact(False, 150)
    assert sit.height() > h100 * 1.3
    sit.set_compact(False, 100)
    assert sit.height() == h100


# -- her own voice in every language ----------------------------------------------------------------------------
class _FakeKokoro:
    """Stands in for kokoro_onnx: records what she was asked to say, and how."""
    def __init__(self):
        import numpy as np
        self.calls = []
        self.styles = {n: np.full((510, 1, 256), i + 1.0, np.float32)
                       for i, n in enumerate(["af_bella", "af_heart", "ef_dora", "ff_siwis", "if_sara", "pf_dora"])}

    def get_voice_style(self, name):
        return self.styles[name]

    def create(self, text, voice, speed, lang):
        import numpy as np
        self.calls.append((text, voice, lang))
        return np.zeros(2400, np.float32), 24000


def _kokoro_engine():
    from capri.speech.engines import KokoroEngine
    engine = KokoroEngine.__new__(KokoroEngine)
    engine._kokoro = _FakeKokoro()
    return engine


def test_her_own_voice_reads_each_language_with_its_own_pronunciation():
    import numpy as np
    from capri import languages
    engine = _kokoro_engine()
    fake = engine._kokoro
    capri = 0.6 * fake.styles["af_bella"] + 0.4 * fake.styles["af_heart"]
    try:
        for code in [c for c in languages.LANGUAGES if c != "en"]:
            languages.set_current(code)
            engine.synthesize("Hallo", "neural: Capri", 0.5)
            _text, style, lang = fake.calls[-1]
            info = languages.get(code)
            native = info.kokoro[0] if info.kokoro else "ef_dora"
            assert lang == (info.kokoro[1] if info.kokoro else info.espeak)         # that language's sounds
            expected = (1 - engine.ACCENT) * capri + engine.ACCENT * fake.styles[native]
            assert np.allclose(style, expected)                                    # mostly her own voice
        languages.set_current("en")
        engine.synthesize("hello", "neural: Capri", 0.5)
        assert fake.calls[-1][2] == "en-us" and np.allclose(fake.calls[-1][1], capri)
    finally:
        languages.set_current("en")


def test_in_another_language_she_keeps_her_neural_voice_instead_of_espeak():
    from capri import languages
    from capri.speech import engines as e
    kokoro = _kokoro_engine()
    kokoro.voices = lambda: ["neural: Capri"]
    espeak = e.EspeakEngine()
    espeak.voices = lambda: ["espeak: en"]
    box = e.VoiceBox.__new__(e.VoiceBox)
    box.engines = [kokoro, espeak]
    try:
        for code in ("de", "ru", "pl", "el", "fi"):
            languages.set_current(code)
            assert box.for_language("neural: Capri") == "neural: Capri"
            assert box.for_language("espeak: en") == "neural: Capri"            # (picked for you, if you had espeak)
    finally:
        languages.set_current("en")


def test_the_built_app_keeps_every_language_s_pronunciation():
    """The packaged app used to keep only English's espeak dictionary: no pronunciation for her other languages."""
    from pathlib import Path
    spec = (Path(__file__).resolve().parents[1] / "packaging" / "capri.spec").read_text()
    assert '!= "en_dict"' not in spec and "KEEP_DICTS" in spec
    from capri import languages
    keep = {lang.espeak.split("-")[0] + "_dict" for lang in languages.LANGUAGES.values()}
    assert len(keep) == 25
