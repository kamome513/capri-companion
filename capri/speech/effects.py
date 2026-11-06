"""Voice styles - turns a plain TTS voice into something more Capri.

All offline numpy DSP on the rendered audio, a few milliseconds per sentence.

* natural   - the voice as-is
* netrunner - brighter, with a thin digital double and a touch of bit-crush:
              a voice coming through a cyberdeck
* glitch    - netrunner with a hiccup now and then (a repeated grain, a tiny cut-out)
* capri     - clean, bright and airy: her preset. No ring-mod, comb or bit-crush
              (those are what made her sound robotic) - the digital edge lives
              in netrunner / glitch now.
"""

from __future__ import annotations

import numpy as np

from .engines import Audio

STYLES = {"capri": "Capri (bright and airy)", "studio": "Studio (clean and clear)", "natural": "Natural (no effects)",
          "holocall": "Holocall (on a call - phone line and static)",
          "netrunner": "Netrunner (digital, doubled)", "glitch": "Glitch (breaking signal)",
          "android": "Android (robotic ring)", "cyberspace": "Cyberspace (echoing, far away)"}

# The "Capri" preset: her character's vibe - young, quick, bright, anime-girl energy.
# (A sound-alike in spirit; it doesn't copy any real person's voice.)
# Voice "" = the default, which is her neural "Capri" voice once that's installed.
CAPRI_PRESET = {"speech_voice": "", "speech_style": "capri", "speech_pitch": 0.78, "speech_speed": 0.6}
LEVEL_FRAME = 1 / 30          # lip-sync resolution: one level per animation frame


def time_stretch(x: np.ndarray, factor: float, rate: int) -> np.ndarray:
    """Make audio `factor` times longer without changing pitch (WSOLA)."""
    frame = int(0.030 * rate)
    hop_out = frame // 2
    hop_in = hop_out / factor
    tol = int(0.008 * rate)
    if len(x) < frame * 2:
        return x
    window = np.hanning(frame).astype(np.float32)
    n_frames = int((len(x) - frame - tol) / hop_in)
    out = np.zeros(n_frames * hop_out + frame, dtype=np.float32)
    norm = np.zeros_like(out)
    prev = 0
    for k in range(n_frames):
        ideal = int(k * hop_in)
        if k == 0:
            pos = ideal
        else:
            natural = prev + hop_out                       # where the last frame "wants" to continue
            template = x[natural:natural + frame]
            lo, hi = max(0, ideal - tol), min(len(x) - frame, ideal + tol)
            if len(template) < frame or hi <= lo:
                pos = min(max(ideal, 0), len(x) - frame)
            else:
                search = x[lo:hi + frame]
                pos = lo + int(np.argmax(np.correlate(search, template, mode="valid")))
        seg = x[pos:pos + frame]
        if len(seg) < frame:
            break
        out[k * hop_out:k * hop_out + frame] += seg * window
        norm[k * hop_out:k * hop_out + frame] += window
        prev = pos
    norm[norm < 1e-3] = 1.0
    return (out / norm).astype(np.float32)


def pitch_shift(x: np.ndarray, rate: int, semitones: float) -> np.ndarray:
    """Raise/lower pitch while keeping her speaking speed."""
    if abs(semitones) < 0.05:
        return x
    f = 2 ** (semitones / 12)
    return time_stretch(_resample(x, f), f, rate)


def _resample(x: np.ndarray, factor: float) -> np.ndarray:
    """Play back `factor` times faster (raises pitch and tempo together)."""
    n = int(len(x) / factor)
    return np.interp(np.arange(n) * factor, np.arange(len(x)), x).astype(np.float32)


def _highpass(x: np.ndarray, rate: int, cutoff: float = 140.0) -> np.ndarray:
    """Thin out the low end: subtract a moving average (a cheap high-pass)."""
    k = max(3, int(rate / cutoff))
    return (x - np.convolve(x, np.ones(k, dtype=np.float32) / k, mode="same")).astype(np.float32)


def _brighten(x: np.ndarray, rate: int, amount: float = 0.35) -> np.ndarray:
    """Lift the highs (presence / air) - reads younger and brighter."""
    k = max(3, int(rate / 2500))
    low = np.convolve(x, np.ones(k, dtype=np.float32) / k, mode="same")
    return (x + amount * (x - low)).astype(np.float32)


def _shimmer(x: np.ndarray, rate: int, hz: float = 55.0, depth: float = 0.12) -> np.ndarray:
    """A faint ring-mod ripple: the 'voice through a cyberdeck' edge, kept subtle."""
    t = np.arange(len(x), dtype=np.float32) / rate
    return (x * (1 - depth + depth * np.cos(2 * np.pi * hz * t))).astype(np.float32)


def _crush(x: np.ndarray, bits: int) -> np.ndarray:
    q = 2 ** (bits - 1)
    return np.round(x * q) / q


def _double(x: np.ndarray, rate: int, ms: float = 11.0, mix: float = 0.35) -> np.ndarray:
    d = int(rate * ms / 1000)
    y = x.copy()
    y[d:] += mix * x[:-d]
    return y


GLITCHES = ("stutter", "stutter", "cut", "skip")


def _glitch(x: np.ndarray, rate: int, rng: np.random.Generator) -> np.ndarray:
    """A signal that hiccups now and then: a short repeated grain ("b-break"), a tiny cut-out, or
    a skip back - about one a second, each a few hundredths of a second. Noticeable, not noisy."""
    out, pos, step = [], 0, int(rate * rng.uniform(0.25, 0.6))
    while pos < len(x):
        out.append(x[pos:pos + step])
        pos += step
        step = int(rate * rng.uniform(0.8, 1.5))
        if pos >= len(x) - rate // 10:
            break
        g = int(rate * rng.uniform(0.03, 0.05))
        grain = x[pos:pos + g]
        kind = GLITCHES[int(rng.integers(len(GLITCHES)))]
        if kind == "stutter":
            out.append((grain * 0.85).astype(np.float32))       # one repeat: "b-break"
        elif kind == "cut":
            out.append(np.zeros(int(rate * 0.025), np.float32))
            pos += g // 2
        elif kind == "skip":
            out.append(x[max(0, pos - g):pos].copy())
    return np.concatenate(out).astype(np.float32) if out else x


def _lowpass(x: np.ndarray, rate: int, cutoff: float) -> np.ndarray:
    k = max(2, int(rate / cutoff))
    return np.convolve(x, np.ones(k, dtype=np.float32) / k, mode="same").astype(np.float32)


def _ring(x: np.ndarray, rate: int, hz: float, mix: float) -> np.ndarray:
    """Ring modulation: the classic robot voice."""
    t = np.arange(len(x), dtype=np.float32) / rate
    return ((1 - mix) * x + mix * x * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def _echo(x: np.ndarray, rate: int, taps=((0.09, 0.45), (0.19, 0.3), (0.31, 0.18), (0.46, 0.1))) -> np.ndarray:
    """A spacey echo tail (the line gets a little longer)."""
    longest = int(rate * taps[-1][0]) + 1
    y = np.concatenate([x, np.zeros(longest, dtype=np.float32)])
    for delay, gain in taps:
        d = int(rate * delay)
        y[d:d + len(x)] += gain * x
    return y.astype(np.float32)


def _mix(dry: np.ndarray, wet: np.ndarray, amount: float) -> np.ndarray:
    """Some of the effect, some of her plain voice: a flavour, not a filter over everything."""
    n = min(len(dry), len(wet))
    out = wet.copy()
    out[:n] = (1 - amount) * dry[:n] * ((float(np.max(np.abs(wet))) or 1.0) / (float(np.max(np.abs(dry))) or 1.0)) \
        + amount * wet[:n]
    return out.astype(np.float32)


def _static(x: np.ndarray, rng: np.random.Generator, level: float = 0.025) -> np.ndarray:
    noise = rng.standard_normal(len(x)).astype(np.float32) * level * float(np.max(np.abs(x)) or 1.0)
    return (x + noise).astype(np.float32)


def _even(x: np.ndarray, rate: int, amount: float = 0.5) -> np.ndarray:
    """Gentle level-evening (like a vocal compressor): quiet syllables come up a little, loud ones don't jump."""
    hop = max(1, rate // 200)
    n = len(x) // hop
    if n < 4:
        return x
    env = np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-9)
    env = np.convolve(env, np.ones(8) / 8, mode="same")
    ref = float(np.percentile(env, 90)) or 1.0
    gain = (np.clip(env / ref, 0.05, 1.0)) ** (-amount * 0.5)
    gain = np.minimum(gain, 2.5)
    g = np.interp(np.arange(len(x)) / hop, np.arange(n), gain).astype(np.float32)
    return (x * g).astype(np.float32)


def apply_style(audio: Audio, style: str, seed: int = 0, pitch: float = 0.0) -> Audio:
    """Voice style + pitch (semitones; skipped when the engine already pitched it)."""
    x, rate = audio.samples.astype(np.float32), audio.rate
    if len(x) < rate // 20:                       # a blip (under 50 ms): too short to filter
        return Audio(x, rate, pitched=True)
    if not audio.pitched:
        x = pitch_shift(x, rate, pitch)
    rng = np.random.default_rng(seed)
    if style == "capri":
        x = _highpass(x, rate, cutoff=110.0)      # trim the boom
        x = _brighten(x, rate, amount=0.55)       # bright, airy top
        x = _double(x, rate, ms=7.0, mix=0.18)    # a touch of sparkle
    elif style == "studio":                       # clean and clear (2.3.4): no doubling, just polish
        x = _highpass(x, rate, cutoff=85.0)
        x = _brighten(x, rate, amount=0.25)
        x = _even(x, rate, amount=0.5)
    elif style == "holocall":                     # a light phone-line colour: still clearly her
        line = _lowpass(_highpass(x, rate, cutoff=300.0), rate, cutoff=3400.0)
        line = np.tanh(line * 1.6 / (float(np.max(np.abs(line))) or 1.0)).astype(np.float32)
        x = _mix(x, _static(_shimmer(line, rate, hz=50.0, depth=0.04), rng, 0.01), 0.55)
    elif style in ("netrunner", "glitch"):       # a faint digital double and edge
        wet = _shimmer(_double(_highpass(x, rate, cutoff=150.0), rate, ms=10.0, mix=0.22), rate, hz=60.0, depth=0.07)
        x = _mix(x, _crush(wet / (float(np.max(np.abs(wet))) or 1.0), 9), 0.85)
        if style == "glitch":
            x = _glitch(x, rate, rng)
    elif style == "android":                      # a hint of robot ring
        x = _double(_ring(_highpass(x, rate, cutoff=120.0), rate, hz=48.0, mix=0.26), rate, ms=4.0, mix=0.15)
    elif style == "cyberspace":                   # a little room around her
        x = _echo(_brighten(_highpass(x, rate, cutoff=110.0), rate, amount=0.2), rate,
                  taps=((0.08, 0.22), (0.17, 0.11), (0.28, 0.05)))
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak > 0:
        x = x * (0.9 / peak)                      # same loudness for every style
    return Audio(x.astype(np.float32), rate)


def intonation(audio: Audio, amount: float, question: bool = False, exclaim: bool = False, seed: int = 0) -> Audio:
    """Highs and lows instead of one steady tone - like someone actually talking:
    * louder (stressed) syllables go up, quiet ones settle down;
    * gentle rises and falls every few syllables;
    * a statement drifts down towards its end, a question rises at the end, "!" is livelier.
    amount: 0 = flat (as the voice made it), 1 = lively (about +-3 semitones), more = very animated.
    Done by playing the sentence back at a smoothly varying speed (higher = a touch quicker)."""
    x, rate = audio.samples.astype(np.float32), audio.rate
    if amount <= 0.01 or len(x) < rate // 5:
        return audio
    rng = np.random.default_rng(seed)
    hop = max(1, rate // 100)                                   # 10 ms frames
    n = len(x) // hop
    env = np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1))
    env = np.convolve(env, np.ones(7) / 7, mode="same")         # syllable-ish loudness
    voiced = env > 0.15 * (float(env.max()) or 1.0)
    if voiced.sum() < 5:
        return audio
    level = (env - env[voiced].mean()) / (env[voiced].std() + 1e-6)
    stress = np.clip(level, -1.5, 2.0) * 1.1                   # semitones per std of loudness
    t = np.linspace(0.0, 1.0, n)
    knots = max(3, int(n / 30))                                 # a rise or fall every ~0.3 s
    wander = np.interp(t, np.linspace(0, 1, knots), rng.uniform(-1.6, 1.6, knots))
    wander = np.convolve(wander, np.ones(15) / 15, mode="same")
    drift = 1.0 - 2.0 * t                                       # down over a statement
    contour = stress + wander + drift
    if question:
        contour = contour - drift + 4.0 * np.clip((t - 0.7) / 0.3, 0, 1) ** 1.5   # ...and up at the end
    if exclaim:
        contour = contour * 1.3 + 0.8
    contour = np.convolve(contour, np.ones(9) / 9, mode="same") * amount
    contour = np.clip(contour, -5.0, 6.0)
    factor = np.interp(np.arange(len(x)) / hop, np.arange(n), 2.0 ** (contour / 12.0))
    out_time = np.cumsum(1.0 / factor)                          # where each input sample lands
    positions = np.interp(np.arange(int(out_time[-1])), out_time, np.arange(len(x), dtype=np.float64))
    y = np.interp(positions, np.arange(len(x)), x).astype(np.float32)
    return Audio(y, rate, pitched=True)


TONES = ("warm", "soft", "flat", "sharp", "bouncy", "rasp", "punchy")


def apply_tone(audio: Audio, tone: str) -> Audio:
    """Her personality's voice colour, on top of the style: warm (sarcastic), soft (sweet,
    kuudere), flat (deadpan), sharp (tsundere), bouncy (silly), rasp (gremlin), punchy (hype)."""
    x, rate = audio.samples.astype(np.float32), audio.rate
    if tone not in TONES or len(x) < rate // 20:
        return audio
    peak = float(np.max(np.abs(x))) or 1.0
    if tone == "warm":
        x = 0.45 * x + 0.55 * _lowpass(x, rate, 2400.0)
    elif tone == "soft":
        x = 0.35 * x + 0.65 * _lowpass(x, rate, 3000.0)
    elif tone == "flat":                                      # squashed and dull: no excitement
        x = _lowpass(np.tanh(3.0 * x / peak).astype(np.float32), rate, 3400.0)
    elif tone == "sharp":
        x = _brighten(x, rate, amount=0.8)
    elif tone == "bouncy":                                    # a quick wobble in her voice
        t = np.arange(len(x), dtype=np.float32) / rate
        x = x * (0.72 + 0.28 * np.cos(2 * np.pi * 6.5 * t))
    elif tone == "rasp":                                      # gritty
        x = 0.5 * x + 0.5 * np.tanh(5.0 * x / peak) * peak
    elif tone == "punchy":                                    # loud and in your face
        x = _brighten(np.tanh(2.2 * x / peak).astype(np.float32) * peak, rate, amount=0.4)
    top = float(np.max(np.abs(x))) or 1.0
    level = 0.7 if tone == "soft" else 1.0                    # soft really is quieter
    return Audio((x * (level * peak / top)).astype(np.float32), rate, pitched=True)


def levels(audio: Audio) -> list[float]:
    """Loudness per animation frame, 0..1 - drives her mouth and the voice bars."""
    frame = max(1, int(audio.rate * LEVEL_FRAME))
    x = audio.samples
    n = len(x) // frame
    if n == 0:
        return []
    rms = np.sqrt(np.mean(x[:n * frame].reshape(n, frame) ** 2, axis=1))
    top = float(np.percentile(rms, 95)) or 1.0
    return [float(v) for v in np.clip(rms / top, 0.0, 1.0)]
