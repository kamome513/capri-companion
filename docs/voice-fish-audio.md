# Give her a Fish Audio voice

[Fish Audio](https://fish.audio) has thousands of community voices, including anime and game-style ones.
It needs an internet connection, and only the text of what she says is sent (never your microphone).

## 1. Make an account and a key

1. Sign up at [fish.audio](https://fish.audio).
2. Open the **API** page (your profile menu → **API**, or [fish.audio/app/api-keys](https://fish.audio/app/api-keys))
   and create an **API key**. Copy it.
3. The API uses its own credit balance (separate from a website subscription). Check you have some on the
   API page.

## 2. Pick a voice

1. Browse the voices on [fish.audio](https://fish.audio) and open one you like.
2. Copy its link from your browser's address bar. It looks like `https://fish.audio/m/7f92f8afb8ec43bf81429cc1c9199cb1/`.
   (The bare ID - the long part after `/m/` - works too.)

## 3. Put it in Capri

1. Right-click her → **Settings...** → **Assistant** → **Capri's voice**.
2. Paste the key into **Fish Audio key**. She switches to Fish Audio and says a test line.
3. Paste the voice link into **Fish Audio voice** (empty = Fish's default voice).
4. Make sure **Voice** says *Fish Audio*, and press **Test voice**.

## If it doesn't work

When Fish Audio refuses, she uses her normal voice for that line and **Test voice** shows the reason.

| What you see | What to do |
|---|---|
| The key doesn't work (401) | Copy the key again from the API page |
| Out of credit (402 / 403) | Add API credit on Fish Audio's API page |
| It didn't take that voice ID (400 / 404) | Copy the voice's link again; private voices only work with their owner's key |
| Too many requests (429) | Wait a moment |

The **Speed** slider changes Fish Audio's speed too (the middle is the voice as it is). Fish Audio voices
speak every language Capri knows.
