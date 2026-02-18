# LangTARS Plugin for LangBot
# Control your Mac through IM messages (like OpenClaw)

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
from pathlib import Path
from typing import Any

from langbot_plugin.api.definition.plugin import BasePlugin


class LangTARSPlugin(BasePlugin):
    """LangTARS Plugin - Control your Mac through IM messages (like OpenClaw)"""

    # Safety constants
    DANGEROUS_PATTERNS = [
        r'rm\s+-rf\s+/',
        r'mkfs',
        r'dd\s+if=/dev/zero',
        r':(){:|:&};:',
        r'chmod\s+777\s+/',
        r'sudo\s+.*',
        r'>\s*/dev/',
        r'&\s*>/dev/',
    ]

    # Default command whitelist (safe commands)
    DEFAULT_WHITELIST = [
        'ls', 'pwd', 'echo', 'cat', 'head', 'tail', 'grep', 'find',
        'ps', 'top', 'whoami', 'date', 'time', 'hostname', 'uname',
        'mkdir', 'touch', 'cp', 'mv', 'rm',  # rm is allowed but restricted
        'which', 'type', 'file', 'wc', 'sort', 'uniq', 'cut',
        'tr', 'sed', 'awk', 'printf', 'clear',
    ]

    def __init__(self):
        super().__init__()
        self.config: dict[str, Any] = {}
        self._workspace_path: Path | None = None
        self._allowed_users: set[str] = set()
        self._command_whitelist: list[str] = []
        self._initialized = False

    def get_config(self) -> dict[str, Any]:
        """Get the config of the plugin."""
        return self.config

    async def initialize(self) -> None:
        """Initialize the plugin."""
        # Load configuration
        self.config = self.config or {}

        # Get workspace path
        workspace = self.config.get('workspace_path', '~/.langtars')
        self._workspace_path = Path(workspace).expanduser()
        self._workspace_path.mkdir(parents=True, exist_ok=True)

        # Get allowed users
        self._allowed_users = set(self.config.get('allowed_users', []))

        # Get command whitelist
        self._command_whitelist = self.config.get('command_whitelist', [])

        self._initialized = True

    def __del__(self) -> None:
        """Cleanup on plugin termination."""
        pass

    # ========== Safety Methods ==========

    def is_user_allowed(self, user_id: str) -> bool:
        """Check if a user is allowed to control this Mac."""
        if not self._allowed_users:
            return True  # No restrictions if no users configured
        return user_id in self._allowed_users

    def is_command_allowed(self, command: str) -> bool:
        """Check if a shell command is allowed."""
        if not self._command_whitelist:
            return True  # No whitelist means all commands allowed (with dangerous pattern check)
        # Check if command starts with any whitelisted command
        cmd_base = command.strip().split()[0] if command.strip() else ''
        return cmd_base in self._command_whitelist

    def check_dangerous_pattern(self, command: str) -> tuple[bool, str]:
        """Check for dangerous patterns in command."""
        import re
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return True, f"Dangerous pattern detected: {pattern}"
        return False, ""

    # ========== Shell Execution ==========

    async def run_shell(
        self,
        command: str,
        timeout: int = 30,
        working_dir: str | None = None,
    ) -> dict[str, Any]:
        """Execute a shell command safely."""
        # Safety checks
        if not self.config.get('enable_shell', True):
            return {
                'success': False,
                'error': 'Shell execution is disabled',
                'stdout': '',
                'stderr': '',
                'returncode': -1,
            }

        # Check if command is allowed
        if not self.is_command_allowed(command):
            return {
                'success': False,
                'error': 'Command not in whitelist',
                'stdout': '',
                'stderr': '',
                'returncode': -1,
            }

        # Check for dangerous patterns
        is_dangerous, danger_msg = self.check_dangerous_pattern(command)
        if is_dangerous:
            return {
                'success': False,
                'error': f'Dangerous command blocked: {danger_msg}',
                'stdout': '',
                'stderr': '',
                'returncode': -1,
            }

        # Restrict working directory
        if working_dir:
            working_path = Path(working_dir).expanduser()
            try:
                working_path = working_path.resolve()
                workspace_path = self._workspace_path.resolve()
                # Allow subdirectories of workspace
                if not str(working_path).startswith(str(workspace_path)):
                    working_path = workspace_path
            except Exception:
                working_path = self._workspace_path
        else:
            working_path = self._workspace_path

        # Execute command
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(working_path),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                return {
                    'success': False,
                    'error': f'Command timed out after {timeout}s',
                    'stdout': '',
                    'stderr': '',
                    'returncode': -1,
                }

            return {
                'success': process.returncode == 0,
                'stdout': stdout.decode('utf-8', errors='replace'),
                'stderr': stderr.decode('utf-8', errors='replace'),
                'returncode': process.returncode,
                'error': '',
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'stdout': '',
                'stderr': '',
                'returncode': -1,
            }

    # ========== Process Management ==========

    async def list_processes(
        self,
        filter_pattern: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List running processes."""
        if not self.config.get('enable_process', True):
            return {
                'success': False,
                'error': 'Process management is disabled',
                'processes': [],
            }

        # Get process list using ps
        if filter_pattern:
            command = f'ps aux | grep -E "{filter_pattern}" | grep -v grep | head -n {limit}'
        else:
            command = f'ps aux | head -n {limit + 1}'

        result = await self.run_shell(command)

        if not result['success']:
            return result

        processes = []
        for line in result['stdout'].strip().split('\n'):
            if not line:
                continue
            parts = line.split(None, 10)
            if len(parts) >= 11:
                processes.append({
                    'user': parts[0],
                    'pid': parts[1],
                    'cpu': parts[2],
                    'mem': parts[3],
                    'command': parts[10] if len(parts) > 10 else parts[-1],
                })

        return {
            'success': True,
            'processes': processes,
            'count': len(processes),
        }

    async def kill_process(
        self,
        target: str,
        signal: str = 'TERM',
        force: bool = False,
    ) -> dict[str, Any]:
        """Kill a process by PID or name."""
        if not self.config.get('enable_process', True):
            return {
                'success': False,
                'error': 'Process management is disabled',
            }

        # Determine if target is PID or name
        is_pid = target.isdigit()

        # Build kill command
        if is_pid:
            kill_signal = 'KILL' if force else signal
            command = f'kill -{kill_signal} {target}'
        else:
            # Kill by name - find PIDs first
            find_cmd = f'pgrep -f "{target}"'
            if force:
                command = f'pkill -9 "{target}"'
            else:
                command = f'pkill -TERM "{target}"'

        result = await self.run_shell(command)

        if result['success']:
            return {
                'success': True,
                'message': f'Process {"PID " + target if is_pid else target} terminated',
            }
        else:
            return {
                'success': False,
                'error': result.get('stderr', 'Process not found'),
            }

    # ========== File Operations ==========

    async def read_file(self, path: str) -> dict[str, Any]:
        """Read file content."""
        if not self.config.get('enable_file', True):
            return {
                'success': False,
                'error': 'File operations are disabled',
                'content': '',
            }

        # Resolve path within workspace
        file_path = self._resolve_path(path)
        if not file_path:
            return {
                'success': False,
                'error': 'Access denied: path outside workspace',
                'content': '',
            }

        try:
            content = file_path.read_text(encoding='utf-8')
            return {
                'success': True,
                'path': str(file_path),
                'content': content,
                'size': len(content),
            }
        except UnicodeDecodeError:
            # Try binary read
            try:
                content = file_path.read_bytes()
                return {
                    'success': True,
                    'path': str(file_path),
                    'content': f'[Binary file, {len(content)} bytes]',
                    'size': len(content),
                    'is_binary': True,
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'content': '',
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'content': '',
            }

    async def write_file(
        self,
        path: str,
        content: str,
        mode: str = 'w',
    ) -> dict[str, Any]:
        """Write content to a file."""
        if not self.config.get('enable_file', True):
            return {
                'success': False,
                'error': 'File operations are disabled',
            }

        # Resolve path within workspace
        file_path = self._resolve_path(path)
        if not file_path:
            return {
                'success': False,
                'error': 'Access denied: path outside workspace',
            }

        try:
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if mode == 'a':
                file_path.append_text(content, encoding='utf-8')
            else:
                file_path.write_text(content, encoding='utf-8')

            return {
                'success': True,
                'path': str(file_path),
                'message': 'File written successfully',
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
            }

    async def list_directory(
        self,
        path: str = '.',
        show_hidden: bool = False,
    ) -> dict[str, Any]:
        """List directory contents."""
        if not self.config.get('enable_file', True):
            return {
                'success': False,
                'error': 'File operations are disabled',
                'items': [],
            }

        # Resolve path within workspace
        dir_path = self._resolve_path(path)
        if not dir_path:
            return {
                'success': False,
                'error': 'Access denied: path outside workspace',
                'items': [],
            }

        try:
            items = []
            for item in dir_path.iterdir():
                if not show_hidden and item.name.startswith('.'):
                    continue
                items.append({
                    'name': item.name,
                    'type': 'directory' if item.is_dir() else 'file',
                    'size': item.stat().st_size if item.is_file() else 0,
                })

            return {
                'success': True,
                'path': str(dir_path),
                'items': sorted(items, key=lambda x: (x['type'], x['name'])),
                'count': len(items),
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'items': [],
            }

    async def search_files(
        self,
        pattern: str,
        path: str = '.',
        recursive: bool = True,
    ) -> dict[str, Any]:
        """Search for files matching a pattern."""
        if not self.config.get('enable_file', True):
            return {
                'success': False,
                'error': 'File operations are disabled',
                'files': [],
            }

        # Resolve path within workspace
        search_path = self._resolve_path(path)
        if not search_path:
            return {
                'success': False,
                'error': 'Access denied: path outside workspace',
                'files': [],
            }

        try:
            files = []
            if recursive:
                for item in search_path.rglob(pattern):
                    if item.is_file():
                        files.append(str(item))
            else:
                for item in search_path.glob(pattern):
                    if item.is_file():
                        files.append(str(item))

            return {
                'success': True,
                'path': str(search_path),
                'pattern': pattern,
                'files': files[:50],  # Limit results
                'count': len(files),
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'files': [],
            }

    # ========== Application Control ==========

    async def open_app(
        self,
        app_name: str,
        url: str | None = None,
    ) -> dict[str, Any]:
        """Open an application or URL."""
        if not self.config.get('enable_app', True):
            return {
                'success': False,
                'error': 'App control is disabled',
            }

        try:
            if url:
                command = f'open "{url}"'
            else:
                command = f'open -a "{app_name}"'

            result = await self.run_shell(command)

            if result['success']:
                return {
                    'success': True,
                    'message': f'{"URL" if url else "Application"} opened: {app_name or url}',
                }
            else:
                return {
                    'success': False,
                    'error': result.get('stderr', f'Failed to open {app_name}'),
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
            }

    async def close_app(self, app_name: str, force: bool = False) -> dict[str, Any]:
        """Close an application."""
        if not self.config.get('enable_app', True):
            return {
                'success': False,
                'error': 'App control is disabled',
            }

        try:
            signal = '9' if force else 'TERM'
            command = f'pkill -{signal} "{app_name}"'

            result = await self.run_shell(command)

            if result['success']:
                return {
                    'success': True,
                    'message': f'Application closed: {app_name}',
                }
            else:
                return {
                    'success': False,
                    'error': result.get('stderr', f'Failed to close {app_name}'),
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
            }

    async def get_frontmost_app(self) -> dict[str, Any]:
        """Get the currently active application."""
        if not self.config.get('enable_app', True):
            return {
                'success': False,
                'error': 'App control is disabled',
            }

        try:
            command = '''osascript -e 'tell application "System Events" to get name of first process whose frontmost is true' 2>/dev/null || echo "Unknown"'''
            result = await self.run_shell(command)

            if result['success']:
                app_name = result['stdout'].strip()
                return {
                    'success': True,
                    'app_name': app_name or 'Unknown',
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to get frontmost app',
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
            }

    async def list_apps(self, limit: int = 20) -> dict[str, Any]:
        """List running applications."""
        if not self.config.get('enable_app', True):
            return {
                'success': False,
                'error': 'App control is disabled',
                'apps': [],
            }

        try:
            command = f'''osascript -e 'tell application "System Events" to get name of every process' 2>/dev/null | tr ',' '\\n' | head -n {limit}'''
            result = await self.run_shell(command)

            if result['success']:
                apps = [a.strip() for a in result['stdout'].strip().split('\n') if a.strip()]
                return {
                    'success': True,
                    'apps': apps,
                    'count': len(apps),
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to list applications',
                    'apps': [],
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'apps': [],
            }

    # ========== System Info ==========

    async def get_system_info(self) -> dict[str, Any]:
        """Get basic system information."""
        try:
            info = {
                'platform': platform.system(),
                'platform_version': platform.version(),
                'architecture': platform.architecture(),
                'processor': platform.processor(),
                'hostname': platform.node(),
                'python_version': platform.python_version(),
            }

            # Get uptime
            uptime_result = await self.run_shell('uptime')
            if uptime_result['success']:
                info['uptime'] = uptime_result['stdout'].strip()

            return {
                'success': True,
                'info': info,
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
            }

    # ========== Helper Methods ==========

    def _resolve_path(self, path: str) -> Path | None:
        """Resolve a path within the workspace, returns None if outside."""
        if not self._workspace_path:
            return None

        try:
            requested = Path(path).expanduser()

            # If it's an absolute path, check if it's within workspace
            if requested.is_absolute():
                resolved = requested.resolve()
                workspace = self._workspace_path.resolve()

                # Allow absolute paths that are within workspace
                if not str(resolved).startswith(str(workspace)):
                    return None
                return resolved
            else:
                # Relative path - make relative to workspace
                return (self._workspace_path / requested).resolve()
        except Exception:
            return None
