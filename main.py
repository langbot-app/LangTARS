# LangTARS Plugin for LangBot
# Control your Mac through IM messages (like OpenClaw)

from __future__ import annotations

import asyncio
import json
import os
import platform
from pathlib import Path
from typing import Any

from langbot_plugin.api.definition.components.command.command import Command, Subcommand
from langbot_plugin.api.definition.plugin import BasePlugin
from langbot_plugin.api.entities.builtin.command.context import ExecuteContext
from langbot_plugin.api.entities.builtin.command.context import CommandReturn


class LangTARS(Command, BasePlugin):
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

    def __init__(self):
        super().__init__()
        self.config: dict[str, Any] = {}
        self._workspace_path: Path | None = None
        self._allowed_users: set[str] = set()
        self._command_whitelist: list[str] = []
        self._initialized = False

        # Register subcommands
        self.registered_subcommands = {
            "info": Subcommand(
                subcommand=self.cmd_info,
                help="Get system information",
                usage="/tars info",
                aliases=["system", "sysinfo"],
            ),
            "shell": Subcommand(
                subcommand=self.cmd_shell,
                help="Execute shell command",
                usage="/tars shell <command>",
                aliases=["sh", "exec"],
            ),
            "ps": Subcommand(
                subcommand=self.cmd_ps,
                help="List running processes",
                usage="/tars ps [filter]",
                aliases=["processes", "process"],
            ),
            "ls": Subcommand(
                subcommand=self.cmd_ls,
                help="List directory contents",
                usage="/tars ls [path]",
                aliases=["dir", "list"],
            ),
            "cat": Subcommand(
                subcommand=self.cmd_cat,
                help="Read file content",
                usage="/tars cat <path>",
                aliases=["read", "view"],
            ),
            "kill": Subcommand(
                subcommand=self.cmd_kill,
                help="Kill a process",
                usage="/tars kill <pid|name>",
                aliases=["stop"],
            ),
            "open": Subcommand(
                subcommand=self.cmd_open,
                help="Open an application or URL",
                usage="/tars open <app_name|url>",
                aliases=["launch"],
            ),
            "close": Subcommand(
                subcommand=self.cmd_close,
                help="Close an application",
                usage="/tars close <app_name>",
                aliases=["quit"],
            ),
            "apps": Subcommand(
                subcommand=self.cmd_apps,
                help="List running applications",
                usage="/tars apps [limit]",
                aliases=["listapps"],
            ),
            "stop": Subcommand(
                subcommand=self.cmd_stop,
                help="Stop the current running task",
                usage="/tars stop",
                aliases=["pause", "cancel"],
            ),
            "status": Subcommand(
                subcommand=self.cmd_status,
                help="Check current task status",
                usage="/tars status",
                aliases=["running"],
            ),
            "help": Subcommand(
                subcommand=self.cmd_help,
                help="Show help",
                usage="/tars help",
                aliases=["?"],
            ),
            "*": Subcommand(
                subcommand=self.cmd_natural,
                help="Handle natural language commands",
                usage="Natural language input",
                aliases=[],
            ),
        }

    def get_config(self) -> dict[str, Any]:
        """Get the config of the plugin."""
        return self.config

    async def initialize(self) -> None:
        """Initialize the plugin."""
        self.config = self.config or {}
        workspace = self.config.get('workspace_path', '~/.langtars')
        self._workspace_path = Path(workspace).expanduser()
        self._workspace_path.mkdir(parents=True, exist_ok=True)
        self._allowed_users = set(self.config.get('allowed_users', []))
        self._command_whitelist = self.config.get('command_whitelist', [])
        self._initialized = True

    # ========== Safety Methods ==========

    def is_user_allowed(self, user_id: str) -> bool:
        """Check if a user is allowed to control this Mac."""
        if not self._allowed_users:
            return True
        return user_id in self._allowed_users

    def is_command_allowed(self, command: str) -> bool:
        """Check if a shell command is allowed."""
        if not self._command_whitelist:
            return True
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
        if not self.config.get('enable_shell', True):
            return {
                'success': False,
                'error': 'Shell execution is disabled',
                'stdout': '',
                'stderr': '',
                'returncode': -1,
            }

        if not self.is_command_allowed(command):
            return {
                'success': False,
                'error': 'Command not in whitelist',
                'stdout': '',
                'stderr': '',
                'returncode': -1,
            }

        is_dangerous, danger_msg = self.check_dangerous_pattern(command)
        if is_dangerous:
            return {
                'success': False,
                'error': f'Dangerous command blocked: {danger_msg}',
                'stdout': '',
                'stderr': '',
                'returncode': -1,
            }

        if working_dir:
            working_path = Path(working_dir).expanduser()
            try:
                working_path = working_path.resolve()
                workspace_path = self._workspace_path.resolve()
                if not str(working_path).startswith(str(workspace_path)):
                    working_path = self._workspace_path
            except Exception:
                working_path = self._workspace_path
        else:
            working_path = self._workspace_path

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

    # ========== Subcommand Implementations ==========

    async def cmd_info(self, context: ExecuteContext) -> CommandReturn:
        """Get system information."""
        try:
            info = {
                'platform': platform.system(),
                'platform_version': platform.version(),
                'architecture': platform.architecture(),
                'processor': platform.processor(),
                'hostname': platform.node(),
                'python_version': platform.python_version(),
            }

            uptime_result = await self.run_shell('uptime')
            if uptime_result['success']:
                info['uptime'] = uptime_result['stdout'].strip()

            return CommandReturn(text=json.dumps(info, indent=2, ensure_ascii=False))
        except Exception as e:
            return CommandReturn(text=f"Error: {str(e)}")

    async def cmd_shell(self, context: ExecuteContext) -> CommandReturn:
        """Execute a shell command."""
        command = " ".join(context.crt_params)
        if not command:
            return CommandReturn(text="Please provide a command")

        result = await self.run_shell(command)
        output = []
        if result['stdout']:
            output.append(result['stdout'])
        if result['stderr']:
            output.append(f"stderr: {result['stderr']}")
        if result.get('error'):
            output.append(f"Error: {result['error']}")

        text = "\n".join(output) if output else f"Return code: {result.get('returncode')}"
        return CommandReturn(text=text)

    async def cmd_ps(self, context: ExecuteContext) -> CommandReturn:
        """List running processes."""
        if not self.config.get('enable_process', True):
            return CommandReturn(text="Process management is disabled")

        filter_pattern = context.crt_params[0] if len(context.crt_params) > 0 else None
        limit = 20
        if len(context.crt_params) > 1:
            try:
                limit = int(context.crt_params[1])
            except ValueError:
                pass

        if filter_pattern:
            command = f'ps aux | grep -E "{filter_pattern}" | grep -v grep | head -n {limit}'
        else:
            command = f'ps aux | head -n {limit + 1}'

        result = await self.run_shell(command)
        if not result['success']:
            return CommandReturn(text=f"Error: {result.get('error', 'Unknown error')}")

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

        output = [f"{p['pid']:>6} {p['user']:>10} {p['cpu']:>5} {p['mem']:>5} {p['command']}" for p in processes[:limit]]
        return CommandReturn(text="PID      USER         CPU    MEM COMMAND\n" + "\n".join(output))

    async def cmd_ls(self, context: ExecuteContext) -> CommandReturn:
        """List directory contents."""
        if not self.config.get('enable_file', True):
            return CommandReturn(text="File operations are disabled")

        path = context.crt_params[0] if len(context.crt_params) > 0 else '.'
        dir_path = self._resolve_path(path)
        if not dir_path:
            return CommandReturn(text=f"Access denied: path outside workspace")

        try:
            items = []
            for item in dir_path.iterdir():
                if item.name.startswith('.'):
                    continue
                items.append(f"{'[DIR] ' if item.is_dir() else '[FILE]'} {item.name}")
            if not items:
                items = ["(empty)"]
            return CommandReturn(text="\n".join(sorted(items)))
        except Exception as e:
            return CommandReturn(text=f"Error: {str(e)}")

    async def cmd_cat(self, context: ExecuteContext) -> CommandReturn:
        """Read file content."""
        if not self.config.get('enable_file', True):
            return CommandReturn(text="File operations are disabled")

        if len(context.crt_params) < 1:
            return CommandReturn(text="Please provide a file path")

        path = context.crt_params[0]
        file_path = self._resolve_path(path)
        if not file_path:
            return CommandReturn(text="Access denied: path outside workspace")

        try:
            content = file_path.read_text(encoding='utf-8')
            return CommandReturn(text=content)
        except UnicodeDecodeError:
            return CommandReturn(text=f"[Binary file, {file_path.stat().st_size} bytes]")
        except Exception as e:
            return CommandReturn(text=f"Error: {str(e)}")

    async def cmd_kill(self, context: ExecuteContext) -> CommandReturn:
        """Kill a process."""
        if not self.config.get('enable_process', True):
            return CommandReturn(text="Process management is disabled")

        if len(context.crt_params) < 1:
            return CommandReturn(text="Please provide a PID or process name")

        target = context.crt_params[0]
        is_pid = target.isdigit()

        if is_pid:
            command = f'kill -{("KILL" if "-9" in context.crt_params else "TERM")} {target}'
        else:
            command = f'pkill -TERM "{target}"'

        result = await self.run_shell(command)
        if result['success']:
            return CommandReturn(text=f"Process terminated: {target}")
        else:
            return CommandReturn(text=f"Failed to terminate: {result.get('stderr', 'Unknown error')}")

    async def cmd_open(self, context: ExecuteContext) -> CommandReturn:
        """Open an application or URL."""
        if not self.config.get('enable_app', True):
            return CommandReturn(text="App control is disabled")

        if len(context.crt_params) < 1:
            return CommandReturn(text="Please provide an app name or URL")

        target = context.crt_params[0]
        if target.startswith('http'):
            command = f'open "{target}"'
        else:
            command = f'open -a "{target}"'

        result = await self.run_shell(command)
        if result['success']:
            return CommandReturn(text=f"Opened: {target}")
        else:
            return CommandReturn(text=f"Failed to open: {result.get('stderr', 'Unknown error')}")

    async def cmd_close(self, context: ExecuteContext) -> CommandReturn:
        """Close an application."""
        if not self.config.get('enable_app', True):
            return CommandReturn(text="App control is disabled")

        if len(context.crt_params) < 1:
            return CommandReturn(text="Please provide an app name")

        app_name = context.crt_params[0]
        signal = '9' if '-9' in context.crt_params else 'TERM'
        command = f'pkill -{signal} "{app_name}"'

        result = await self.run_shell(command)
        if result['success']:
            return CommandReturn(text=f"Closed: {app_name}")
        else:
            return CommandReturn(text=f"Failed to close: {result.get('stderr', 'Unknown error')}")

    async def cmd_apps(self, context: ExecuteContext) -> CommandReturn:
        """List running applications."""
        if not self.config.get('enable_app', True):
            return CommandReturn(text="App control is disabled")

        limit = int(context.crt_params[0]) if len(context.crt_params) > 0 else 20

        try:
            command = f'''osascript -e 'tell application "System Events" to get name of every process' 2>/dev/null | tr ',' '\n' | head -n {limit}'''
            result = await self.run_shell(command)

            if result['success']:
                apps = [a.strip() for a in result['stdout'].strip().split('\n') if a.strip()]
                return CommandReturn(text="\n".join(apps))
            else:
                return CommandReturn(text="Failed to list applications")
        except Exception as e:
            return CommandReturn(text=f"Error: {str(e)}")

    async def cmd_stop(self, context: ExecuteContext) -> CommandReturn:
        """Stop the current running task."""
        # Import here to avoid circular import
        from components.tools.planner import PlannerTool

        if PlannerTool.is_task_stopped():
            return CommandReturn(text="Task is already stopped.")

        PlannerTool.stop_task()
        return CommandReturn(text="Task has been stopped.")

    async def cmd_status(self, context: ExecuteContext) -> CommandReturn:
        """Check current task status."""
        # Import here to avoid circular import
        from components.tools.planner import PlannerTool

        current_task = PlannerTool.get_current_task()
        is_stopped = PlannerTool.is_task_stopped()

        if not current_task.get("task_description"):
            return CommandReturn(text="No task is currently running.")

        status_text = f"Task Status:\n"
        status_text += f"  Running: {not is_stopped}\n"
        status_text += f"  Stopped: {is_stopped}\n"
        status_text += f"  Task: {current_task.get('task_description', 'Unknown')[:50]}..."

        return CommandReturn(text=status_text)

    async def cmd_help(self, context: ExecuteContext) -> CommandReturn:
        """Show help."""
        help_text = """LangTARS - Control your Mac through IM messages

Available commands:
  /tars info              - Get system information
  /tars shell <command>   - Execute shell command
  /tars ps [filter]       - List running processes
  /tars ls [path]        - List directory contents
  /tars cat <path>       - Read file content
  /tars kill <pid|name>  - Kill a process
  /tars open <app|url>   - Open an application or URL
  /tars close <app>      - Close an application
  /tars apps [limit]     - List running applications
  /tars stop             - Stop the current task
  /tars status            - Check task status
  /tars help             - Show this help

Examples:
  /tars info
  /tars shell ls -la
  /tars ps python
  /tars open Safari
"""
        return CommandReturn(text=help_text)

    async def cmd_natural(self, context: ExecuteContext) -> CommandReturn:
        """Handle natural language commands via LLM."""
        query = " ".join(context.crt_params) if context.crt_params else context.full_command_text
        query_lower = query.lower()

        if any(kw in query_lower for kw in ['system', 'info', 'os', 'version']):
            return await self.cmd_info(context)
        elif any(kw in query_lower for kw in ['process', 'ps', 'running', 'task']):
            return await self.cmd_ps(context)
        elif any(kw in query_lower for kw in ['directory', 'folder', 'list', 'ls', 'dir']):
            return await self.cmd_ls(context)
        elif any(kw in query_lower for kw in ['file', 'read', 'cat', 'view', 'content']):
            return await self.cmd_cat(context)
        elif any(kw in query_lower for kw in ['open', 'launch', 'start']):
            return await self.cmd_open(context)
        elif any(kw in query_lower for kw in ['close', 'quit', 'stop', 'kill']):
            return await self.cmd_kill(context) if any(kw in query_lower for kw in ['kill', 'process']) else await self.cmd_close(context)
        elif any(kw in query_lower for kw in ['app', 'application', 'software']):
            return await self.cmd_apps(context)
        elif any(kw in query_lower for kw in ['shell', 'command', 'exec', 'run']):
            return await self.cmd_shell(context)
        else:
            return CommandReturn(text=f"I'm not sure what you mean by: {query}\nTry /tars help for available commands.")

    # ========== Helper Methods ==========

    def _resolve_path(self, path: str) -> Path | None:
        """Resolve a path within the workspace, returns None if outside."""
        if not self._workspace_path:
            return None

        try:
            requested = Path(path).expanduser()
            if requested.is_absolute():
                resolved = requested.resolve()
                workspace = self._workspace_path.resolve()
                if not str(resolved).startswith(str(workspace)):
                    return None
                return resolved
            else:
                return (self._workspace_path / requested).resolve()
        except Exception:
            return None

    # ========== Tool/Command Helper Methods ==========
    # These methods are called by components/commands/langtars.py and tools

    async def list_processes(self, filter_pattern: str | None = None, limit: int = 20) -> dict[str, Any]:
        """List running processes. Used by tools and commands."""
        if not self.config.get('enable_process', True):
            return {'success': False, 'error': 'Process management is disabled', 'processes': []}

        if filter_pattern:
            command = f'ps aux | grep -E "{filter_pattern}" | grep -v grep | head -n {limit}'
        else:
            command = f'ps aux | head -n {limit + 1}'

        result = await self.run_shell(command)
        if not result['success']:
            return {'success': False, 'error': result.get('error', 'Unknown error'), 'processes': []}

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

        return {'success': True, 'processes': processes[:limit]}

    async def kill_process(self, target: str, force: bool = False) -> dict[str, Any]:
        """Kill a process by name or PID."""
        if not self.config.get('enable_process', True):
            return {'success': False, 'error': 'Process management is disabled'}

        is_pid = target.isdigit()
        signal = 'KILL' if force else 'TERM'

        if is_pid:
            command = f'kill -{signal} {target}'
        else:
            command = f'pkill -{signal} "{target}"'

        result = await self.run_shell(command)
        if result['success']:
            return {'success': True, 'message': f'Process terminated: {target}'}
        else:
            return {'success': False, 'error': result.get('stderr', 'Unknown error')}

    async def list_directory(self, path: str = '.', show_hidden: bool = False) -> dict[str, Any]:
        """List directory contents."""
        if not self.config.get('enable_file', True):
            return {'success': False, 'error': 'File operations are disabled', 'items': []}

        dir_path = self._resolve_path(path)
        if not dir_path:
            return {'success': False, 'error': 'Access denied: path outside workspace', 'items': []}

        try:
            items = []
            for item in dir_path.iterdir():
                if item.name.startswith('.') and not show_hidden:
                    continue
                items.append({
                    'name': item.name,
                    'type': 'directory' if item.is_dir() else 'file',
                    'size': item.stat().st_size if item.is_file() else 0
                })
            return {'success': True, 'path': str(dir_path), 'items': items, 'count': len(items)}
        except Exception as e:
            return {'success': False, 'error': str(e), 'items': []}

    async def read_file(self, path: str) -> dict[str, Any]:
        """Read file content."""
        if not self.config.get('enable_file', True):
            return {'success': False, 'error': 'File operations are disabled'}

        file_path = self._resolve_path(path)
        if not file_path:
            return {'success': False, 'error': 'Access denied: path outside workspace'}

        try:
            if not file_path.is_file():
                return {'success': False, 'error': 'Not a file'}

            # Check if binary
            try:
                content = file_path.read_text(encoding='utf-8')
                return {'success': True, 'path': str(file_path), 'content': content, 'size': len(content)}
            except UnicodeDecodeError:
                return {'success': True, 'path': str(file_path), 'is_binary': True, 'size': file_path.stat().st_size}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def write_file(self, path: str, content: str, _mode: str = 'w') -> dict[str, Any]:
        """Write content to a file."""
        if not self.config.get('enable_file', True):
            return {'success': False, 'error': 'File operations are disabled'}

        file_path = self._resolve_path(path)
        if not file_path:
            return {'success': False, 'error': 'Access denied: path outside workspace'}

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding='utf-8')
            return {'success': True, 'path': str(file_path), 'message': 'File written successfully'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def open_app(self, app_name: str | None = None, url: str | None = None) -> dict[str, Any]:
        """Open an application or URL."""
        if not self.config.get('enable_app', True):
            return {'success': False, 'error': 'App control is disabled'}

        if url:
            command = f'open "{url}"'
        elif app_name:
            command = f'open -a "{app_name}"'
        else:
            return {'success': False, 'error': 'Please provide app_name or url'}

        result = await self.run_shell(command)
        if result['success']:
            return {'success': True, 'message': f'Opened: {url or app_name}'}
        else:
            return {'success': False, 'error': result.get('stderr', 'Unknown error')}

    async def close_app(self, app_name: str, force: bool = False) -> dict[str, Any]:
        """Close an application."""
        if not self.config.get('enable_app', True):
            return {'success': False, 'error': 'App control is disabled'}

        signal = '9' if force else 'TERM'
        command = f'pkill -{signal} "{app_name}"'

        result = await self.run_shell(command)
        if result['success']:
            return {'success': True, 'message': f'Closed: {app_name}'}
        else:
            return {'success': False, 'error': result.get('stderr', 'Unknown error')}

    async def list_apps(self, limit: int = 20) -> dict[str, Any]:
        """List running applications."""
        if not self.config.get('enable_app', True):
            return {'success': False, 'error': 'App control is disabled', 'apps': []}

        try:
            command = f'''osascript -e 'tell application "System Events" to get name of every process' 2>/dev/null | tr ',' '\\n' | head -n {limit}'''
            result = await self.run_shell(command)

            if result['success']:
                apps = [a.strip() for a in result['stdout'].strip().split('\n') if a.strip()]
                return {'success': True, 'apps': apps, 'count': len(apps)}
            else:
                return {'success': False, 'error': 'Failed to list applications'}
        except Exception as e:
            return {'success': False, 'error': str(e), 'apps': []}

    async def get_system_info(self) -> dict[str, Any]:
        """Get system information."""
        try:
            info = {
                'platform': platform.system(),
                'platform_version': platform.version(),
                'architecture': platform.architecture()[0],
                'processor': platform.processor(),
                'hostname': platform.node(),
                'python_version': platform.python_version(),
            }

            uptime_result = await self.run_shell('uptime')
            if uptime_result['success']:
                info['uptime'] = uptime_result['stdout'].strip()

            return {'success': True, 'info': info}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def search_files(self, pattern: str, path: str = '.', recursive: bool = True) -> dict[str, Any]:
        """Search for files matching a pattern."""
        if not self.config.get('enable_file', True):
            return {'success': False, 'error': 'File operations are disabled', 'files': []}

        search_path = self._resolve_path(path)
        if not search_path:
            return {'success': False, 'error': 'Access denied: path outside workspace', 'files': []}

        try:
            if recursive:
                command = f'find "{search_path}" -name "*{pattern}*" -type f 2>/dev/null | head -n 50'
            else:
                command = f'ls "{search_path}" | grep -i "*{pattern}*" | head -n 50'

            result = await self.run_shell(command)
            if result['success']:
                files = [f.strip() for f in result['stdout'].strip().split('\n') if f.strip()]
                return {'success': True, 'files': files, 'count': len(files), 'path': str(search_path)}
            else:
                return {'success': False, 'error': result.get('error', 'Unknown error'), 'files': []}
        except Exception as e:
            return {'success': False, 'error': str(e), 'files': []}

    async def run_applescript(self, script: str) -> dict[str, Any]:
        """Execute an AppleScript script."""
        if not self.config.get('enable_applescript', True):
            return {'success': False, 'error': 'AppleScript execution is disabled'}

        if not script:
            return {'success': False, 'error': 'No script provided'}

        try:
            # Use osascript to execute AppleScript
            command = f'osascript -e \'{script.replace("\'", "\\\'")}\''
            result = await self.run_shell(command)

            if result['success']:
                return {
                    'success': True,
                    'stdout': result['stdout'],
                    'stderr': result['stderr'],
                    'returncode': result['returncode']
                }
            else:
                return {
                    'success': False,
                    'error': result.get('stderr', result.get('error', 'Unknown error')),
                    'stdout': result.get('stdout', '')
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}
