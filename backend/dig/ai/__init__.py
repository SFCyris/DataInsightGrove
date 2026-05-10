"""AI assistant — pluggable LLM provider for DIG.

The provider is a thin OpenAI-compatible HTTP client. Every supported
endpoint (Ollama, llama.cpp, vLLM, Anthropic via /v1/messages, OpenAI,
Groq, OpenRouter, Together, …) speaks the same chat-completions schema,
so DIG only needs one client implementation.

Settings (provider, endpoint, model, api_key) live in the existing
key/value `settings` table. See dig/api/settings.py for the allow-list.

Use cases live in dig/ai/features.py — explain_pipeline, fix_expression,
generate_connector. They build prompts, call the client, parse the
response. Each is a pure function; the API endpoints in
dig/api/ai.py wire them up.

Internal-only design notes maintained outside the public tree.
"""
