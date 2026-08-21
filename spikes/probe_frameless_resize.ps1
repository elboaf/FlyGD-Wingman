# spikes/probe_frameless_resize.ps1
#
# Answers the parts of the frameless-resize spike that do NOT need a
# human hand on the mouse, by inspecting the running spike window with
# Win32 calls.
#
# Question 0 -- does the WebView2 child cover the border band? -- is
# decided here rather than inferred. Windows routes WM_NCHITTEST to the
# window under the cursor, so if a Chromium child HWND owns the edge
# pixels the parent's subclass can never see the message. EnumChildWindows
# plus WindowFromPoint settles that without moving anything.
#
# What this canNOT answer, and still needs a person: the cursor SHAPE
# over an edge, whether a drag feels right, and Aero Snap. Those are in
# the spike's own checklist.
#
# Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File probe_frameless_resize.ps1
#         -Title "Frameless resize spike"

param(
  [string]$Title = "Frameless resize spike",
  [string]$ProcessName = "frameless-resize-spike",
  [int]$MinWidth = 880,
  [int]$MinHeight = 560,
  # Stop before anything that MUTATES the window. SetWindowPos and
  # ShowWindow are synchronous cross-process calls: they block until the
  # target's message loop answers, so against a wedged window they hang
  # the probe too and the read-only findings never get printed. Run
  # read-only first, then re-run without it once the window is known good.
  [switch]$ReadOnly
)

$ErrorActionPreference = "Stop"

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;

public struct RECT { public int Left, Top, Right, Bottom; }
public struct POINT { public int X, Y; }

public struct MONITORINFO {
  public int cbSize;
  public RECT rcMonitor;
  public RECT rcWork;
  public int dwFlags;
}

public class Probe {
  [DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
  public static extern IntPtr FindWindow(string cls, string title);

  [DllImport("user32.dll")]
  public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);

  [DllImport("user32.dll")]
  public static extern IntPtr WindowFromPoint(POINT p);

  [DllImport("user32.dll", CharSet=CharSet.Unicode)]
  public static extern int GetClassName(IntPtr hWnd, StringBuilder buf, int max);

  public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);

  [DllImport("user32.dll")]
  public static extern bool EnumChildWindows(IntPtr parent, EnumProc cb, IntPtr lParam);

  [DllImport("user32.dll", SetLastError=true)]
  public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

  [DllImport("user32.dll")]
  public static extern bool ShowWindow(IntPtr hWnd, int cmd);

  [DllImport("user32.dll")]
  public static extern IntPtr MonitorFromWindow(IntPtr hWnd, uint flags);

  [DllImport("user32.dll", CharSet=CharSet.Unicode)]
  public static extern bool GetMonitorInfo(IntPtr hMonitor, ref MONITORINFO mi);

  [DllImport("user32.dll")]
  public static extern bool IsWindowVisible(IntPtr hWnd);

  public static string ClassOf(IntPtr h) {
    var sb = new StringBuilder(256);
    GetClassName(h, sb, sb.Capacity);
    return sb.ToString();
  }
}
"@

function Get-Rect([IntPtr]$h) {
  $r = New-Object RECT
  [void][Probe]::GetWindowRect($h, [ref]$r)
  $r
}

function At([int]$x, [int]$y) {
  $p = New-Object POINT
  $p.X = $x; $p.Y = $y
  [Probe]::WindowFromPoint($p)
}

# ---- locate the window -------------------------------------------------
# MainWindowHandle first, FindWindow only as a fallback. FindWindow was
# tried first and did NOT match this window even though its title is an
# exact match -- so it is not trustworthy here, and the process's own
# view of its main window is.
$hwnd = [IntPtr]::Zero
$proc = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne 0 } |
        Select-Object -First 1
if ($proc) {
  $hwnd = $proc.MainWindowHandle
  Write-Output "found via process '$ProcessName' (pid $($proc.Id))"
} else {
  $hwnd = [Probe]::FindWindow($null, $Title)
  if ($hwnd -ne [IntPtr]::Zero) { Write-Output "found via FindWindow" }
}
if ($hwnd -eq [IntPtr]::Zero) {
  Write-Error "No window for process '$ProcessName' or title '$Title'. Is the spike running?"
  exit 1
}
$rect = Get-Rect $hwnd
# Pull the edges out as plain ints immediately. Reading $rect.Top inline
# can yield a single-element Object[] via PowerShell member enumeration,
# and "+" on an array APPENDS instead of adding -- so the bug shows up
# later as a confusing op_Subtraction failure rather than at the addition.
[int]$L = $rect.Left
[int]$T = $rect.Top
[int]$R = $rect.Right
[int]$B = $rect.Bottom
$w = $R - $L
$h = $B - $T
Write-Output "form hwnd=0x$($hwnd.ToString('x')) class=$([Probe]::ClassOf($hwnd)) rect=$L,$T ${w}x${h}"

# ---- children ----------------------------------------------------------
# A Chromium child docked Fill will report a rect equal to the form's
# client area. If its bounds reach the form's outer edges, it owns the
# pixels the synthetic resize border needs.
Write-Output ""
Write-Output "== child windows =="
$script:children = @()
$cb = [Probe+EnumProc]{
  param($c, $l)
  $cr = Get-Rect $c
  $script:children += [pscustomobject]@{
    Handle  = $c
    Class   = [Probe]::ClassOf($c)
    Rect    = $cr
    Visible = [Probe]::IsWindowVisible($c)
  }
  return $true
}
[void][Probe]::EnumChildWindows($hwnd, $cb, [IntPtr]::Zero)
foreach ($c in $script:children) {
  $cw = $c.Rect.Right - $c.Rect.Left
  $ch = $c.Rect.Bottom - $c.Rect.Top
  Write-Output ("  0x{0:x}  {1,-32} {2},{3} {4}x{5} visible={6}" -f `
    $c.Handle.ToInt64(), $c.Class, $c.Rect.Left, $c.Rect.Top, $cw, $ch, $c.Visible)
}

# ---- QUESTION 0 --------------------------------------------------------
# Probe 2px inside each edge: that is where the synthetic border lives.
Write-Output ""
Write-Output "== QUESTION 0: who owns the border pixels? =="
$mid_x = [int](($L + $R) / 2)
$mid_y = [int](($T + $B) / 2)
# Every arithmetic element is parenthesised deliberately. PowerShell's
# comma binds TIGHTER than +/-, so @($mid_x, $T + 2) parses as
# ($mid_x, $T) + 2 -- an array append that silently succeeds -- and the
# matching subtraction then fails with a baffling op_Subtraction error
# pointing at the whole hashtable.
$points = @{
  "top edge"     = @($mid_x, ($T + 2))
  "bottom edge"  = @($mid_x, ($B - 3))
  "left edge"    = @(($L + 2), $mid_y)
  "right edge"   = @(($R - 3), $mid_y)
  "bottom-right" = @(($R - 3), ($B - 3))
  "centre"       = @($mid_x, $mid_y)
}
$ownedByForm = 0
$ownedByChild = 0
foreach ($name in "top edge","bottom edge","left edge","right edge","bottom-right","centre") {
  $pt = $points[$name]
  $owner = At $pt[0] $pt[1]
  $isForm = ($owner -eq $hwnd)
  if ($name -ne "centre") { if ($isForm) { $ownedByForm++ } else { $ownedByChild++ } }
  $tag = if ($isForm) { "FORM" } else { "child" }
  Write-Output ("  {0,-13} -> 0x{1:x} {2,-28} [{3}]" -f `
    $name, $owner.ToInt64(), [Probe]::ClassOf($owner), $tag)
}
Write-Output ""
if ($ownedByChild -gt 0) {
  Write-Output "  VERDICT: the child owns $ownedByChild of 5 border points."
  Write-Output "  The plain subclass cannot hit-test those. Try --pad 6."
} else {
  Write-Output "  VERDICT: the form owns every border point. Subclass can work."
}

# ---- min-size clamp ----------------------------------------------------
# Shrink far below min_size and see what the window settles at. WinForms
# enforces MinimumSize through WM_GETMINMAXINFO, which only survives if
# the spike chained to the original WndProc before overriding.
if ($ReadOnly) {
  Write-Output ""
  Write-Output "-ReadOnly: skipping the min-size and maximize checks."
  exit 0
}
Write-Output ""
Write-Output "== min-size clamp =="
$SWP_NOMOVE = 0x0002; $SWP_NOZORDER = 0x0004
[void][Probe]::SetWindowPos($hwnd, [IntPtr]::Zero, 0, 0, 400, 300, $SWP_NOMOVE -bor $SWP_NOZORDER)
Start-Sleep -Milliseconds 400
$after = Get-Rect $hwnd
$aw = $after.Right - $after.Left
$ah = $after.Bottom - $after.Top
Write-Output "  asked for 400x300, got ${aw}x${ah} (min_size is ${MinWidth}x${MinHeight} logical)"
if ($aw -le 400 -and $ah -le 300) {
  Write-Output "  MinimumSize was NOT enforced -- check the WM_GETMINMAXINFO chaining order."
} else {
  Write-Output "  clamped, so MinimumSize survived."
}
# put it back
[void][Probe]::SetWindowPos($hwnd, [IntPtr]::Zero, 0, 0, $w, $h, $SWP_NOMOVE -bor $SWP_NOZORDER)
Start-Sleep -Milliseconds 300

# ---- maximize vs the taskbar -------------------------------------------
Write-Output ""
Write-Output "== maximize vs taskbar =="
$mi = New-Object MONITORINFO
$mi.cbSize = [Runtime.InteropServices.Marshal]::SizeOf($mi)
[void][Probe]::GetMonitorInfo([Probe]::MonitorFromWindow($hwnd, 2), [ref]$mi)
$workW = $mi.rcWork.Right - $mi.rcWork.Left
$workH = $mi.rcWork.Bottom - $mi.rcWork.Top
$fullW = $mi.rcMonitor.Right - $mi.rcMonitor.Left
$fullH = $mi.rcMonitor.Bottom - $mi.rcMonitor.Top
Write-Output "  monitor ${fullW}x${fullH}, work area ${workW}x${workH}"

[void][Probe]::ShowWindow($hwnd, 3)   # SW_MAXIMIZE
Start-Sleep -Milliseconds 600
$max = Get-Rect $hwnd
$mw = $max.Right - $max.Left
$mh = $max.Bottom - $max.Top
Write-Output "  maximized to ${mw}x${mh} at $($max.Left),$($max.Top)"
if ($mh -ge $fullH -and $workH -lt $fullH) {
  Write-Output "  COVERS THE TASKBAR -- WM_GETMINMAXINFO clamp did not take effect."
} elseif ($workH -eq $fullH) {
  Write-Output "  inconclusive: the taskbar is hidden or on another monitor."
} else {
  Write-Output "  clamped to the work area, taskbar preserved."
}
[void][Probe]::ShowWindow($hwnd, 9)   # SW_RESTORE
Start-Sleep -Milliseconds 400
Write-Output ""
Write-Output "probe done; the window is left running for the manual checks."
