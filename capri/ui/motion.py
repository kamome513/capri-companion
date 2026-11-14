"""How Capri moves on her own (2.6.2): standing still, being picked up, carried and put down.

Everything here runs on real elapsed time (delta-time), so it looks the same at any frame rate, and is built
from damped springs: values glide towards where they want to be, overshoot a little and settle - no snapping,
no fixed-length loops.

* IdleMotion - while she stands: breathing, small weight shifts, her head tilting now and then, her arms
  drifting, her eyes glancing about, and every so often a little posture adjustment. Each one wanders on its
  own clock, so it never repeats like a loop.
* DragMotion - picked up, she hangs from the point you grabbed her by: she swings behind your movement like
  a pendulum, her legs dangle and her arms hang with gravity, her head, hair and legs follow a little later
  than her body (follow-through), and she looks where you're taking her. Let go and she swings back upright,
  her knees give as she settles, and her idle picks up again.

The art is one standing picture cut into parts (see rig.py): legs, hips, upper body, head, arms (split at
the elbow), her face with separate eyes, and the traced hair. All of this moves those parts - nothing here
pretends to be frames of artwork that don't exist.
"""

from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF

SUBSTEP = 1 / 120                       # springs are stepped at least this finely (stable at any frame rate)


class Spring:
    """A damped spring: `value` chases a target. freq: how quick (Hz), damping: 1 = no overshoot, less = a
    little bounce (0.5-0.7 reads as natural follow-through)."""

    def __init__(self, freq: float, damping: float, value: float = 0.0) -> None:
        self.w = 2 * math.pi * freq
        self.z = damping
        self.value = value
        self.vel = 0.0

    def step(self, target: float, dt: float) -> float:
        n = max(1, math.ceil(dt / SUBSTEP))
        h = dt / n
        for _ in range(n):                                        # semi-implicit Euler: stable, cheap
            acc = self.w * self.w * (target - self.value) - 2 * self.z * self.w * self.vel
            self.vel += acc * h
            self.value += self.vel * h
        return self.value

    def kick(self, velocity: float) -> None:
        self.vel += velocity

    def resting(self, target: float = 0.0, eps: float = 1e-3) -> bool:
        return abs(self.value - target) < eps and abs(self.vel) < eps * 10

    def reset(self, value: float = 0.0) -> None:
        self.value, self.vel = value, 0.0


class _Wander:
    """A value that picks a new spot now and then (at varied times) and glides there."""

    def __init__(self, rng: random.Random, spread: float, every: tuple[float, float], freq: float,
                 damping: float = 1.0, centre_bias: float = 0.0) -> None:
        self.rng, self.spread, self.every, self.centre_bias = rng, spread, every, centre_bias
        self.spring = Spring(freq, damping)
        self.target = 0.0
        self.next = rng.uniform(*every) * 0.5

    def step(self, dt: float, clock: float) -> float:
        if clock >= self.next:
            if self.rng.random() < self.centre_bias:
                self.target = 0.0
            else:
                self.target = self.rng.uniform(-self.spread, self.spread)
            self.next = clock + self.rng.uniform(*self.every)
        return self.spring.step(self.target, dt)


class IdleMotion:
    """Her life while she stands still. step(dt) each frame, then moves() for the pose."""

    BREATH_PERIOD = 3.9                 # seconds per breath (it varies a little, breath to breath)

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        r = self.rng
        self.clock = 0.0
        self._breath_phase = r.uniform(0, 2 * math.pi)
        self._breath_rate = 1.0
        self._next_rate = 0.0
        self.weight = _Wander(r, 0.011, (4.0, 9.0), 0.35)               # leaning onto one hip, then the other
        self.head = _Wander(r, 2.2, (2.5, 7.0), 0.55, 0.85, 0.3)        # head tilt (degrees)
        self.look_x = _Wander(r, 1.0, (1.6, 5.0), 3.2, 1.0, 0.45)       # eyes: quick glances, mostly ahead
        self.look_y = _Wander(r, 0.6, (2.2, 6.0), 3.2, 1.0, 0.6)
        self.arms = _Wander(r, 1.6, (3.0, 8.0), 0.4)                    # arms drifting a degree or two
        self.adjust = Spring(1.6, 0.6)                                  # a posture adjustment: knees dip...
        self.adjust_tilt = Spring(0.9, 0.7)                             # ...and her head settles a new way
        self._next_adjust = r.uniform(9.0, 16.0)
        self._adjust_side = 1.0

    def step(self, dt: float) -> None:
        dt = max(0.0, min(0.1, dt))
        self.clock += dt
        c, r = self.clock, self.rng
        if c >= self._next_rate:                                     # each breath a touch longer or shorter
            self._breath_rate = r.uniform(0.88, 1.12)
            self._next_rate = c + self.BREATH_PERIOD * r.uniform(0.9, 1.6)
        self._breath_phase += dt * 2 * math.pi / self.BREATH_PERIOD * self._breath_rate
        for w in (self.weight, self.head, self.look_x, self.look_y, self.arms):
            w.step(dt, c)
        if c >= self._next_adjust:                                   # now and then: shift her stance
            self._next_adjust = c + r.uniform(10.0, 22.0)
            self._adjust_side = r.choice((-1.0, 1.0))
            self.adjust.kick(0.35)
            self.adjust_tilt.kick(9.0 * self._adjust_side)
            self.weight.target = -self.weight.target if abs(self.weight.target) > 0.004 else \
                0.009 * self._adjust_side
        self.adjust.step(0.0, dt)
        self.adjust_tilt.step(0.0, dt)

    @property
    def breath(self) -> float:
        """0..1: in and out (a breath in is a little quicker than the breath out)."""
        s = math.sin(self._breath_phase)
        return 0.5 + 0.5 * (s if s > 0 else s * 0.85)

    def moves(self) -> dict[str, float]:
        b = self.breath
        dip = max(0.0, self.adjust.value)
        return {
            "breath": b,
            "lean": self.weight.spring.value + 0.004 * math.sin(self.clock * 0.37),
            "tilt": self.head.spring.value + self.adjust_tilt.value + 0.35 * math.sin(self.clock * 0.53 + 1.0),
            "arms": self.arms.spring.value + 0.9 * (b - 0.5),           # arms lift a hair with each breath in
            "look_x": self.look_x.spring.value,
            "look_y": self.look_y.spring.value,
            "squat": 0.05 * dip,
            "hair_drag": 0.035 * math.sin(self.clock * 0.8) + 0.02 * math.sin(self.clock * 1.9 + 2.0),
        }


class DragMotion:
    """Picked up and carried. grab(), moved() with the cursor, drop(); step(dt) every frame."""

    MAX_SWING = 15.0                     # degrees she can swing out from hanging straight
    SPEED_FOR_MAX = 1400.0               # px/s of your cursor for most of the swing

    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self.held = False
        self.pivot = QPointF()           # where you're holding her (her window's coordinates)
        self.since = 0.0
        self.dropped_at = -1e9
        self.grip = Spring(3.2, 0.85)    # 0..1: how "picked up" she is - eases in on grab, out on release
        self.swing = Spring(1.15, 0.55)  # her whole body swinging from your grip (degrees)
        self.lag = Spring(1.9, 0.5)      # her head / hair / legs, a little behind her body (follow-through)
        self.lift = Spring(2.2, 0.6)     # up / down: legs tuck when you lower her fast, hair streams
        self.settle = Spring(2.6, 0.45)  # put down: her knees give and come back
        self._vel = QPointF()            # your cursor's speed (px/s), smoothed
        self._acc = QPointF()
        self._last: tuple[float, QPointF] | None = None
        self._last_step = clock()

    # -- input ----------------------------------------------------------------------------------------------------
    def grab(self, pivot: QPointF | None = None) -> None:
        self.held, self.since, self._last = True, self.clock(), None
        if pivot is not None:
            self.pivot = QPointF(pivot)
        self._vel, self._acc = QPointF(), QPointF()
        self.lag.kick(-25.0)                                    # a little jolt as she's lifted

    def drop(self) -> None:
        if self.held:
            self.held = False
            self.dropped_at = self.clock()
            self.settle.kick(1.6 + min(1.5, abs(self.lift.value) * 2))   # knees give as she's put down

    def moved(self, pos) -> None:
        """Your cursor's screen position (a QPointF, or just x)."""
        if not isinstance(pos, QPointF):
            pos = QPointF(float(pos), self._last[1].y() if self._last else 0.0)
        now = self.clock()
        if self._last is not None:
            t0, p0 = self._last
            dt = now - t0
            if dt > 1e-4:
                raw = (pos - p0) / dt
                k = 1 - math.exp(-dt / 0.045)                   # smoothed over ~45 ms: steady, not laggy
                new = self._vel + (raw - self._vel) * k
                self._acc = self._acc + ((new - self._vel) / dt - self._acc) * k
                self._vel = new
        self._last = (now, QPointF(pos))

    # -- every frame ----------------------------------------------------------------------------------------------
    def step(self, dt: float) -> None:
        dt = max(0.0, min(0.1, dt))
        if self.held and self._last is not None and self.clock() - self._last[0] > 0.03:
            fade = math.exp(-dt / 0.06)                         # you stopped moving: her speed fades out
            self._vel *= fade
            self._acc *= fade
        vx, vy = self._vel.x(), self._vel.y()
        if self.held:
            swing_to = -self.MAX_SWING * math.tanh(vx / self.SPEED_FOR_MAX)       # trails behind you
            lift_to = math.tanh(vy / 1600.0)                                       # + = being lowered
        else:
            swing_to, lift_to = 0.0, 0.0
        self.grip.step(1.0 if self.held else 0.0, dt)
        self.swing.step(swing_to, dt)
        self.lag.step(self.swing.value, dt)
        self.lift.step(lift_to, dt)
        self.settle.step(0.0, dt)

    # -- what it looks like -----------------------------------------------------------------------------------------
    @property
    def swinging(self) -> bool:
        """Still moving (needs smooth frames): held, or swinging / settling after."""
        return self.held or not (self.grip.resting(0.0) and self.swing.resting() and self.lag.resting()
                                 and self.lift.resting() and self.settle.resting())

    @property
    def angle(self) -> float:
        """Her whole-body swing, in degrees (+ = clockwise)."""
        return self.swing.value

    def pose_moves(self, now: float | None = None) -> dict[str, float]:
        """Added to her pose while she's held and while she settles after."""
        g = max(0.0, min(1.0, self.grip.value))
        now = self.clock() if now is None else now
        t = now - self.since
        follow = self.lag.value - self.swing.value              # how far her head / hair / legs trail behind
        speed = math.hypot(self._vel.x(), self._vel.y())
        lift = self.lift.value
        sway = math.sin(t * 2.1) * 0.5 + math.sin(t * 3.3 + 1.2) * 0.25      # legs idly dangling
        moves = {
            "arms": -self.swing.value * 0.75 * g,                # arms hang with gravity...
            "spread": 7.0 * g + 4.0 * max(0.0, lift) * g,        # ...a little out from her sides
            "dangle": (-self.swing.value * 0.55 + follow * 0.9 + 3.0 * sway) * g,
            "stride": 0.12 * sway * g,
            "tilt": (follow * 0.6 - 2.5 * lift) * g,
            "lean": (-follow * 0.004 + 0.012 * lift) * g,
            "hair_drag": max(-1.0, min(1.0, -self.swing.value / self.MAX_SWING * 0.8 + follow / 20.0)) * g,
            "energy": (0.35 + 0.65 * min(1.0, speed / 1800.0 + abs(lift) * 0.5)) * g,
            "squat": max(0.0, 0.1 * g + 0.22 * max(0.0, lift) * g) + 0.16 * max(0.0, self.settle.value),
            "sweep": (0.12 + 0.25 * min(1.0, speed / 2000.0)) * g,
            "look_x": max(-1.0, min(1.0, self._vel.x() / 900.0)) * g,
            "look_y": (0.35 + max(-0.6, min(0.6, self._vel.y() / 1200.0))) * g,
        }
        return moves
