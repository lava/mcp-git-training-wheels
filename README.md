# MCP Git Training Wheels

LLMs try to please, but as the context window gets larger and larger, errors
start to happen. In particular, current models have a tendency to just
`git add -a` the whole source tree, accidentally adding lots of random stuff
to their commits.

These issues become especially noticable when multiple agents are working on
a codebase in parallel, or if you're doing quick fixes while an agent is working.
And no current model has the ability to un-fuck a git history.

This MCP server gives the agent some training wheels for using git safely,. It
ensures that only a specific named set of files can be committed, and also
provides a convenient way to fixup earlier commits.

## Installation

### Using uv

```bash
uv pip install mcp-git-training-wheels
```

### From source

```bash
git clone https://github.com/yourusername/mcp-git-training-wheels
cd mcp-git-training-wheels
uv pip install -e .
```

## Usage

### Add the following

Depending on your agent of choice, run something like the following

```sh
claude mcp add git-commit -- uvx mcp-git-training-wheels
```

or drop the following JSON into `.mcp.json` or any other location of your
choice.

```json
{
  "mcpServers": {
    "gtw": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "mcp-git-training-wheels"
      ],
      "env": {}
    }
  }
}
```

The specific command may change depending on your installation method.

### Available Tools

#### git_commit

Commits specified files with a message and saves the commit information for
later use.

**Parameters:**

- `files`: List of file paths to commit
- `message`: Commit message

**Example:**

```json
{
  "tool": "git_commit",
  "parameters": {
    "files": ["src/main.py", "tests/test_main.py"],
    "message": "Add main functionality and tests"
  }
}
```

#### fixup_commit

Adds files to a previously created commit. If the commit is still HEAD, it
uses `git commit --amend`. Otherwise, it uses the `gitrevise` module to edit
the commit in history.

**Parameters:**

- `files`: List of file paths to add to the commit

**Example:**

```json
{
  "tool": "fixup_commit",
  "parameters": {
    "files": ["src/utils.py"]
  }
}
```
