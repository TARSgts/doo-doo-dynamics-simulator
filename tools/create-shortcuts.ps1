param([switch]$SkipDesktop)
$ErrorActionPreference = 'Stop'
$simProject = Split-Path $PSScriptRoot -Parent
$simPython = Join-Path $simProject '.venv\Scripts\pythonw.exe'
$simIcon = Join-Path $simProject 'src\opensim\assets\app-icon.ico'
if (-not (Test-Path -LiteralPath $simPython)) { throw 'Install the desktop app first.' }
if (-not (Test-Path -LiteralPath $simIcon)) { throw 'The application icon is missing.' }

if (-not ('SimulatorShortcutProperties' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class SimulatorShortcutProperties {
    [StructLayout(LayoutKind.Sequential)]
    public struct PropertyKey { public Guid Format; public uint Id; }

    [StructLayout(LayoutKind.Explicit, Size=24)]
    public struct PropertyValue {
        [FieldOffset(0)] public ushort Type;
        [FieldOffset(8)] public IntPtr Text;
    }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface PropertyStore {
        [PreserveSig] int GetCount(out uint count);
        [PreserveSig] int GetAt(uint index, out PropertyKey key);
        [PreserveSig] int GetValue(ref PropertyKey key, out PropertyValue value);
        [PreserveSig] int SetValue(ref PropertyKey key, ref PropertyValue value);
        [PreserveSig] int Commit();
    }

    [DllImport("shell32.dll", CharSet=CharSet.Unicode, PreserveSig=true)]
    private static extern int SHGetPropertyStoreFromParsingName(string path, IntPtr context, uint flags, ref Guid identifier, out PropertyStore store);

    public static void SetApplicationId(string path, string applicationId) {
        Guid identifier = typeof(PropertyStore).GUID;
        PropertyStore store;
        Marshal.ThrowExceptionForHR(SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, 2, ref identifier, out store));
        PropertyKey key = new PropertyKey { Format = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), Id = 5 };
        PropertyValue value = new PropertyValue { Type = 31, Text = Marshal.StringToCoTaskMemUni(applicationId) };
        try {
            Marshal.ThrowExceptionForHR(store.SetValue(ref key, ref value));
            Marshal.ThrowExceptionForHR(store.Commit());
        } finally {
            Marshal.FreeCoTaskMem(value.Text);
            Marshal.FinalReleaseComObject(store);
        }
    }
}
'@
}

$simFolders = @([Environment]::GetFolderPath('Programs'))
if (-not $SkipDesktop) { $simFolders += [Environment]::GetFolderPath('Desktop') }
$simShell = New-Object -ComObject WScript.Shell
foreach ($simFolder in $simFolders) {
    New-Item -ItemType Directory -Path $simFolder -Force | Out-Null
    $simPath = Join-Path $simFolder 'Doo Doo Dynamics Simulator.lnk'
    $simLink = $simShell.CreateShortcut($simPath)
    $simLink.TargetPath = $simPython
    $simLink.Arguments = '-m opensim.desktop'
    $simLink.WorkingDirectory = $simProject
    $simLink.Description = 'Doo Doo Dynamics Simulator — structural and modal simulation'
    $simLink.IconLocation = "$simIcon,0"
    $simLink.Save()
    [SimulatorShortcutProperties]::SetApplicationId($simPath, 'TARSgts.DooDooDynamicsSimulator.1')
    Write-Output "Created shortcut: $simPath"
}
