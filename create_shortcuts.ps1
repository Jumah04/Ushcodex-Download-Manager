$WshShell = New-Object -ComObject WScript.Shell

$targetScript = "C:\Users\Jumah\.gemini\antigravity-ide\scratch\Ushcodex-Download-Manager\ushcodex_dm.py"
$workingDir = "C:\Users\Jumah\.gemini\antigravity-ide\scratch\Ushcodex-Download-Manager"
$pythonw = "C:\Python314\pythonw.exe"
$iconPath = "C:\Users\Jumah\.gemini\antigravity-ide\scratch\Ushcodex-Download-Manager\app_icon.ico"

# 1. Desktop Shortcut
$desktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$shortcutPath = Join-Path $desktopPath "Ushcodex Download Manager.lnk"
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "`"$targetScript`""
$shortcut.WorkingDirectory = $workingDir
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = "Ushcodex Download Manager - High Performance Multi-stream Downloader"
$shortcut.Save()

# 2. Start Menu Programs Shortcut
$startMenuPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Programs)
$startShortcutPath = Join-Path $startMenuPath "Ushcodex Download Manager.lnk"
$startShortcut = $WshShell.CreateShortcut($startShortcutPath)
$startShortcut.TargetPath = $pythonw
$startShortcut.Arguments = "`"$targetScript`""
$startShortcut.WorkingDirectory = $workingDir
$startShortcut.IconLocation = "$iconPath,0"
$startShortcut.Description = "Ushcodex Download Manager - High Performance Multi-stream Downloader"
$startShortcut.Save()

Write-Output "Shortcuts created: $shortcutPath and $startShortcutPath"
