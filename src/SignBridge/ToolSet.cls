/// SignBridge ToolSet — exposes the orchestration tool surface over MCP and to the Orchestrator.
Class SignBridge.ToolSet Extends %AI.ToolSet [ DependsOn = (SignBridge.Tools, SignBridge.DelegateTools, SignBridge.ReportWriter, SignBridge.Entry) ]
{

XData Definition
{
    <ToolSet>
        <Description>Pre-visit triage toolset for SignBridge. RAG retrieval, read-only SQL, four specialist sub-agent delegates, report assembly, and the ProcessIntake MCP entry point.</Description>
        <Include Class="SignBridge.Tools"></Include>
        <Include Class="SignBridge.DelegateTools"></Include>
        <Include Class="SignBridge.ReportWriter"></Include>
        <Include Class="SignBridge.Entry"></Include>
    </ToolSet>
}

}
