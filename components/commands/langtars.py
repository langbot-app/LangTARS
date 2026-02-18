# LangTARS Command Handler
# Handle direct commands like /shell, /ps, /ls, etc.

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator

from langbot_plugin.api.definition.components.command.command import Command, Subcommand
from langbot_plugin.api.entities.builtin.command.context import ExecuteContext, CommandReturn
from langbot_plugin.api.entities.builtin.platform.message import MessageChain, Plain


class LangTARS(Command):
    """LangTARS Command Handler"""

    async def initialize(self):
        await super().initialize()

        # Register subcommands with class methods (unbound)
        self.registered_subcommands["shell"] = Subcommand(
            subcommand=LanTARSCommand.shell,
            help="Execute a shell command",
            usage="/tars shell <command>",
            aliases=["sh", "exec"],
        )

        self.registered_subcommands["ps"] = Subcommand(
            subcommand=LanTARSCommand.ps,
            help="List running processes",
            usage="/tars ps [filter] [limit]",
            aliases=["processes", "process"],
        )

        self.registered_subcommands["kill"] = Subcommand(
            subcommand=LanTARSCommand.kill,
            help="Kill a process by name or PID",
            usage="/tars kill <name|PID> [-f]",
            aliases=[],
        )

        self.registered_subcommands["ls"] = Subcommand(
            subcommand=LanTARSCommand.ls,
            help="List directory contents",
            usage="/tars ls [path] [-a]",
            aliases=["list", "dir"],
        )

        self.registered_subcommands["cat"] = Subcommand(
            subcommand=LanTARSCommand.cat,
            help="Read file content",
            usage="/tars cat <path>",
            aliases=["read", "view"],
        )

        self.registered_subcommands["write"] = Subcommand(
            subcommand=LanTARSCommand.write,
            help="Write content to a file",
            usage="/tars write <path> <content>",
            aliases=["save", "create"],
        )

        self.registered_subcommands["open"] = Subcommand(
            subcommand=LanTARSCommand.open,
            help="Open an application or URL",
            usage="/tars open <app|url>",
            aliases=["launch", "start"],
        )

        self.registered_subcommands["close"] = Subcommand(
            subcommand=LanTARSCommand.close,
            help="Close an application",
            usage="/tars close <app_name> [-f]",
            aliases=["quit", "stop"],
        )

        self.registered_subcommands["top"] = Subcommand(
            subcommand=LanTARSCommand.top,
            help="Show running applications",
            usage="/tars top",
            aliases=["apps"],
        )

        self.registered_subcommands["info"] = Subcommand(
            subcommand=LanTARSCommand.info,
            help="Show system information",
            usage="/tars info",
            aliases=["system", "status"],
        )

        self.registered_subcommands["search"] = Subcommand(
            subcommand=LanTARSCommand.search,
            help="Search for files",
            usage="/tars search <pattern> [path]",
            aliases=["find"],
        )

        # Wildcard subcommand to handle no subcommand
        self.registered_subcommands["*"] = Subcommand(
            subcommand=LanTARSCommand.default,
            help="Show help or handle default",
            usage="/tars help",
            aliases=[],
        )


# Separate class for command handlers to avoid self binding issues
class LanTARSCommand:
    """Static command handlers that delegate to main plugin."""

    @staticmethod
    async def shell(self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle shell command execution."""
        params = context.crt_params
        if not params:
            yield CommandReturn(text="Usage: /tars shell <command>")
            return

        command = ' '.join(params)
        yield CommandReturn(text=f"Executing: `{command}`\n\n")

        from main import LangTARS
        plugin = LangTARS()
        await plugin.initialize()
        result = await plugin.run_shell(command)

        if result['success']:
            output = result.get('stdout', '') or result.get('stderr', '')
            yield CommandReturn(text=f"Command executed successfully\n\n```\n{output}\n```")
        else:
            yield CommandReturn(text=f"Command failed: {result.get('error', 'Unknown error')}")

    @staticmethod
    async def ps(self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle process listing."""
        params = context.crt_params
        filter_pattern = params[0] if params else None
        limit = 20

        from main import LangTARS
        plugin = LangTARS()
        await plugin.initialize()
        result = await plugin.list_processes(filter_pattern, limit)

        if result['success']:
            processes = result.get('processes', [])
            if not processes:
                yield CommandReturn(text="No processes found.")
                return

            lines = ["**Processes:**\n"]
            lines.append(f"{'PID':<8} {'CPU%':<8} {'MEM%':<8} {'COMMAND'}")
            lines.append("-" * 60)
            for p in processes[:15]:
                cmd = p.get('command', '')[:30]
                lines.append(f"{p.get('pid',''):<8} {p.get('cpu',''):<8} {p.get('mem',''):<8} {cmd}")

            if len(processes) > 15:
                lines.append(f"... and {len(processes) - 15} more")

            yield CommandReturn(text='\n'.join(lines))
        else:
            yield CommandReturn(text=f"Failed: {result.get('error', 'Unknown error')}")

    @staticmethod
    async def kill(self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle process killing."""
        params = context.crt_params
        if not params:
            yield CommandReturn(text="Usage: /tars kill <name|PID> [-f]")
            return

        target = params[0]
        force = '-f' in params

        from main import LangTARS
        plugin = LangTARS()
        await plugin.initialize()
        result = await plugin.kill_process(target, force=force)

        if result['success']:
            yield CommandReturn(text=f"Process terminated: {target}")
        else:
            yield CommandReturn(text=f"Failed: {result.get('error', 'Unknown error')}")

    @staticmethod
    async def ls(self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle directory listing."""
        params = context.crt_params
        path = params[0] if params else '.'
        show_hidden = '-a' in params

        from main import LangTARS
        plugin = LangTARS()
        await plugin.initialize()
        result = await plugin.list_directory(path, show_hidden)

        if result['success']:
            items = result.get('items', [])
            if not items:
                yield CommandReturn(text=f"Directory is empty: {result.get('path', path)}")
                return

            lines = [f"**Contents of `{result.get('path', path)}`**\n"]
            for item in items:
                icon = '📁' if item['type'] == 'directory' else '📄'
                size_str = f" ({item['size']} bytes)" if item['size'] > 0 else ''
                lines.append(f"{icon} {item['name']}{size_str}")

            lines.append(f"\nTotal: {result.get('count', 0)} items")
            yield CommandReturn(text='\n'.join(lines))
        else:
            yield CommandReturn(text=f"Failed: {result.get('error', 'Access denied')}")

    @staticmethod
    async def cat(self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle file reading."""
        params = context.crt_params
        if not params:
            yield CommandReturn(text="Usage: /tars cat <path>")
            return

        path = params[0]

        from main import LangTARS
        plugin = LangTARS()
        await plugin.initialize()
        result = await plugin.read_file(path)

        if result['success']:
            content = result.get('content', '')
            if result.get('is_binary'):
                yield CommandReturn(text=f"Binary file: {result.get('path', path)} ({result.get('size', 0)} bytes)")
            elif len(content) > 2000:
                yield CommandReturn(text=f"```\n{content[:2000]}\n```\n\n... (truncated)")
            else:
                yield CommandReturn(text=f"```\n{content}\n```")
        else:
            yield CommandReturn(text=f"Failed: {result.get('error', 'Access denied')}")

    @staticmethod
    async def write(self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle file writing."""
        params = context.crt_params
        if len(params) < 2:
            yield CommandReturn(text="Usage: /tars write <path> <content>")
            return

        path = params[0]
        content = ' '.join(params[1:])

        from main import LangTARS
        plugin = LangTARS()
        await plugin.initialize()
        result = await plugin.write_file(path, content)

        if result['success']:
            yield CommandReturn(text=f"File written: {result.get('path', path)}")
        else:
            yield CommandReturn(text=f"Failed: {result.get('error', 'Unknown error')}")

    @staticmethod
    async def open(self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle app/URL opening."""
        params = context.crt_params
        if not params:
            yield CommandReturn(text="Usage: /tars open <app_name|url>")
            return

        target = params[0]
        is_url = target.startswith(('http://', 'https://', 'mailto:', 'tel:'))

        from main import LangTARS
        plugin = LangTARS()
        await plugin.initialize()
        result = await plugin.open_app(target if not is_url else None, url=target if is_url else None)

        if result['success']:
            yield CommandReturn(text=f"Opened: {target}")
        else:
            yield CommandReturn(text=f"Failed: {result.get('error', 'Unknown error')}")

    @staticmethod
    async def close(self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle app closing."""
        params = context.crt_params
        if not params:
            yield CommandReturn(text="Usage: /tars close <app_name> [-f]")
            return

        app_name = params[0]
        force = '-f' in params

        from main import LangTARS
        plugin = LangTARS()
        await plugin.initialize()
        result = await plugin.close_app(app_name, force=force)

        if result['success']:
            yield CommandReturn(text=f"Closed: {app_name}")
        else:
            yield CommandReturn(text=f"Failed: {result.get('error', 'Unknown error')}")

    @staticmethod
    async def top(self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle app listing."""
        from main import LangTARS
        plugin = LangTARS()
        await plugin.initialize()
        result = await plugin.list_apps()

        if result['success']:
            apps = result.get('apps', [])
            if not apps:
                yield CommandReturn(text="No applications running.")
                return

            lines = ["**Running Applications:**\n"]
            lines.append('\n'.join(f"• {app}" for app in apps))
            yield CommandReturn(text='\n'.join(lines))
        else:
            yield CommandReturn(text=f"Failed: {result.get('error', 'Unknown error')}")

    @staticmethod
    async def info(self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle system info display."""
        from main import LangTARS
        plugin = LangTARS()
        await plugin.initialize()
        result = await plugin.get_system_info()

        if result['success']:
            info = result.get('info', {})
            lines = ["**System Information:**\n"]
            for key, value in info.items():
                if isinstance(value, dict):
                    continue
                lines.append(f"• **{key}**: {value}")
            yield CommandReturn(text='\n'.join(lines))
        else:
            yield CommandReturn(text=f"Failed: {result.get('error', 'Unknown error')}")

    @staticmethod
    async def search(self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle file search."""
        params = context.crt_params
        if not params:
            yield CommandReturn(text="Usage: /tars search <pattern> [path]")
            return

        pattern = params[0]
        path = params[1] if len(params) > 1 else '.'

        from main import LangTARS
        plugin = LangTARS()
        await plugin.initialize()
        result = await plugin.search_files(pattern, path)

        if result['success']:
            files = result.get('files', [])
            if not files:
                yield CommandReturn(text=f"No files found matching '{pattern}'")
                return

            lines = [f"**Search Results for '{pattern}':**\n"]
            for f in files[:20]:
                lines.append(f"• {f}")

            if len(files) > 20:
                lines.append(f"... and {len(files) - 20} more")

            yield CommandReturn(text='\n'.join(lines))
        else:
            yield CommandReturn(text=f"Failed: {result.get('error', 'Unknown error')}")

    @staticmethod
    async def default(self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle default case - show help."""
        help_text = """LangTARS - Control your Mac through IM messages

Available commands:
  /tars shell <command>   - Execute shell command
  /tars ps [filter]       - List running processes
  /tars kill <pid|name>   - Kill a process
  /tars ls [path]         - List directory contents
  /tars cat <path>        - Read file content
  /tars write <path> <content> - Write file
  /tars open <app|url>   - Open an application or URL
  /tars close <app>      - Close an application
  /tars top              - List running applications
  /tars info             - Show system information
  /tars search <pattern> - Search files

Examples:
  /tars info
  /tars shell ls -la
  /tars ps python
  /tars open Safari
"""
        yield CommandReturn(text=help_text)
