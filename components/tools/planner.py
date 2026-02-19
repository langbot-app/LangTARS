# LangTARS Planner Tool
# ReAct loop for autonomous task planning and execution

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from langbot_plugin.api.definition.components.tool.tool import Tool
from langbot_plugin.api.entities.builtin.provider import session as provider_session
from langbot_plugin.api.entities.builtin.provider import message as provider_message
from langbot_plugin.api.entities.builtin.resource import tool as resource_tool

from .planner_tools import BasePlannerTool
from .planner_tools.registry import ToolRegistry


class PlannerTool(Tool):
    """Planner tool - ReAct loop for autonomous task execution"""

    __kind__ = "Tool"

    # Class variable for rate limiting
    _last_llm_call_time: float = 0.0

    # Class variable for task pause/stop control
    _task_stopped: bool = False
    _current_task_info: dict = {}

    # Tool registry instance
    _tool_registry: ToolRegistry | None = None

    SYSTEM_PROMPT = """You are a task planning assistant. Your job is to help users accomplish tasks on their Mac by intelligently calling tools.

Task execution rules:
1. Understand the user's request
2. Plan the steps needed to complete the task
3. Execute steps one by one using the appropriate tools
4. After each tool execution, analyze the result and decide next steps
5. When task is complete, provide a summary

When you need to use a tool, respond in this JSON format:
{"tool": "tool_name", "arguments": {"param1": "value1", "param2": "value2"}}

For example:
{"tool": "shell", "arguments": {"command": "ls -la"}}

After executing a tool, continue the conversation with the results.

Important:
- Always explain what you're doing before taking action
- If something fails, try alternative approaches
- When the task is complete, start your final response with "DONE:" followed by a summary
- Keep your responses concise but informative
- Use fetch_url to get content from URLs when needed
"""

    async def _get_tool_registry(self) -> ToolRegistry:
        """Get or create the tool registry"""
        if PlannerTool._tool_registry is None:
            plugin = getattr(self, 'plugin', None)
            if plugin:
                PlannerTool._tool_registry = ToolRegistry(plugin)
                await PlannerTool._tool_registry.initialize()
        return PlannerTool._tool_registry

    @classmethod
    def stop_task(cls, task_id: str = "default") -> bool:
        """Stop the current running task"""
        PlannerTool._task_stopped = True
        return True

    @classmethod
    def reset_task_state(cls) -> None:
        """Reset task state for a new task"""
        PlannerTool._task_stopped = False
        PlannerTool._current_task_info = {}

    @classmethod
    def is_task_stopped(cls) -> bool:
        """Check if the current task has been stopped"""
        return cls._task_stopped

    @classmethod
    def set_current_task(cls, task_id: str, task_description: str) -> None:
        """Set the current running task info"""
        cls._current_task_info = {
            "task_id": task_id,
            "task_description": task_description,
        }

    @classmethod
    def get_current_task(cls) -> dict:
        """Get the current running task info"""
        return cls._current_task_info

    async def call(
        self,
        params: dict[str, Any],
        session: provider_session.Session,
        query_id: int,
    ) -> str:
        """Execute the planner to complete a task using ReAct loop."""
        task = params.get('task', '')
        max_iterations = params.get('max_iterations', 5)
        llm_model_uuid = params.get('llm_model_uuid', '')

        if not task:
            return "Error: No task provided. Please specify a task to execute."

        # Try to get the plugin instance which has invoke_llm and get_llm_models methods
        plugin = getattr(self, 'plugin', None)

        if not plugin:
            return "Error: Plugin context not available. Please use /tars auto command instead."

        # Get configured model from plugin config
        config = plugin.get_config()
        configured_model_uuid = config.get('planner_model_uuid', '')

        # Auto-detect model
        if not llm_model_uuid:
            try:
                models = await plugin.get_llm_models()
                if not models:
                    return "Error: No LLM models available. Please configure a model in the pipeline settings."

                if configured_model_uuid:
                    for model in models:
                        if isinstance(model, dict) and model.get('uuid') == configured_model_uuid:
                            llm_model_uuid = configured_model_uuid
                            break
                    else:
                        llm_model_uuid = models[0].get('uuid', '') if isinstance(models[0], dict) else models[0]
                else:
                    first_model = models[0]
                    if isinstance(first_model, dict):
                        llm_model_uuid = first_model.get('uuid', '')
                    else:
                        llm_model_uuid = first_model

                if not llm_model_uuid:
                    return "Error: No LLM models available or model does not have a valid UUID."
            except Exception as e:
                return f"Error: Failed to get available models: {str(e)}"

        # Initialize tool registry and load dynamic tools
        registry = await self._get_tool_registry()
        config = plugin.get_config()
        auto_load_mcp = config.get('planner_auto_load_mcp', True)

        if auto_load_mcp:
            try:
                dynamic_tools = await registry.load_dynamic_tools()
                if dynamic_tools:
                    print(f"[DEBUG] Loaded {len(dynamic_tools)} dynamic tools")
            except Exception as e:
                print(f"[DEBUG] Failed to load dynamic tools: {e}")

        # Import main module to get helper methods
        from main import LangTARS
        helper_plugin = LangTARS()
        await helper_plugin.initialize()

        return await self.execute_task(
            task=task,
            max_iterations=max_iterations,
            llm_model_uuid=llm_model_uuid,
            plugin=plugin,
            helper_plugin=helper_plugin,
            registry=registry,
            session=session,
            query_id=query_id
        )

    async def execute_task(
        self,
        task: str,
        max_iterations: int,
        llm_model_uuid: str,
        plugin: 'LangTARSPlugin',
        helper_plugin: 'LangTARS' = None,
        registry: ToolRegistry | None = None,
        session=None,
        query_id: int = 0,
    ) -> str:
        """Execute task with ReAct loop using provided plugin instance."""
        # Reset task state for new task
        PlannerTool.reset_task_state()
        PlannerTool.set_current_task("default", task)

        if not task:
            return "Error: No task provided."

        if not llm_model_uuid:
            return "Error: No LLM model specified. Please configure a model in the pipeline settings."

        # Get rate limit from config
        config = plugin.get_config() if plugin else {}
        rate_limit_seconds = float(config.get('planner_rate_limit_seconds', 1))

        # Get tools description from registry
        tools_description = registry.get_tools_description() if registry else ""

        # Build initial messages
        messages = [
            provider_message.Message(
                role="system",
                content=self.SYSTEM_PROMPT
            ),
            provider_message.Message(
                role="user",
                content=task
            )
        ]

        # ReAct loop
        for iteration in range(max_iterations):
            # Check if task has been stopped
            if PlannerTool._task_stopped:
                return "Task has been stopped by user."

            try:
                # Add tools description to the last user message if this is first iteration
                if iteration == 0:
                    messages[-1] = provider_message.Message(
                        role="user",
                        content=f"{task}\n\nAvailable tools:\n{tools_description}"
                    )

                # Debug: print model info before invoking LLM
                print(f"[DEBUG] Invoking LLM with model_uuid: {llm_model_uuid}")
                try:
                    models = await plugin.get_llm_models()
                    for m in models:
                        if isinstance(m, dict) and m.get('uuid') == llm_model_uuid:
                            provider_name = m.get('provider', {}).get('name', 'unknown')
                            print(f"[DEBUG] Provider: {provider_name}")
                            break
                except Exception as e:
                    print(f"[DEBUG] Failed to get provider info: {e}")

                # Rate limiting: wait if necessary
                current_time = time.time()
                time_since_last_call = current_time - PlannerTool._last_llm_call_time
                if time_since_last_call < rate_limit_seconds:
                    wait_time = rate_limit_seconds - time_since_last_call
                    print(f"[DEBUG] Rate limiting: waiting {wait_time:.2f}s before LLM call")
                    await asyncio.sleep(wait_time)
                PlannerTool._last_llm_call_time = time.time()

                response = await plugin.invoke_llm(
                    llm_model_uuid=llm_model_uuid,
                    messages=messages,
                    funcs=[]
                )

                # Check if there's content (non-tool response)
                if response.content and not response.tool_calls:
                    content_str = str(response.content)
                    if content_str.strip().upper().startswith("DONE:"):
                        return content_str[5:].strip()

                    # Try to parse JSON tool call from content
                    tool_call = self._parse_tool_call_from_content(content_str)
                    if tool_call:
                        result = await self._execute_tool(
                            tool_call, helper_plugin or plugin, registry
                        )
                        messages.append(
                            provider_message.Message(
                                role="tool",
                                content=json.dumps(result),
                                tool_call_id=f"call_{iteration}"
                            )
                        )
                        if iteration == max_iterations - 1:
                            return f"Task reached maximum iterations ({max_iterations}). Progress so far:\n{result}"
                        continue

                    if content_str.strip():
                        messages.append(response)
                        continue

                # Handle structured tool calls
                if response.tool_calls:
                    for tool_call in response.tool_calls:
                        result = await self._execute_tool(
                            tool_call, helper_plugin or plugin, registry
                        )
                        messages.append(
                            provider_message.Message(
                                role="tool",
                                content=json.dumps(result),
                                tool_call_id=tool_call.id
                            )
                        )
                        if iteration == max_iterations - 1:
                            return f"Task reached maximum iterations ({max_iterations}). Progress so far:\n{result}"
                else:
                    if response.content:
                        content_str = str(response.content)
                        if content_str.strip().upper().startswith("DONE:"):
                            return content_str[5:].strip()

            except Exception as e:
                return f"Error during execution: {str(e)}"

        return f"Task reached maximum iterations ({max_iterations}) without completion."

    def _parse_tool_call_from_content(self, content: str):
        """Parse JSON tool call from LLM response content."""
        import re
        json_pattern = r'\{["\']tool["\']:\s*["\'](\w+)["\']\s*,\s*["\']arguments["\']:\s*\{[^}]*\}'
        match = re.search(json_pattern, content)
        if match:
            tool_name = match.group(1)
            try:
                start = content.find('{', match.start())
                depth = 0
                end = start
                for i, c in enumerate(content[start:], start):
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                json_str = content[start:end]
                data = json.loads(json_str)
                tool = data.get('tool', '')
                arguments = data.get('arguments', {})
                if tool and arguments:
                    class MockToolCall:
                        def __init__(self, name, args):
                            self.id = f"call_{id(self)}"
                            self.function = type('obj', (object,), {'name': name, 'arguments': args})()
                    return MockToolCall(tool, arguments)
            except (json.JSONDecodeError, KeyError):
                pass
        return None

    async def _execute_tool(
        self,
        tool_call,
        helper_plugin: 'LangTARS',
        registry: ToolRegistry | None = None,
    ) -> dict[str, Any]:
        """Execute a tool call and return the result."""
        tool_name = tool_call.function.name
        arguments = tool_call.function.arguments

        # Parse arguments if they're a string
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return {"error": f"Invalid arguments: {arguments}"}

        # Try to get tool from registry first
        tool = None
        if registry:
            tool = registry.get_tool(tool_name)

        # Execute the tool
        if isinstance(tool, BasePlannerTool):
            try:
                return await tool.execute(helper_plugin, arguments)
            except Exception as e:
                return {"error": str(e)}

        # Fallback: execute built-in tools directly
        try:
            return await self._execute_builtin_tool(tool_name, arguments, helper_plugin)
        except Exception as e:
            return {"error": f"Unknown tool: {tool_name}, error: {str(e)}"}

    async def _execute_builtin_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        helper_plugin: 'LangTARS',
    ) -> dict[str, Any]:
        """Execute built-in tools directly"""
        if tool_name == "shell":
            return await helper_plugin.run_shell(
                command=arguments.get('command', ''),
                timeout=arguments.get('timeout', 30)
            )
        elif tool_name == "read_file":
            return await helper_plugin.read_file(arguments.get('path', ''))
        elif tool_name == "write_file":
            return await helper_plugin.write_file(
                path=arguments.get('path', ''),
                content=arguments.get('content', '')
            )
        elif tool_name == "list_directory":
            return await helper_plugin.list_directory(
                path=arguments.get('path', '.'),
                show_hidden=arguments.get('show_hidden', False)
            )
        elif tool_name == "list_processes":
            return await helper_plugin.list_processes(
                filter_pattern=arguments.get('filter'),
                limit=arguments.get('limit', 20)
            )
        elif tool_name == "kill_process":
            return await helper_plugin.kill_process(
                target=arguments.get('target', ''),
                force=arguments.get('force', False)
            )
        elif tool_name == "open_app":
            target = arguments.get('target', '')
            is_url = target.startswith(('http://', 'https://', 'mailto:', 'tel:'))
            return await helper_plugin.open_app(
                app_name=None if is_url else target,
                url=target if is_url else None
            )
        elif tool_name == "close_app":
            return await helper_plugin.close_app(
                app_name=arguments.get('app_name', ''),
                force=arguments.get('force', False)
            )
        elif tool_name == "list_apps":
            return await helper_plugin.list_apps(limit=arguments.get('limit', 20))
        elif tool_name == "get_system_info":
            return await helper_plugin.get_system_info()
        elif tool_name == "search_files":
            return await helper_plugin.search_files(
                pattern=arguments.get('pattern', ''),
                path=arguments.get('path', '.')
            )
        elif tool_name == "fetch_url":
            url = arguments.get('url', '')
            if not url:
                return {"error": "URL is required"}
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        content = await response.text()
                        if len(content) > 10000:
                            content = content[:10000] + "\n... (truncated)"
                        return {
                            "success": True,
                            "url": url,
                            "status_code": response.status,
                            "content": content
                        }
            except Exception as e:
                return {"error": f"Failed to fetch URL: {str(e)}"}
        else:
            return {"error": f"Unknown tool: {tool_name}"}
