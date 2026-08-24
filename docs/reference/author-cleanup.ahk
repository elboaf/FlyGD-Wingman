#Persistent
#SingleInstance
SetStoreCapsLockMode, Off
GroupAdd, EVEWindows, EVE -

; --- Root tracking ---
RootKey := ""
RootJustFired := False
LastSigId := ""
LastFinisherWasAlpha := False
RootModeActive := False
ZeroMode := False
ReadyToIncrement := False

; Used slot tracking
UsedNums := {}
UsedAlphas := {}
NextNum := 1
NextAlpha := 1
LastUsedNum := ""
LastUsedAlpha := ""

; --- Keybind defaults ---
KB_GrabSig     := ""
KB_SetRoot     := ""
KB_FormatEnf   := ""
KB_FinH        := ""
KB_Fin13       := ""
KB_Fin1        := ""
KB_Fin2        := ""
KB_Fin3        := ""
KB_Fin4        := ""
KB_Fin5        := ""
KB_Fin6        := ""
KB_FinETag     := ""
KB_FinSlash    := ""
KB_FinN        := ""
KB_FinL        := ""
KB_FinS        := ""
KB_FinC        := ""
KB_ConvertScout := "^+s"   ; Ctrl+Shift+S default

; Maps hotkey string -> label, so we can disable by exact label
HotkeyLabelMap := {}

; Single INI file for everything
IniFile := "eve_bookmark_helper.ini"

; Load or create settings
GoSub, LoadAllSettings
GoSub, RefreshHotkeys
SetTimer, RefreshHotkeys, 10000

; Initialize to Home/Zero mode by default
RootModeActive := True
RootKey := ""
ZeroMode := False
ReadyToIncrement := False
RootJustFired := False
UsedNums := {}
UsedAlphas := {}
NextNum := 1
NextAlpha := 1
LastUsedNum := ""
LastUsedAlpha := ""

Return

ExitScript:
ExitApp
Return

ReloadScript:
Reload
Return

LoadAllSettings:
; Create INI file with defaults if it doesn't exist
IfNotExist, %IniFile%
{
    GoSub, SaveAllSettings
    Return
}

; Load window enabled settings
IniRead, EnabledSection, %IniFile%, Enabled
; No need to store globally, will be read in RefreshHotkeys

; Load keybindings
IniRead, KB_GrabSig,     %IniFile%, Keybinds, GrabSig,   
IniRead, KB_SetRoot,     %IniFile%, Keybinds, SetRoot,   
IniRead, KB_FormatEnf,   %IniFile%, Keybinds, FormatEnf, 
IniRead, KB_FinH,        %IniFile%, Keybinds, FinH,      
IniRead, KB_Fin13,       %IniFile%, Keybinds, Fin13,     
IniRead, KB_Fin1,        %IniFile%, Keybinds, Fin1,      
IniRead, KB_Fin2,        %IniFile%, Keybinds, Fin2,      
IniRead, KB_Fin3,        %IniFile%, Keybinds, Fin3,      
IniRead, KB_Fin4,        %IniFile%, Keybinds, Fin4,      
IniRead, KB_Fin5,        %IniFile%, Keybinds, Fin5,      
IniRead, KB_Fin6,        %IniFile%, Keybinds, Fin6,      
IniRead, KB_FinETag,     %IniFile%, Keybinds, FinETag,   
IniRead, KB_FinSlash,    %IniFile%, Keybinds, FinSlash,  
IniRead, KB_FinN,        %IniFile%, Keybinds, FinN,      
IniRead, KB_FinL,        %IniFile%, Keybinds, FinL,      
IniRead, KB_FinS,        %IniFile%, Keybinds, FinS,      
IniRead, KB_FinC,        %IniFile%, Keybinds, FinC,      
IniRead, KB_ConvertScout, %IniFile%, Keybinds, ConvertScout, ^+s
Return

SaveAllSettings:
; Save all keybindings
IniWrite, %KB_GrabSig%,     %IniFile%, Keybinds, GrabSig
IniWrite, %KB_SetRoot%,     %IniFile%, Keybinds, SetRoot
IniWrite, %KB_FormatEnf%,   %IniFile%, Keybinds, FormatEnf
IniWrite, %KB_FinH%,        %IniFile%, Keybinds, FinH
IniWrite, %KB_Fin13%,       %IniFile%, Keybinds, Fin13
IniWrite, %KB_Fin1%,        %IniFile%, Keybinds, Fin1
IniWrite, %KB_Fin2%,        %IniFile%, Keybinds, Fin2
IniWrite, %KB_Fin3%,        %IniFile%, Keybinds, Fin3
IniWrite, %KB_Fin4%,        %IniFile%, Keybinds, Fin4
IniWrite, %KB_Fin5%,        %IniFile%, Keybinds, Fin5
IniWrite, %KB_Fin6%,        %IniFile%, Keybinds, Fin6
IniWrite, %KB_FinETag%,     %IniFile%, Keybinds, FinETag
IniWrite, %KB_FinSlash%,    %IniFile%, Keybinds, FinSlash
IniWrite, %KB_FinN%,        %IniFile%, Keybinds, FinN
IniWrite, %KB_FinL%,        %IniFile%, Keybinds, FinL
IniWrite, %KB_FinS%,        %IniFile%, Keybinds, FinS
IniWrite, %KB_FinC%,        %IniFile%, Keybinds, FinC
IniWrite, %KB_ConvertScout%, %IniFile%, Keybinds, ConvertScout

; Save window enabled settings (preserve existing if any)
Loop % GuiWinTotalControls
{
    WinTitle := WinControlIndex%A_Index%
    VarName := "WCB" . A_Index
    GuiControlGet, Val, Main:, %VarName%
    IniWrite, %Val%, %IniFile%, Enabled, %WinTitle%
}
Return

SaveWindowSettings:
; Save only window enabled settings
Loop % GuiWinTotalControls
{
    WinTitle := WinControlIndex%A_Index%
    VarName := "WCB" . A_Index
    GuiControlGet, Val, Main:, %VarName%
    IniWrite, %Val%, %IniFile%, Enabled, %WinTitle%
}
Return

KBDisplay(kb) {
    if (kb = "")
        return "(none)"
    
    Display := kb
    
    ; Handle modifier prefixes at the start of the string
    ; Process them in order, removing each as we go
    Modifiers := ""
    
    ; Check for Ctrl (^)
    while (SubStr(Display, 1, 1) = "^") {
        Modifiers .= "Ctrl+"
        Display := SubStr(Display, 2)
    }
    
    ; Check for Alt (!)
    while (SubStr(Display, 1, 1) = "!") {
        Modifiers .= "Alt+"
        Display := SubStr(Display, 2)
    }
    
    ; Check for Shift (+)
    while (SubStr(Display, 1, 1) = "+") {
        Modifiers .= "Shift+"
        Display := SubStr(Display, 2)
    }
    
    ; Handle special vk codes (these are for punctuation keys)
    ; Only do this if the remaining Display starts with "vk"
    if (SubStr(Display, 1, 2) = "vk") {
        if (Display = "vkDE")
            Display := "'"
        else if (Display = "vkBC")
            Display := ","
        else if (Display = "vkBE")
            Display := "."
        else if (Display = "vkBF")
            Display := "/"
        else if (Display = "vkC0")
            Display := "`"
        else if (Display = "vk3B")
            Display := ";"
        else if (Display = "vkDB")
            Display := "["
        else if (Display = "vkDD")
            Display := "]"
        else if (Display = "vkDC")
            Display := "\"
        else if (Display = "vkBD")
            Display := "-"
        else if (Display = "vkBB")
            Display := "="
    }
    
    ; Handle the backtick escape if present
    if (Display = "``")
        Display := "`"
    
    ; Return modifiers + key
    return Modifiers . Display
}

ShowRootTooltip:
if (RootModeActive) {
    NextNumDisplay   := BuildSystemKey(RootKey, NextNum,   False)
    NextAlphaDisplay := BuildSystemKey(RootKey, NextAlpha, True)
    if (RootKey = "")
        TipText := "root: home mode`nnext num: " . NextNumDisplay . "  next alpha: " . NextAlphaDisplay
    else
        TipText := "root: " . RootKey . "`nnext num: " . NextNumDisplay . "  next alpha: " . NextAlphaDisplay
} else {
    TipText := "root: not set"
}
ToolTip, %TipText%
SetTimer, RemoveTooltip, -2500
Return

RemoveTooltip:
ToolTip
Return

RefreshHotkeys:
; Step 1: First, disable ALL hotkeys (global ones too)
Hotkey, IfWinActive
; Disable all hotkeys that might be registered
For hk, lbl in HotkeyLabelMap
{
    if (hk != "")
        Hotkey, %hk%, Off, UseErrorLevel
}

; Step 2: Read all enabled windows
IniRead, EnabledSection, %IniFile%, Enabled

; Step 3: Build the new label map (only non-empty bindings)
HotkeyLabelMap := {}
if (KB_GrabSig != "")
    HotkeyLabelMap[KB_GrabSig]   := "DoQ"
if (KB_SetRoot != "")
    HotkeyLabelMap[KB_SetRoot]   := "DoSemi"
if (KB_FormatEnf != "")
    HotkeyLabelMap[KB_FormatEnf] := "DoE"
if (KB_ConvertScout != "")
    HotkeyLabelMap[KB_ConvertScout] := "DoConvertScout"
if (KB_FinH != "")
    HotkeyLabelMap[KB_FinH]      := "DoY"
if (KB_Fin13 != "")
    HotkeyLabelMap[KB_Fin13]     := "DoO"
if (KB_Fin1 != "")
    HotkeyLabelMap[KB_Fin1]      := "Do1"
if (KB_Fin2 != "")
    HotkeyLabelMap[KB_Fin2]      := "Do2"
if (KB_Fin3 != "")
    HotkeyLabelMap[KB_Fin3]      := "Do3"
if (KB_Fin4 != "")
    HotkeyLabelMap[KB_Fin4]      := "Do4"
if (KB_Fin5 != "")
    HotkeyLabelMap[KB_Fin5]      := "Do5"
if (KB_Fin6 != "")
    HotkeyLabelMap[KB_Fin6]      := "Do6"
if (KB_FinETag != "")
    HotkeyLabelMap[KB_FinETag]   := "DoQuote"
if (KB_FinSlash != "")
    HotkeyLabelMap[KB_FinSlash]  := "DoComma"
if (KB_FinN != "")
    HotkeyLabelMap[KB_FinN]      := "DoDot"
if (KB_FinL != "")
    HotkeyLabelMap[KB_FinL]      := "DoP"
if (KB_FinS != "")
    HotkeyLabelMap[KB_FinS]      := "DoS"
if (KB_FinC != "")
    HotkeyLabelMap[KB_FinC]      := "DoC"

; Step 4: Register window-specific hotkeys for enabled windows
Loop, Parse, EnabledSection, `n, `r
{
    Line := Trim(A_LoopField)
    if (Line = "")
        continue
    EqPos := InStr(Line, "=")
    if (!EqPos)
        continue
    WinTitle := Trim(SubStr(Line, 1, EqPos - 1))
    Val      := Trim(SubStr(Line, EqPos + 1))
    
    if (Val = "1") {
        Hotkey, IfWinActive, %WinTitle%
        ; Register all hotkeys
        if (KB_GrabSig != "")
            Hotkey, %KB_GrabSig%, DoQ, On UseErrorLevel
        if (KB_SetRoot != "")
            Hotkey, %KB_SetRoot%, DoSemi, On UseErrorLevel
        if (KB_FormatEnf != "")
            Hotkey, %KB_FormatEnf%, DoE, On UseErrorLevel
        if (KB_ConvertScout != "")
            Hotkey, %KB_ConvertScout%, DoConvertScout, On UseErrorLevel
        if (KB_FinH != "")
            Hotkey, %KB_FinH%, DoY, On UseErrorLevel
        if (KB_Fin13 != "")
            Hotkey, %KB_Fin13%, DoO, On UseErrorLevel
        if (KB_Fin1 != "")
            Hotkey, %KB_Fin1%, Do1, On UseErrorLevel
        if (KB_Fin2 != "")
            Hotkey, %KB_Fin2%, Do2, On UseErrorLevel
        if (KB_Fin3 != "")
            Hotkey, %KB_Fin3%, Do3, On UseErrorLevel
        if (KB_Fin4 != "")
            Hotkey, %KB_Fin4%, Do4, On UseErrorLevel
        if (KB_Fin5 != "")
            Hotkey, %KB_Fin5%, Do5, On UseErrorLevel
        if (KB_Fin6 != "")
            Hotkey, %KB_Fin6%, Do6, On UseErrorLevel
        if (KB_FinETag != "")
            Hotkey, %KB_FinETag%, DoQuote, On UseErrorLevel
        if (KB_FinSlash != "")
            Hotkey, %KB_FinSlash%, DoComma, On UseErrorLevel
        if (KB_FinN != "")
            Hotkey, %KB_FinN%, DoDot, On UseErrorLevel
        if (KB_FinL != "")
            Hotkey, %KB_FinL%, DoP, On UseErrorLevel
        if (KB_FinS != "")
            Hotkey, %KB_FinS%, DoS, On UseErrorLevel
        if (KB_FinC != "")
            Hotkey, %KB_FinC%, DoC, On UseErrorLevel
    }
}

; Step 5: Reset the hotkey context
Hotkey, IfWinActive
Return

BuildSystemKey(root, counter, isAlpha) {
    if (isAlpha)
        return root . Chr(64 + counter)
    else
        return root . counter
}

FindNextNum() {
    global UsedNums, NextNum
    while (UsedNums[NextNum])
        NextNum++
}

FindNextAlpha() {
    global UsedAlphas, NextAlpha
    while (UsedAlphas[NextAlpha])
        NextAlpha++
}

FireRootFinisher(finChar, isAlpha) {
    global RootKey, RootJustFired, LastSigId, LastFinisherWasAlpha
    global UsedNums, UsedAlphas, NextNum, NextAlpha
    global ReadyToIncrement, LastUsedNum, LastUsedAlpha

    if (isAlpha) {
        if (ReadyToIncrement) {
            ; Use next available and mark as used
            SysKey := BuildSystemKey(RootKey, NextAlpha, True)
            UsedAlphas[NextAlpha] := True
            LastUsedAlpha := NextAlpha
            FindNextAlpha()
        } else {
            ; Correct-in-place: reuse last used alpha
            if (LastUsedAlpha = "")
                LastUsedAlpha := NextAlpha
            SysKey := BuildSystemKey(RootKey, LastUsedAlpha, True)
        }
    } else {
        if (ReadyToIncrement) {
            ; Use next available and mark as used
            SysKey := BuildSystemKey(RootKey, NextNum, False)
            UsedNums[NextNum] := True
            LastUsedNum := NextNum
            FindNextNum()
        } else {
            ; Correct-in-place: reuse last used number
            if (LastUsedNum = "")
                LastUsedNum := NextNum
            SysKey := BuildSystemKey(RootKey, LastUsedNum, False)
        }
    }

    Result := SysKey . LastSigId . " " . finChar
    StringUpper, Result, Result
    Clipboard := Result
    ClipWait, 2

    if (!ReadyToIncrement) {
        Send ^a
        Sleep 50
    }

    Sleep 50
    Send ^v

    ReadyToIncrement     := False
    RootJustFired        := True
    LastFinisherWasAlpha := isAlpha
}

GetFirstField(line) {
    TabPos := InStr(line, "`t")
    if (TabPos > 0)
        return Trim(SubStr(line, 1, TabPos - 1))
    return Trim(line)
}

CountValidBookmarkLines(clip) {
    count := 0
    Loop, Parse, clip, `n, `r
    {
        Line := Trim(A_LoopField)
        if (Line = "")
            continue
        FirstField := GetFirstField(Line)
        if (FirstField = "")
            continue
        StringUpper, FirstField, FirstField
        HyphenPos := InStr(FirstField, "-")
        if (HyphenPos >= 2) {
            AfterHyphen := SubStr(FirstField, HyphenPos + 1)
            if (AfterHyphen ~= "^[A-Z]{3}")
                count++
        } else if (FirstField ~= "^[A-Z0-9]+$" && StrLen(FirstField) <= 10) {
            count++
        }
    }
    return count
}

AllPrefixesSingle(clip) {
    foundAny := False
    Loop, Parse, clip, `n, `r
    {
        Line := Trim(A_LoopField)
        if (Line = "")
            continue
        FirstField := GetFirstField(Line)
        if (FirstField = "")
            continue
        StringUpper, FirstField, FirstField
        HyphenPos := InStr(FirstField, "-")
        if (HyphenPos < 2)
            continue
        Prefix := SubStr(FirstField, 1, HyphenPos - 1)
        AfterHyphen := SubStr(FirstField, HyphenPos + 1)
        if (AfterHyphen ~= "^[A-Z]{3}") {
            foundAny := True
            if !(Prefix ~= "^[A-Z0-9]$")
                return False
        }
    }
    return foundAny
}

DoQ:
Send ^c
Sleep 100
ClipWait, 2
ClipSaved := Clipboard
ClipTrim := SubStr(ClipSaved, 1, 3)
Clipboard := "-" . ClipTrim . " "
LastSigId := "-" . ClipTrim
ReadyToIncrement := True
RootJustFired := False
Return

DoSemi:
Clipboard := ""
Send ^c
Sleep 100
ClipWait, 2, 1
ClipSaved := Clipboard
RootKey              := ""
RootJustFired        := False
LastFinisherWasAlpha := False
RootModeActive       := False
ZeroMode             := False
ReadyToIncrement     := False
UsedNums             := {}
UsedAlphas           := {}
NextNum              := 1
NextAlpha            := 1
LastUsedNum          := ""
LastUsedAlpha        := ""
if (ClipSaved = "") {
    RootModeActive := True
    GoSub, ShowRootTooltip
    Return
}
ValidCount := CountValidBookmarkLines(ClipSaved)
if (ValidCount > 1 && AllPrefixesSingle(ClipSaved)) {
    RootKey        := ""
    RootModeActive := True
    ZeroMode       := True
} else {
    Loop, Parse, ClipSaved, `n, `r
    {
        Line := Trim(A_LoopField)
        if (Line = "")
            continue
        FirstField := GetFirstField(Line)
        if (FirstField = "")
            continue
        StringUpper, FirstField, FirstField
        if (FirstField ~= "^[A-Z0-9]+$" && StrLen(FirstField) <= 10) {
            RootKey        := FirstField
            RootModeActive := True
            ZeroMode       := False
            Break
        }
        HyphenPos := InStr(FirstField, "-")
        if (HyphenPos < 2)
            continue
        Prefix      := SubStr(FirstField, 1, HyphenPos - 1)
        AfterHyphen := SubStr(FirstField, HyphenPos + 1)
        if (AfterHyphen ~= "^[A-Z]{3}") {
            RootKey        := Prefix
            RootModeActive := True
            ZeroMode       := False
            Break
        }
    }
}
if (!RootModeActive) {
    HyphenPos := InStr(ClipSaved, "-")
    if (HyphenPos > 1) {
        RootKey        := SubStr(ClipSaved, 1, HyphenPos - 1)
        StringUpper, RootKey, RootKey
        RootModeActive := True
        ZeroMode       := False
        Clipboard      := RootKey
    }
    GoSub, ShowRootTooltip
    Return
}
Loop, Parse, ClipSaved, `n, `r
{
    Line := Trim(A_LoopField)
    if (Line = "")
        continue
    FirstField := GetFirstField(Line)
    if (FirstField = "")
        continue
    HyphenPos := InStr(FirstField, "-")
    if (HyphenPos < 2)
        continue
    Prefix := SubStr(FirstField, 1, HyphenPos - 1)
    StringUpper, Prefix, Prefix
    if (ZeroMode) {
        if (Prefix ~= "^\d$")
            UsedNums[Prefix + 0] := True
        else if (Prefix ~= "^[A-Z]$")
            UsedAlphas[Asc(Prefix) - 64] := True
    } else {
        if (SubStr(Prefix, 1, StrLen(RootKey)) != RootKey)
            continue
        KeySuffix := SubStr(Prefix, StrLen(RootKey) + 1)
        if (KeySuffix = "")
            continue
        if (KeySuffix ~= "^\d+$")
            UsedNums[KeySuffix + 0] := True
        else if (KeySuffix ~= "^[A-Z]$")
            UsedAlphas[Asc(KeySuffix) - 64] := True
    }
}
FindNextNum()
FindNextAlpha()
Clipboard := RootKey
GoSub, ShowRootTooltip
Return

DoConvertScout:
; Read current clipboard
ClipSaved := ClipboardAll
Clipboard := ""
Send ^c
ClipWait, 2
if (ErrorLevel) {
    Clipboard := ClipSaved
    ClipSaved := ""
    ToolTip, Failed to copy clipboard content
    SetTimer, RemoveTooltip, -1500
    Return
}

InputText := Clipboard
Clipboard := ClipSaved
ClipSaved := ""

; Process each line
OutputLines := ""
ConvertedCount := 0
Loop, Parse, InputText, `n, `r
{
    Line := Trim(A_LoopField)
    if (Line = "")
        continue
    
    ; Check if this is an EvE-Scout bookmark
    if (InStr(Line, "EvE-Scout") || InStr(Line, "EVE-Scout")) {
        ; Extract the signature ID (format like XXX-### or similar)
        ; Look for pattern: letters/hyphen/numbers at the start of the line
        SigId := ""
        
        ; Try to match pattern: any characters until first space or tab
        ; But specifically, look for something like "FSV-922"
        FirstSpace := InStr(Line, " ")
        FirstTab := InStr(Line, "`t")
        
        ; Find the earliest delimiter
        DelimPos := 0
        if (FirstSpace > 0)
            DelimPos := FirstSpace
        if (FirstTab > 0 && (FirstTab < DelimPos || DelimPos = 0))
            DelimPos := FirstTab
        
        if (DelimPos > 0) {
            SigId := Trim(SubStr(Line, 1, DelimPos - 1))
        } else {
            ; No delimiter found, use whole line but try to extract first word
            ; Split by any whitespace
            SigId := RegExMatch(Line, "^\S+", Match) ? Match : Line
        }
        
        ; Additional cleanup: if SigId contains parentheses or extra text, try to extract just the first token
        ; Sometimes the bookmark might have format like "FSV-922" - keep only alphanumeric + hyphen
        ; But don't over-clean - the signature ID should be something like "FSV-922"
        
        ; Build the probe scanner formatted line
        ; Format: SIGID<TAB>Cosmic Signature<TAB>Wormhole<TAB>Unstable Wormhole<TAB>100.0%<TAB>98 km
        if (SigId != "") {
            OutputLines .= SigId . "`tCosmic Signature`tWormhole`tUnstable Wormhole`t100.0%`t98 km`n"
            ConvertedCount++
        }
    }
}

; Remove trailing newline
OutputLines := RegExReplace(OutputLines, "`n$")

if (OutputLines = "") {
    ToolTip, No EvE-Scout bookmarks found in clipboard
    SetTimer, RemoveTooltip, -1500
    Return
}

; Replace clipboard with converted content
Clipboard := OutputLines
ToolTip, Converted %ConvertedCount% EvE-Scout bookmarks to probe format
SetTimer, RemoveTooltip, -2000
Return

DoE:
NewSuffix := ""
NewE := 0
NewSlash := 0
NewFFlag := 0
NewC := 0
GoSub, ReadField
StringUpper, ClipUpper, ClipRaw
GoSub, FormatClipAndPaste
Return

DoY:
if (RootModeActive) {
    FinChar := GetKeyState("CapsLock", "T") ? "h" : "H"
    FireRootFinisher(FinChar, True)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := GetKeyState("CapsLock", "T") ? "h" : "H"
    NewE := 0
    NewSlash := 0
    NewFFlag := 0
    NewC := 0
    GoSub, FormatClipAndPaste
}
Return

DoO:
if (RootModeActive) {
    FireRootFinisher("13", False)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := "13"
    NewE := 0
    NewSlash := 0
    NewFFlag := 0
    NewC := 0
    GoSub, FormatClipAndPaste
}
Return

DoP:
if (RootModeActive) {
    FinChar := GetKeyState("CapsLock", "T") ? "l" : "L"
    FireRootFinisher(FinChar, True)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := GetKeyState("CapsLock", "T") ? "l" : "L"
    NewE := 0
    NewSlash := 0
    NewFFlag := 0
    NewC := 0
    GoSub, FormatClipAndPaste
}
Return

DoDot:
if (RootModeActive) {
    FinChar := GetKeyState("CapsLock", "T") ? "n" : "N"
    FireRootFinisher(FinChar, True)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := GetKeyState("CapsLock", "T") ? "n" : "N"
    NewE := 0
    NewSlash := 0
    NewFFlag := 0
    NewC := 0
    GoSub, FormatClipAndPaste
}
Return

DoS:
GoSub, ReadField
StringUpper, ClipUpper, ClipRaw
NewSuffix := ""
NewE := 0
NewSlash := 0
NewFFlag := 1
NewC := 0
GoSub, FormatClipAndPaste
Return

DoC:
GoSub, ReadField
StringUpper, ClipUpper, ClipRaw
NewSuffix := ""
NewE := 0
NewSlash := 0
NewFFlag := 0
NewC := 1
GoSub, FormatClipAndPaste
Return

Do1:
if (RootModeActive) {
    FireRootFinisher("1", False)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := "1"
    NewE := 0
    NewSlash := 0
    NewFFlag := 0
    NewC := 0
    GoSub, FormatClipAndPaste
}
Return

Do2:
if (RootModeActive) {
    FireRootFinisher("2", False)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := "2"
    NewE := 0
    NewSlash := 0
    NewFFlag := 0
    NewC := 0
    GoSub, FormatClipAndPaste
}
Return

Do3:
if (RootModeActive) {
    FireRootFinisher("3", False)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := "3"
    NewE := 0
    NewSlash := 0
    NewFFlag := 0
    NewC := 0
    GoSub, FormatClipAndPaste
}
Return

Do4:
if (RootModeActive) {
    FireRootFinisher("4", False)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := "4"
    NewE := 0
    NewSlash := 0
    NewFFlag := 0
    NewC := 0
    GoSub, FormatClipAndPaste
}
Return

Do5:
if (RootModeActive) {
    FireRootFinisher("5", False)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := "5"
    NewE := 0
    NewSlash := 0
    NewFFlag := 0
    NewC := 0
    GoSub, FormatClipAndPaste
}
Return

Do6:
if (RootModeActive) {
    FireRootFinisher("6", False)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := "6"
    NewE := 0
    NewSlash := 0
    NewFFlag := 0
    NewC := 0
    GoSub, FormatClipAndPaste
}
Return

DoQuote:
GoSub, ReadField
StringUpper, ClipUpper, ClipRaw
NewSuffix := ""
NewE := 1
NewSlash := 0
NewFFlag := 0
NewC := 0
GoSub, FormatClipAndPaste
Return

DoComma:
GoSub, ReadField
StringUpper, ClipUpper, ClipRaw
NewSuffix := ""
NewE := 0
NewSlash := 1
NewFFlag := 0
NewC := 0
GoSub, FormatClipAndPaste
Return

ReadField:
Clipboard := ""
Send ^a
Sleep 50
Send ^c
ClipWait, 2
ClipRaw := Clipboard
Return

FormatClipAndPaste:
global NewFFlag, NewC
Raw := ClipUpper
DashPos := InStr(Raw, "-")
if (DashPos > 0) {
    Prefix := SubStr(Raw, 1, DashPos - 1)
    Rest   := SubStr(Raw, DashPos + 1)
    CleanPrefix := ""
    Loop, Parse, Prefix
    {
        c := A_LoopField
        if (c >= "A" && c <= "Z") || (c >= "0" && c <= "9")
            CleanPrefix .= c
    }
    SysCode      := ""
    RestAfterSys := Rest
    Loop, Parse, Rest
    {
        c := A_LoopField
        if (StrLen(SysCode) < 3) && (c >= "A" && c <= "Z")
            SysCode .= c
        else {
            RestAfterSys := SubStr(Rest, A_Index)
            break
        }
    }
    Base := CleanPrefix . "-" . SysCode
} else {
    Clipboard := Raw
    ClipWait, 2
    Send ^v
    NewSuffix := ""
    NewE      := 0
    NewSlash  := 0
    NewFFlag  := 0
    NewC      := 0
    Return
}
RestAfterSys := RegExReplace(RestAfterSys, "^\s+", "")
ExistingE      := 0
ExistingSlash  := 0
ExistingF      := 0
ExistingC      := 0
ExistingSuffix := ""
Tokens := StrSplit(RestAfterSys, " ")
Loop % Tokens.MaxIndex()
{
    t := Tokens[A_Index]
    if (t = "13" || (StrLen(t) = 1 && (t >= "1" && t <= "6" || t = "H" || t = "L" || t = "N" || t = "T" || t = "D")))
        ExistingSuffix := t
    else if (t = "e" || t = "E")
        ExistingE := 1
    else if (t = "/")
        ExistingSlash := 1
    else if (t = "f" || t = "S")
        ExistingF := 1
    else if (t = "c" || t = "C")
        ExistingC := 1
}

; Apply mutual exclusivity rules
; / and c are mutually exclusive (if setting one, clear the other)
if (NewSlash) {
    NewC := 0
}
if (NewC) {
    NewSlash := 0
}

FinalSuffix := (NewSuffix != "") ? NewSuffix : ExistingSuffix

; f has no conflicts since M was removed
FinalF := (ExistingF || NewFFlag)

; / and c are mutually exclusive
if (NewSlash) {
    FinalSlash := 1
    FinalC := 0
} else if (NewC) {
    FinalSlash := 0
    FinalC := 1
} else {
    if (ExistingSlash && ExistingC) {
        FinalSlash := 0
        FinalC := 1
    } else {
        FinalSlash := ExistingSlash
        FinalC := ExistingC
    }
}

; e can stack with anything, no mutual exclusivity needed
FinalE := (ExistingE || NewE)

Result := Base
if (FinalSuffix != "")
    Result .= " " . FinalSuffix
if (FinalE)
    Result .= " e"
if (FinalSlash)
    Result .= " /"
if (FinalF)
    Result .= " f"
if (FinalC)
    Result .= " c"
Clipboard := Result
ClipWait, 2
Sleep 50
Send ^v
NewSuffix := ""
NewE      := 0
NewSlash  := 0
NewFFlag  := 0
NewC      := 0
Return