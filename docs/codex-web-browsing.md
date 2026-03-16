# Codex web browsing via Bright Data MCP

This project can expose real web browsing to Codex through a Bright Data MCP server.

## What this adds

- Google-style web search from Codex
- Page fetching and scraping
- Structured web data retrieval through MCP tools

## Files added

- `scripts/codex-brightdata-mcp.sh`: local wrapper that launches the Bright Data MCP server

The wrapper avoids storing the API token in the repository or in `~/.codex/config.toml`.

## Required environment variable

Before starting Codex, export your Bright Data token:

```bash
export BRIGHTDATA_API_TOKEN="your-token-here"
```

## Codex registration

Register the MCP server once:

```bash
codex mcp add brightdata-web -- /home/cundo/Bureau/job-search-automation-package/scripts/codex-brightdata-mcp.sh
```

Check that Codex sees it:

```bash
codex mcp list
codex mcp get brightdata-web
```

## Usage

Start Codex normally after exporting the token. The agent can then use Bright Data MCP tools for web search and scraping.

If you only need native search and not external scraping, Codex also supports:

```bash
codex --search
```
