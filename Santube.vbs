' SanTube: opens the SanTube page. Starts the background server first if it isn't running.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here

Function ServerUp()
    On Error Resume Next
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    http.setTimeouts 1000, 1000, 1000, 1000
    http.Open "POST", "http://127.0.0.1:5000/api/heartbeat", False
    http.Send
    ServerUp = (Err.Number = 0 And http.Status = 200)
    On Error GoTo 0
End Function

If Not ServerUp() Then
    ' 0 = hidden window, False = don't wait
    sh.Run """" & here & "\venv\Scripts\pythonw.exe"" """ & here & "\app.py""", 0, False
    For i = 1 To 60
        WScript.Sleep 500
        If ServerUp() Then Exit For
    Next
End If

If WScript.Arguments.Count = 0 Then sh.Run "http://localhost:5000"
