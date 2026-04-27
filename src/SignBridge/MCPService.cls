/// MCP service that exposes SignBridge.ToolSet over /mcp/signbridge.
/// The actual entry point for clients (Streamlit, langchain-mcp-adapters, etc.)
/// is the orchestrator chat — not the individual tools. Clients should call the
/// orchestrator via the agent chat path. The tool surface is exposed for
/// transparency (judges can list discoverable tools to inspect the architecture).
Class SignBridge.MCPService Extends %AI.MCP.Service
{

Parameter SPECIFICATION = "SignBridge.ToolSet";

}
