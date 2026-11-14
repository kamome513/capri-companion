# Making Capri mods

A mod is a folder (or a `.capri-mod` file - a zip of that folder) with a **mod.json** and its pictures and
sounds. Mods are data only: pictures (.png .jpg .webp), sounds (16-bit .wav) and text. **Nothing in a mod is ever
run as a program**, so mods are safe to share.

## Quick start
1. **Make mods** tab -> pick a kind, type a name, press **Make a mod**. A folder opens with a working example.
2. Edit **mod.json** and the files.
3. **Check a mod folder...** tells you exactly what's wrong, if anything.
4. **Try a mod folder on Capri...** installs it so you can see it.
5. **Installed** tab -> **Export to share...** gives you a `.capri-mod` file. Anyone can install it with
   **Import mod...**, or by dropping it on Capri.

## mod.json - every mod
```json
{
  "id": "my-mod", "name": "My Mod", "version": "1.0.0", "author": "you",
  "type": "skin", "description": "What it does.", "tags": ["blue"],
  "capri": ">=2.4.0", "preview": "preview.png", "conflicts": []
}
```
- **id**: 2-40 lower-case letters, digits, `-` `_` `.`  (unique: a newer version replaces the old one)
- **capri**: the versions it works with, like `>=2.4.0` or `>=2.4,<3`
- **preview**: a picture shown in the store and the mods list (256x256 looks best)

## The kinds of mods
**skin** - her colours: `"palette": {"hair": "#33e0ff", "accent": "#ff3fbf", "outline": "#2a6cff", "body": "#0e1626", "eyes": "#ffffff"}`
(any of them). One skin at a time.

**cosmetic** - pictures on her head, moving with her:
`"items": [{"image": "ears.png", "slot": "ears", "x": 0.5, "y": 0.0, "width": 1.3, "layer": "back"}]`
- slot: ears, hair, hat, face, neck, back, other (one cosmetic per slot - stack different slots)
- x / y: where the picture's middle goes, in head widths / heights from her head's top-left corner
- width: in head widths. layer: back (behind her) or front.

**animations** - moves she does by herself now and then (or "do a dance"):
`"animations": [{"name": "Hip sway", "seconds": 1.6, "loop": 3, "keys": [{"t": 0, "lean": 0}, {"t": 0.5, "lean": 0.1, "eyes": "happy"}, {"t": 1, "lean": 0}]}]`
Pose values (-1.5 to 1.5): lean, reach, sweep, squat, wave, wag, stride, blink, mouth, energy. eyes: "", "happy", "wink".
`t` goes from 0 to 1 over `seconds`. Shown in her full-body style.

**personality** - a new personality in her list:
`"personality": {"key": "noir", "label": "Noir", "prompt": "Personality: ...", "remarks": ["Case closed."], "chance": 0.3, "intro": "...", "emotion": "smirk"}`

**lines** - greetings and reactions mixed in with hers:
`"lines": {"greet": [...], "pat": [...], "poke": [...], "ouch": [...], "hello": [...], "bye": [...]}`

**sounds** - sound effects: `"sounds": {"wake": "wake.wav", "done": "done.wav", "error": "e.wav", "pat": "p.wav", "throw": "t.wav", "greet": "g.wav", "click": "c.wav"}`

**behaviour** - her habits while it's on (your own settings come back when it's off):
`"settings": {"roaming": true, "idle_acts": true, "glitches": 240, "nap_minutes": 20}`
Allowed: roaming, idle_acts, idle_animation, glitches, throwable, head_pats, music_dance, slang,
speech_expression, speech_speed, speech_pitch, speech_style, nap_minutes, watch_every, game_hype_encourage.

## Limits
Up to 60 files and 20 MB. Pictures up to 2 MB each, sounds up to 3 MB. No other file types.
