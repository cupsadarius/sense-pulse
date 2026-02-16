"""Docker Compose container runner."""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# Default timeout for ephemeral containers (seconds)
DEFAULT_TIMEOUT = 60


class DockerRunner:
    """Manages Docker Compose container lifecycle."""

    def __init__(self, project_name: str | None = None) -> None:
        self.project_name = project_name or os.environ.get("COMPOSE_PROJECT_NAME", "sense-pulse")
        self._running: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def running(self) -> set[str]:
        """Currently running containers."""
        return set(self._running)

    def _base_cmd(self) -> list[str]:
        """Base docker compose command with project name."""
        return ["docker", "compose", "-p", self.project_name]

    async def run_ephemeral(
        self,
        service: str,
        env: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> bool:
        """Run an ephemeral container via docker compose run --rm.

        Returns True on exit code 0, False otherwise.
        Prevents double-spawning the same service.
        """
        async with self._lock:
            if service in self._running:
                logger.warning("Service %s is already running, skipping", service)
                return False
            self._running.add(service)

        try:
            cmd = [*self._base_cmd(), "--profile", "poll", "run", "--rm"]

            if env:
                for key, val in env.items():
                    cmd.extend(["-e", f"{key}={val}"])

            cmd.append(service)

            logger.debug("Running: %s", " ".join(cmd))
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error("Service %s timed out after %.0fs", service, timeout)
                proc.kill()
                await proc.wait()
                return False

            if proc.returncode == 0:
                logger.info("Service %s completed successfully", service)
                return True
            else:
                logger.error(
                    "Service %s failed (exit %d)\nstdout: %s\nstderr: %s",
                    service,
                    proc.returncode,
                    stdout.decode() if stdout else "",
                    stderr.decode() if stderr else "",
                )
                return False
        finally:
            async with self._lock:
                self._running.discard(service)

    async def start_service(self, service: str) -> bool:
        """Start a long-running service via docker compose up -d.

        Returns True on success.
        """
        async with self._lock:
            if service in self._running:
                logger.warning("Service %s is already running, skipping start", service)
                return False
            self._running.add(service)

        try:
            cmd = [*self._base_cmd(), "--profile", "camera", "up", "-d", service]
            logger.debug("Running: %s", " ".join(cmd))
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                logger.info("Service %s started successfully", service)
                return True
            else:
                logger.error(
                    "Failed to start %s (exit %d)\nstdout: %s\nstderr: %s",
                    service,
                    proc.returncode,
                    stdout.decode() if stdout else "",
                    stderr.decode() if stderr else "",
                )
                # Remove from running since it failed to start
                async with self._lock:
                    self._running.discard(service)
                return False
        except Exception:
            async with self._lock:
                self._running.discard(service)
            raise

    async def stop_service(self, service: str) -> bool:
        """Stop a running service via docker compose stop.

        Returns True on success.
        """
        cmd = [*self._base_cmd(), "--profile", "camera", "stop", service]
        logger.debug("Running: %s", " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        async with self._lock:
            self._running.discard(service)

        if proc.returncode == 0:
            logger.info("Service %s stopped successfully", service)
            return True
        else:
            logger.error(
                "Failed to stop %s (exit %d)\nstdout: %s\nstderr: %s",
                service,
                proc.returncode,
                stdout.decode() if stdout else "",
                stderr.decode() if stderr else "",
            )
            return False
