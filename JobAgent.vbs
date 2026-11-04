' Job Agent silent launcher.
' Finds a python.exe that can import PySide6, then runs launch.py with pythonw.
Option Explicit
Dim fso, sh, here, cands, i, py, pyw, ok, rc

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)

cands = Array( _
    ReadFirstLine(fso.BuildPath(here, "python.txt")), _
    sh.ExpandEnvironmentStrings("%JOBAGENT_PYTHON%"), _
    fso.BuildPath(here, ".venv\Scripts\python.exe"), _
    "D:\Projects\Code\q_env\Scripts\python.exe", _
    "python.exe")

py = ""
For i = 0 To UBound(cands)
    If Len(cands(i)) > 0 Then
        If Candidate(cands(i)) Then
            py = cands(i)
            Exit For
        End If
    End If
Next

If Len(py) = 0 Then
    MsgBox "No Python with PySide6 found." & vbCrLf & vbCrLf & _
           "Fix: write the interpreter path into python.txt next to JobAgent.vbs," & vbCrLf & _
           "e.g.  D:\Projects\Code\q_env\Scripts\python.exe", 16, "Job Agent"
    WScript.Quit 1
End If

pyw = Replace(py, "python.exe", "pythonw.exe")
If Not fso.FileExists(pyw) Then pyw = py

sh.CurrentDirectory = here
sh.Run """" & pyw & """ """ & fso.BuildPath(here, "launch.py") & """", 0, False

Function ReadFirstLine(p)
    Dim f, s
    ReadFirstLine = ""
    If Not fso.FileExists(p) Then Exit Function
    Set f = fso.OpenTextFile(p, 1)
    If Not f.AtEndOfStream Then s = Trim(f.ReadLine())
    f.Close
    ReadFirstLine = s
End Function

Function Candidate(p)
    Dim rc2
    Candidate = False
    If InStr(p, "\") > 0 Then
        If Not fso.FileExists(p) Then Exit Function
    End If
    On Error Resume Next
    rc2 = sh.Run("""" & p & """ -c ""import PySide6""", 0, True)
    If Err.Number <> 0 Then
        Err.Clear
        On Error GoTo 0
        Exit Function
    End If
    On Error GoTo 0
    If rc2 = 0 Then Candidate = True
End Function