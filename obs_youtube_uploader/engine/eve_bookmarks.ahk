; ============================================================
; eve_bookmarks.ahk - EVE Bookmark Helper (Flygd/ABH)
; ============================================================
#Persistent
; Force, explicitly: a duplicate spawn must replace the previous copy, not
; raise a prompt for a user who no longer has a GUI to answer it in.
#SingleInstance Force

; Wingman passes /token <value> at spawn and records the same value beside
; the PID. Orphan recovery matches on it before terminating anything, so
; the interpreter running someone else's script is never killed.
RunToken := ""
Loop %0%
{
    Arg := %A_Index%
    if (Arg = "/token" && A_Index < %0%)
    {
        Next := A_Index + 1
        RunToken := %Next%
    }
}

; Unix seconds, to compare against Python's time.time() for staleness.
EpochNow() {
    diff := A_NowUTC
    EnvSub, diff, 19700101000000, Seconds
    return diff
}

SetStoreCapsLockMode, Off
GroupAdd, EVEWindows, EVE -

; Pin the encoding: the app reads this file with encoding="utf-8", and sig
; is three characters taken straight from the clipboard, so a non-ASCII
; signature would otherwise decode differently on each side and show as a
; permanent "stale" readout. UTF-8-RAW is UTF-8 without a BOM -- a BOM
; would make json.loads fail on the first character. Set here, in the
; auto-execute section, so it becomes the default for every later-launched
; thread (including the RefreshStatusTab timer) rather than just this one.
FileEncoding, UTF-8-RAW

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
KB_FinM        := ""
KB_FinS        := ""
KB_FinC        := ""
KB_ConvertScout := "^+s"   ; Ctrl+Shift+S default

; Maps hotkey string -> label, so we can disable by exact label
HotkeyLabelMap := {}

; Window titles whose hotkey variants were registered on the last pass.
; Required for teardown: a variant registered under IfWinActive <title> can
; only be disabled from inside that same criterion.
RegisteredWindows := []
FailedBinds := ""

; Highest command sequence executed from eve_command.ini. Adopted from disk
; before the auto-execute section returns; see ReadCommand.
ConsumedSeq := 0

; Single INI file for everything
IniFile := "eve_bookmark_helper.ini"

; Load or create settings
GoSub, LoadAllSettings
GoSub, RefreshHotkeys
SetTimer, RefreshHotkeys, 10000
SetTimer, RefreshStatusTab, 2000

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

; Adopt whatever sequence is already on disk, so a command left by a
; previous session is not replayed on this one's first tick.
IniRead, StartSeq, eve_command.ini, Command, Seq, 0
ConsumedSeq := StartSeq + 0

Return

LoadAllSettings:
; Wingman owns creating and writing eve_bookmark_helper.ini; the engine must
; only ever read it, never create or rewrite it.
IfNotExist, %IniFile%
    Return

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
IniRead, KB_FinM,        %IniFile%, Keybinds, FinM,      
IniRead, KB_FinS,        %IniFile%, Keybinds, FinS,      
IniRead, KB_FinC,        %IniFile%, Keybinds, FinC,      
IniRead, KB_ConvertScout, %IniFile%, Keybinds, ConvertScout, ^+s
Return

RefreshStatusTab:
GoSub, ReadCommand
if (RootModeActive) {
    RootText     := RootKey = "" ? "(home)" : RootKey
    NextNumText  := BuildSystemKey(RootKey, NextNum,   False)
    NextAlphaText := BuildSystemKey(RootKey, NextAlpha, True)
} else {
    RootText := "", NextNumText := "", NextAlphaText := ""
}
SigText := LastSigId

; Written to a temp name and moved over the target: Wingman polls this at
; ~1Hz and must never read a half-written file.
StatusBody := "{"
    . """sig"":""" . JsonEsc(SigText) . ""","
    . """root"":""" . JsonEsc(RootText) . ""","
    . """next_num"":""" . JsonEsc(NextNumText) . ""","
    . """next_alpha"":""" . JsonEsc(NextAlphaText) . ""","
    . """failed_binds"":[" . JsonList(FailedBinds) . "],"
    . """seq"":" . (ConsumedSeq + 0) . ","
    . """written"":" . EpochNow()
    . "}"
FileDelete, eve_status.json.tmp
FileAppend, %StatusBody%, eve_status.json.tmp
FileMove, eve_status.json.tmp, eve_status.json, 1
Return

; Strip control characters before escaping. json.loads rejects raw
; control characters inside strings, and sig is three characters taken
; straight from the clipboard, so a stray tab or newline is reachable.
; Stripping rather than \uXXXX-escaping: none of these values
; legitimately contains one, and a signature with a tab in it is not
; meaningful. Order matters: strip first, then escape backslashes, then
; quotes -- escaping backslashes after quotes would double-escape the
; backslashes the quote replacement introduces.
JsonEsc(text) {
    clean := ""
    Loop, Parse, text
    {
        code := Asc(A_LoopField)
        if (code >= 32 && code != 127)
            clean .= A_LoopField
    }
    StringReplace, clean, clean, \, \\, All
    StringReplace, clean, clean, ", \", All
    return clean
}

JsonList(csv) {
    if (csv = "")
        return ""
    out := ""
    Loop, Parse, csv, `,
        out .= (out = "" ? "" : ",") . """" . JsonEsc(A_LoopField) . """"
    return out
}

ReadCommand:
IfNotExist, eve_command.ini
    Return
IniRead, CmdSeq,  eve_command.ini, Command, Seq, 0
IniRead, CmdName, eve_command.ini, Command, Name, %A_Space%
IniRead, CmdArg,  eve_command.ini, Command, Argument, %A_Space%
CmdSeq += 0
; Strictly greater: the file is never deleted, so re-running anything at or
; below the last consumed sequence would replay it on every tick.
if (CmdSeq <= ConsumedSeq)
    Return
ConsumedSeq := CmdSeq
if (CmdName = "clear_root")
    GoSub, ClearRoot
else if (CmdName = "set_root")
{
    ManualRoot := Trim(CmdArg)
    GoSub, SetManualRoot
}
Return

; ============================================================
; INTELLIGENT PARSER: Extracts Chain ID, Class, and Sig ID from any format
; ============================================================
ParseBookmark(input) {
    global
    
    ; Step 1: Strip preface (leading non-alphanumeric characters)
    CleanInput := input
    Loop
    {
        FirstChar := SubStr(CleanInput, 1, 1)
        if (FirstChar = "" || FirstChar ~= "[A-Za-z0-9]")
            break
        CleanInput := SubStr(CleanInput, 2)
    }
    
    ; Step 2: Extract all alphanumeric tokens
    Tokens := []
    CurrentToken := ""
    Loop, Parse, CleanInput
    {
        char := A_LoopField
        if (char ~= "[A-Za-z0-9]") {
            CurrentToken .= char
        } else {
            if (CurrentToken != "") {
                Tokens.Push(CurrentToken)
                CurrentToken := ""
            }
        }
    }
    if (CurrentToken != "")
        Tokens.Push(CurrentToken)
    
    ; Step 3: Identify Sig ID (exactly 3 letters)
    SigId := ""
    SigIndex := -1
    For index, token in Tokens
    {
        if (StrLen(token) = 3 && token ~= "^[A-Za-z]+$") {
            ; Found a 3-letter token - this is our sig
            SigId := token
            SigIndex := index
            break
        }
    }
    
    ; Step 4: Identify Class (token that matches class patterns)
    Class := ""
    ClassIndex := -1
    ClassPattern := "^(1|2|3|4|5|6|13|c1|c2|c3|c4|c5|c6|c13|h|hs|l|ls|n|ns|t|d)$"
    
    For index, token in Tokens
    {
        ; Convert to lowercase for comparison
        StringLower, tokenLower, token
        if (tokenLower ~= ClassPattern) {
            ; Don't match if this is the sig
            if (index != SigIndex) {
                Class := tokenLower
                ClassIndex := index
                break
            }
        }
    }
    
    ; Step 5: Chain ID is always the first token
    Chain := ""
    if (Tokens.Length() > 0) {
        Chain := Tokens[1]
    }
    
    ; Return results
    return {chain: Chain, class: Class, sig: SigId, tokens: Tokens}
}

; ============================================================
; FIND COMMON CHAIN: Finds the longest common prefix across all first tokens
; ============================================================
FindCommonChain(firstTokens) {
    if (firstTokens.Length() = 0)
        return ""
    
    if (firstTokens.Length() = 1)
        return firstTokens[1]
    
    ; Start with the shortest token
    Shortest := firstTokens[1]
    For index, token in firstTokens
    {
        if (StrLen(token) < StrLen(Shortest))
            Shortest := token
    }
    
    ; Try to find a chain by progressively stripping characters from the shortest token
    ; Start with the full shortest token, then strip from the end
    Chain := Shortest
    Loop
    {
        ; Check if all tokens start with this chain
        AllMatch := True
        For index, token in firstTokens
        {
            if (SubStr(token, 1, StrLen(Chain)) != Chain) {
                AllMatch := False
                break
            }
        }
        
        if (AllMatch)
            return Chain
        
        ; If we've stripped down to nothing, return the shortest token
        if (StrLen(Chain) <= 1) {
            ; If all tokens start with the same single character, use that
            FirstChar := SubStr(Shortest, 1, 1)
            AllMatch := True
            For index, token in firstTokens
            {
                if (SubStr(token, 1, 1) != FirstChar) {
                    AllMatch := False
                    break
                }
            }
            if (AllMatch)
                return FirstChar
            return Shortest
        }
        
        ; Strip the last character and try again
        Chain := SubStr(Chain, 1, StrLen(Chain) - 1)
    }
    
    return Shortest
}

; ============================================================
; PARSE BOOKMARK WITH SUFFIX: Gets chain, suffix, class, sig from a single line
; ============================================================
ParseBookmarkWithSuffix(input, detectedChain) {
    global
    
    ; First, get the basic parse
    Parsed := ParseBookmark(input)
    Chain := detectedChain
    Class := Parsed.class
    Sig := Parsed.sig
    
    ; If no chain, return empty
    if (Chain = "")
        return {chain: "", suffix: "", class: Class, sig: Sig}
    
    ; Extract the first token
    CleanInput := input
    Loop
    {
        FirstChar := SubStr(CleanInput, 1, 1)
        if (FirstChar = "" || FirstChar ~= "[A-Za-z0-9]")
            break
        CleanInput := SubStr(CleanInput, 2)
    }
    
    ; Get the first alphanumeric token
    FirstToken := ""
    Loop, Parse, CleanInput
    {
        char := A_LoopField
        if (char ~= "[A-Za-z0-9]") {
            FirstToken .= char
        } else {
            if (FirstToken != "")
                break
        }
    }
    if (FirstToken = "")
        FirstToken := Chain
    
    ; Extract the suffix
    Suffix := ""
    if (FirstToken != Chain && SubStr(FirstToken, 1, StrLen(Chain)) = Chain) {
        Suffix := SubStr(FirstToken, StrLen(Chain) + 1)
    }
    
    return {chain: Chain, suffix: Suffix, class: Class, sig: Sig, firstToken: FirstToken}
}

SetManualRoot:
ManualRoot := Trim(ManualRoot)
if (ManualRoot = "") {
    GoSub, ClearRoot
    Return
}

; Parse the input intelligently
Parsed := ParseBookmark(ManualRoot)
RootKey := Parsed.chain

if (RootKey != "") {
    RootModeActive := True
    ZeroMode := False
    ReadyToIncrement := False
    RootJustFired := False
    LastFinisherWasAlpha := False
    UsedNums := {}
    UsedAlphas := {}
    NextNum := 1
    NextAlpha := 1
    LastUsedNum := ""
    LastUsedAlpha := ""
    
    ; Build display root
    DisplayRoot := RootKey

    Clipboard := DisplayRoot
    GoSub, ShowRootTooltip
    Return
}

GoSub, ShowRootTooltip
Return

ClearRoot:
RootKey          := ""
RootModeActive   := True
ZeroMode         := False
ReadyToIncrement := False
RootJustFired    := False
UsedNums         := {}
UsedAlphas       := {}
NextNum          := 1
NextAlpha        := 1
LastUsedNum      := ""
LastUsedAlpha    := ""
ToolTip, Root cleared - now in Home/Zero mode
SetTimer, RemoveTooltip, -1500
GoSub, ShowRootTooltip
Return

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
GoSub, LoadAllSettings          ; hot reload: keybinds and settings, not just [Enabled]

; Disable the global-context variants. Permanently dead now: nothing is ever
; registered globally any more (see the comment below), so this loop never
; has a live global binding to turn off. Left in place as documentation
; rather than removed.
Hotkey, IfWinActive
For hk, lbl in HotkeyLabelMap
{
    if (hk != "")
        Hotkey, %hk%, Off, UseErrorLevel
}

; Disable the window-scoped variants IN THEIR OWN CONTEXT. Turning them off
; from the global context above does nothing at all -- that is the bug this
; loop exists to fix. Without it, changing a bind or disabling a window
; leaves the previous hotkey live.
For idx, OldTitle in RegisteredWindows
{
    Hotkey, IfWinActive, %OldTitle%
    For hk, lbl in HotkeyLabelMap
    {
        if (hk != "")
            Hotkey, %hk%, Off, UseErrorLevel
    }
}
Hotkey, IfWinActive
RegisteredWindows := []
FailedBinds := ""

; Read all enabled windows
IniRead, EnabledSection, %IniFile%, Enabled

; Build the new label map (only non-empty bindings)
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
if (KB_FinM != "")
    HotkeyLabelMap[KB_FinM]      := "DoM"
if (KB_FinS != "")
    HotkeyLabelMap[KB_FinS]      := "DoS"
if (KB_FinC != "")
    HotkeyLabelMap[KB_FinC]      := "DoC"

; Register window-specific hotkeys for enabled windows. Nothing is global
; any more -- Set Root moved here too, since its global scope only existed
; to support the removed dual-use naming mode.
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
        RegisteredWindows.Push(WinTitle)
        RegisterBind("GrabSig",      KB_GrabSig,      "DoQ")
        RegisterBind("SetRoot",      KB_SetRoot,      "DoSemi")
        RegisterBind("FormatEnf",    KB_FormatEnf,    "DoE")
        RegisterBind("ConvertScout", KB_ConvertScout, "DoConvertScout")
        RegisterBind("FinH",  KB_FinH,  "DoY")
        RegisterBind("FinL",  KB_FinL,  "DoP")
        RegisterBind("FinN",  KB_FinN,  "DoDot")
        RegisterBind("Fin13", KB_Fin13, "DoO")
        RegisterBind("Fin1",  KB_Fin1,  "Do1")
        RegisterBind("Fin2",  KB_Fin2,  "Do2")
        RegisterBind("Fin3",  KB_Fin3,  "Do3")
        RegisterBind("Fin4",  KB_Fin4,  "Do4")
        RegisterBind("Fin5",  KB_Fin5,  "Do5")
        RegisterBind("Fin6",  KB_Fin6,  "Do6")
        RegisterBind("FinETag",  KB_FinETag,  "DoQuote")
        RegisterBind("FinSlash", KB_FinSlash, "DoComma")
        RegisterBind("FinM", KB_FinM, "DoM")
        RegisterBind("FinS", KB_FinS, "DoS")
        RegisterBind("FinC", KB_FinC, "DoC")
    }
}

; Reset the hotkey context
Hotkey, IfWinActive
Return

; Every Hotkey ... On UseErrorLevel in the original discarded its result,
; so a bind Windows refused -- one already claimed by another application --
; failed silently and the key simply did nothing.
RegisterBind(id, key, label) {
    global FailedBinds
    if (key = "")
        return
    Hotkey, %key%, %label%, On UseErrorLevel
    if (ErrorLevel)
        FailedBinds .= (FailedBinds = "" ? "" : ",") . id
}

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
            SysKey := BuildSystemKey(RootKey, NextAlpha, True)
            UsedAlphas[NextAlpha] := True
            LastUsedAlpha := NextAlpha
            FindNextAlpha()
        } else {
            if (LastUsedAlpha = "")
                LastUsedAlpha := NextAlpha
            SysKey := BuildSystemKey(RootKey, LastUsedAlpha, True)
        }
    } else {
        if (ReadyToIncrement) {
            ; Home mode numbers from .0. This was the HomeZeroIs0 option,
            ; whose default was on (:32); it is now fixed behaviour. It is
            ; NOT tied to the removed Protean mode -- the original condition
            ; never mentioned CurrentMode.
            if (RootKey = "") {
                Num := NextNum - 1
            } else {
                Num := NextNum
            }
            UsedNums[NextNum] := True
            LastUsedNum := NextNum
            FindNextNum()
        } else {
            ; Preserve the original structure exactly. The home-mode first
            ; correction is .0, which the original produced by seeding
            ; LastUsedNum with 1 and subtracting below -- NOT by seeding it
            ; with NextNum, which diverges as soon as NextNum > 1.
            if (LastUsedNum = "") {
                LastUsedNum := (RootKey = "") ? 1 : NextNum
            }
            Num := (RootKey = "") ? LastUsedNum - 1 : LastUsedNum
        }
        SysKey := BuildSystemKey(RootKey, Num, False)
    }

    ; Flygd/Thera: ROOT-SIGID TYPE (hyphen-separated, all uppercase)
    SigClean := LTrim(LastSigId, "-")
    StringUpper, finType, finChar
    StringUpper, SigClean, SigClean
    Result := SysKey . "-" . SigClean . " " . finType

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

StringUpper, ClipTrim, ClipTrim
Clipboard := "-" . ClipTrim . " "
LastSigId := "-" . ClipTrim

ReadyToIncrement := True
RootJustFired := False
Return

; ============================================================
; SET ROOT: Normal copy/parse/set root flow with resume.
; The bind is now window-scoped (registered under IfWinActive per enabled
; EVE window), so this can only fire inside an enabled EVE window -- the
; dual-use "not in an EVE window" branch it used to need is gone.
; ============================================================
DoSemi:
; Reset everything
RootKey := ""
RootJustFired := False
LastFinisherWasAlpha := False
RootModeActive := False
ZeroMode := False
ReadyToIncrement := False
UsedNums := {}
UsedAlphas := {}
NextNum := 1
NextAlpha := 1
LastUsedNum := ""
LastUsedAlpha := ""

; Copy selected text
Clipboard := ""
Send ^c
Sleep 100
ClipWait, 2, 1
ClipSaved := Clipboard

if (ClipSaved = "") {
    ; Home mode - no text selected
    RootModeActive := True
    RootKey := ""
    Clipboard := ""
    GoSub, ShowRootTooltip
    Return
}

; ============================================================
; Process each line to extract first tokens and find common chain
; ============================================================
Lines := StrSplit(ClipSaved, "`n")
FirstTokens := []

; First pass: collect all first tokens
For lineIndex, Line in Lines
{
    Line := Trim(Line)
    if (Line = "")
        continue
    
    ; Strip preface and get first token
    CleanLine := Line
    Loop
    {
        FirstChar := SubStr(CleanLine, 1, 1)
        if (FirstChar = "" || FirstChar ~= "[A-Za-z0-9]")
            break
        CleanLine := SubStr(CleanLine, 2)
    }
    
    FirstToken := ""
    Loop, Parse, CleanLine
    {
        char := A_LoopField
        if (char ~= "[A-Za-z0-9]") {
            FirstToken .= char
        } else {
            if (FirstToken != "")
                break
        }
    }
    if (FirstToken != "")
        FirstTokens.Push(FirstToken)
}

; Find the common chain across all first tokens
DetectedChain := FindCommonChain(FirstTokens)

; Second pass: process each line with the detected chain
For lineIndex, Line in Lines
{
    Line := Trim(Line)
    if (Line = "")
        continue
    
    ; Parse with the detected chain
    Parsed := ParseBookmarkWithSuffix(Line, DetectedChain)
    Suffix := Parsed.suffix
    
    ; Track suffixes
    if (Suffix != "") {
        ; Determine if suffix is numeric or alphabetic
        if (Suffix ~= "^\d+$") {
            ; Numeric suffix - add to UsedNums
            UsedNums[Suffix + 0] := True
        } else if (Suffix ~= "^[A-Za-z]$") {
            ; Alphabetic suffix - convert to index and add to UsedAlphas
            StringUpper, SuffixUpper, Suffix
            AlphaIndex := Asc(SuffixUpper) - 64  ; A=1, B=2, etc.
            if (AlphaIndex >= 1 && AlphaIndex <= 26) {
                UsedAlphas[AlphaIndex] := True
            }
        }
    }
}

; If we found a chain, set it as the root
if (DetectedChain != "") {
    RootKey := DetectedChain
    RootModeActive := True
    ZeroMode := False
    
    ; Find next available numeric and alpha
    FindNextNum()
    FindNextAlpha()
    
    ; Build display root (bookmark format)
    DisplayRoot := RootKey

    ; Put bookmark format in clipboard for EVE return bookmark
    Clipboard := DisplayRoot
    ClipWait, 2
    
    GoSub, ShowRootTooltip
    Return
}

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
        SigId := ""
        
        FirstSpace := InStr(Line, " ")
        FirstTab := InStr(Line, "`t")
        
        DelimPos := 0
        if (FirstSpace > 0)
            DelimPos := FirstSpace
        if (FirstTab > 0 && (FirstTab < DelimPos || DelimPos = 0))
            DelimPos := FirstTab
        
        if (DelimPos > 0) {
            SigId := Trim(SubStr(Line, 1, DelimPos - 1))
        } else {
            SigId := RegExMatch(Line, "^\S+", Match) ? Match : Line
        }
        
        if (SigId != "") {
            OutputLines .= SigId . "`tCosmic Signature`tWormhole`tUnstable Wormhole`t100.0%`t98 km`n"
            ConvertedCount++
        }
    }
}

OutputLines := RegExReplace(OutputLines, "`n$")

if (OutputLines = "") {
    ToolTip, No EvE-Scout bookmarks found in clipboard
    SetTimer, RemoveTooltip, -1500
    Return
}

Clipboard := OutputLines
ToolTip, Converted %ConvertedCount% EvE-Scout bookmarks to probe format
SetTimer, RemoveTooltip, -2000
Return

DoE:
NewSuffix := ""
NewE := 0
NewSlash := 0
NewM := 0
NewSFlag := 0
NewC := 0
GoSub, ReadField
StringUpper, ClipUpper, ClipRaw
GoSub, FormatFlygdClipAndPaste
Return

DoY:
if (RootModeActive) {
    FireRootFinisher("H", True)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := "H"
    NewE := 0
    NewSlash := 0
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
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
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
}
Return

DoP:
if (RootModeActive) {
    FireRootFinisher("L", True)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := "L"
    NewE := 0
    NewSlash := 0
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
}
Return

DoDot:
if (RootModeActive) {
    FireRootFinisher("N", True)
} else {
    GoSub, ReadField
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := "N"
    NewE := 0
    NewSlash := 0
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
}
Return

DoM:
GoSub, ReadField
StringUpper, ClipUpper, ClipRaw
NewSuffix := ""
NewE := 0
NewSlash := 0
NewM := 1
NewSFlag := 0
NewC := 0
GoSub, FormatFlygdClipAndPaste
Return

DoS:
GoSub, ReadField
StringUpper, ClipUpper, ClipRaw
NewSuffix := ""
NewE := 0
NewSlash := 0
NewM := 0
NewSFlag := 1
NewC := 0
GoSub, FormatFlygdClipAndPaste
Return

DoC:
GoSub, ReadField
StringUpper, ClipUpper, ClipRaw
NewSuffix := ""
NewE := 0
NewSlash := 0
NewM := 0
NewSFlag := 0
NewC := 1
GoSub, FormatFlygdClipAndPaste
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
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
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
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
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
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
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
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
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
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
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
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
}
Return

DoQuote:
GoSub, ReadField
StringUpper, ClipUpper, ClipRaw
NewSuffix := ""
NewE := 1
NewSlash := 0
NewM := 0
NewSFlag := 0
NewC := 0
GoSub, FormatFlygdClipAndPaste
Return

DoComma:
GoSub, ReadField
StringUpper, ClipUpper, ClipRaw
NewSuffix := ""
NewE := 0
NewSlash := 1
NewM := 0
NewSFlag := 0
NewC := 0
GoSub, FormatFlygdClipAndPaste
Return

ReadField:
Clipboard := ""
Send ^a
Sleep 50
Send ^c
ClipWait, 2
ClipRaw := Clipboard
Return

; ============================================================
; FLYGD/THERA MODE: Parse hyphen-based bookmarks
; Format: ROOT-SIGID TYPE [tags...]
; Example: 3-EPA C5 E /
; ============================================================
FormatFlygdClipAndPaste:
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
    NewM      := 0
    NewSFlag  := 0
    NewC      := 0
    Return
}

RestAfterSys := RegExReplace(RestAfterSys, "^\s+", "")
ExistingE      := 0
ExistingSlash  := 0
ExistingM      := 0
ExistingS      := 0
ExistingC      := 0
ExistingSuffix := ""

Tokens := StrSplit(RestAfterSys, " ")
Loop % Tokens.MaxIndex()
{
    t := Tokens[A_Index]
    if (t = "13" || (StrLen(t) = 1 && (t >= "1" && t <= "6" || t = "H" || t = "L" || t = "N" || t = "T" || t = "D")))
        ExistingSuffix := t
    else if (t = "E")
        ExistingE := 1
    else if (t = "/")
        ExistingSlash := 1
    else if (t = "M")
        ExistingM := 1
    else if (t = "S")
        ExistingS := 1
    else if (t = "C")
        ExistingC := 1
}

; Apply mutual exclusivity rules
if (NewM) {
    NewSFlag := 0
}
if (NewSFlag) {
    NewM := 0
}
if (NewSlash) {
    NewC := 0
}
if (NewC) {
    NewSlash := 0
}

FinalSuffix := (NewSuffix != "") ? NewSuffix : ExistingSuffix

if (NewM) {
    FinalM := 1
    FinalS := 0
} else if (NewSFlag) {
    FinalM := 0
    FinalS := 1
} else {
    if (ExistingM && ExistingS) {
        FinalM := 0
        FinalS := 1
    } else {
        FinalM := ExistingM
        FinalS := ExistingS
    }
}

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

FinalE := (ExistingE || NewE)

Result := Base
if (FinalSuffix != "")
    Result .= " " . FinalSuffix
if (FinalE)
    Result .= " E"
if (FinalSlash)
    Result .= " /"
if (FinalM)
    Result .= " M"
if (FinalS)
    Result .= " S"
if (FinalC)
    Result .= " C"

Clipboard := Result
ClipWait, 2
Sleep 50
Send ^v

NewSuffix := ""
NewE      := 0
NewSlash  := 0
NewM      := 0
NewSFlag  := 0
NewC      := 0
Return