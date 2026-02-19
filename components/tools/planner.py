# LangTARS Planner Tool
# ReAct loop for autonomous task planning and execution

from __future__ import annotations

import json
from typing import Any

from langbot_plugin.api.definition.components.tool.tool import Tool
from langbot_plugin.api.entities.builtin.provider import session as provider_session
from langbot_plugin.api.entities.builtin.provider import message as provider_message
from langbot_plugin.api.entities.builtin.resource import tool as resource_tool


class PlannerTool(Tool):
    """Planner tool - ReAct loop for autonomous task execution"""

    __kind__ = "Tool"

    # Available tools for the planner to use
    AVAILABLE_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "shell",
                "description": "Execute a shell command on this Mac. Use this for running terminal commands like ls, ps, grep, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute"
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Timeout in seconds (default: 30)",
                            "default": 30
                        }
                    },
                    "required": ["command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the content of a file. Returns the file content or error message.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "The path to the file to read"
                        }
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Write content to a file. Creates new file or overwrites existing file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "The path to the file to write"
                        },
                        "content": {
                            "type": "string",
                            "description": "The content to write to the file"
                        }
                    },
                    "required": ["path", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "List the contents of a directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "The path to the directory (default: current directory)"
                        },
                        "show_hidden": {
                            "type": "boolean",
                            "description": "Show hidden files (default: false)"
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_processes",
                "description": "List running processes on this Mac.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filter": {
                            "type": "string",
                            "description": "Filter processes by name (optional)"
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of processes to return (default: 20)"
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "kill_process",
                "description": "Kill a process by name or PID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Process name or PID to kill"
                        },
                        "force": {
                            "type": "boolean",
                            "description": "Force kill (default: false)"
                        }
                    },
                    "required": ["target"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "open_app",
                "description": "Open an application or URL on this Mac.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Application name (e.g., 'Safari') or URL (e.g., 'https://...')"
                        }
                    },
                    "required": ["target"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "close_app",
                "description": "Close an application by name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "description": "The name of the application to close"
                        },
                        "force": {
                            "type": "boolean",
                            "description": "Force quit (default: false)"
                        }
                    },
                    "required": ["app_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_apps",
                "description": "List running applications on this Mac.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of apps to return (default: 20)"
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_system_info",
                "description": "Get system information about this Mac.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_files",
                "description": "Search for files matching a pattern.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "File pattern to search for (e.g., '*.py')"
                        },
                        "path": {
                            "type": "string",
                            "description": "Directory to search in (default: current)"
                        }
                    },
                    "required": ["pattern"]
                }
            }
        }
    ]

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
"""

    async def call(
        self,
        params: dict[str, Any],
        session: provider_session.Session,
        query_id: int,
    ) -> str:
        """Execute the planner to complete a task using ReAct loop."""
        task = params.get('task', '')
        max_iterations = params.get('max_iterations', 5)
        # llm_model_uuid is now optional - will be auto-detected from available models
        llm_model_uuid = params.get('llm_model_uuid', '')

        if not task:
            return "Error: No task provided. Please specify a task to execute."

        # Try to get the plugin instance which has invoke_llm and get_llm_models methods
        # The plugin is available via self.plugin when this tool is called from a command
        plugin = getattr(self, 'plugin', None)

        if not plugin:
            # Fallback: try to get from session's conversation if available
            return "Error: Plugin context not available. Please use /tars auto command instead."

        # Get configured model from plugin config
        config = plugin.get_config()
        configured_model_uuid = config.get('planner_model_uuid', '')

        # Auto-detect model: use configured UUID or get from available models
        if not llm_model_uuid:
            try:
                models = await plugin.get_llm_models()
                if not models:
                    return "Error: No LLM models available. Please configure a model in the pipeline settings."

                # If user configured a specific model, validate it exists
                if configured_model_uuid:
                    for model in models:
                        if isinstance(model, dict) and model.get('uuid') == configured_model_uuid:
                            llm_model_uuid = configured_model_uuid
                            break
                    else:
                        # Model not found, fall back to first available
                        llm_model_uuid = models[0].get('uuid', '') if isinstance(models[0], dict) else models[0]
                else:
                    # No model configured, use first available
                    first_model = models[0]
                    if isinstance(first_model, dict):
                        llm_model_uuid = first_model.get('uuid', '')
                    else:
                        llm_model_uuid = first_model

                if not llm_model_uuid:
                    return "Error: No LLM models available or model does not have a valid UUID."
            except Exception as e:
                return f"Error: Failed to get available models: {str(e)}"

        # Import main module to get helper methods (run_shell, read_file, etc.)
        from main import LangTARS
        helper_plugin = LangTARS()
        await helper_plugin.initialize()

        return await self.execute_task(
            task=task,
            max_iterations=max_iterations,
            llm_model_uuid=llm_model_uuid,
            plugin=plugin,  # Use the Plugin instance with invoke_llm
            helper_plugin=helper_plugin,
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
        session=None,
        query_id: int = 0,
    ) -> str:
        """Execute task with ReAct loop using provided plugin instance."""
        if not task:
            return "Error: No task provided."

        # Get the LLM model to use
        if not llm_model_uuid:
            return "Error: No LLM model specified. Please configure a model in the pipeline settings."

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

        # Get tools description for the LLM (instead of passing funcs parameter which has serialization issues)
        tools_description = self._get_tools_description()

        # ReAct loop
        for iteration in range(max_iterations):
            try:
                # Add tools description to the last user message if this is first iteration
                if iteration == 0:
                    # Insert tools info after the task
                    messages[-1] = provider_message.Message(
                        role="user",
                        content=f"{task}\n\nAvailable tools:\n{tools_description}"
                    )

                # Invoke LLM - without funcs parameter to avoid serialization issues
                # We'll manually handle tool calls based on LLM's response

                # Debug: print model info before invoking LLM
                print(f"[DEBUG] Invoking LLM with model_uuid: {llm_model_uuid}")
                # Get provider info for debugging
                try:
                    models = await plugin.get_llm_models()
                    for m in models:
                        if isinstance(m, dict) and m.get('uuid') == llm_model_uuid:
                            provider_name = m.get('provider', {}).get('name', 'unknown')
                            print(f"[DEBUG] Provider: {provider_name}")
                            break
                except Exception as e:
                    print(f"[DEBUG] Failed to get provider info: {e}")

                response = await plugin.invoke_llm(
                    llm_model_uuid=llm_model_uuid,
                    messages=messages,
                    funcs=[]  # Pass empty funcs to avoid validation error
                )

                # Check if there's content (non-tool response)
                if response.content and not response.tool_calls:
                    # Check if task is complete
                    content_str = str(response.content)
                    if content_str.strip().upper().startswith("DONE:"):
                        return content_str[5:].strip()

                    # Try to parse JSON tool call from content
                    tool_call = self._parse_tool_call_from_content(content_str)
                    if tool_call:
                        # Execute the tool
                        result = await self._execute_tool(
                            tool_call, helper_plugin or plugin, session, query_id
                        )

                        # Add tool result to messages
                        messages.append(
                            provider_message.Message(
                                role="tool",
                                content=json.dumps(result),
                                tool_call_id=f"call_{iteration}"
                            )
                        )

                        # If this was the last iteration, summarize
                        if iteration == max_iterations - 1:
                            return f"Task reached maximum iterations ({max_iterations}). Progress so far:\n{result}"
                        continue

                    # Regular response, continue the conversation
                    if content_str.strip():
                        messages.append(response)
                        continue

                # Handle tool calls (structured tool calls)
                if response.tool_calls:
                    for tool_call in response.tool_calls:
                        # Execute the tool using helper_plugin for the actual operations
                        result = await self._execute_tool(
                            tool_call, helper_plugin or plugin, session, query_id
                        )

                        # Add tool result to messages
                        messages.append(
                            provider_message.Message(
                                role="tool",
                                content=json.dumps(result),
                                tool_call_id=tool_call.id
                            )
                        )

                        # If this was the last iteration, summarize
                        if iteration == max_iterations - 1:
                            return f"Task reached maximum iterations ({max_iterations}). Progress so far:\n{result}"
                else:
                    # No tool call and no content - might be done
                    if response.content:
                        content_str = str(response.content)
                        if content_str.strip().upper().startswith("DONE:"):
                            return content_str[5:].strip()

            except Exception as e:
                return f"Error during execution: {str(e)}"

        return f"Task reached maximum iterations ({max_iterations}) without completion."

    def _get_tools_description(self) -> str:
        """Generate a description of available tools for the LLM."""
        lines = []
        for tool_def in self.AVAILABLE_TOOLS:
            func_def = tool_def["function"]
            name = func_def["name"]
            desc = func_def["description"]
            params = func_def.get("parameters", {})
            props = params.get("properties", {})

            lines.append(f"- {name}: {desc}")
            if props:
                for param_name, param_info in props.items():
                    required = " (required)" if param_name in params.get("required", []) else ""
                    lines.append(f"  - {param_name}: {param_info.get('description', '')}{required}")

        return "\n".join(lines)

    def _parse_tool_call_from_content(self, content: str):
        """Parse JSON tool call from LLM response content."""
        import re
        # Try to find JSON in the content
        # Look for patterns like {"tool": "name", "arguments": {...}}
        json_pattern = r'\{["\']tool["\']:\s*["\'](\w+)["\']\s*,\s*["\']arguments["\']:\s*\{[^}]*\}'
        match = re.search(json_pattern, content)
        if match:
            tool_name = match.group(1)
            # Try to extract the full JSON with arguments
            try:
                # Find the JSON object
                start = content.find('{', match.start())
                # Find matching closing brace
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
                    # Create a mock tool_call object
                    class MockToolCall:
                        def __init__(self, name, args):
                            self.id = f"call_{id(self)}"
                            self.function = type('obj', (object,), {'name': name, 'arguments': args})()
                    return MockToolCall(tool, arguments)
            except (json.JSONDecodeError, KeyError):
                pass
        return None

    def _get_llm_tools(self) -> list[resource_tool.LLMTool]:
        """Convert tool definitions to LLMTool objects."""
        tools = []
        for tool_def in self.AVAILABLE_TOOLS:
            func_def = tool_def["function"]
            tool_name = func_def["name"]

            # Create a callable that will be used when LLM calls this tool
            # Use default parameter to capture tool_name value (avoid late binding issue)
            async def tool_call_wrapper(
                query,  # Query object (not used directly)
                _tool_name=tool_name,
                **kwargs
            ) -> str:
                return await self._execute_tool_callback(_tool_name, kwargs)

            tools.append(
                resource_tool.LLMTool(
                    name=func_def["name"],
                    human_desc=func_def["description"],
                    description=func_def["description"],
                    parameters=func_def.get("parameters", {}),
                    func=tool_call_wrapper
                )
            )
        return tools

    async def _execute_tool_callback(self, tool_name: str, arguments: dict) -> str:
        """Callback for executing tools when LLM requests them."""
        # Import main module to get helper methods
        from main import LangTARS
        helper_plugin = LangTARS()
        await helper_plugin.initialize()

        # Create a mock tool_call object with the function name and arguments
        class MockToolCall:
            def __init__(self, name, args):
                self.function = type('obj', (object,), {'name': name, 'arguments': args})()

        tool_call = MockToolCall(tool_name, arguments)
        result = await self._execute_tool(tool_call, helper_plugin, None, 0)
        return json.dumps(result)

    async def _execute_tool(
        self,
        tool_call,
        helper_plugin: 'LangTARS',
        session,
        query_id: int
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

        try:
            if tool_name == "shell":
                result = await helper_plugin.run_shell(
                    command=arguments.get('command', ''),
                    timeout=arguments.get('timeout', 30)
                )
                return result

            elif tool_name == "read_file":
                result = await helper_plugin.read_file(arguments.get('path', ''))
                return result

            elif tool_name == "write_file":
                result = await helper_plugin.write_file(
                    path=arguments.get('path', ''),
                    content=arguments.get('content', '')
                )
                return result

            elif tool_name == "list_directory":
                result = await helper_plugin.list_directory(
                    path=arguments.get('path', '.'),
                    show_hidden=arguments.get('show_hidden', False)
                )
                return result

            elif tool_name == "list_processes":
                result = await helper_plugin.list_processes(
                    filter_pattern=arguments.get('filter'),
                    limit=arguments.get('limit', 20)
                )
                return result

            elif tool_name == "kill_process":
                result = await helper_plugin.kill_process(
                    target=arguments.get('target', ''),
                    force=arguments.get('force', False)
                )
                return result

            elif tool_name == "open_app":
                target = arguments.get('target', '')
                is_url = target.startswith(('http://', 'https://', 'mailto:', 'tel:'))
                result = await helper_plugin.open_app(
                    app_name=None if is_url else target,
                    url=target if is_url else None
                )
                return result

            elif tool_name == "close_app":
                result = await helper_plugin.close_app(
                    app_name=arguments.get('app_name', ''),
                    force=arguments.get('force', False)
                )
                return result

            elif tool_name == "list_apps":
                result = await helper_plugin.list_apps(limit=arguments.get('limit', 20))
                return result

            elif tool_name == "get_system_info":
                result = await helper_plugin.get_system_info()
                return result

            elif tool_name == "search_files":
                result = await helper_plugin.search_files(
                    pattern=arguments.get('pattern', ''),
                    path=arguments.get('path', '.')
                )
                return result

            else:
                return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            return {"error": str(e)}
