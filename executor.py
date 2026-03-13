"""Safe sandboxed Python executor.

Fixes applied vs. the AI-generated version:
  - FIX #5:  stdout/stderr captured via io.StringIO + redirect_*; real print() never leaks.
  - BUGFIX:  `from contextlib import ...` was placed AFTER first use — moved to top.
  - BUGFIX:  Redundant `io.TextIOWrapper(io.BytesIO())` wrapper removed (caused TypeError).
  - BUGFIX:  safe_globals['__builtins__'] iterated correctly (it's a dict, not globals()).
"""
import io
import signal
import time
from contextlib import redirect_stderr, redirect_stdout
from typing import Optional

import structlog
from restrictedpython import compile_restricted, safe_globals

from config import settings

logger = structlog.get_logger()

# Whitelist — only safe builtins allowed inside sandbox
_ALLOWED = {
    "None", "True", "False",
    "abs", "all", "any", "ascii", "bin", "bool", "bytes", "chr",
    "complex", "dict", "divmod", "enumerate", "filter", "float",
    "format", "frozenset", "getattr", "hasattr", "hash", "hex",
    "id", "int", "isinstance", "issubclass", "iter", "len", "list",
    "map", "max", "min", "next", "oct", "ord", "pow", "range",
    "repr", "reversed", "round", "set", "slice", "sorted", "str",
    "sum", "tuple", "type", "zip",
}

# restrictedpython provides safe_globals with __builtins__ as a dict
_SAFE_BUILTINS = {
    k: v for k, v in safe_globals.get("__builtins__", {}).items()
    if k in _ALLOWED
}
SANDBOX_GLOBALS: dict = {"__builtins__": _SAFE_BUILTINS}


class SafeExecutor:

    @staticmethod
    def execute(code: str, timeout: Optional[int] = None) -> str:
        timeout = timeout or settings.sandbox_timeout_seconds
        t0 = time.monotonic()

        # Compile
        try:
            bytecode = compile_restricted(code, "<sandbox>", "exec")
        except SyntaxError as exc:
            return f"❌ Syntax error at line {exc.lineno}: {exc.msg}"

        if getattr(bytecode, "errors", None):
            return "❌ Compile errors:\n" + "\n".join(bytecode.errors)

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        local_ns: dict = {}

        def _timeout_handler(signum, frame):
            raise TimeoutError

        old = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout)
        try:
            # BUGFIX: removed io.TextIOWrapper wrapper — redirect_stdout handles it
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                exec(bytecode, SANDBOX_GLOBALS.copy(), local_ns)  # noqa: S102
        except TimeoutError:
            return f"⏱️ Timeout after {timeout}s"
        except Exception as exc:
            logger.error("sandbox_runtime_error", error=str(exc))
            return f"❌ Runtime error: {type(exc).__name__}: {exc}"
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

        output = stdout_buf.getvalue()
        errors = stderr_buf.getvalue()
        max_c = settings.sandbox_max_output_chars

        if len(output) > max_c:
            output = output[:max_c] + "\n… [truncated]"

        elapsed = (time.monotonic() - t0) * 1000
        logger.info("sandbox_executed", ms=round(elapsed, 1))

        lines = [output.strip() or "✅ Executed (no output)"]
        if errors.strip():
            lines.append(f"⚠️ Stderr:\n{errors.strip()}")
        return "\n".join(lines)


executor = SafeExecutor()
