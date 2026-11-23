# cc-things

Claude Code plugin marketplace.

## Install

```
/plugin marketplace add oleggohman/cc-things
/plugin install mitre-attack@oleggohman-cc-things
/plugin install cloudzone-hava@oleggohman-cc-things
/plugin install whatsapp@oleggohman-cc-things
/plugin install provider-router@oleggohman-cc-things
/plugin install outlook@oleggohman-cc-things
```

Claude organization marketplaces only accept private repositories, so `main` is mirrored to a private copy by `.github/workflows/mirror.yml`; the organization syncs from that copy.

## Plugins

### mitre-attack

MITRE ATT&CK v20 and ATLAS for Claude Code: map incidents, alerts and CloudTrail events to techniques, mitigations, detections and log sources, look up threat groups, and build Navigator layers.

- MCP server: [oleggohman/mitre-attack-mcp](https://github.com/oleggohman/mitre-attack-mcp), run with `uvx`
- Skill: `using-mitre-attack-mcp`, with helper scripts for revoked IDs, detections and Navigator layers

Requires [uv](https://docs.astral.sh/uv/).

### cloudzone-hava

Hava Cloud Diagrams: 47 MCP tools and the `hava-diagrams` skill to list, search, export and manage cloud architecture diagrams for AWS, Azure, GCP and Kubernetes.

- Source: [CLDZE/hava_mcp](https://github.com/CLDZE/hava_mcp), vendored in `plugins/cloudzone-hava`.
- Enter your Hava API token when enabling the plugin (kept in OS secure storage). Turn on read-only mode to hide every tool that changes data.

Requires [uv](https://docs.astral.sh/uv/) and Node.js, plus a Hava Teams/Business plan or self-hosted install.

### whatsapp

Search, read and send your personal WhatsApp messages and media from Claude, through a local Go bridge linked to your account as a device.

- MCP server: [oleggohman/whatsapp-mcp](https://github.com/oleggohman/whatsapp-mcp). It builds and starts the bridge on first use (1-2 minutes).
- Pair once: ask Claude to "pair WhatsApp with &lt;your number&gt;" and enter the code under Linked devices on your phone.
- Messages, session and token are kept in the plugin data folder, so they survive plugin updates.

Requires [uv](https://docs.astral.sh/uv/), Go and a C compiler; `ffmpeg` is optional for voice notes. Review every send call before approving it: an incoming message can carry prompt injection.

### provider-router

Route model requests by prefix (`anthropic:`, `zai:`, `openai:`, `custom:<name>:`) to other providers while unprefixed models stay on your Claude subscription. Works for the main session and subagents in parallel.

- Source: [oleggohman/cc-provider-router](https://github.com/oleggohman/cc-provider-router), a TypeScript mod with no build step.
- API keys and custom endpoints are set in the plugin config when you enable it.

### outlook

List, search and read the mail, contacts and calendar that New Outlook for Mac has cached locally. Read-only, local, no network.

- MCP server: [oleggohman/outlook-mcp](https://github.com/oleggohman/outlook-mcp) with nine read-only tools, plus the `outlook-local-mail` skill.
- On Apple Silicon the launcher downloads a checksum-verified program from the release; otherwise it builds with cargo.

macOS only. Requires New Outlook for Mac; Rust is needed only when there is no prebuilt program for your machine.
