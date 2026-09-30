Option Explicit
Dim fso, shell, root, executable, python
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)
executable = root & "\dist\Hana\Hana.exe"
python = root & "\.venv\Scripts\pythonw.exe"
If fso.FileExists(executable) Then
    shell.Run Chr(34) & executable & Chr(34) & " --avatar-demo", 0, False
ElseIf fso.FileExists(python) Then
    shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & root & "\hana_avatar.py" & Chr(34), 0, False
Else
    MsgBox "Run setup_hana.bat and build_hana.ps1 first.", 48, "Hana"
End If
