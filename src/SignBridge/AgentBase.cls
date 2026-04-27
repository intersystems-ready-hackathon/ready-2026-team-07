/// Shared base for all SignBridge agents (Orchestrator + four specialist sub-agents).
/// Centralises OPENAI_API_KEY -> Provider construction and the model choice.
Class SignBridge.AgentBase Extends %AI.Agent
{

Parameter PROVIDER = "openai";

Parameter MODEL = "gpt-5-nano";

Method %CreateProvider() As %Status
{
    Set apiKey = $System.Util.GetEnviron("OPENAI_API_KEY")
    If apiKey = "" {
        Quit $$$ERROR($$$GeneralError, "OPENAI_API_KEY is not set")
    }
    Set sc = $$$OK
    Try {
        Set settings = {"api_key": (apiKey)}
        Set ..Provider = ##class(%AI.Provider).Create(..#PROVIDER, settings)
    } Catch ex {
        Set sc = $$$ERROR($$$GeneralError, "Failed to create provider '" _ ..#PROVIDER _ "': " _ ex.DisplayString())
    }
    Quit sc
}

}
