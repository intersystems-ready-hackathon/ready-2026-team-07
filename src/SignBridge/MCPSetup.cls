/// Registers the /mcp/signbridge web application that fronts SignBridge.MCPService.
/// Invoked from module.xml during zpm load.
Class SignBridge.MCPSetup Extends %RegisteredObject
{

ClassMethod Run() As %Status
{
    New $NAMESPACE
    Set $NAMESPACE = "%SYS"
    Do ##class(Security.Applications).Delete("/mcp/signbridge")
    Kill props
    Set props("DispatchClass") = "SignBridge.MCPService"
    Set props("AutheEnabled") = 64    // Unauthenticated — hackathon only
    Set props("Type") = 18             // MCP service type
    Set props("NameSpace") = "IRISAPP"
    Set props("MatchRoles") = ":%All"
    Set sc = ##class(Security.Applications).Create("/mcp/signbridge", .props)
    If $$$ISERR(sc) {
        Write "Error creating SignBridge MCP Service: ", $SYSTEM.Status.GetErrorText(sc), !
        Quit sc
    }
    Write "SignBridge MCP Service created at /mcp/signbridge", !
    Quit $$$OK
}

}
