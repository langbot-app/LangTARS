# LangTARS Command Handler
# Handle direct commands like /shell, /ps, /ls, etc.

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

from langbot_plugin.api.definition.components.command.command import Command, Subcommand
from langbot_plugin.api.entities.builtin.command.context import ExecuteContext, CommandReturn
from langbot_plugin.api.entities.builtin.platform.message import MessageChain, Plain

logger = logging.getLogger(__name__)


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
            aliases=["quit"],
        )

        self.registered_subcommands["stop"] = Subcommand(
            subcommand=LanTARSCommand.stop,
            help="Stop the current running task",
            usage="/tars stop",
            aliases=["pause", "cancel"],
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

        self.registered_subcommands["auto"] = Subcommand(
            subcommand=LanTARSCommand.auto,
            help="Autonomous task planning (AI-powered)",
            usage="/tars auto <task description>",
            aliases=["plan", "run"],
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
    async def stop(self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle task stopping."""
        from components.tools.planner import PlannerTool

        if PlannerTool.is_task_stopped():
            yield CommandReturn(text="Task is already stopped.")
            return

        PlannerTool.stop_task()
        yield CommandReturn(text="Task has been stopped.")

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
  /tars auto <task>      - Autonomous task planning (AI-powered)

Examples:
  /tars info
  /tars shell ls -la
  /tars ps python
  /tars open Safari
  /tars auto Open Safari and search for AI news
"""
        yield CommandReturn(text=help_text)

    @staticmethod
    async def auto(_self_cmd: Command, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
        """Handle autonomous task planning using ReAct loop."""
        # Get the task from params
        params = context.crt_params
        if not params:
            yield CommandReturn(text="""Usage: /tars auto <task description>

Example:
  /tars auto Open Safari and search for AI news
""")
            return

        task = ' '.join(params)

        # Get config from the command's plugin instance
        config = _self_cmd.plugin.get_config()
        # Ensure max_iterations is an integer
        max_iterations = int(config.get('planner_max_iterations', 5) or 5)

        # Get model: use configured model first, then fall back to auto-detect
        configured_model_uuid = config.get('planner_model_uuid', '')

        # Auto-detect model: use get_llm_models() to get available models
        try:
            models = await _self_cmd.plugin.get_llm_models()
            if not models:
                yield CommandReturn(text="""Error: No LLM models available.

Please configure an LLM model in the pipeline settings first.
Go to Pipelines → Configure → Select LLM Model
""")
                return

            # If user configured a specific model, validate it exists
            if configured_model_uuid:
                logger.info(f"[langtars.py] 配置的模型 UUID: {configured_model_uuid}")
                logger.info(f"[langtars.py] 可用模型列表: {models}")
                # Find the configured model
                for model in models:
                    if isinstance(model, dict) and model.get('uuid') == configured_model_uuid:
                        llm_model_uuid = configured_model_uuid
                        logger.info(f"[langtars.py] 找到配置的模型，使用: {configured_model_uuid}")
                        break
                else:
                    # Model not found, fall back to first available
                    logger.warning(f"[langtars.py] 配置的模型 '{configured_model_uuid}' 未在可用模型列表中找到，fallback 到第一个模型")
                    llm_model_uuid = models[0].get('uuid', '') if isinstance(models[0], dict) else models[0]
            else:
                # No model configured, use first available
                first_model = models[0]
                if isinstance(first_model, dict):
                    llm_model_uuid = first_model.get('uuid', '')
                else:
                    llm_model_uuid = first_model

            if not llm_model_uuid:
                yield CommandReturn(text="Error: Model does not have a valid UUID")
                return
        except Exception as e:
            yield CommandReturn(text=f"Error: Failed to get available models: {str(e)}")
            return

        # Import and use the plugin instance
        try:
            # _self_cmd is the Command object, _self_cmd.plugin is the main LangTARS plugin
            # plugin needs invoke_llm (from BasePlugin), helper_plugin needs helper methods
            from components.tools.planner import PlannerTool
            planner = PlannerTool()

            # Execute the planner - pass _self_cmd.plugin as plugin (has invoke_llm)
            # and _self_cmd.plugin as helper_plugin (has run_shell, read_file, etc.)
            result = await planner.execute_task(
                task=task,
                max_iterations=max_iterations,
                llm_model_uuid=llm_model_uuid,
                plugin=_self_cmd.plugin,  # Main plugin with invoke_llm
                helper_plugin=_self_cmd.plugin,
                session=context.session,
                query_id=context.query_id
            )

            yield CommandReturn(text=result)

        except Exception as e:
            import traceback
            yield CommandReturn(text=f"Error executing task: {str(e)}\n\n{traceback.format_exc()}")
