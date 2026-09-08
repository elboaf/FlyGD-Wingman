"""Versioned public V24.01 compatibility data, not client implementation code.

Public jotunn_default.pyj YAML SHA256:
2e89abe9207dd5e166c0c8b2908ccfee07054a7fe4d6af79457c41efc4387185
Archive/call-chain provenance: docs/ui-setup-client-evidence.md. Fingerprints
cover compact UTF-8 JSON with alphabetical alwaysShownStates, filteredStates,
groups keys. Arrays retain order and duplicates; no full catalogue is vendored.
"""

JOTUNN_FINGERPRINTS = {
    "DefaultPreset_639431": "cd9c0969b015bee71eab867e62fe81dc4ebc2317cb3e660b630b634a9473a60d",
    "DefaultPreset_639432": "17b7298c4589d426969c9dba1801db391e03ca6d1361c9a77ea59680c65127eb",
    "DefaultPreset_639433": "439411734c4e11c08a51cc81335f0e30816acf83bacef8ec9e507f7712387516",
    "DefaultPreset_639434": "47d6c654d1fe2dba90e5e66428869fd4e57ffc352557764335ccb6500f52e8ec",
    "DefaultPreset_639435": "ac29c1ebcc3c500704771a9e409d23faae9449b7905d074102a9ca44ebe3ad40",
    "DefaultPreset_639436": "110396e33acca31bb06ba7075c2f97b5bbaf46d57ff7b1438ffb2a58fff72b91",
    "DefaultPreset_639437": "98b0ef786498ee1e62de8091960373288370bdf33b742fa7de5e0b4956dc410a",
    "DefaultPreset_639438": "37374fd33ba9b92ff360186969cef9dc8e975d9a82e18f46d5c9b585e9942c6b",
    "DefaultPreset_639439": "a0d226efde4dd7e8bf37a5c2c0a8fb9864eaf8b0cc8100dce183f49a196f7036",
    "DefaultPreset_639440": "a5df132aca3e9078af48574ddba8c2c6bc1cec1063a5f62fbddb78556769ea66",
    "DefaultPreset_639441": "99d6ba582af15d7ecee3e7ecdffc4f7d029ae88bfd3a4adfb2dbaef5c08fb025",
    "DefaultPreset_639442": "b229b5b4d6c4b159ddf54349b24e2fea1baa69a5b70207355a0a923341c7f63b",
    "DefaultPreset_639443": "6ea064eb6e3893e56cb0bc574b70059ed29b56d52a8bcbfd8d552c14447692c3",
    "DefaultPreset_639444": "52b9a94cbba45cd4010e73398aff547174aeb5327eab134eec1eee3d097e553b",
    "DefaultPreset_639445": "6c2e523420d1356e216759d05769322b3f08c339c5d391a372f8763a027c3f15",
    "DefaultPreset_639446": "ab60c8bf35c9240b027e3a1b1b7b4961dd1a1d386d20a37d291ea927d5d54378",
    "DefaultPreset_639447": "ba91034757ae385f26932b67deda8e7b0c69568af98c594986ce192422ad2fdf",
    "DefaultPreset_639448": "ccf99154f5604c93b313de496e8bd6421ba869703d5b934420948d9fa79b1379",
    "DefaultPreset_639449": "568a0656e5770c3cc965c4ca788a501dc6fa9f2ae0e10d80323cc955332cffcf",
    "DefaultPreset_639450": "984fe48c2f751f4264bc0bd50bc1061614251862285f8a779dd11798fb42e3aa",
    "DefaultPreset_639451": "6a8222543dfb99be5e87ee42f8d33438336a977d073d6300d18d3eb2786fc918",
    "DefaultPreset_639452": "98eb8e8f7b2618657c42732cc715a6b757ec560f56ef63945fe4c33982e4089d",
    "DefaultPreset_639453": "8ab2c2c64fdd825af1fcbddd5df6fec1d8c2f82826127af6f82f1b3ee18a8d5c",
    "DefaultPreset_639454": "11e327b091fc814f923f907b01027e707e5f1ac27334cdfc3c226dce9ba1e212",
    "DefaultPreset_639455": "54a0826219473915b812cbad60cf4b53372ab303d758125e27e29c64d08db183",
    "DefaultPreset_639456": "dcfb6cf9393c3da73ffe732a937bd4b1e996889ad1f4c23ad5676c0dfd2b973c",
    "DefaultPreset_639457": "d299fc20fb19b06bf1085e5a85e9ac08d54c5ac84171a7a9ac448029d50ca3f5",
    "DefaultPreset_639458": "75b24f12031c6fe85ab6e5a990e6fcdded237b24e8d079fa30ff0565769445bd",
    "DefaultPreset_639459": "26fabf8b1f1c446ce76ae2063ba3f8b0b0f333c4a94be65036e1023c189a0b9d",
    "DefaultPreset_639460": "59068a2948f2d5ec40d727d353404b8d049d1588b630c69e01bc415f6bf6980a",
    "DefaultPreset_639461": "2b9ad0756d59f09ce8b61fd6b81f181939146d1f4f8d5aa3958ec32261fbe0b3",
    "DefaultPreset_639462": "f0c9c2f673126ccf5c3ffef808db84709e2104b9243377180c064941be13d594",
    "DefaultPreset_639463": "c7ca15bc917c5c621d3ac0f9f58d1da980f8d4c1dcce88e4c207eb05a026c096",
    "DefaultPreset_639464": "c319278f9a8e39231956f653e8986258463e476b49ce6842e75d872fe08511a4",
    "DefaultPreset_639465": "b1ee3aa5480d7633d21b158ca76fe1ceb0ac97d9adde8162133c08b38afd7055",
    "DefaultPreset_639466": "926e22056a3bc9a6e1ad6afda74fa59ea34dd7f48f75e8fc715bf0d8f3d8bf69",
}

# overviewConst:33 / :40 / :57; order fallback is NOT overviewColumnOrder.
DEFAULT_COLUMNS = ("ICON", "DISTANCE", "NAME", "TYPE", "VELOCITY")
ALL_COLUMNS = (
    "ICON",
    "DISTANCE",
    "NAME",
    "TYPE",
    "TAG",
    "CORPORATION",
    "ALLIANCE",
    "FACTION",
    "MILITIA",
    "SIZE",
    "VELOCITY",
    "RADIALVELOCITY",
    "TRANSVERSALVELOCITY",
    "ANGULARVELOCITY",
)
# overviewSettingsConst:83; independent of Wingman's eight-tab budget.
CLIENT_TAB_SLOTS = 20
