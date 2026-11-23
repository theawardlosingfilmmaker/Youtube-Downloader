' Starts SanTube's server silently (no window, no browser). Runs at Windows sign-in.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run "wscript.exe """ & here & "\Santube.vbs"" background", 0, False
