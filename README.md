<p align="center">
  <img src="assets/icon.svg" alt="LangTARS" width="128">
</p>

<p align="center">
  <strong>LangTARS</strong> — LangBot Native Plugin
</p>

<p align="center">
  <a href="README_zh.md">中文</a>&nbsp; • &nbsp;
  <a href="https://github.com/langbot-app/LangTARS">GitHub</a>
</p>

---

## What is LangTARS?

LangTARS is a **LangBot native plugin** inspired by Nanobot's ReAct philosophy, designed to bring the **OpenClaw** experience to LangBot users. It enables you to control your Mac through IM messages using autonomous AI task planning. Like **TARS** from *Interstellar*, it works faithfully for you.

Like [OpenClaw](https://github.com/openclaw/openclaw), LangTARS allows AI assistants to execute real actions on your Mac—but with the simplicity and elegance of a LangBot plugin.

## Why LangTARS?

[OpenClaw](https://github.com/openclaw/openclaw) is an impressive project with a great vision. However, running such complex software with access to your digital life requires trust in systems you may not fully understand.

LangTARS takes a different approach:
- **Native LangBot integration** — Runs directly within LangBot using the Nanobot kernel
- **Lightweight** — Minimal codebase you can understand and audit
- **Autonomous planning** — Uses ReAct loop for intelligent task execution
- **Safety-first** — Built-in command restrictions, workspace isolation, and dangerous command blocking

## Quick Start

1. Install LangTARS through LangBot's plugin system
2. Configure your preferred LLM model for task planning
3. Start controlling your Mac via IM messages!

## Main Command

### `!tars auto` — Autonomous Task Planning

This is the **primary command** that makes LangTARS special. Simply describe what you want to do, and the AI will autonomously plan and execute the task using available tools.

```
!tars auto 帮我下载一个文件到桌面
!tars auto open Safari and navigate to github
!tars auto 帮我整理桌面上的文件
```

The AI will:
1. Understand your request
2. Plan the necessary steps
3. Execute them one by one using shell commands, file operations, app control, etc.
4. Report back with results

You can **stop** a running task at any time:
```
!tars stop
```

Check task status:
```
!tars status
```

## Testing Commands

These commands are available for testing and direct control:

| Command | Description |
|---------|-------------|
| `!tars shell <command>` | Execute a shell command |
| `!tars ps [filter]` | List running processes |
| `!tars kill <pid\|name>` | Kill a process |
| `!tars ls [path]` | List directory contents |
| `!tars cat <path>` | Read file content |
| `!tars open <app\|url>` | Open an application or URL |
| `!tars close <app>` | Close an application |
| `!tars apps [limit]` | List running applications |
| `!tars info` | Show system information |

## Configuration

Configure LangTARS through LangBot's settings:

| Option | Description | Default |
|--------|-------------|---------|
| `allowed_users` | User IDs allowed to control this Mac | [] |
| `command_whitelist` | Allowed shell commands (empty = all with restrictions) | [] |
| `workspace_path` | Working directory for file operations | ~/.langtars |
| `enable_shell` | Enable shell command execution | true |
| `enable_process` | Enable process management | true |
| `enable_file` | Enable file operations | true |
| `enable_app` | Enable app control | true |
| `planner_max_iterations` | Max ReAct loop iterations | 5 |
| `planner_model_uuid` | LLM model for task planning | (first available) |
| `planner_rate_limit_seconds` | Rate limit between LLM calls | 1 |
| `planner_auto_load_mcp` | Auto-load MCP tools | true |

## Safety Features

- **Dangerous command blocking** — Commands like `rm -rf /` are blocked by default
- **Workspace isolation** — File operations restricted to configured workspace
- **Command whitelist** — Optionally restrict to specific commands
- **User access control** — Optionally limit to specific users

## Architecture

```
IM Message --> LangBot --> PlannerTool (ReAct Loop) --> Tools --> Mac Actions
```

- **PlannerTool** — ReAct loop for autonomous task planning using LLM
- **Tool Registry** — Dynamic tool loading from MCP servers and plugins
- **Built-in Tools** — Shell, process, file, app control

## License

MIT
