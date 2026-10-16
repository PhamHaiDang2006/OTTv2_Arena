class RunnerError(Exception):
    """Base class for errors safe to report through a worker callback."""


class JobValidationError(RunnerError):
    """The queued payload does not satisfy contract v1."""


class BotBuildError(RunnerError):
    """A source/archive/compiler failure attributable to a submission."""


class InfrastructureError(RunnerError):
    """An unavailable or broken worker integration, not a bot loss."""


class LeaseLost(InfrastructureError):
    """This worker no longer owns the job lease."""


class UnsupportedLanguage(InfrastructureError):
    """Language has not been enabled in the deployed worker configuration."""
