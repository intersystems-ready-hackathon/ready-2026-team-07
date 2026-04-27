/// SignBridge delegate tools — each tool spawns a specialist sub-agent and returns its JSON output.
/// All methods are ClassMethods so they are discovered correctly by %AI.ToolSet.
Class SignBridge.DelegateTools Extends %AI.Tool
{

Parameter DESCRIPTION = "Delegate-task tools for the SignBridge orchestrator. Each tool spawns a specialist sub-agent (SymptomAnalyzer, HistoryAgent, TriageScorer, InterpreterBriefer) and returns its structured JSON output.";

/// Run the SymptomAnalyzer sub-agent.
/// `intake` is the original patient intake JSON string.
/// `evidence` is the JSON result from KbSearch.
ClassMethod AnalyzeSymptoms(intake As %String, evidence As %String) As %DynamicObject
{
    Set payload = {}
    Do payload.%Set("intake",   ##class(SignBridge.DelegateTools).ParseJsonOrRaw(intake))
    Do payload.%Set("evidence", ##class(SignBridge.DelegateTools).ParseJsonOrRaw(evidence))
    Return ##class(SignBridge.DelegateTools).RunSubAgent("SignBridge.SubAgents.SymptomAnalyzer", payload.%ToJSON())
}

/// Run the HistoryAgent sub-agent.
/// `intake` is the original patient intake JSON string.
/// `sqlResults` is a JSON array of {query, rows} objects.
ClassMethod SummarizeHistory(intake As %String, sqlResults As %String) As %DynamicObject
{
    Set payload = {}
    Do payload.%Set("intake",       ##class(SignBridge.DelegateTools).ParseJsonOrRaw(intake))
    Do payload.%Set("sql_results",  ##class(SignBridge.DelegateTools).ParseJsonOrRaw(sqlResults))
    Return ##class(SignBridge.DelegateTools).RunSubAgent("SignBridge.SubAgents.HistoryAgent", payload.%ToJSON())
}

/// Run the TriageScorer sub-agent (pure-reasoning ESI 1-5 scorer).
/// `intake`, `symptoms`, `history` are JSON strings from the prior steps.
ClassMethod ScoreTriage(intake As %String, symptoms As %String, history As %String) As %DynamicObject
{
    Set payload = {}
    Do payload.%Set("intake",    ##class(SignBridge.DelegateTools).ParseJsonOrRaw(intake))
    Do payload.%Set("symptoms",  ##class(SignBridge.DelegateTools).ParseJsonOrRaw(symptoms))
    Do payload.%Set("history",   ##class(SignBridge.DelegateTools).ParseJsonOrRaw(history))
    Return ##class(SignBridge.DelegateTools).RunSubAgent("SignBridge.SubAgents.TriageScorer", payload.%ToJSON())
}

/// Run the InterpreterBriefer sub-agent.
/// `intake`, `topicKeywords`, `glossaryEvidence`, `triage` are JSON strings.
ClassMethod BuildGlossary(intake As %String, topicKeywords As %String, glossaryEvidence As %String, triage As %String) As %DynamicObject
{
    Set payload = {}
    Do payload.%Set("intake",            ##class(SignBridge.DelegateTools).ParseJsonOrRaw(intake))
    Do payload.%Set("topic_keywords",    ##class(SignBridge.DelegateTools).ParseJsonOrRaw(topicKeywords))
    Do payload.%Set("glossary_evidence", ##class(SignBridge.DelegateTools).ParseJsonOrRaw(glossaryEvidence))
    Do payload.%Set("triage",            ##class(SignBridge.DelegateTools).ParseJsonOrRaw(triage))
    Return ##class(SignBridge.DelegateTools).RunSubAgent("SignBridge.SubAgents.InterpreterBriefer", payload.%ToJSON())
}

/// Generic sub-agent runner: instantiate, init, chat, return parsed JSON content.
ClassMethod RunSubAgent(className As %String, taskJson As %String) As %DynamicObject
{
    Set wrap = {"sub_agent": (className), "ok": 0, "content": ""}
    Try {
        Set agent = $CLASSMETHOD(className, "%New")
        Set sc = agent.%Init()
        If $$$ISERR(sc) {
            Set wrap.error = $SYSTEM.Status.GetErrorText(sc)
            Return wrap
        }
        Set session = agent.CreateSession()
        Set response = agent.Chat(session, taskJson)
        Set wrap.ok = 1
        Try {
            Set parsed = {}.%FromJSON(response.Content)
            Do wrap.%Set("content", parsed)
        } Catch {
            Set wrap.content = response.Content
        }
        Try { Set wrap.tokens = session.GetStats()."total_completion_tokens" } Catch {}
    } Catch ex {
        Set wrap.error = ex.DisplayString()
    }
    Return wrap
}

/// Parse a string as JSON object or array; fall back to the raw string.
ClassMethod ParseJsonOrRaw(s As %String) As %String
{
    If s = "" Return ""
    Try {
        Set obj = {}.%FromJSON(s)
        Return obj
    } Catch {}
    Try {
        Set arr = [].%FromJSON(s)
        Return arr
    } Catch {}
    Return s
}

}
