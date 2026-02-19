# Tool registry for planner
# Central registry for all available tools

from __future__ import annotations

from typing import Any

from . import BasePlannerTool
from .system import (
    ShellTool,
    ListProcessesTool,
    KillProcessTool,
    OpenAppTool,
    CloseAppTool,
    ListAppsTool,
    GetSystemInfoTool,
    AppleScriptTool,
)
from .file import (
    ReadFileTool,
    WriteFileTool,
    ListDirectoryTool,
    SearchFilesTool,
)
from .network import FetchURLTool
from .dynamic import DynamicToolLoader


# Built-in tools that are always available
BUILTIN_TOOLS: list[type[BasePlannerTool]] = [
    # System tools
    ShellTool,
    ListProcessesTool,
    KillProcessTool,
    OpenAppTool,
    CloseAppTool,
    ListAppsTool,
    GetSystemInfoTool,
    AppleScriptTool,
    # File tools
    ReadFileTool,
    WriteFileTool,
    ListDirectoryTool,
    SearchFilesTool,
    # Network tools
    FetchURLTool,
]


class ToolRegistry:
    """Registry for all planner tools"""

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self._builtin_tools: dict[str, BasePlannerTool] = {}
        self._dynamic_loader: DynamicToolLoader | None = None
        self._initialized = False

    async def initialize(self):
        """Initialize the tool registry"""
        if self._initialized:
            return

        # Register built-in tools
        for tool_class in BUILTIN_TOOLS:
            tool = tool_class()
            self._builtin_tools[tool.name] = tool

        # Initialize dynamic tool loader
        self._dynamic_loader = DynamicToolLoader(self.plugin)

        self._initialized = True

    def get_tool(self, name: str) -> BasePlannerTool | None:
        """Get a tool by name"""
        return self._builtin_tools.get(name)

    def get_all_tools(self) -> list[BasePlannerTool]:
        """Get all registered tools"""
        return list(self._builtin_tools.values())

    def to_openai_format(self) -> list[dict[str, Any]]:
        """Convert all tools to OpenAI function calling format"""
        return [tool.to_openai_format() for tool in self._builtin_tools.values()]

    async def load_dynamic_tools(self) -> list[BasePlannerTool]:
        """Load dynamic tools from MCP servers and plugins"""
        if not self._dynamic_loader:
            return []

        dynamic_tools = await self._dynamic_loader.load_all_tools()

        # Register dynamic tools (they override built-ins with same name)
        for tool in dynamic_tools:
            if tool.name not in self._builtin_tools:
                self._builtin_tools[tool.name] = tool

        return dynamic_tools

    def get_tools_description(self) -> str:
        """Generate a description of all available tools for the LLM"""
        lines = []
        for tool in self._builtin_tools.values():
            lines.append(f"- {tool.name}: {tool.description}")
            params = tool.parameters.get("properties", {})
            for param_name, param_info in params.items():
                required = " (required)" if param_name in tool.parameters.get("required", []) else ""
                lines.append(f"  - {param_name}: {param_info.get('description', '')}{required}")

        return "\n".join(lines)
