"""AI-backed user-facing features.

Each module in this package is one feature: it builds a prompt, calls
the configured LLM via dig.ai.client, and returns a structured result
the API endpoint can serialize. Every feature is small + pure so it can
be tested without an LLM (mock the chat() call).
"""
