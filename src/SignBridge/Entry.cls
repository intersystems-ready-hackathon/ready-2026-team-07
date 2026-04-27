/// SignBridge MCP entry-point tool. External clients (Streamlit, langchain-mcp-adapters)
/// call ProcessIntake() with a patient intake JSON and receive the final Markdown brief.
/// All multi-agent orchestration happens server-side inside the IRIS Orchestrator.
Class SignBridge.Entry Extends %AI.Tool
{

Parameter DESCRIPTION = "SignBridge primary entry point. Pass a patient intake JSON, receive a fully-orchestrated pre-visit briefing.";

/// Process a patient intake end-to-end. The orchestrator plans the call sequence,
/// invokes four specialist sub-agents, optionally re-queries the knowledge base
/// when red flags appear, and returns the assembled Markdown brief.
///
/// `intakeJson` must be a JSON object with at least: chief_complaint, duration,
/// age, sign_style. See SignBridge.Orchestrator INSTRUCTIONS for full schema.
ClassMethod ProcessIntake(intakeJson As %String) As %DynamicObject
{
    Set result = {"ok": 0, "brief": "", "activity": []}
    Try {
        Set agent = ##class(SignBridge.Orchestrator).%New()
        Set sc = agent.%Init()
        If $$$ISERR(sc) {
            Set result.error = $SYSTEM.Status.GetErrorText(sc)
            Return result
        }
        Set session = agent.CreateSession()
        Set response = agent.Chat(session, intakeJson)
        Set result.ok = 1
        Set result.brief = response.Content
        Try {
            Set stats = session.GetStats()
            Set tokens = {}
            Set tokens.prompt     = stats."total_prompt_tokens"
            Set tokens.completion = stats."total_completion_tokens"
            Do tokens.%Set("tool_calls", stats."total_tool_calls")
            Do result.%Set("tokens", tokens)
        } Catch {}
    } Catch ex {
        Set result.error = ex.DisplayString()
    }
    Return result
}

}
