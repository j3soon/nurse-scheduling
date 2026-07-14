"""Application errors raised by server services and persistence adapters."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


class ServerApplicationError(Exception):
    """Base class for errors translated by the HTTP adapter."""

    code = "server_error"
    """Stable machine-readable error code returned by the HTTP API."""


class JobNotFoundError(ServerApplicationError):
    """The requested job does not exist or is no longer retained."""

    code = "job_not_found"


class JobInputNotFoundError(ServerApplicationError):
    """A job exists but its submitted input is unavailable."""

    code = "job_input_not_found"


class JobArtifactNotFoundError(ServerApplicationError):
    """The requested named artifact does not exist for a job."""

    code = "job_artifact_not_found"


class JobArtifactNotReadyError(ServerApplicationError):
    """A job has not produced a downloadable artifact."""

    code = "job_artifact_not_ready"


class JobOperationNotAllowedError(ServerApplicationError):
    """Lifecycle state or solver capability disallows a requested operation."""

    code = "job_operation_not_allowed"


class JobOperationContentionError(ServerApplicationError):
    """Retryable store conflicts prevented a job operation from completing."""

    code = "job_operation_contention"


class JobCapacityError(ServerApplicationError):
    """The store cannot accept another job under its configured limits."""

    code = "job_capacity_exceeded"


class StoreWriteConflictError(Exception):
    """Internal signal that an atomic store write precondition no longer holds.

    `JobController` catches this error, re-reads current state, and retries the
    operation. It must not reach the HTTP adapter.
    """


class OptimizationExecutionError(Exception):
    """A scheduler result could not produce a normal optimization result."""

    def __init__(self, code: str, message: str):
        """Create an execution failure with a stable result code."""
        super().__init__(message)
        self.code = code
        """Machine-readable reason that optimization could not complete normally."""
