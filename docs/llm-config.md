# LLM configuration

`LLM_PROVIDER` selects which provider generates the narrative. Swapping
providers is a config change, not a code change.

## OpenAI

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Uses `gpt-4o-mini`.

## Anthropic

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Uses `claude-sonnet-4-5`.

## Ollama (fully local, zero internet traffic)

```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
```

Start the optional `ollama` profile so the container pulls a small local
model on boot:

```bash
docker compose --profile ollama up --build
```

With `LLM_PROVIDER=ollama`, no request ever leaves your network — useful for
regulated environments where ticket data (even after PII stripping) shouldn't
touch a third-party API.

## Testing a provider before saving

The config UI's LLM form has a **Test connection** button that fires a
minimal real request (5–8 tokens) against the provider you've selected, so
you catch a bad key before scheduling a report against it.

## Token budget

`MAX_TOKENS_OUTPUT` (default `800`) caps how long the generated narrative can
be, regardless of provider.
