import re
from eudplib import *
from eudplib.core.mapdata.stringmap import strmap
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass, asdict, field

import webbrowser
import os
import locale
import json


## Translation
using_korean = locale.getlocale()[0] == 'Korean_Korea'

def __(text: str):
    return text

# def __(text: str):
#     if not using_korean:
#         return text
#     match text:
#         case "Wireframe Color Settings":
#             return "와이어프레임 색상 설정"
#         case "Configuration complete. Please change the plugin settings and re-run euddraft.":
#             return "설정이 완료되었습니다. 플러그인 설정을 변경하고 euddraft를 다시 실행하십시오."
#         case _:
#             return text

settings: dict[str, str]
if TYPE_CHECKING:
    settings = {}


@dataclass
class WFSettings:
    scenario_name_original: str
    scenario_name_new: Optional[str]
    tileset_index: int
    dimensions_are_256_256: bool
    human_plus_computer_is_eight: bool
    assignment_table: dict[str, dict[int, tuple[int]]]


def make_wf_settings() -> WFSettings:
    chkt = GetChkTokenized()

    # scenario name
    scenario_name_index = b2i2(chkt.getsection("SPRP")[0:2])
    scenario_name_bytes = strmap.GetString(scenario_name_index)
    try: # try decoding with utf-8.
        scenario_name_original = scenario_name_bytes.decode('utf-8')
    except UnicodeDecodeError: 
        try: # if it fails, try decoding with system default encoding.
            scenario_name_original = scenario_name_bytes.decode(locale.getpreferredencoding())
        except UnicodeDecodeError: # if it still fails, use cp949.
            scenario_name_original = scenario_name_bytes.decode('cp949')
            
    scenario_name_new = settings.get("new_map_title", None)
    
    # tileset
    tileset_index = b2i2(chkt.getsection("ERA ")) & 7

    # dimensions
    dimensions_are_256_256 = list(chkt.getsection("DIM ")) == [0, 1, 0, 1]
    print(list(chkt.getsection("DIM ")))

    # count the human and computer player numbers
    human_plus_computer_is_eight = {*chkt.getsection("OWNR")[:8]}.issubset({5, 6})

    # extract assignment table from settings
    assignment_table: dict[str, dict[int, tuple[int]]] = {
        "tp": {},
        "z": {},
        "s": {}
    }

    for key, value in settings.items():
        if key.startswith("tp_"):
            assignment_table["tp"][int(key[3:])] = tuple(map(int, value.split(',')))
        elif key.startswith("z_"):
            assignment_table["z"][int(key[2:])] = tuple(map(int, value.split(',')))
        elif key.startswith("s_"):
            assignment_table["s"][int(key[2:])] = tuple(map(int, value.split(',')))

    return WFSettings(
        scenario_name_original=scenario_name_original,
        scenario_name_new=scenario_name_new,
        tileset_index=tileset_index,
        dimensions_are_256_256=dimensions_are_256_256,
        human_plus_computer_is_eight=human_plus_computer_is_eight,
        assignment_table=assignment_table
    )

# GUI for configuration mode

def show_config_dialog(wf_settings: WFSettings):
    html_content = r""""""

    # Write the HTML content to a temporary file
    temp_html_file = 'temp.html'
    with open(temp_html_file, 'w') as f:
        f.write(html_content)

    
    wf_json = json.dumps(asdict(wf_settings), indent=4)
    
    webbrowser.open(f'file://{os.path.realpath(temp_html_file)}')


def unescape_map_name(escaped_map_name):
    map_name = ""
    i = 0
    while i < len(escaped_map_name):
        if escaped_map_name[i] == "\\":
            if i + 1 < len(escaped_map_name) and escaped_map_name[i + 1] == "x":
                # Handle hexadecimal escape sequences
                hex = escaped_map_name[i + 2:i + 4]
                # if hex is not a valid 2-digit hexadecimal number, just add the backslash and x to the map name
                if not re.match("^[0-9A-Fa-f]{2}$", hex):
                    map_name += "\\x"
                    i += 2  # Skip over the backslash and x
                else:
                    map_name += chr(int(hex, 16))
                    i += 4  # Skip over this escape sequence
            elif i + 1 < len(escaped_map_name) and escaped_map_name[i + 1] == "\\":
                # Handle escaped backslashes
                map_name += "\\"
                i += 2  # Skip over this escape sequence
            else:
                # If the backslash is not followed by an x or another backslash, just add the backslash to the map name
                map_name += "\\"
                i += 1
        else:
            map_name += escaped_map_name[i]
            i += 1
    return map_name


def is32Bit():
    return Memory(0x190913EC, AtLeast, 1)


def setup_wf_colors(wf_settings: WFSettings):
    # un-escape new map name
    scenario_name_new = unescape_map_name(wf_settings.scenario_name_new)

    # change map name
    chkt = GetChkTokenized()
    SPRP = bytearray(chkt.getsection("SPRP"))
    SPRP[0:2] = i2b2(GetStringIndex(scenario_name_new))
    chkt.setsection("SPRP", SPRP)

    # convert to byte representation in utf-8
    scenario_name_new_bytes_list = list(scenario_name_new.encode('utf-8'))

    wf_and_mapname_diff = EUDVariable()
    wf_and_mapname_diff << 123 + \
        (0 if wf_settings.tileset_index == 0 else 1) + \
        (0 if wf_settings.dimensions_are_256_256 else 2) + \
        EUDTernary(is32Bit())(0)(64) + \
        f_strlen(0x6D0F78) # Host name length
    
    if wf_settings.human_plus_computer_is_eight:
        num_humans_in_game = EUDVariable()
        num_humans_in_game << 0
        for i in range(8):
            if GetPlayerInfo(i).typestr != "Human":
                continue

            if EUDIf()(f_playerexist(i)):
                num_humans_in_game += 1
            EUDEndIf()
        
        if EUDIf()(num_humans_in_game == 1):
            wf_and_mapname_diff -= 2

    def color_to_wf_index(color: int):
        if color in default_available_colors:
            return default_available_colors.index(color)
        else:
            assert color in scenario_name_new_bytes_list, f"요구되는 색상 {color}을 맵 제목에서 찾을 수 없었습니다."
            return scenario_name_new_bytes_list.index(color) + wf_and_mapname_diff
        

    for index, assignment in wf_settings.assignment_table["tp"].items():
        DoActions([
            SetMemory(tp_solutions[index][i], SetTo, sum(color_to_wf_index(assignment[j]) * (1 << (j * 8)) for j in range(4))) for i in range(2)
        ])
    for index, assignment in wf_settings.assignment_table["z"].items():
        DoActions([
            SetMemory(z_solutions[index][i], SetTo, sum(color_to_wf_index(assignment[j]) * (1 << (j * 8)) for j in range(4))) for i in range(2)
        ])
    for index, assignment in wf_settings.assignment_table["s"].items():
        DoActions([
            SetMemory(s_solutions[index][i], SetTo, 0x10001 * sum(color_to_wf_index(assignment[j]) * (1 << (j * 8)) for j in range(2))) for i in range(2)
        ])


class ConfigurationException(Exception):
    # exception to stop EUDDraft compilation
    pass


def onPluginStart():
    try:
        wf_settings = make_wf_settings()
    except Exception:
        raise ConfigurationException("\n" + __("설정 구성에 실패했습니다.") + "\n")
    
    if settings.get("config_mode", "True") != "False": # config mode
        show_config_dialog(wf_settings)
        raise ConfigurationException("\n" + __("설정 구성 이후 EUDDraft를 다시 실행해 주세요.") + "\n")

    # if not config mode, proceed to wireframe color settings
    setup_wf_colors(wf_settings)

default_available_colors = [0x87, 0x75, 0x8a, 0xa5, 0xa5, 0xa2, 0xa2, 0xa0, 0xa0, 0x29, 0xae, 0x17, 0x17, 0x62, 0xa4, 0xa4, 0xa3, 0xa1, 0x9c, 0xb1, 0x1a, 0x00, 0x00, 0x00]
tp_solutions = [(0x669a40, 0x669cb4), (0x669a44, 0x669cb8), (0x669a48, 0x669cc0), (0x669a4c, 0x669cc4), (0x669a50, 0x669cc8), (0x669a54, 0x669cd0), (0x669a58, 0x669cd4), (0x669a5c, 0x669cd8), (0x669a60, 0x669cdc), (0x669a64, 0x669ce4), (0x669a68, 0x669ce8), (0x669a6c, 0x669cec), (0x669a70, 0x669cf0), (0x669a74, 0x669cf8), (0x669a78, 0x669cfc), (0x669a7c, 0x669d00), (0x669a80, 0x669d04), (0x669a84, 0x669d0c), (0x669a88, 0x669d10), (0x669a8c, 0x669d14), (0x669a90, 0x669d18), (0x669a94, 0x669d20), (0x669a98, 0x669d24), (0x669a9c, 0x669d28), (0x669aa0, 0x669d2c), (0x669aa4, 0x669d34), (0x669aa8, 0x669d38), (0x669aac, 0x669d3c), (0x669ab0, 0x669d40), (0x669ab4, 0x669d48), (0x669ab8, 0x669d4c)]
z_solutions = [(0x669ac4, 0x669d44), (0x669acc, 0x669d50), (0x669ad0, 0x669d54), (0x669ad4, 0x669d58), (0x669ad8, 0x669d5c), (0x669adc, 0x669d60), (0x669ae0, 0x669d64), (0x669ae4, 0x669d68), (0x669ae8, 0x669d70), (0x669aec, 0x669d74), (0x669af0, 0x669d78), (0x669af4, 0x669d7c), (0x669af8, 0x669d84), (0x669afc, 0x669d88), (0x669b00, 0x669d8c), (0x669b04, 0x669d90), (0x669b08, 0x669d98), (0x669b0c, 0x669d9c), (0x669b10, 0x669da0), (0x669b14, 0x669da4), (0x669b18, 0x669dac), (0x669b1c, 0x669db0), (0x669b20, 0x669db4), (0x669b24, 0x669db8), (0x669b28, 0x669dc0), (0x669b2c, 0x669dc4), (0x669b30, 0x669dc8), (0x669b34, 0x669dd0), (0x669b38, 0x669dd4), (0x669b3c, 0x669dd8), (0x669b40, 0x669ddc)]
s_solutions = [(0x669b44, 0x669de8), (0x669b48, 0x669dec), (0x669b4c, 0x669df0), (0x669b50, 0x669df4), (0x669b54, 0x669dfc), (0x669b58, 0x669e00), (0x669b5c, 0x669e04), (0x669b60, 0x669e0c), (0x669b64, 0x669e10), (0x669b68, 0x669e14), (0x669b6c, 0x669e18), (0x669b70, 0x669e1c), (0x669b74, 0x669e24), (0x669abc, 0x669ba8), (0x669ac0, 0x669bac), (0x669ac8, 0x669bb8), (0x669b78, 0x669c94), (0x669b7c, 0x669c98), (0x669b80, 0x669ca0), (0x669b84, 0x669ca4), (0x669b88, 0x669ca8), (0x669b8c, 0x669cac), (0x669b94, 0x669cbc), (0x669ba0, 0x669ccc), (0x669bb0, 0x669ce0), (0x669bc0, 0x669cf4), (0x669bd0, 0x669d08), (0x669be0, 0x669d1c), (0x669bf0, 0x669d30), (0x669c20, 0x669d6c), (0x669c30, 0x669d80)]
