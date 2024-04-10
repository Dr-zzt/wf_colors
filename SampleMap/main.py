from eudplib import *
def onPluginStart():
    DoActions(RemoveUnit("Any unit", AllPlayers))
    for p in EUDLoopPlayer():
        marine = CUnit.from_read(EPD(0x628438))
        DoActions(CreateUnit(1, "Terran Marine", 1, p))
        marine.hp = 318815 * 256
        marine.wireframeRandomizer = 1
        # set marine max HP accordingly
        f_dwwrite_epd(221179 + EncodeUnit("Terran Marine"),
                      EUDTernary(Is64BitWireframe(), neg=True)(ontrue=34 * 256)(onfalse=27 * 256))
        
        darchon = CUnit.from_read(EPD(0x628438))
        DoActions(CreateUnit(1, "Protoss Dark Archon", 1, p))
        darchon.hp = 573929 * 256

        f_dwwrite_epd(221179 + EncodeUnit("Protoss Dark Archon"),
                      EUDTernary(Is64BitWireframe(), neg=True)(ontrue=34 * 256)(onfalse=27 * 256))
        EUDBreak()

def beforeTriggerExec():
    f_printAllAt(1, "{:x} " * 8, *[f_dwread_epd(-11553 + 1 + 9 * i) for i in range(8)])
