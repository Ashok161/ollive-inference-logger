# inference-sdk

Lightweight auto-instrumenting wrapper for LLM calls.

- Multi-provider: Groq, OpenAI, Anthropic, Google Gemini
- Streaming and non-streaming
- Captures latency, tokens, errors, session IDs, I/O previews
- Fire-and-forget async log shipping to an ingestion endpoint