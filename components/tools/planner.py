# LangTARS Planner Tool
# ReAct loop for autonomous task planning and execution

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

    # Class variable for LLM call count tracking
    _llm_call_count: int = 0

    # Class variable for task pause/stop control
    _task_stopped: bool = False
    _current_task_info: dict = {}

    # Tool registry instance
    _tool_registry: ToolRegistry | None = None

    # File-based stop flag for cross-process communication
    _stop_file_path: str = "/tmp/langtars_stop"

    @classmethod
    def _get_stop_file_path(cls) -> str:
        """Get the path to the stop flag file"""
        return cls._stop_file_path

    @classmethod
    def _is_stopped_from_file(cls) -> bool:
        """Check if stop flag file exists (for cross-process stop)"""
        import os
        return os.path.exists(cls._stop_file_path)

    @classmethod
    def _clear_stop_file(cls) -> None:
        """Clear the stop flag file"""
        import os
        try:
            if os.path.exists(cls._stop_file_path):
                os.remove(cls._stop_file_path)
        except:
            pass

    @classmethod
    def stop_task(cls, task_id: str = "default") -> bool:
        """Stop the current running task - writes to file for cross-process communication"""
        # Set class variable
        cls._task_stopped = True
        # Also write to file for cross-process communication
        try:
            with open(cls._stop_file_path, 'w') as f:
                f.write(f"stopped:{task_id}")
        except:
            pass
        return True

    @classmethod
    def is_task_stopped(cls) -> bool:
        """Check if the current task has been stopped (checks both class var and file)"""
        # First check class variable
        if cls._task_stopped:
            return True
        # Also check file for cross-process communication
        if cls._is_stopped_from_file():
            cls._task_stopped = True
            return True
        return False

    @classmethod
    def reset_task_state(cls) -> None:
        """Reset task state for a new task"""
        cls._task_stopped = False
        cls._current_task_info = {}
        cls._llm_call_count = 0
        cls._clear_stop_file()

    SYSTEM_PROMPT = """You are a task planning assistant. Your job is to help users accomplish tasks on their Mac by intelligently calling tools.

AVAILABLE TOOLS:
You MUST use the tools listed below to accomplish tasks. NEVER claim you cannot do something without trying the tools first.

## Response Format - VERY IMPORTANT:

When you need to execute a tool, you MUST respond with ONLY a JSON object in this exact format:
{"tool": "tool_name", "arguments": {"param1": "value1", "param2": "value2"}}

When the task is COMPLETED, respond with ONLY:
DONE: Your summary here

When you need a skill that doesn't exist, respond with ONLY:
NEED_SKILL: Description of what capability you need

## Examples:

User: "List files in current directory"
Response: {"tool": "shell", "arguments": {"command": "ls -la"}}

User: "Open Safari and go to github.com"
Response: {"tool": "safari_navigate", "arguments": {"url": "https://github.com"}}

User: "Open Chrome and search for AI news"
Response: {"tool": "chrome_navigate", "arguments": {"url": "https://www.google.com/search?q=AI+news"}}

User: "Open a website"
Response: {"tool": "browser_navigate", "arguments": {"url": "https://example.com"}}

User: "What's the weather?"
Response: {"tool": "fetch_url", "arguments": {"url": "https://weather.com"}}

User: "Task complete, show result"
Response: DONE: Successfully completed the task...

## Browser Selection Rules - VERY IMPORTANT:
- If user says "open website" or "go to website" WITHOUT specifying browser → Use browser_navigate (Playwright)
- If user says "open Safari" or "use Safari" → Use safari_navigate (controls real Safari app)
- If user says "open Chrome" or "use Chrome" → Use chrome_navigate (controls real Chrome app)
- For Safari: use safari_open, safari_navigate, safari_get_content, safari_click, safari_type, safari_press
- For Chrome: use chrome_open, chrome_navigate, chrome_get_content, chrome_click, chrome_type, chrome_press
- For general web automation: use browser_navigate, browser_click, browser_type, browser_screenshot

## Important Rules:
1. ALWAYS try to use available tools before giving up
2. ALWAYS respond with valid JSON when calling tools
3. NEVER respond with natural language text when tools are needed
4. Use browser_navigate for general web automation (Playwright)
5. Use safari_* tools when user specifically mentions Safari
6. Use chrome_* tools when user specifically mentions Chrome
7. Use shell for terminal commands
8. Use fetch_url to get web page content

If no tool can accomplish the user's request, then respond with NEED_SKILL: and describe what you need.
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
                    logger.debug(f"Loaded {len(dynamic_tools)} dynamic tools")
            except Exception as e:
                logger.debug(f"Failed to load dynamic tools: {e}")

        # Import main module to get helper methods
        from main import LangTARS
        helper_plugin = LangTARS()
        # Pass the config to the helper plugin so browser tools work
        helper_plugin.config = config.copy()
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

        # Build initial messages - start with system prompt
        messages = [
            provider_message.Message(
                role="system",
                content=self.SYSTEM_PROMPT
            ),
        ]

        # Try to get conversation history from session
        if session and hasattr(session, 'conversations') and session.conversations:
            try:
                # Get the current (last) conversation
                current_conversation = session.conversations[-1]
                if hasattr(current_conversation, 'messages') and current_conversation.messages:
                    # Add historical messages (skip the first one if it's the system prompt)
                    for msg in current_conversation.messages:
                        if hasattr(msg, 'role') and hasattr(msg, 'content'):
                            # Skip if it's a duplicate of our system prompt
                            if msg.role == 'system' and 'You are a task planning assistant' in str(msg.content):
                                continue
                            # Convert to our message format
                            messages.append(provider_message.Message(
                                role=msg.role,
                                content=msg.content if isinstance(msg.content, str) else str(msg.content),
                                name=getattr(msg, 'name', None),
                                tool_calls=getattr(msg, 'tool_calls', None),
                                tool_call_id=getattr(msg, 'tool_call_id', None)
                            ))
                    logger.debug(f"Loaded {len(messages)} messages from session history")
            except Exception as e:
                logger.debug(f"Failed to load session history: {e}")

        # Add the current task
        messages.append(provider_message.Message(
            role="user",
            content=task
        ))

        # ReAct loop
        for iteration in range(max_iterations):
            # Check if task has been stopped
            if PlannerTool._task_stopped:
                logger.info(f"LLM 调用结束，共调用 {PlannerTool._llm_call_count} 次")
                return "Task has been stopped by user."

            try:
                # Check if stopped before LLM call
                if PlannerTool._task_stopped:
                    logger.info(f"LLM 调用结束，共调用 {PlannerTool._llm_call_count} 次")
                    return "Task has been stopped by user."

                # Add tools description to the last user message
                # Always include tools description to remind LLM of available tools
                messages[-1] = provider_message.Message(
                    role="user",
                    content=f"{task}\n\nIMPORTANT: Use a tool to complete this task. Available tools:\n{tools_description}\n\nRemember: Respond with JSON format only: {{\"tool\": \"name\", \"arguments\": {{...}}}}"
                )

                # Rate limiting: wait if necessary
                current_time = time.time()
                time_since_last_call = current_time - PlannerTool._last_llm_call_time
                if time_since_last_call < rate_limit_seconds:
                    wait_time = rate_limit_seconds - time_since_last_call
                    logger.debug(f"Rate limiting: waiting {wait_time:.2f}s before LLM call")
                    await asyncio.sleep(wait_time)
                PlannerTool._last_llm_call_time = time.time()

                # Increment LLM call count and log the start of LLM invocation
                PlannerTool._llm_call_count += 1
                logger.info(f"LLM 调用开始 (第 {PlannerTool._llm_call_count} 次)")

                response = await plugin.invoke_llm(
                    llm_model_uuid=llm_model_uuid,
                    messages=messages,
                    funcs=[]
                )

                # Check if there's content (non-tool response)
                if response.content and not response.tool_calls:
                    content_str = str(response.content)
                    if content_str.strip().upper().startswith("DONE:"):
                        result = content_str[5:].strip()
                        logger.info(f"LLM 调用结束，共调用 {PlannerTool._llm_call_count} 次")
                        return result

                    # Check if LLM indicates it needs a skill
                    if content_str.strip().upper().startswith("NEED_SKILL:"):
                        skill_needed = content_str[11:].strip()
                        logger.info(f"LLM 调用结束，共调用 {PlannerTool._llm_call_count} 次")
                        return self._generate_skill_suggestion(skill_needed)

                    # Try to parse JSON tool call from content
                    tool_call = self._parse_tool_call_from_content(content_str)
                    if tool_call:
                        result = await self._execute_tool(
                            tool_call, helper_plugin or plugin, registry
                        )

                        # Check if stopped after tool execution
                        if PlannerTool._task_stopped:
                            logger.info(f"LLM 调用结束，共调用 {PlannerTool._llm_call_count} 次")
                            return f"Task stopped by user. Last result:\n{result}"

                        messages.append(
                            provider_message.Message(
                                role="tool",
                                content=json.dumps(result),
                                tool_call_id=f"call_{iteration}"
                            )
                        )
                        if iteration == max_iterations - 1:
                            logger.info(f"LLM 调用结束，共调用 {PlannerTool._llm_call_count} 次")
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

                        # Check if stopped after tool execution
                        if PlannerTool._task_stopped:
                            logger.info(f"LLM 调用结束，共调用 {PlannerTool._llm_call_count} 次")
                            return f"Task stopped by user. Last result:\n{result}"

                        messages.append(
                            provider_message.Message(
                                role="tool",
                                content=json.dumps(result),
                                tool_call_id=tool_call.id
                            )
                        )
                        if iteration == max_iterations - 1:
                            logger.info(f"LLM 调用结束，共调用 {PlannerTool._llm_call_count} 次")
                            return f"Task reached maximum iterations ({max_iterations}). Progress so far:\n{result}"
                else:
                    if response.content:
                        content_str = str(response.content)
                        if content_str.strip().upper().startswith("DONE:"):
                            result = content_str[5:].strip()
                            logger.info(f"LLM 调用结束，共调用 {PlannerTool._llm_call_count} 次")
                            return result
                        # Check if LLM indicates it needs a skill
                        if content_str.strip().upper().startswith("NEED_SKILL:"):
                            skill_needed = content_str[11:].strip()
                            logger.info(f"LLM 调用结束，共调用 {PlannerTool._llm_call_count} 次")
                            return self._generate_skill_suggestion(skill_needed)

            except Exception as e:
                error_msg = str(e)
                # Check for specific error types
                if "429" in error_msg or "rate limit" in error_msg.lower():
                    return f"""错误: LLM API 请求过于频繁或余额不足。

请检查:
1. 账户是否有足够的余额
2. 是否开启了速率限制

可以稍后再试，或等待几秒钟后重试。

错误详情: {error_msg[:200]}"""
                logger.info(f"LLM 调用结束，共调用 {PlannerTool._llm_call_count} 次")
                return f"Error during execution: {error_msg}"

        logger.info(f"LLM 调用结束，共调用 {PlannerTool._llm_call_count} 次")
        return f"Task reached maximum iterations ({max_iterations}) without completion."

    def _generate_skill_suggestion(self, skill_needed: str) -> str:
        """Generate a suggestion for the user when a skill is needed."""
        # Check if skill loader is available
        skill_info = ""
        install_command = ""
        found_skills = []

        if PlannerTool._tool_registry and PlannerTool._tool_registry._skill_loader:
            try:
                # Try to search for relevant skills
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                found_skills = loop.run_until_complete(
                    PlannerTool._tool_registry._skill_loader.search_skills(skill_needed)
                )
                loop.close()

                if found_skills:
                    skill_info = "\n\n找到以下相关 Skills:\n"
                    for skill in found_skills[:5]:  # Show up to 5 skills
                        skill_info += f"- {skill.name}: {skill.description}\n"

                    # Try to auto-install the first matching skill
                    first_skill = found_skills[0]
                    install_result = self._try_auto_install(first_skill.name)
                    if install_result["success"]:
                        return f"""我发现了相关技能「{first_skill.name}」，正在自动安装...

安装成功！技能「{first_skill.name}」已安装。

请再次发送任务，我将使用新安装的技能来完成你的请求。
"""
            except Exception as e:
                logger.debug(f"Failed to search skills: {e}")

        # If no skills found or auto-install failed, provide manual instructions
        return f"""抱歉，我无法完成这个任务，因为缺少必要的工具/技能。

需要的技能: {skill_needed}{skill_info}

要解决这个问题，你可以:

1. 安装 ClawHub Skills:
   - 在 ~/.claude/skills/ 目录下添加相应的 skill
   - 或者从 GitHub 安装，例如:
     git clone https://github.com/langbot-app/clawhub-weather.git ~/.claude/skills/weather

2. 配置 MCP 服务器:
   - 在 LangBot 设置中添加支持该功能的 MCP 服务器

3. 手动执行:
   - 如果你有其他方式完成这个任务，可以直接告诉我

常见技能的 GitHub 仓库:
- 天气: https://github.com/langbot-app/clawhub-weather
- 邮件: https://github.com/langbot-app/clawhub-email
- 等等...
"""

    def _try_auto_install(self, skill_name: str) -> dict[str, Any]:
        """Try to automatically install a skill"""
        if not PlannerTool._tool_registry or not PlannerTool._tool_registry._skill_loader:
            return {"success": False, "error": "Skill loader not available"}

        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                PlannerTool._tool_registry._skill_loader.install_skill(skill_name)
            )
            loop.close()
            return result
        except Exception as e:
            logger.debug(f"Auto-install failed: {e}")
            return {"success": False, "error": str(e)}

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
                            import uuid
                            self.id = f"call_{uuid.uuid4().hex[:8]}"
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
            if tool:
                logger.debug(f"Found tool '{tool_name}' in registry: {type(tool).__name__}")
            else:
                logger.debug(f"Tool '{tool_name}' not found in registry")

        # Execute the tool
        if isinstance(tool, BasePlannerTool):
            try:
                logger.debug(f"Executing tool '{tool_name}' with args: {arguments}")
                result = await tool.execute(helper_plugin, arguments)
                logger.debug(f"Tool result: {result}")
                return result
            except Exception as e:
                import traceback
                error_msg = f"Error executing tool {tool_name}: {str(e)}"
                logger.debug(error_msg)
                traceback.print_exc()
                return {"error": error_msg}

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
