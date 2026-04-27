/// ReportWriter — an %AI.Tool that assembles the four specialist outputs into a
/// final pre-visit Markdown brief using an internal sub-agent.
/// Registered on the Orchestrator so the model can call AssembleReport as a tool.
Class SignBridge.ReportWriter Extends %AI.Tool
{

Parameter DESCRIPTION = "Assemble the final pre-visit Markdown brief from the four specialist sub-agent outputs.";

ClassMethod AssembleReport(userRequest As %String) As %DynamicObject
{
    Set result = {"ok": 0, "report": ""}
    Try {
        Set agent = ##class(SignBridge.SubAgents.ReportWriterAgent).%New()
        Set sc = agent.%Init()
        If $$$ISERR(sc) {
            Set result.error = $SYSTEM.Status.GetErrorText(sc)
            Return result
        }
        Set session = agent.CreateSession()
        Set response = agent.Chat(session, userRequest)
        Set result.ok = 1
        Set result.report = response.Content
    } Catch ex {
        Set result.error = ex.DisplayString()
    }
    Return result
}

}
