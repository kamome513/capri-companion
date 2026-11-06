# Give her an ElevenLabs voice

[ElevenLabs](https://elevenlabs.io) has very natural online voices. It needs an internet connection, and
only the text of what she says is sent to ElevenLabs (never your microphone).

## 1. Make an account and a key

1. Sign up at [elevenlabs.io](https://elevenlabs.io) (there's a free plan with a monthly amount of credits).
2. Open **Developers** → **API Keys** (or click your profile picture → **API Keys**).
3. Click **Create API Key**. If it asks about permissions, give it access to **Text to Speech** (and
   **Voices: read**). Copy the key. It's only shown once.

## 2. Pick a voice

1. In ElevenLabs open **Voices** (**My Voices**, or the **Voice Library** to find more).
2. On the voice you like, open its menu (the **⋯** button) → **Copy voice ID**. A voice ID is 20 letters and
   numbers, like `21m00Tcm4TlvDq8ikWAM`. Pasting the voice's link works too.
3. Voices from the Voice Library: click **Add to my voices** first.

## 3. Put it in Capri

1. Right-click her → **Settings...** → **Assistant** → **Capri's voice**.
2. Paste the key into **ElevenLabs key**. She switches to ElevenLabs and says a test line.
3. Paste the voice ID into **ElevenLabs voice** (leave it empty for a standard voice).
4. Make sure **Voice** says *ElevenLabs*, and press **Test voice**.

## If it doesn't work

When ElevenLabs refuses, she uses her normal voice for that line and **Test voice** shows ElevenLabs'
reason. Common ones:

| What you see | What to do |
|---|---|
| The key doesn't work (401) | Copy the key again. If you made a restricted key, give it *Text to Speech* access. Also check your credits |
| "Voice not found" / no voice with that ID | Copy the voice ID again (not the voice's name). Library voices need **Add to my voices** first |
| Your plan can't use that voice | Free plans can't use some Voice Library voices through apps. She uses ElevenLabs' standard voice instead; pick one of your own voices, or upgrade |
| Out of credit / too many requests (402, 429) | You've used this month's credits. They refill monthly, or switch back to her own voice |
| Error 400 | Since 2.3.2 she repairs the request by herself (without the speed, then their other models). If it still fails, the reason is shown: usually the voice ID |

ElevenLabs voices speak every language Capri knows.
