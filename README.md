# MCP File Server

An MCP server for reading and writing files from your local file system. This server can be used with Claude for Desktop or any other MCP client to provide file system access for AI assistants.

## Features

- List files and directories
- Read file contents
- Write content to files
- Delete files and directories
- Execute commands inside the container

## Prerequisites

- Docker installed on your system
- Git (optional, for cloning the repository)

## Setup and Deployment

### Option 1: Using Docker Compose (Recommended)

1. Clone this repository:
   ```bash
   git clone https://github.com/abhishekloiwal/mcp-file-server.git
   cd mcp-file-server
   ```

2. Edit the `docker-compose.yml` file to update the volume mount path if needed. By default, it's set to:
   ```yaml
   volumes:
     - /Users/abhishekloiwal/CascadeProjects/ClaudeProjects:/data
   ```
   Replace with your desired local path if different.

3. Deploy with Docker Compose:
   ```bash
   docker-compose up -d
   ```

### Option 2: Using Docker directly

1. Clone the repository:
   ```bash
   git clone https://github.com/abhishekloiwal/mcp-file-server.git
   cd mcp-file-server
   ```

2. Build the Docker image:
   ```bash
   docker build -t mcp-file-server .
   ```

3. Run the container with your local directory mounted:
   ```bash
   docker run -d --name mcp-file-server -v /Users/abhishekloiwal/CascadeProjects/ClaudeProjects:/data mcp-file-server
   ```
   Replace the path with your desired local directory path.

## Connecting to Claude for Desktop

1. Create or update your Claude for Desktop configuration file at:
   - Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%AppData%\Claude\claude_desktop_config.json`

2. Add the mcp-file-server to your configuration:
   ```json
   {
     "mcpServers": {
       "file-server": {
         "command": "docker",
         "args": ["exec", "-i", "mcp-file-server", "python", "server.py"]
       }
     }
   }
   ```

3. Restart Claude for Desktop.

4. You should now see the file-server tools available in Claude.

## Available Tools

The following tools are available through this MCP server:

- `list_files`: List all files in a directory
- `read_file`: Read the contents of a file
- `write_file`: Write content to a file
- `delete_file`: Delete a file or directory
- `run_command`: Run a shell command with optional STDIN and get STDOUT/STDERR

### `run_command` examples

- Basic:
  - Command: `hostname`
  - Returns: JSON with `stdout`, `stderr`, `exit_code`.

- List files (with options):
  - Command: `ls -al`
  - Optional `cwd`: relative to the mounted base directory (`/data`).

- Pass text via STDIN:
  - Command: `cat >> notes/todo.txt`
  - STDIN: `Buy milk\nCall Alice\n`
  - Effect: Appends the STDIN text into `notes/todo.txt`.

- Send code to a REPL via STDIN:
  - Command: `python -`
  - STDIN: `print('hello from stdin')\n`
  - Note: Any program that reads from STDIN (e.g., `bash`, `sh`, `python`) can receive code/text this way.

#### Timeouts

- By default, commands time out after 60 seconds.
- You can control timeouts with either:
  - `timeout`: seconds (float or string), e.g., `5`.
  - `timeout_ms`: milliseconds (int/float/string), e.g., `5000`.
- Values `<= 0` disable the timeout (run until completion).
- On timeout, the server terminates the entire process group and returns JSON with `timed_out: true` and `timeout_seconds`.

#### Output Limits

- `stdout` and `stderr` are capped at a configurable number of lines (default: 1000) to prevent excessive output.
- The JSON response includes:
  - `truncated`: whether either stream was truncated.
  - `stdout_truncated` / `stderr_truncated`: per-stream truncation flags.
  - `max_lines`: the per-stream cap in effect.

##### Configure line cap

- Environment variable (takes precedence):
  - Set `RUN_COMMAND_MAX_LINES` (or `MAX_OUTPUT_LINES`) to a positive integer.
  - Example: `RUN_COMMAND_MAX_LINES=200`.
- Config file (fallback if env not set):
  - Create a `config.json` next to `server.py` (or set `FILE_SERVER_CONFIG_PATH` to point to a JSON file) with either:
    - Nested:
      ```json
      { "run_command": { "max_lines": 500 } }
      ```
    - Or top-level:
      ```json
      { "max_lines": 500 }
      ```

## License

MIT

## Troubleshooting

- If Claude for Desktop doesn't connect to the server, check the Docker container status:
  ```bash
  docker ps -a | grep mcp-file-server
  ```

- View server logs:
  - Prefer your MCP client's server logs panel when launching via `docker exec`.
  - If running the server as the container's main process, `docker logs mcp-file-server` works as well.

- Make sure the volume is correctly mounted:
  ```bash
  docker inspect mcp-file-server | grep -A 10 Mounts
  ```
