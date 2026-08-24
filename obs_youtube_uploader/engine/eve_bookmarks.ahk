; ============================================================
; eve_bookmarks.ahk - EVE Bookmark Helper (Flygd/ABH)
;
; Vendored from the helper author's own script (docs/reference/), with
; Wingman's integration layer applied on top and the standalone tool's
; self-configuration removed. The behaviour below is deliberately the
; author's -- when they ship a new revision, re-vendor it and re-apply the
; same layer rather than porting changes across by hand. The previous
; approach (forking an older revision and maintaining it here) is what let
; Set Root's home-hole resumption silently diverge.
;
; Removed from the author's script, all of it self-configuration Wingman
; owns instead: SaveAllSettings, SaveWindowSettings (both still called
; GuiControlGet after the GUI was stripped, so both were broken), the 20
; IniWrite calls, ExitScript, ReloadScript, and KBDisplay (a GUI-only
; formatter with no remaining caller).
;
; Added: the /token handshake, the status file, and failure-recording bind
; registration. Each is marked WINGMAN below. There is no channel in the
; other direction -- Wingman configures the engine through the INI and
; reads its state from the status file, and nothing sends it commands.
;
; ONE behaviour block is not the author's: DoQ clears the clipboard before
; its own Send ^c and checks ClipWait's ErrorLevel, so a copy that does not
; land is reported instead of silently reading stale clipboard contents as
; the signature. It is marked WINGMAN like the rest. The divergence is
; deliberately the smallest available -- it applies the clear-then-check
; shape the author already uses in DoConvertScout, so it is a fix worth
; offering back upstream rather than a local invention.
; ============================================================
#Persistent
; Force, explicitly: a duplicate spawn must replace the previous copy, not
; raise a prompt for a user who no longer has a GUI to answer it in.
#SingleInstance Force
SetStoreCapsLockMode, Off
GroupAdd, EVEWindows, EVE -

; --- WINGMAN: /token handshake ------------------------------------
; Wingman passes /token <value> at spawn and records the same value beside
; the PID. Orphan recovery matches on it before terminating anything, so
; the interpreter running someone else's script is never killed.
RunToken := ""
; ArgCount is captured with a LEGACY assignment (= not :=) on purpose. In an
; expression, %0% is a double-dereference: it reads variable `0` (the count,
; e.g. "2") and then dereferences the variable NAMED "2" -- the second
; argument's text. Writing `A_Index < %0%` therefore compared the index
; against the token itself, which string-compares true for tokens beginning
; 1-9 or a-f and false for those beginning "0", silently dropping the token
; on about one launch in sixteen. `:=` here would reintroduce exactly that.
ArgCount = %0%
Loop %ArgCount%
{
    Arg := %A_Index%
    if (Arg = "/token" && A_Index < ArgCount)
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

; Pin the encoding: the app reads the status file with encoding="utf-8", and
; sig is three characters taken straight from the clipboard, so a non-ASCII
; signature would otherwise decode differently on each side and show as a
; permanent "stale" readout. UTF-8-RAW is UTF-8 without a BOM -- a BOM would
; make json.loads fail on the first character. Set here, in the auto-execute
; section, so it becomes the default for every later-launched thread
; (including the RefreshStatusTab timer) rather than just this one.
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
KB_FinS        := ""
KB_FinC        := ""
KB_ConvertScout := "^+s"   ; Ctrl+Shift+S default

; Maps hotkey string -> label, so we can disable by exact label
HotkeyLabelMap := {}

; --- WINGMAN: registration bookkeeping ----------------------------
; Every window title we currently hold registrations against. A
; window-scoped hotkey can only be disabled from inside the same criterion
; it was registered in, so the teardown in RefreshHotkeys needs this list.
RegisteredWindows := []
FailedBinds := ""

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

Return

LoadAllSettings:
; WINGMAN: Wingman owns creating and writing eve_bookmark_helper.ini; the
; engine must only ever read it. The author's script calls SaveAllSettings
; here instead, which would make the engine a second writer to config that
; settings.json is the source of truth for.
IfNotExist, %IniFile%
    Return

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

; ============================================================
; WINGMAN: status file
; ============================================================
; Written to a temp name and moved over the target: Wingman polls this at
; ~1Hz and must never read a half-written file.
RefreshStatusTab:
if (RootModeActive) {
    RootText     := RootKey = "" ? "(home)" : RootKey
    NextNumText  := BuildSystemKey(RootKey, NextNum,   False)
    NextAlphaText := BuildSystemKey(RootKey, NextAlpha, True)
} else {
    RootText := "", NextNumText := "", NextAlphaText := ""
}
SigText := LastSigId

StatusBody := "{"
    . """sig"":""" . JsonEsc(SigText) . ""","
    . """root"":""" . JsonEsc(RootText) . ""","
    . """next_num"":""" . JsonEsc(NextNumText) . ""","
    . """next_alpha"":""" . JsonEsc(NextAlphaText) . ""","
    . """failed_binds"":[" . JsonList(FailedBinds) . "],"
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
; WINGMAN: hot reload. The author's script reads only [Enabled] here; the
; keybinds themselves are re-read too, because Wingman rewrites the whole
; INI whenever the user saves the Bookmarks route and there is no other
; moment at which a changed bind would be picked up.
GoSub, LoadAllSettings

; Step 1: disable anything registered in the global context. Nothing is
; registered there, so on a normal pass this finds nothing -- it is kept
; because it is the cheap half of the teardown below, and UseErrorLevel
; makes a miss free. It must stay ahead of the window-scoped teardown: the
; two are different registrations and each is only reachable from the
; context it was made in.
Hotkey, IfWinActive
For hk, lbl in HotkeyLabelMap
{
    if (hk != "")
        Hotkey, %hk%, Off, UseErrorLevel
}

; WINGMAN: disable the window-scoped variants IN THEIR OWN CONTEXT.
; Turning them off from the global context above does nothing at all.
; Without this, changing a bind or disabling a window leaves the previous
; hotkey live. The author's script has no equivalent -- its Step 1 clears
; only the global context. Why it gets away with that is not recorded
; anywhere and is not worth guessing at; what matters here is that Wingman
; rewrites the INI on every save and refreshes in place, so the stale
; registration is reachable and has to be torn down.
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

; Step 4: Register window-specific hotkeys for enabled windows.
; WINGMAN: every registration goes through RegisterBind rather than a bare
; Hotkey ... On UseErrorLevel, so a bind Windows refuses is reported to the
; UI instead of failing silently.
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
        RegisterBind("Fin13", KB_Fin13, "DoO")
        RegisterBind("Fin1",  KB_Fin1,  "Do1")
        RegisterBind("Fin2",  KB_Fin2,  "Do2")
        RegisterBind("Fin3",  KB_Fin3,  "Do3")
        RegisterBind("Fin4",  KB_Fin4,  "Do4")
        RegisterBind("Fin5",  KB_Fin5,  "Do5")
        RegisterBind("Fin6",  KB_Fin6,  "Do6")
        RegisterBind("FinETag",  KB_FinETag,  "DoQuote")
        RegisterBind("FinSlash", KB_FinSlash, "DoComma")
        RegisterBind("FinN", KB_FinN, "DoDot")
        RegisterBind("FinL", KB_FinL, "DoP")
        RegisterBind("FinS", KB_FinS, "DoS")
        RegisterBind("FinC", KB_FinC, "DoC")
    }
}

; Step 5: Reset the hotkey context
Hotkey, IfWinActive
Return

; WINGMAN: every Hotkey ... On UseErrorLevel in the author's script
; discards its result, so a bind Windows refuses -- one already claimed by
; another application -- fails silently and the key simply does nothing.
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
; WINGMAN: clear-then-check, the same shape DoConvertScout already uses a
; few lines below. The author's version sends ^c onto whatever the
; clipboard already holds and ignores ClipWait's ErrorLevel, so a copy that
; does not land reads the PREVIOUS contents -- and ClipWait returns at once
; rather than stalling, because the clipboard is not empty. DoSemi ends with
; `Clipboard := RootKey`, so straight after a Set Root that stale content is
; the root: a failed Grab Sig took root J214811 and produced sig "-J21",
; which FireRootFinisher then wrote into real bookmarks while the status bar
; showed it like any ordinary signature.
Clipboard := ""
Send ^c
Sleep 100
ClipWait, 2
if (ErrorLevel) {
    ToolTip, Grab Sig failed - nothing was copied
    SetTimer, RemoveTooltip, -1500
    Return
}
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