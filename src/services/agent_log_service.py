import os
import sys
import traceback
import json
from datetime import datetime
from contextvars import ContextVar
from typing import List, Dict, Any, Optional
import functools
from src.models.persistence import PersistenceManager
from src.config import settings

# Thread-safe breadcrumb path
_BREADCRUMBS: ContextVar[List[str]] = ContextVar("breadcrumbs", default=[])

class AgentLogService:
    def __init__(self, error_file: str = "AGENT_ERROR.md", history_file: str = "logs/agent_history.md"):
        self.error_file = error_file
        self.history_file = history_file
        self.persistence = PersistenceManager(settings.DB_PATH)
        os.makedirs("logs", exist_ok=True)

    def log_thought(self, signal_id: str, bull: str, bear: str, news: str, verdict: str, shap: Dict = None, fundamental_impact: float = None, sec_ref: str = None):
        """Persists the adversarial thought process to the Thought Journal (SQLite)."""
        self.persistence.log_thought(
            signal_id=signal_id,
            bull=bull,
            bear=bear,
            news=news,
            verdict=verdict,
            shap=shap,
            fundamental_impact=fundamental_impact,
            sec_ref=sec_ref
        )
        print(f"AGENT_LOGGER: Thought Journal persisted for signal {signal_id}")

    def push_breadcrumb(self, name: str):
        """Pushes a step onto the current execution path."""
        crumbs = _BREADCRUMBS.get().copy()
        crumbs.append(name)
        _BREADCRUMBS.set(crumbs)

    def pop_breadcrumb(self):
        """Pops the last step from the execution path."""
        crumbs = _BREADCRUMBS.get().copy()
        if crumbs:
            crumbs.pop()
        _BREADCRUMBS.set(crumbs)

    def get_path(self) -> str:
        """Returns the current execution path string."""
        return " -> ".join(_BREADCRUMBS.get())

    def capture_error(self, e: Exception, context: Optional[Dict[str, Any]] = None):
        """Captures an error and generates the agent-friendly Markdown report."""
        now = datetime.now().isoformat()
        
        # Priority: 1. Path attached to exception, 2. Current path, 3. Unknown
        path = getattr(e, "__agent_path__", self.get_path())
        tb = traceback.format_exc()
        
        # Scrub sensitive data from context
        clean_context = self._scrub_dict(context) if context else {}
        
        remediation = self._get_remediation_hints(e, path)
        
        report = f"""# 🚨 Agent Assistance Required
**Timestamp**: `{now}`
**Error Type**: `{type(e).__name__}`
**Message**: {str(e)}

## 🛤️ Execution Path
`{path if path else "Unknown (Root)"}`

## 🔍 Context Snapshot
```json
{json.dumps(clean_context, indent=2)}
```

## 🛠️ Remediation Handbook
{remediation}

## 📄 Raw Traceback
```python
{tb}
```
"""
        # Write to immediate error file
        with open(self.error_file, "w") as f:
            report_with_instr = report + "\n\n**Instruction**: Read the sections above, identify the bug in the code, and use the suggested remediation steps to fix it."
            f.write(report_with_instr)
            
        # Append to history
        with open(self.history_file, "a") as f:
            f.write(f"\n---\n{report}\n")
            
        print(f"AGENT_LOGGER: Error report generated at {self.error_file}")

    def _scrub_dict(self, d: Any) -> Any:
        """Recursively removes sensitive keys from dictionaries."""
        if not isinstance(d, dict):
            return d
        
        sensitive_keys = {"api_key", "token", "secret", "password", "key"}
        scrubbed = {}
        for k, v in d.items():
            if any(sk in k.lower() for sk in sensitive_keys):
                scrubbed[k] = "[REDACTED]"
            elif isinstance(v, dict):
                scrubbed[k] = self._scrub_dict(v)
            else:
                scrubbed[k] = v
        return scrubbed

    def _get_remediation_hints(self, e: Exception, path: str) -> str:
        """Generates dynamic hints based on the error and path."""
        hints = []
        err_msg = str(e).lower()
        
        if "timeout" in err_msg or "connection" in err_msg:
            hints.append("- [ ] Check network connectivity or API status.")
            hints.append("- [ ] Increase timeout settings in `src/config.py`.")
        elif "no such column" in err_msg or "table" in err_msg:
            hints.append("- [ ] Database schema mismatch detected.")
            hints.append("- [ ] Run `python scripts/init_db.py` or create a migration script.")
        elif "module not found" in err_msg:
            hints.append("- [ ] Missing dependency. Add the library to `requirements.txt`.")
            hints.append("- [ ] Run `pip install [module]` inside the environment.")
        elif "keyerror" in err_msg:
            hints.append("- [ ] Check if the expected key exists in the data source (SEC/Polygon).")
            hints.append("- [ ] Add a safety check or default value using `.get()`.")
        else:
            hints.append("- [ ] Analyze the raw traceback to find the failing line.")
            hints.append("- [ ] Use `read_file` to inspect the logic at the end of the execution path.")

        return "\n".join(hints)

def agent_trace(name: str):
    """Decorator to automatically trace execution steps."""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            agent_logger.push_breadcrumb(name)
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if not hasattr(e, "__agent_path__"):
                    setattr(e, "__agent_path__", agent_logger.get_path())
                raise
            finally:
                agent_logger.pop_breadcrumb()

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            agent_logger.push_breadcrumb(name)
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if not hasattr(e, "__agent_path__"):
                    setattr(e, "__agent_path__", agent_logger.get_path())
                raise
            finally:
                agent_logger.pop_breadcrumb()

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

# Global instance
import asyncio
agent_logger = AgentLogService()
