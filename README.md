# LangTARS Plugin

Control your Mac through IM messages using LangBot (like OpenClaw).

## Features

- **Shell Commands**: Execute shell commands safely
- **Process Management**: List and kill running processes
- **File Operations**: Read, write, and search files
- **App Control**: Open and close applications

## Commands

| Command | Description |
|---------|-------------|
| `!tars shell <command>` | Execute a shell command |
| `!tars ps [filter]` | List running processes |
| `!tars kill [name]` | Kill a process |
| `!tars ls [path]` | List directory contents |
| `!tars cat <path>` | Read file content |
| `!tars write <path> <content>` | Write to a file |
| `!tars open <app>` | Open an application |
| `!tars close <app>` | Close an application |
| `!tars top` | List running apps |
| `!tars info` | Show system info |

## Configuration

- `allowed_users`: List of user IDs allowed to control
- `command_whitelist`: Allowed shell commands
- `workspace_path`: Working directory for file operations
- `enable_shell`: Enable/disable shell execution
- `enable_process`: Enable/disable process management
- `enable_file`: Enable/disable file operations
- `enable_app`: Enable/disable app control

## Safety

- Dangerous commands are blocked by default
- Working directory is restricted to workspace
- Command whitelist can be configured
