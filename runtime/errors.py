# Runtime Framework — Error Taxonomy
#
# All runtime errors are classified so the Harness can make
# intelligent recovery decisions.

from typing import Optional


class AgentError(Exception):
    """Base error for all agent runtime errors."""

    def __init__(self, message: str, context: Optional[dict] = None):
        self.message = message
        self.context = context or {}
        super().__init__(self.message)


class RecoverableError(AgentError):
    """Error that can be retried (rate limit, transient failure, timeout).

    The Harness will retry operations that raise RecoverableError
    according to the configured retry policy.
    """

    def __init__(
        self,
        message: str,
        retry_after: Optional[float] = None,
        context: Optional[dict] = None,
    ):
        super().__init__(message, context)
        self.retry_after = retry_after


class FatalError(AgentError):
    """Error that cannot be recovered.

    Missing API tokens, invalid configuration, or unrecoverable
    system errors. The Harness will fail immediately.
    """
    pass


class TimeoutError(AgentError):
    """Operation exceeded its time limit.

    Can be retried once. If it times out again, treat as FatalError.
    """
    pass


class SkillError(AgentError):
    """Error during skill execution.

    Skills raise this for domain-specific failures.
    The Harness logs the error and continues (best-effort).
    """
    pass


class ToolError(AgentError):
    """Error during tool invocation.

    Tool errors are classified by the ToolRegistry:
    - Recoverable (rate limit, timeout): wrapped as RecoverableError
    - Non-recoverable (invalid args): propagated as-is
    """

    def __init__(
        self,
        message: str,
        tool_name: str,
        recoverable: bool = False,
        context: Optional[dict] = None,
    ):
        super().__init__(message, context)
        self.tool_name = tool_name
        self.recoverable = recoverable
