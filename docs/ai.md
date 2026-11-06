# Set up her AI

Commands ("open Discord", "pause") always work without an AI. An AI lets her **chat about anything**,
understand odd ways of saying things, answer in your language, and look at your screen.

Open Settings → **Assistant** → **AI conversation**, tick **Chatbot**, then pick one under **AI**.
Paste the key into **API key** (she checks it straight away) and press **Test AI**.

## Free options

### Google Gemini (free, easiest)
1. Go to [aistudio.google.com](https://aistudio.google.com) and sign in with a Google account.
2. Click **Get API key** → **Create API key** and copy it.
3. In Capri pick **Google Gemini** and paste the key.

### Groq (free tier, very fast)
1. Sign up at [console.groq.com](https://console.groq.com) → **API Keys** → **Create API Key**.
2. Pick **Groq** in Capri and paste the key.

### NVIDIA (free credits)
1. Sign in at [build.nvidia.com](https://build.nvidia.com), pick any model, click **Get API Key** (it starts
   with `nvapi-`).
2. Pick **NVIDIA** in Capri and paste it.

### Ollama (free, runs on your own PC)
Nothing leaves your PC, but it needs a fairly strong PC (8 GB of RAM or more; a graphics card helps).
1. Click **Set up Ollama for me** (or say **"Hey Capri, set up your brain"**). She installs Ollama and
   downloads a chat model that suits your PC (about 3 GB, a few minutes).
2. For "what do you see?" and letting her play games she needs a model that can see pictures. Say
   **"Hey Capri, give yourself eyes"** and she downloads one (gemma3, about 3 GB, once).

## Paid options

| AI | Where to get a key |
|---|---|
| ChatGPT (OpenAI) | [platform.openai.com](https://platform.openai.com) → API keys (needs credit on the account; a ChatGPT Plus subscription doesn't include API use) |
| Claude (Anthropic) | [console.anthropic.com](https://console.anthropic.com) → API keys. Paste it into **Claude API key** |
| OpenRouter | [openrouter.ai](https://openrouter.ai) → Keys (hundreds of models, some free) |
| DeepSeek, Mistral, xAI (Grok) | Their developer consoles → API keys |
| LM Studio | Runs on your PC: start its local server, then pick **LM Studio** (no key) |

**Model:** leave it empty for the one shown, or press **Show my models** and pick one.

## When something goes wrong

- **Last try** (under the AI box) always says what happened the last time she asked the AI.
- **"Error 400" / "it turned that down":** she already retries by herself in a few different ways. If it
  keeps happening, the reason she reads out says what the service didn't like. Usually it's a model that
  can't see pictures (for "what do you see?") or can't use her tools: pick another model.
- **"Model doesn't exist":** press **Show my models** and pick one from the list.
- **401 / key doesn't work:** copy the key again (no spaces), and check the account has credit.

## Privacy

Only what you say to her goes to the AI, and personal things (your files, your Windows user name) are left
out. With Ollama or LM Studio nothing leaves your PC. "What do you see?" sends a picture of your screen to
the AI you picked; she won't look at password managers, banks, sign-in pages or private windows.
