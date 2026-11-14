"""Capri mods: skins, cosmetics, animation / expression packs, personalities, behaviour, greetings & reactions,
sound packs - shared as .capri-mod files (a zip with a mod.json).

Mods are DATA only: pictures, sounds and JSON. Nothing in a mod is ever run as code, so installing one (from the
store or a file someone sent you) can't do anything to your PC beyond changing how Capri looks, sounds and talks.
Every mod is checked before it's installed (mods/manifest.py): what it says it is, its files, its size, and that it
fits this version of Capri.

    manifest.py   - mod.json: what a mod is, and the checks
    manager.py    - installed mods: install / uninstall / enable / disable / import / export / update
    store.py      - the mod store: the mods that come with Capri + the online list (ratings, previews, updates)
    effects.py    - what the enabled mods change, read by the rest of Capri
    sounds.py     - sound-pack playback
    creator.py    - "Make a mod": a ready-to-edit template for each kind of mod
"""
