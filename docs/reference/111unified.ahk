; ============================================================
; 111unified.ahk - EVE Bookmark Helper (Protean + Flygd/Thera)
; ============================================================
#Persistent
#SingleInstance
SetStoreCapsLockMode, Off
GroupAdd, EVEWindows, EVE -

; --- Mode selection ---
; 1 = Protean mode (space-separated tokens, .NUMBER TYPE SIGID, all lowercase)
; 2 = Flygd/Thera mode (hyphen-based, ROOT-SIGID TYPE, all uppercase)
CurrentMode := 1  ; Default to Protean mode

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

; --- Settings ---
HomeZeroIs0 := 1   ; Default: first home hole is .0
PrefaceReturn := 1 ; Default: enabled
ReturnPreface := "!" ; Default return preface character

; --- Keybind defaults ---
KB_Copy        := ""
KB_Paste       := ""
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

; --- Tray setup ---
Menu, Tray, NoStandard
Menu, Tray, Add, Open GUI, ShowMainGui
Menu, Tray, Add, Reload Script, ReloadScript
Menu, Tray, Add, Exit, ExitScript
Menu, Tray, Default, Open GUI
Menu, Tray, Tip, EVE Bookmark Helper

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

; Show GUI on launch
GoSub, ShowMainGui

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

; Load settings
IniRead, HomeZeroIs0, %IniFile%, Settings, HomeZeroIs0, 1
IniRead, CurrentMode, %IniFile%, Settings, Mode, 1
IniRead, PrefaceReturn, %IniFile%, Settings, PrefaceReturn, 1
IniRead, ReturnPreface, %IniFile%, Settings, ReturnPreface, !

; Load keybindings
IniRead, KB_Copy,        %IniFile%, Keybinds, Copy,      
IniRead, KB_Paste,       %IniFile%, Keybinds, Paste,     
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

SaveAllSettings:
; Save all keybindings
IniWrite, %KB_Copy%,        %IniFile%, Keybinds, Copy
IniWrite, %KB_Paste%,       %IniFile%, Keybinds, Paste
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
IniWrite, %KB_FinM%,        %IniFile%, Keybinds, FinM
IniWrite, %KB_FinS%,        %IniFile%, Keybinds, FinS
IniWrite, %KB_FinC%,        %IniFile%, Keybinds, FinC
IniWrite, %KB_ConvertScout%, %IniFile%, Keybinds, ConvertScout

; Save settings
IniWrite, %HomeZeroIs0%, %IniFile%, Settings, HomeZeroIs0
IniWrite, %CurrentMode%, %IniFile%, Settings, Mode
IniWrite, %PrefaceReturn%, %IniFile%, Settings, PrefaceReturn
IniWrite, %ReturnPreface%, %IniFile%, Settings, ReturnPreface

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

ShowMainGui:
GoSub, BuildMainGui
Return

BuildMainGui:
Gui, Main:Destroy
Gui, Main:New, +AlwaysOnTop, Wormhole Bookmark Helper
Gui, Main:Font, s10
Gui, Main:Add, Tab3, vMainTab w520 h580, Status|Windows|Keybinds

Gui, Main:Tab, 1
Gui, Main:Font, s10 bold
Gui, Main:Add, Text, x20 y50,  Current Sig ID:
Gui, Main:Add, Text, x20 y78,  Root System:
Gui, Main:Add, Text, x20 y106, Root Mode:
Gui, Main:Add, Text, x20 y134, Next Numeric:
Gui, Main:Add, Text, x20 y162, Next Alpha:
Gui, Main:Font, s10 norm
Gui, Main:Add, Text, vStatusSig       x200 y50  w250, ---
Gui, Main:Add, Text, vStatusRoot      x200 y78  w250, ---
Gui, Main:Add, Text, vStatusMode      x200 y106 w250, ---
Gui, Main:Add, Text, vStatusNextNum   x200 y134 w250, ---
Gui, Main:Add, Text, vStatusNextAlpha x200 y162 w250, ---
Gui, Main:Font, s10 bold
Gui, Main:Add, Text, x20 y200, Set Root Manually:
Gui, Main:Font, s10 norm
Gui, Main:Add, Edit,   vManualRoot x20  y222 w160
Gui, Main:Add, Button, x188 y220 w80 gSetManualRoot, Set Root
Gui, Main:Add, Button, x276 y220 w80 gClearRoot,     Clear Root

Gui, Main:Add, Text, x20 y255, Mode:
Gui, Main:Add, DropDownList, x80 y252 w150 vModeDropdown gOnModeChange, Protean/v21||Flygd/ABH
if (CurrentMode = 2)
    GuiControl, Main: Choose, ModeDropdown, 2

HomeZeroChecked := HomeZeroIs0 ? "Checked" : ""
Gui, Main:Add, CheckBox, x20 y280 vHomeZeroIs0 %HomeZeroChecked% gOnHomeZeroToggle, First home hole is 0 (v21/null static mode)

; --- Return Preface settings ---
PrefaceChecked := PrefaceReturn ? "Checked" : ""
Gui, Main:Add, CheckBox, x20 y310 vPrefaceReturn %PrefaceChecked% gOnPrefaceToggle, Preface return bookmark
Gui, Main:Add, Text, x20 y335, Return preface value:
Gui, Main:Add, Edit, x160 y332 w80 vReturnPreface gOnPrefaceChange, %ReturnPreface%

Gui, Main:Tab, 2
Gui, Main:Font, s9
Gui, Main:Add, Text, x20 y50 w480, Select which EVE windows have hotkeys active:
Gui, Main:Add, Button, x20 y70 w80 gRefreshWinList, Refresh
WinList := []
WinGet, AllIDs, List
Loop % AllIDs
{
    ID := AllIDs%A_Index%
    WinGetTitle, Title, ahk_id %ID%
    if (Title ~= "^EVE - ") {
        AlreadyAdded := False
        Loop % WinList.MaxIndex()
        {
            if (WinList[A_Index] = Title) {
                AlreadyAdded := True
                Break
            }
        }
        if (!AlreadyAdded)
            WinList.Push(Title)
    }
}
WinYPos := 100
if (WinList.MaxIndex() = 0) {
    Gui, Main:Add, Text, x20 y%WinYPos%, No EVE windows found.
} else {
    Loop % WinList.MaxIndex()
    {
        WinTitle := WinList[A_Index]
        IniRead, Saved, %IniFile%, Enabled, %WinTitle%, 0
        Checked := Saved ? "Checked" : ""
        VarName := "WCB" . A_Index
        Gui, Main:Add, CheckBox, x20 y%WinYPos% v%VarName% %Checked% gOnWinCheck, %WinTitle%
        WinControlIndex%A_Index% := WinTitle
        WinTotalControls := A_Index
        WinYPos += 24
    }
}
GuiWinTotalControls := WinTotalControls

Gui, Main:Tab, 3
Gui, Main:Font, s9 bold
Gui, Main:Add, Text, x20 y50 w220, Function
Gui, Main:Add, Text, x250 y50 w220, Hotkey (click then press combo)
Gui, Main:Font, s9 norm
KBDefs := []
KBDefs.Push(["Copy",                      "KB_Copy"])
KBDefs.Push(["Paste",                     "KB_Paste"])
KBDefs.Push(["Grab Sig ID",               "KB_GrabSig"])
KBDefs.Push(["Set Root",                  "KB_SetRoot"])
KBDefs.Push(["Format Enforcer",           "KB_FormatEnf"])
KBDefs.Push(["Convert EvE-Scout Bookmarks", "KB_ConvertScout"])
KBDefs.Push(["Finisher: HS (highsec)",     "KB_FinH"])
KBDefs.Push(["Finisher: LS (lowsec)",      "KB_FinL"])
KBDefs.Push(["Finisher: NS (nullsec)",     "KB_FinN"])
KBDefs.Push(["Finisher: C13 (shattered)",  "KB_Fin13"])
KBDefs.Push(["Finisher: C1",               "KB_Fin1"])
KBDefs.Push(["Finisher: C2",               "KB_Fin2"])
KBDefs.Push(["Finisher: C3",               "KB_Fin3"])
KBDefs.Push(["Finisher: C4",               "KB_Fin4"])
KBDefs.Push(["Finisher: C5",               "KB_Fin5"])
KBDefs.Push(["Finisher: C6",               "KB_Fin6"])
KBDefs.Push(["E Tag (end of life)",       "KB_FinETag"])
KBDefs.Push(["/ Tag (half mass)",         "KB_FinSlash"])
KBDefs.Push(["M Tag (medium hole)",       "KB_FinM"])
KBDefs.Push(["S Tag (frig hole)",         "KB_FinS"])
KBDefs.Push(["C Tag (critical)",          "KB_FinC"])
KBYPos := 68
Loop % KBDefs.MaxIndex()
{
    FuncName := KBDefs[A_Index][1]
    VarRef   := KBDefs[A_Index][2]
    CurVal   := %VarRef%
    CtrlName := "KBCtrl" . A_Index
    KBCtrlRef%A_Index% := VarRef
    Gui, Main:Add, Text,   x20  y%KBYPos% w220, %FuncName%
    Gui, Main:Add, Hotkey, x250 y%KBYPos% w220 v%CtrlName% gKBChange Limit1, %CurVal%
    KBYPos += 22
}
KBTotalCtrls := KBDefs.MaxIndex()
Gui, Main:Add, Button, x20 y%KBYPos% w120 gResetKeybinds, Reset Defaults

Gui, Main:Tab
Gui, Main:Add, Button, x20 y590 w80 gMainGuiClose, Close
Gui, Main:Show, w540 h640
Return

MainGuiClose:
Gui, Main:Hide
Return

RefreshWinList:
GoSub, BuildMainGui
Return

OnWinCheck:
GoSub, SaveWindowSettings
GoSub, RefreshHotkeys
Return

OnModeChange:
GuiControlGet, ModeChoice, Main:, ModeDropdown
if (ModeChoice = "Protean/v21")
    CurrentMode := 1
else if (ModeChoice = "Flygd/ABH")
    CurrentMode := 2
GoSub, SaveAllSettings
GoSub, RefreshStatusTab
Return

OnHomeZeroToggle:
GuiControlGet, HomeZeroIs0, Main:, HomeZeroIs0
GoSub, SaveAllSettings
GoSub, RefreshStatusTab
Return

OnPrefaceToggle:
GuiControlGet, PrefaceReturn, Main:, PrefaceReturn
GoSub, SaveAllSettings
Return

OnPrefaceChange:
GuiControlGet, ReturnPreface, Main:, ReturnPreface
GoSub, SaveAllSettings
Return

RefreshStatusTab:
if (RootModeActive) {
    ModeText      := RootKey = "" ? "Home/Zero" : "Active"
    RootText      := RootKey = "" ? "(home)" : RootKey
    NextNumText   := BuildSystemKey(RootKey, NextNum,   False)
    
    ; For Protean mode, show "N/A" for alpha since alphas aren't used
    if (CurrentMode = 1) {
        NextAlphaText := "N/A (Protean mode)"
    } else {
        NextAlphaText := BuildSystemKey(RootKey, NextAlpha, True)
    }
} else {
    ModeText      := "Not set"
    RootText      := "---"
    NextNumText   := "---"
    NextAlphaText := "---"
}
SigText := LastSigId = "" ? "---" : LastSigId
GuiControl, Main:, StatusSig,        %SigText%
GuiControl, Main:, StatusRoot,       %RootText%
GuiControl, Main:, StatusMode,       %ModeText%
GuiControl, Main:, StatusNextNum,    %NextNumText%
GuiControl, Main:, StatusNextAlpha,  %NextAlphaText%
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
GuiControlGet, ManualRoot, Main:, ManualRoot
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
    if (CurrentMode = 1) {
        DisplayRoot := "." . DisplayRoot
    }
    if (PrefaceReturn) {
        DisplayRoot := ReturnPreface . DisplayRoot
    }
    
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

KBChange:
Loop % KBTotalCtrls
{
    CtrlName := "KBCtrl" . A_Index
    if (A_GuiControl = CtrlName) {
        VarRef := KBCtrlRef%A_Index%
        GuiControlGet, NewKey, Main:, %CtrlName%
        if (NewKey = "" || NewKey = "None") {
            %VarRef% := ""
        } else {
            %VarRef% := NewKey
        }
        GoSub, SaveAllSettings
        GoSub, RefreshHotkeys
        Break
    }
}
Return

ResetKeybinds:
KB_Copy        := ""
KB_Paste       := ""
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
KB_ConvertScout := "^+s"
GoSub, SaveAllSettings
GoSub, RefreshHotkeys
GoSub, BuildMainGui
Return

ShowRootTooltip:
if (RootModeActive) {
    NextNumDisplay   := BuildSystemKey(RootKey, NextNum,   False)
    if (CurrentMode = 1) {
        NextAlphaDisplay := "N/A (Protean mode)"
    } else {
        NextAlphaDisplay := BuildSystemKey(RootKey, NextAlpha, True)
    }
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
if (KB_Copy != "")
    HotkeyLabelMap[KB_Copy]      := "DoCopy"
if (KB_Paste != "")
    HotkeyLabelMap[KB_Paste]     := "DoPaste"
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

; Step 4: Register GLOBAL hotkeys (Copy, Paste, and Set Root) - no window restriction
; Reset to global context
Hotkey, IfWinActive
if (KB_Copy != "")
    Hotkey, %KB_Copy%, DoCopy, On UseErrorLevel
if (KB_Paste != "")
    Hotkey, %KB_Paste%, DoPaste, On UseErrorLevel
if (KB_SetRoot != "")
    Hotkey, %KB_SetRoot%, DoSemi, On UseErrorLevel

; Step 5: Register window-specific hotkeys for enabled windows (excluding copy, paste, and set root)
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
        ; Register all hotkeys EXCEPT copy, paste, and set root (which are global)
        if (KB_GrabSig != "")
            Hotkey, %KB_GrabSig%, DoQ, On UseErrorLevel
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
        if (KB_FinM != "")
            Hotkey, %KB_FinM%, DoM, On UseErrorLevel
        if (KB_FinS != "")
            Hotkey, %KB_FinS%, DoS, On UseErrorLevel
        if (KB_FinC != "")
            Hotkey, %KB_FinC%, DoC, On UseErrorLevel
    }
}

; Step 6: Reset the hotkey context
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
    global ReadyToIncrement, LastUsedNum, LastUsedAlpha, CurrentMode, HomeZeroIs0

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
            ; HOME MODE: offset by -1 so first bookmark is .0, then .1, .2, etc.
            ; (only when HomeZeroIs0 is enabled and root is empty)
            if (RootKey = "" && HomeZeroIs0) {
                Num := NextNum - 1
                ; Mark the number we're using as used
                UsedNums[NextNum] := True
                LastUsedNum := NextNum
                FindNextNum()
            } else {
                ; Normal mode: use next available as-is (starts at 1)
                Num := NextNum
                UsedNums[NextNum] := True
                LastUsedNum := NextNum
                FindNextNum()
            }
        } else {
            ; Correct-in-place: reuse last used number
            if (LastUsedNum = "") {
                if (RootKey = "" && HomeZeroIs0) {
                    ; Home mode first correction starts at 0
                    LastUsedNum := 1  ; This becomes NextNum - 1 = 0
                } else {
                    LastUsedNum := NextNum
                }
            }
            if (RootKey = "" && HomeZeroIs0) {
                ; Home mode: convert to 0-based
                Num := LastUsedNum - 1
            } else {
                Num := LastUsedNum
            }
        }
        SysKey := BuildSystemKey(RootKey, Num, False)
    }

    ; Format based on mode
    SigClean := LTrim(LastSigId, "-")
    if (CurrentMode = 1) {
        ; Protean mode: .ROOT+NUMBER TYPE SIGID (space-separated, all lowercase)
        StringLower, finType, finChar
        StringLower, SigClean, SigClean
        Result := "." . SysKey . " " . finType . " " . SigClean
    } else {
        ; Flygd/Thera mode: ROOT-SIGID TYPE (hyphen-separated, all uppercase)
        StringUpper, finType, finChar
        StringUpper, SigClean, SigClean
        Result := SysKey . "-" . SigClean . " " . finType
    }
    
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

DoCopy:
Send ^c
Return

DoPaste:
Send ^v
Return

DoQ:
Send ^c
Sleep 100
ClipWait, 2
ClipSaved := Clipboard
ClipTrim := SubStr(ClipSaved, 1, 3)

if (CurrentMode = 1) {
    ; Protean mode: lowercase sig ID
    StringLower, ClipTrim, ClipTrim
    Clipboard := "-" . ClipTrim . " "
    LastSigId := "-" . ClipTrim
} else {
    ; Flygd/Thera mode: uppercase sig ID
    StringUpper, ClipTrim, ClipTrim
    Clipboard := "-" . ClipTrim . " "
    LastSigId := "-" . ClipTrim
}

ReadyToIncrement := True
RootJustFired := False
Return

; ============================================================
; SET ROOT: 
; If in EVE window: Normal copy/parse/set root flow with resume
; If NOT in EVE window: Just send the current RootKey
; ============================================================
DoSemi:
; FIRST: Check if we're in an enabled EVE window
IsEveWindow := False
WinGetTitle, ActiveTitle, A
if (ActiveTitle ~= "^EVE - ") {
    ; Check if this specific EVE window is enabled
    IniRead, WindowEnabled, %IniFile%, Enabled, %ActiveTitle%, 0
    if (WindowEnabled = 1) {
        IsEveWindow := True
    }
}

; If NOT in EVE window, just send the current root and exit
if (!IsEveWindow) {
    if (RootKey != "") {
        Sleep 100
        Send %RootKey%
    }
    Return
}

; --- If we get here, we're in an enabled EVE window ---
; Do the normal copy/parse/set root flow

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
    if (CurrentMode = 1) {
        DisplayRoot := "." . DisplayRoot
    }
    if (PrefaceReturn) {
        DisplayRoot := ReturnPreface . DisplayRoot
    }
    
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
if (CurrentMode = 1) {
    ; Protean mode: parse space-separated tokens
    GoSub, FormatProteanClipAndPaste
} else {
    ; Flygd/Thera mode: use hyphen-based parsing
    StringUpper, ClipUpper, ClipRaw
    GoSub, FormatFlygdClipAndPaste
}
Return

DoY:
if (RootModeActive) {
    if (CurrentMode = 1) {
        ; Protean: "hs" (numeric, not alpha)
        FireRootFinisher("hs", False)
    } else {
        ; Flygd/Thera: "H" (alpha)
        FireRootFinisher("H", True)
    }
} else {
    GoSub, ReadField
    if (CurrentMode = 1) {
        NewSuffix := "hs"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatProteanClipAndPaste
    } else {
        StringUpper, ClipUpper, ClipRaw
        NewSuffix := "H"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatFlygdClipAndPaste
    }
}
Return

DoO:
if (RootModeActive) {
    if (CurrentMode = 1) {
        ; Protean: "c13" (numeric)
        FireRootFinisher("c13", False)
    } else {
        ; Flygd/Thera: "13" (numeric)
        FireRootFinisher("13", False)
    }
} else {
    GoSub, ReadField
    if (CurrentMode = 1) {
        NewSuffix := "c13"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatProteanClipAndPaste
    } else {
        StringUpper, ClipUpper, ClipRaw
        NewSuffix := "13"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatFlygdClipAndPaste
    }
}
Return

DoP:
if (RootModeActive) {
    if (CurrentMode = 1) {
        ; Protean: "ls" (numeric)
        FireRootFinisher("ls", False)
    } else {
        ; Flygd/Thera: "L" (alpha)
        FireRootFinisher("L", True)
    }
} else {
    GoSub, ReadField
    if (CurrentMode = 1) {
        NewSuffix := "ls"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatProteanClipAndPaste
    } else {
        StringUpper, ClipUpper, ClipRaw
        NewSuffix := "L"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatFlygdClipAndPaste
    }
}
Return

DoDot:
if (RootModeActive) {
    if (CurrentMode = 1) {
        ; Protean: "ns" (numeric)
        FireRootFinisher("ns", False)
    } else {
        ; Flygd/Thera: "N" (alpha)
        FireRootFinisher("N", True)
    }
} else {
    GoSub, ReadField
    if (CurrentMode = 1) {
        NewSuffix := "ns"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatProteanClipAndPaste
    } else {
        StringUpper, ClipUpper, ClipRaw
        NewSuffix := "N"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatFlygdClipAndPaste
    }
}
Return

DoM:
GoSub, ReadField
if (CurrentMode = 1) {
    NewSuffix := ""
    NewE := 0
    NewSlash := 0
    NewM := 1
    NewSFlag := 0
    NewC := 0
    GoSub, FormatProteanClipAndPaste
} else {
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := ""
    NewE := 0
    NewSlash := 0
    NewM := 1
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
}
Return

DoS:
GoSub, ReadField
if (CurrentMode = 1) {
    NewSuffix := ""
    NewE := 0
    NewSlash := 0
    NewM := 0
    NewSFlag := 1
    NewC := 0
    GoSub, FormatProteanClipAndPaste
} else {
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := ""
    NewE := 0
    NewSlash := 0
    NewM := 0
    NewSFlag := 1
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
}
Return

DoC:
GoSub, ReadField
if (CurrentMode = 1) {
    NewSuffix := ""
    NewE := 0
    NewSlash := 0
    NewM := 0
    NewSFlag := 0
    NewC := 1
    GoSub, FormatProteanClipAndPaste
} else {
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := ""
    NewE := 0
    NewSlash := 0
    NewM := 0
    NewSFlag := 0
    NewC := 1
    GoSub, FormatFlygdClipAndPaste
}
Return

Do1:
if (RootModeActive) {
    if (CurrentMode = 1) {
        ; Protean: "c1" (numeric)
        FireRootFinisher("c1", False)
    } else {
        ; Flygd/Thera: "1" (numeric)
        FireRootFinisher("1", False)
    }
} else {
    GoSub, ReadField
    if (CurrentMode = 1) {
        NewSuffix := "c1"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatProteanClipAndPaste
    } else {
        StringUpper, ClipUpper, ClipRaw
        NewSuffix := "1"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatFlygdClipAndPaste
    }
}
Return

Do2:
if (RootModeActive) {
    if (CurrentMode = 1) {
        FireRootFinisher("c2", False)
    } else {
        FireRootFinisher("2", False)
    }
} else {
    GoSub, ReadField
    if (CurrentMode = 1) {
        NewSuffix := "c2"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatProteanClipAndPaste
    } else {
        StringUpper, ClipUpper, ClipRaw
        NewSuffix := "2"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatFlygdClipAndPaste
    }
}
Return

Do3:
if (RootModeActive) {
    if (CurrentMode = 1) {
        FireRootFinisher("c3", False)
    } else {
        FireRootFinisher("3", False)
    }
} else {
    GoSub, ReadField
    if (CurrentMode = 1) {
        NewSuffix := "c3"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatProteanClipAndPaste
    } else {
        StringUpper, ClipUpper, ClipRaw
        NewSuffix := "3"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatFlygdClipAndPaste
    }
}
Return

Do4:
if (RootModeActive) {
    if (CurrentMode = 1) {
        FireRootFinisher("c4", False)
    } else {
        FireRootFinisher("4", False)
    }
} else {
    GoSub, ReadField
    if (CurrentMode = 1) {
        NewSuffix := "c4"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatProteanClipAndPaste
    } else {
        StringUpper, ClipUpper, ClipRaw
        NewSuffix := "4"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatFlygdClipAndPaste
    }
}
Return

Do5:
if (RootModeActive) {
    if (CurrentMode = 1) {
        FireRootFinisher("c5", False)
    } else {
        FireRootFinisher("5", False)
    }
} else {
    GoSub, ReadField
    if (CurrentMode = 1) {
        NewSuffix := "c5"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatProteanClipAndPaste
    } else {
        StringUpper, ClipUpper, ClipRaw
        NewSuffix := "5"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatFlygdClipAndPaste
    }
}
Return

Do6:
if (RootModeActive) {
    if (CurrentMode = 1) {
        FireRootFinisher("c6", False)
    } else {
        FireRootFinisher("6", False)
    }
} else {
    GoSub, ReadField
    if (CurrentMode = 1) {
        NewSuffix := "c6"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatProteanClipAndPaste
    } else {
        StringUpper, ClipUpper, ClipRaw
        NewSuffix := "6"
        NewE := 0
        NewSlash := 0
        NewM := 0
        NewSFlag := 0
        NewC := 0
        GoSub, FormatFlygdClipAndPaste
    }
}
Return

DoQuote:
GoSub, ReadField
if (CurrentMode = 1) {
    NewSuffix := ""
    NewE := 1
    NewSlash := 0
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatProteanClipAndPaste
} else {
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := ""
    NewE := 1
    NewSlash := 0
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
}
Return

DoComma:
GoSub, ReadField
if (CurrentMode = 1) {
    NewSuffix := ""
    NewE := 0
    NewSlash := 1
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatProteanClipAndPaste
} else {
    StringUpper, ClipUpper, ClipRaw
    NewSuffix := ""
    NewE := 0
    NewSlash := 1
    NewM := 0
    NewSFlag := 0
    NewC := 0
    GoSub, FormatFlygdClipAndPaste
}
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
; PROTEAN MODE: Parse space-separated tokens
; Format: .NUMBER TYPE SIGID [tags...]
; Example: .32 c5 epa e /
; ============================================================
FormatProteanClipAndPaste:
Raw := ClipRaw

; Split by spaces
Tokens := StrSplit(Raw, " ")

; Token 0 (first) should be the .NUMBER
; Token 1 should be the TYPE (hs, ls, ns, c1-c6, c13)
; Token 2 should be the SIGID
; Tokens 3+ are existing tags

NumberToken := Tokens[1]  ; e.g., ".32"
TypeToken := Tokens[2]    ; e.g., "c5"
SigToken := Tokens[3]     ; e.g., "epa"

; Clean up tokens
NumberToken := Trim(NumberToken)
TypeToken := Trim(TypeToken)
SigToken := Trim(SigToken)

; Parse existing tags from tokens 4+
ExistingE := 0
ExistingSlash := 0
ExistingM := 0
ExistingS := 0
ExistingC := 0

Loop % Tokens.MaxIndex()
{
    idx := A_Index
    if (idx <= 3)
        continue
    t := Trim(Tokens[idx])
    if (t = "")
        continue
    ; Convert to lowercase for case-insensitive comparison
    StringLower, tLower, t
    if (tLower = "e")
        ExistingE := 1
    else if (tLower = "/")
        ExistingSlash := 1
    else if (tLower = "m")
        ExistingM := 1
    else if (tLower = "s")
        ExistingS := 1
    else if (tLower = "c")
        ExistingC := 1
}

; Apply mutual exclusivity rules
; S and M are mutually exclusive
if (NewM) {
    NewSFlag := 0
}
if (NewSFlag) {
    NewM := 0
}

; / and C are mutually exclusive
if (NewSlash) {
    NewC := 0
}
if (NewC) {
    NewSlash := 0
}

; Determine final suffix (type) - use new if provided, otherwise keep existing
FinalType := (NewSuffix != "") ? NewSuffix : TypeToken

; Apply mutual exclusivity to final tags
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

; Build the result
Result := NumberToken
if (FinalType != "")
    Result .= " " . FinalType
if (SigToken != "")
    Result .= " " . SigToken
if (FinalE)
    Result .= " e"
if (FinalSlash)
    Result .= " /"
if (FinalM)
    Result .= " m"
if (FinalS)
    Result .= " s"
if (FinalC)
    Result .= " c"

; If we lost the sig token somehow, use the raw as fallback
if (SigToken = "" || Result = NumberToken) {
    Result := Raw
}

Clipboard := Result
ClipWait, 2
Sleep 50
Send ^v

; Reset flags
NewSuffix := ""
NewE      := 0
NewSlash  := 0
NewM      := 0
NewSFlag  := 0
NewC      := 0
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