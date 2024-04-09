from eudplib import *

def is32Bit():
    return Memory(0x190913EC, AtLeast, 1)

def onPluginStart():
    DoActions(RemoveUnit("Any unit", AllPlayers))
    for p in EUDLoopPlayer():
        marine = CUnit.from_read(EPD(0x628438))
        DoActions(CreateUnit(1, "Terran Marine", 1, p))
        marine.hp = 318815 * 256
        marine.wireframeRandomizer = 1
        # set marine max HP accordingly
        f_dwwrite_epd(221179 + EncodeUnit("Terran Marine"),
                      EUDTernary(is32Bit())(ontrue=34 * 256)(onfalse=27 * 256))
        
        darchon = CUnit.from_read(EPD(0x628438))
        DoActions(CreateUnit(1, "Protoss Dark Archon", 1, p))
        darchon.hp = 573929 * 256

        f_dwwrite_epd(221179 + EncodeUnit("Protoss Dark Archon"),
                      EUDTernary(is32Bit())(ontrue=34 * 256)(onfalse=27 * 256))
        EUDBreak()

def beforeTriggerExec():
    pass
