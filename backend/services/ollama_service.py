# backend/services/ollama_service.py
# ═══════════════════════════════════════════════════════════════════════════════
# OllamaProvider — wraps ollama.chat with timeout, retry, and logging.
# Model: llama3   (local execution, no API keys)
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations
import logging
import time

logger = logging.getLogger("ecopulse.ollama")

# ── Lazy import so the rest of EcoPulse still boots if ollama isn't installed ──
try:
    import ollama as _ollama
    _OLLAMA_AVAILABLE = True
except ImportError:
    _OLLAMA_AVAILABLE = False
    logger.warning("ollama package not installed — AI Copilot features disabled. Run: pip install ollama")


class OllamaProvider:
    """
    Thin wrapper around ollama.chat.

    Usage:
        provider = OllamaProvider()
        text = provider.generate("Explain this audit result: ...")
    """

    def __init__(
        self,
        model:       str   = "llama3",
        timeout:     float = 120.0,   # seconds per attempt
        max_retries: int   = 2,
        retry_delay: float = 3.0,     # seconds between retries
    ):
        self.model       = model
        self.timeout     = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate(self, prompt: str) -> str:
        """
        Send *prompt* to llama3 and return the response text.
        Raises RuntimeError on final failure.
        """
        if not _OLLAMA_AVAILABLE:
            raise RuntimeError(
                "ollama package not installed. Run: pip install ollama"
            )

        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 2):   # +2 = initial + retries
            try:
                logger.info("OllamaProvider.generate — attempt %d/%d", attempt, self.max_retries + 1)
                t0 = time.time()

                response = _ollama.chat(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"num_predict": 1500},  # cap output tokens
                )

                elapsed = time.time() - t0
                text = response["message"]["content"]
                logger.info("OllamaProvider: got %d chars in %.1fs", len(text), elapsed)
                return text

            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "OllamaProvider attempt %d failed: %s", attempt, exc
                )
                if attempt <= self.max_retries:
                    logger.info("Retrying in %.1fs…", self.retry_delay)
                    time.sleep(self.retry_delay)

        raise RuntimeError(
            f"Ollama failed after {self.max_retries + 1} attempts. "
            f"Is Ollama running? Last error: {last_exc}"
        )

    def is_available(self) -> bool:
        """Quick health-check — returns True if Ollama is reachable."""
        if not _OLLAMA_AVAILABLE:
            return False
        try:
            _ollama.list()
            return True
        except Exception:
            return False


# Module-level singleton — import this in other services
_provider = OllamaProvider()


def generate(prompt: str) -> str:
    """Convenience function using the shared provider instance."""
    return _provider.generate(prompt)


def is_available() -> bool:
    return _provider.is_available()