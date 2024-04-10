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
    assignment_table: dict[str, dict[int, dict]]


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

    # count the human and computer player numbers
    human_plus_computer_is_eight = {*chkt.getsection("OWNR")[:8]}.issubset({5, 6})

    # extract assignment table from settings
    assignment_table: dict[str, dict[int, dict]] = {
        "tp": {},
        "z": {},
        "s": {}
    }

    for key, value in settings.items():
        if key.startswith("tp_"):
            assignment_table["tp"][int(key[3:])] = {"index": int(key[3:]), "colors": tuple(map(int, value.split(',')))}
        elif key.startswith("z_"):
            assignment_table["z"][int(key[2:])] = {"index": int(key[2:]), "colors": tuple(map(int, value.split(',')))}
        elif key.startswith("s_"):
            assignment_table["s"][int(key[2:])] = {"index": int(key[2:]), "colors": tuple(map(int, value.split(',')))}

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
    html_content = temp_html_raw.replace("// REPLACE HERE //", f"wf_settings = {json.dumps(asdict(wf_settings), indent=4)}")

    # Write the HTML content to a temporary file
    temp_html_file = 'temp.html'
    with open(temp_html_file, 'w', encoding='utf-8') as f:
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
        EUDTernary(Is64BitWireframe())(64)(0) + \
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
        EUDEndIf()

    def color_to_wf_index(color: int):
        if color in default_available_colors:
            return default_available_colors.index(color)
        else:
            assert color in scenario_name_new_bytes_list, f"요구되는 색상 {color}을 맵 제목에서 찾을 수 없었습니다."
            return scenario_name_new_bytes_list.index(color) + wf_and_mapname_diff
        

    for index, assignment in wf_settings.assignment_table["tp"].items():
        DoActions([
            SetMemory(tp_solutions[index][i], SetTo, sum(color_to_wf_index(assignment["colors"][j]) * (1 << (j * 8)) for j in range(4))) for i in range(2)
        ])
    for index, assignment in wf_settings.assignment_table["z"].items():
        DoActions([
            SetMemory(z_solutions[index][i], SetTo, sum(color_to_wf_index(assignment["colors"][j]) * (1 << (j * 8)) for j in range(4))) for i in range(2)
        ])
    for index, assignment in wf_settings.assignment_table["s"].items():
        DoActions([
            SetMemory(s_solutions[index][i], SetTo, 0x10001 * sum(color_to_wf_index(assignment["colors"][j]) * (1 << (j * 8)) for j in range(2))) for i in range(2)
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

temp_html_raw = r"""<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Color Customizer</title>
    <style>
        html {
            overflow-y: scroll;
        }

        .row {
            display: flex;
        }

        .column {
            flex: 1;
            /* This will make each column take up an equal amount of space */
        }

        .color-options-container {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            /* This creates a consistent gap between color options */
        }

        .color-option {
            display: flex;
            align-items: center;
            border: 1px solid #ccc;
            padding: 10px;
            box-sizing: border-box;
            /* This ensures that the border and padding are included in the element's total width and height */
        }

        .color-indicator {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            margin-right: 10px;
            flex-shrink: 0;
            /* This prevents the color indicator from shrinking if the container gets too small */
        }

        .color-number {
            font-weight: bold;
            flex-grow: 1;
            /* This allows the color number to take up the remaining space in the container */
        }

        .dropdown {
            position: relative;
            display: inline-block;
        }

        .dropdown-content {
            display: none;
            grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
            /* This will create as many columns as can fit in the container, with a minimum width of 160px for each column */
            overflow-y: auto;
            /* Add a scrollbar if the content exceeds the maximum height */
            width: 100%;
            /* Set the width to 100% to allow the dropdown to expand horizontally */
            position: absolute;
            background-color: #f1f1f1;
            min-width: 50vw;
            box-shadow: 0px 8px 16px 0px rgba(0, 0, 0, 0.2);
            z-index: 1;
            white-space: nowrap;
        }

        .dropdown-content a {
            box-sizing: border-box;
            color: black;
            padding: 12px 16px;
            text-decoration: none;
            display: block;
            border: 1px solid #ccc;
            /* Add this line */
        }

        .dropdown-content a:hover {
            background-color: #f1f1f1
        }

        .dropdown:hover .dropdown-content {
            display: grid;
        }

        .dropdown-indicator {
            display: inline-block;
            background-color: wheat;
            color: black;
            padding: 2px;
            font-size: 20px;
            border: 1px solid #ccc;
            cursor: pointer;
            margin-top: 10px;
        }

        .color-indicator {
            display: inline-block;
            width: 15px;
            height: 15px;
            border-radius: 50%;
            margin-right: 5px;
        }

        .color-table {
            border-collapse: collapse;
        }

        .color-table th,
        .color-table td {
            border: 1px solid black;
            padding: 10px;
        }
    </style>
</head>

<body>
    <div class="row">
        <div class="column">
            <h2>맵 제목</h2>
            <div id="map-name">
                원래 제목: <b><span id="base-map-name"></span></b> (<span id="base-map-name-length"></span> bytes)
                <br>
                새 제목: <input type="text" id="new-map-name-input" oninput="refreshColorAvailability()">
                <span id="new-map-name-unescaped-and-cut"></span> (<span id="new-map-name-length"></span> bytes)
                <br><br>
                <div id="required-characters"></div>
                <br>
            </div>
            <h2>기본 활용 가능 색상</h2>
            <div id="default-available-colors" class="color-options-container"></div>
            <h2>맵 제목에 의해 쓸 수 있는 색상</h2>
            <div id="available-colors-by-map" class="color-options-container"></div>
            <h2>더 쓰고 싶은 색상 선택</h2>
            <!-- Color options -->
            <!-- object with element id color-options-container-->
            <div id="additional-colors" class="color-options-container"></div>
            <!-- Dropdown menu here-->
            <div class="dropdown">
                <span class="dropdown-indicator">색상 더 보기 ▼</span>
                <div class="dropdown-content">
                </div>
            </div>
            <h2>플러그인 세팅</h2>
            아래 내용을 플러그인 설정에 붙여넣으세요.
            <button onclick="copyToClipboard()">클립보드에 복사</button>
            <span id="copy-success"></span>
            <pre id="output" style="border: 1px solid black;"></pre>
        </div>

        <div class="column" id="right">
        </div>
    </div>

    <script>

        var wf_settings = {
            "scenario_name_original": "^_^",
            "scenario_name_new": null,
            "tileset_index": 4,
            "dimensions_are_256_256": false,
            "human_plus_computer_is_eight": true,
            "assignment_table": {
                "tp": {},
                "z": {
                    "0": {
                        "index": 0,
                        "colors": [
                            85,
                            81,
                            83,
                            85
                        ]
                    }
                },
                "s": {}
            }
        };

        // REPLACE HERE //
        for (let key of ['tp', 'z', 's']) {
            wf_settings.assignment_table[key] = new Map(Object.entries(wf_settings.assignment_table[key]).map(([k, v]) => [parseInt(k), v]));
        }

        document.getElementById("base-map-name").innerText = wf_settings.scenario_name_original;
        // set inner text of base-map-name-length to the length of the base map name in bytes when encoded to utf-8
        document.getElementById("base-map-name-length").innerText = new TextEncoder().encode(wf_settings.scenario_name_original).length;

        function escapeMapName(mapName) {
            var escapedMapName = "";
            for (var i = 0; i < mapName.length; i++) {
                var charCode = mapName.charCodeAt(i);
                if (charCode < 32 || charCode == 127 || charCode == 58 /* colon */) {
                    escapedMapName += "\\x" + charCode.toString(16).padStart(2, "0");
                } else if (charCode == 92) { // backslash
                    escapedMapName += "\\\\"; // escape backslashes
                } else
                    escapedMapName += mapName[i];
            }
            return escapedMapName;
        }

        function unescapeMapName(escapedMapName) {
            var mapName = "";
            for (var i = 0; i < escapedMapName.length; i++) {
                if (escapedMapName[i] == "\\") {
                    if (escapedMapName[i + 1] == "x") {
                        // Handle hexadecimal escape sequences
                        var hex = escapedMapName.substr(i + 2, 2);
                        // if hex is not a valid 2-digit hexadecimal number, just add the backslash and x to the map name
                        if (!/^[0-9A-Fa-f]{2}$/.test(hex)) {
                            mapName += "\\x";
                            i += 1; // Skip over the backslash and x
                        } else {
                            mapName += String.fromCharCode(parseInt(hex, 16));
                            i += 3; // Skip over this escape sequence
                        }
                    } else if (escapedMapName[i + 1] == "\\") {
                        // Handle escaped backslashes
                        mapName += "\\";
                        i++; // Skip over this escape sequence
                    } else {
                        // If the backslash is not followed by an x or another backslash, just add the backslash to the map name
                        mapName += "\\";
                    }
                } else {
                    mapName += escapedMapName[i];
                }
            }
            return mapName;
        }

        var newMapNameBeforeEscape = wf_settings.scenario_name_new === null ? wf_settings.scenario_name_original : wf_settings.scenario_name_new;

        document.getElementById("new-map-name-input").value = escapeMapName(newMapNameBeforeEscape);

        var colorTagTable = [
            ['#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#ff00ff', '#de00de', '#bd00bd', '#9c009c', '#7c007c', '#5b005b', '#3a003a', '#190019', '#2c2418', '#482414', '#5c2c14', '#703014', '#683c24', '#7c4018', '#784c2c', '#a80808', '#8c5430', '#846044', '#a0541c', '#c44c18', '#bc6824', '#b4703c', '#d06420', '#dc9434', '#e09454', '#ecc454', '#344428', '#406c3c', '#486c50', '#4c8050', '#508c5c', '#5ca078', '#000018', '#001034', '#000850', '#243448', '#304054', '#14347c', '#344c6c', '#405874', '#48688c', '#00709c', '#5880a4', '#4068d4', '#18acb8', '#2424fc', '#6494bc', '#70a8cc', '#8cc0d8', '#94dcf4', '#acdce8', '#acfcfc', '#ccf8f8', '#fcfc00', '#f4e490', '#fcfcc0', '#0c0c0c', '#181410', '#1c1c20', '#282830', '#383024', '#383c44', '#4c4030', '#4c4c4c', '#5c5040', '#585858', '#686868', '#78846c', '#68946c', '#74a47c', '#98948c', '#90b894', '#98c4a8', '#b0b0b0', '#acccb0', '#c4c0bc', '#cce0d0', '#f0f0f0', '#1c1008', '#28180c', '#341008', '#34200c', '#381020', '#342820', '#443408', '#483018', '#600000', '#542820', '#504014', '#5c5414', '#840404', '#684c34', '#7c3830', '#706420', '#7c5050', '#a4341c', '#946c00', '#985c40', '#8c8034', '#987454', '#b85444', '#b09018', '#b0745c', '#f40404', '#c87854', '#fc6854', '#e0a484', '#fc9468', '#fccc2c', '#10fc18', '#0c0020', '#1c1c2c', '#24244c', '#282c68', '#2c3084', '#2018b8', '#343cac', '#686894', '#6490fc', '#7cacfc', '#00e4fc', '#9c9040', '#a89454', '#bca45c', '#ccb860', '#e8d880', '#ecc4b0', '#fcfc38', '#fcfc7c', '#fcfca4', '#080808', '#101010', '#181818', '#282828', '#343434', '#4c3c38', '#444444', '#484858', '#585868', '#746838', '#78645c', '#60607c', '#847474', '#84849c', '#ac8c7c', '#ac9894', '#9090b8', '#b8b8e8', '#f88c14', '#10543c', '#209070', '#2cb494', '#042064', '#481c50', '#083498', '#683078', '#88409c', '#0c48cc', '#bcb834', '#dcdc3c', '#100000', '#240000', '#340000', '#480000', '#601804', '#8c2808', '#c81818', '#e02c2c', '#e82020', '#e85014', '#fc2020', '#e87824', '#f8ac3c', '#001400', '#002800', '#004400', '#006400', '#088008', '#249824', '#3c9c3c', '#58b058', '#68b868', '#80c480', '#94d494', '#0c1424', '#243c64', '#305084', '#385c94', '#4874b4', '#5484c4', '#6094d4', '#78b4ec', '#141008', '#18140c', '#28300c', '#101018', '#141420', '#2c2c40', '#444c68', '#040404', '#1c1810', '#201c14', '#24201c', '#30281c', '#40382c', '#544834', '#685c4c', '#907c64', '#282010', '#2c2414', '#342c18', '#382c1c', '#3c301c', '#403420', '#443824', '#504424', '#584c28', '#64582c', '#0c1004', '#141804', '#1c2008', '#20280c', '#343c10', '#404810', '#202030', '#141414', '#20181c', '#202020', '#282018', '#282424', '#302c2c', '#3c3038', '#3c383c', '#483c30', '#443440', '#544048', '#5c6464', '#6c7478', '#584e2f', '#4d432c', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#ffffff'],
            ['#000000', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#ff00ff', '#de00de', '#bd00bd', '#9c009c', '#7c007c', '#5b005b', '#3a003a', '#190019', '#2c2418', '#482414', '#5c2c14', '#703014', '#683c24', '#7c4018', '#784c2c', '#a80808', '#8c5430', '#846044', '#a0541c', '#c44c18', '#bc6824', '#b4703c', '#d06420', '#dc9434', '#e09454', '#ecc454', '#344428', '#406c3c', '#486c50', '#4c8050', '#508c5c', '#5ca078', '#000018', '#001034', '#000850', '#243448', '#304054', '#14347c', '#344c6c', '#405874', '#48688c', '#00709c', '#5880a4', '#4068d4', '#18acb8', '#2424fc', '#6494bc', '#70a8cc', '#8cc0d8', '#94dcf4', '#acdce8', '#acfcfc', '#ccf8f8', '#fcfc00', '#f4e490', '#fcfcc0', '#0c0c0c', '#181410', '#1c1c20', '#282830', '#383024', '#383c44', '#4c4030', '#4c4c4c', '#5c5040', '#585858', '#686868', '#78846c', '#68946c', '#74a47c', '#98948c', '#90b894', '#98c4a8', '#b0b0b0', '#acccb0', '#c4c0bc', '#cce0d0', '#f0f0f0', '#1c1008', '#28180c', '#341008', '#34200c', '#381020', '#342820', '#443408', '#483018', '#600000', '#542820', '#504014', '#5c5414', '#840404', '#684c34', '#7c3830', '#706420', '#7c5050', '#a4341c', '#946c00', '#985c40', '#8c8034', '#987454', '#b85444', '#b09018', '#b0745c', '#f40404', '#c87854', '#fc6854', '#e0a484', '#fc9468', '#fccc2c', '#10fc18', '#0c0020', '#1c1c2c', '#24244c', '#282c68', '#2c3084', '#2018b8', '#343cac', '#686894', '#6490fc', '#7cacfc', '#00e4fc', '#9c9040', '#a89454', '#bca45c', '#ccb860', '#e8d880', '#ecc4b0', '#fcfc38', '#fcfc7c', '#fcfca4', '#080808', '#101010', '#181818', '#282828', '#343434', '#4c3c38', '#444444', '#484858', '#585868', '#746838', '#78645c', '#60607c', '#847474', '#84849c', '#ac8c7c', '#ac9894', '#9090b8', '#b8b8e8', '#f88c14', '#10543c', '#209070', '#2cb494', '#042064', '#481c50', '#083498', '#683078', '#88409c', '#0c48cc', '#bcb834', '#dcdc3c', '#100000', '#240000', '#340000', '#480000', '#601804', '#8c2808', '#c81818', '#e02c2c', '#e82020', '#e85014', '#fc2020', '#e87824', '#f8ac3c', '#001400', '#002800', '#004400', '#006400', '#088008', '#249824', '#3c9c3c', '#58b058', '#68b868', '#80c480', '#94d494', '#0c1424', '#243c64', '#305084', '#385c94', '#4874b4', '#5484c4', '#6094d4', '#78b4ec', '#040404', '#141414', '#24201c', '#202024', '#242428', '#2c2c2c', '#2c3034', '#30343c', '#343840', '#3c3c3c', '#3c4048', '#40444c', '#4c5058', '#606060', '#747070', '#7c7c7c', '#201810', '#3c2c18', '#10100c', '#141418', '#18181c', '#201c18', '#20181c', '#1c2024', '#241c20', '#282024', '#24282c', '#30242c', '#282c34', '#303030', '#2c3038', '#3c2c34', '#383838', '#44382c', '#40303c', '#443440', '#503c48', '#484848', '#444850', '#484c54', '#545050', '#50545c', '#646464', '#706c6c', '#787474', '#888484', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#ffffff'],
            ['#000000', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#ff00ff', '#de00de', '#bd00bd', '#9c009c', '#7c007c', '#5b005b', '#3a003a', '#190019', '#2c2418', '#482414', '#5c2c14', '#703014', '#683c24', '#7c4018', '#784c2c', '#a80808', '#8c5430', '#846044', '#a0541c', '#c44c18', '#bc6824', '#b4703c', '#d06420', '#dc9434', '#e09454', '#ecc454', '#344428', '#406c3c', '#486c50', '#4c8050', '#508c5c', '#5ca078', '#000018', '#001034', '#000850', '#243448', '#304054', '#14347c', '#344c6c', '#405874', '#48688c', '#00709c', '#5880a4', '#4068d4', '#18acb8', '#2424fc', '#6494bc', '#70a8cc', '#8cc0d8', '#94dcf4', '#acdce8', '#acfcfc', '#ccf8f8', '#fcfc00', '#f4e490', '#fcfcc0', '#0c0c0c', '#181410', '#1c1c20', '#282830', '#383024', '#383c44', '#4c4030', '#4c4c4c', '#5c5040', '#585858', '#686868', '#78846c', '#68946c', '#74a47c', '#98948c', '#90b894', '#98c4a8', '#b0b0b0', '#acccb0', '#c4c0bc', '#cce0d0', '#f0f0f0', '#1c1008', '#28180c', '#341008', '#34200c', '#381020', '#342820', '#443408', '#483018', '#600000', '#542820', '#504014', '#5c5414', '#840404', '#684c34', '#7c3830', '#706420', '#7c5050', '#a4341c', '#946c00', '#985c40', '#8c8034', '#987454', '#b85444', '#b09018', '#b0745c', '#f40404', '#c87854', '#fc6854', '#e0a484', '#fc9468', '#fccc2c', '#10fc18', '#0c0020', '#1c1c2c', '#24244c', '#282c68', '#2c3084', '#2018b8', '#343cac', '#686894', '#6490fc', '#7cacfc', '#00e4fc', '#9c9040', '#a89454', '#bca45c', '#ccb860', '#e8d880', '#ecc4b0', '#fcfc38', '#fcfc7c', '#fcfca4', '#080808', '#101010', '#181818', '#282828', '#343434', '#4c3c38', '#444444', '#484858', '#585868', '#746838', '#78645c', '#60607c', '#847474', '#84849c', '#ac8c7c', '#ac9894', '#9090b8', '#b8b8e8', '#f88c14', '#10543c', '#209070', '#2cb494', '#042064', '#481c50', '#083498', '#683078', '#88409c', '#0c48cc', '#bcb834', '#dcdc3c', '#100000', '#240000', '#340000', '#480000', '#601804', '#8c2808', '#c81818', '#e02c2c', '#e82020', '#e85014', '#fc2020', '#e87824', '#f8ac3c', '#001400', '#002800', '#004400', '#006400', '#088008', '#249824', '#3c9c3c', '#58b058', '#68b868', '#80c480', '#94d494', '#0c1424', '#243c64', '#305084', '#385c94', '#4874b4', '#5484c4', '#6094d4', '#78b4ec', '#544804', '#040810', '#040404', '#141414', '#101418', '#181c24', '#20201c', '#202424', '#202430', '#30302c', '#283034', '#3c4038', '#40443c', '#484c44', '#4c6470', '#708088', '#140c08', '#18100c', '#201810', '#241c14', '#2c1c14', '#302018', '#443424', '#504028', '#58442c', '#000408', '#141820', '#202c38', '#080c0c', '#0c0c10', '#0c1014', '#101414', '#141818', '#181c1c', '#1c2020', '#182028', '#242424', '#242828', '#282c30', '#283030', '#2c3030', '#2c3034', '#383838', '#44382c', '#444840', '#4c5048', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#ffffff'],
            ['#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#ff00ff', '#de00de', '#bd00bd', '#9c009c', '#7c007c', '#5b005b', '#3a003a', '#190019', '#2c2418', '#482414', '#5c2c14', '#703014', '#683c24', '#7c4018', '#784c2c', '#a80808', '#8c5430', '#846044', '#a0541c', '#c44c18', '#bc6824', '#b4703c', '#d06420', '#dc9434', '#e09454', '#ecc454', '#344428', '#406c3c', '#486c50', '#4c8050', '#508c5c', '#5ca078', '#000018', '#001034', '#000850', '#243448', '#304054', '#14347c', '#344c6c', '#405874', '#48688c', '#00709c', '#5880a4', '#4068d4', '#18acb8', '#2424fc', '#6494bc', '#70a8cc', '#8cc0d8', '#94dcf4', '#acdce8', '#acfcfc', '#ccf8f8', '#fcfc00', '#f4e490', '#fcfcc0', '#0c0c0c', '#181410', '#1c1c20', '#282830', '#383024', '#383c44', '#4c4030', '#4c4c4c', '#5c5040', '#585858', '#686868', '#78846c', '#68946c', '#74a47c', '#98948c', '#90b894', '#98c4a8', '#b0b0b0', '#acccb0', '#c4c0bc', '#cce0d0', '#f0f0f0', '#1c1008', '#28180c', '#341008', '#34200c', '#381020', '#342820', '#443408', '#483018', '#600000', '#542820', '#504014', '#5c5414', '#840404', '#684c34', '#7c3830', '#706420', '#7c5050', '#a4341c', '#946c00', '#985c40', '#8c8034', '#987454', '#b85444', '#b09018', '#b0745c', '#f40404', '#c87854', '#fc6854', '#e0a484', '#fc9468', '#fccc2c', '#10fc18', '#0c0020', '#1c1c2c', '#24244c', '#282c68', '#2c3084', '#2018b8', '#343cac', '#686894', '#6490fc', '#7cacfc', '#00e4fc', '#9c9040', '#a89454', '#bca45c', '#ccb860', '#e8d880', '#ecc4b0', '#fcfc38', '#fcfc7c', '#fcfca4', '#080808', '#101010', '#181818', '#282828', '#343434', '#4c3c38', '#444444', '#484858', '#585868', '#746838', '#78645c', '#60607c', '#847474', '#84849c', '#ac8c7c', '#ac9894', '#9090b8', '#b8b8e8', '#f88c14', '#10543c', '#209070', '#2cb494', '#042064', '#481c50', '#083498', '#683078', '#88409c', '#0c48cc', '#bcb834', '#dcdc3c', '#100000', '#240000', '#340000', '#480000', '#601804', '#8c2808', '#c81818', '#e02c2c', '#e82020', '#e85014', '#fc2020', '#e87824', '#f8ac3c', '#001400', '#002800', '#004400', '#006400', '#088008', '#249824', '#3c9c3c', '#58b058', '#68b868', '#80c480', '#94d494', '#0c1424', '#243c64', '#305084', '#385c94', '#4874b4', '#5484c4', '#6094d4', '#78b4ec', '#241414', '#301c18', '#3c241c', '#040404', '#141414', '#181414', '#1c1818', '#201c1c', '#242020', '#28201c', '#282424', '#2c2828', '#302c2c', '#343030', '#3c3030', '#403838', '#140c0c', '#280c0c', '#281814', '#34201c', '#500c0c', '#442c24', '#700c0c', '#940c0c', '#b02800', '#100c10', '#242024', '#2c2420', '#282428', '#302424', '#2c282c', '#342828', '#302c30', '#382c2c', '#343034', '#383438', '#403434', '#40303c', '#3c383c', '#443440', '#483838', '#403c40', '#483844', '#48444c', '#544048', '#60484c', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#2323ff', '#ffffff'],
            ['#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#ff00ff', '#de00de', '#bd00bd', '#9c009c', '#7c007c', '#5b005b', '#3a003a', '#190019', '#2c2418', '#482414', '#5c2c14', '#703014', '#683c24', '#7c4018', '#784c2c', '#a80808', '#8c5430', '#846044', '#a0541c', '#c44c18', '#bc6824', '#b4703c', '#d06420', '#dc9434', '#e09454', '#ecc454', '#344428', '#406c3c', '#486c50', '#4c8050', '#508c5c', '#5ca078', '#000018', '#001034', '#000850', '#243448', '#304054', '#14347c', '#344c6c', '#405874', '#48688c', '#00709c', '#5880a4', '#4068d4', '#18acb8', '#2424fc', '#6494bc', '#70a8cc', '#8cc0d8', '#94dcf4', '#acdce8', '#acfcfc', '#ccf8f8', '#fcfc00', '#f4e490', '#fcfcc0', '#0c0c0c', '#181410', '#1c1c20', '#282830', '#383024', '#383c44', '#4c4030', '#4c4c4c', '#5c5040', '#585858', '#686868', '#78846c', '#68946c', '#74a47c', '#98948c', '#90b894', '#98c4a8', '#b0b0b0', '#acccb0', '#c4c0bc', '#cce0d0', '#f0f0f0', '#1c1008', '#28180c', '#341008', '#34200c', '#381020', '#342820', '#443408', '#483018', '#600000', '#542820', '#504014', '#5c5414', '#840404', '#684c34', '#7c3830', '#706420', '#7c5050', '#a4341c', '#946c00', '#985c40', '#8c8034', '#987454', '#b85444', '#b09018', '#b0745c', '#f40404', '#c87854', '#fc6854', '#e0a484', '#fc9468', '#fccc2c', '#10fc18', '#0c0020', '#1c1c2c', '#24244c', '#282c68', '#2c3084', '#2018b8', '#343cac', '#686894', '#6490fc', '#7cacfc', '#00e4fc', '#9c9040', '#a89454', '#bca45c', '#ccb860', '#e8d880', '#ecc4b0', '#fcfc38', '#fcfc7c', '#fcfca4', '#080808', '#101010', '#181818', '#282828', '#343434', '#4c3c38', '#444444', '#484858', '#585868', '#746838', '#78645c', '#60607c', '#847474', '#84849c', '#ac8c7c', '#ac9894', '#9090b8', '#b8b8e8', '#f88c14', '#10543c', '#209070', '#2cb494', '#042064', '#481c50', '#083498', '#683078', '#88409c', '#0c48cc', '#bcb834', '#dcdc3c', '#100000', '#240000', '#340000', '#480000', '#601804', '#8c2808', '#c81818', '#e02c2c', '#e82020', '#e85014', '#fc2020', '#e87824', '#f8ac3c', '#001400', '#002800', '#004400', '#006400', '#088008', '#249824', '#3c9c3c', '#58b058', '#68b868', '#80c480', '#94d494', '#0c1424', '#243c64', '#305084', '#385c94', '#4874b4', '#5484c4', '#6094d4', '#78b4ec', '#141008', '#18140c', '#242c0c', '#101018', '#141420', '#2c2c40', '#444c68', '#040404', '#1c1810', '#201c14', '#24201c', '#30281c', '#40382c', '#544838', '#685c4c', '#907c64', '#282014', '#302814', '#342c18', '#382c1c', '#3c301c', '#443824', '#544430', '#0c1004', '#141804', '#181c08', '#1c2008', '#20240c', '#2c3410', '#343c10', '#404810', '#202030', '#28283c', '#303448', '#141414', '#20181c', '#282018', '#241c24', '#282424', '#302c2c', '#3c2c34', '#3c383c', '#483c30', '#443440', '#503c48', '#5c5034', '#2323ff', '#2323ff', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#ffffff'],
            ['#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#ff00ff', '#de00de', '#bd00bd', '#9c009c', '#7c007c', '#5b005b', '#3a003a', '#190019', '#2c2418', '#482414', '#5c2c14', '#703014', '#683c24', '#7c4018', '#784c2c', '#a80808', '#8c5430', '#846044', '#a0541c', '#c44c18', '#bc6824', '#b4703c', '#d06420', '#dc9434', '#e09454', '#ecc454', '#344428', '#406c3c', '#486c50', '#4c8050', '#508c5c', '#5ca078', '#000018', '#001034', '#000850', '#243448', '#304054', '#14347c', '#344c6c', '#405874', '#48688c', '#00709c', '#5880a4', '#4068d4', '#18acb8', '#2424fc', '#6494bc', '#70a8cc', '#8cc0d8', '#94dcf4', '#acdce8', '#acfcfc', '#ccf8f8', '#fcfc00', '#f4e490', '#fcfcc0', '#0c0c0c', '#181410', '#1c1c20', '#282830', '#383024', '#383c44', '#4c4030', '#4c4c4c', '#5c5040', '#585858', '#686868', '#78846c', '#68946c', '#74a47c', '#98948c', '#90b894', '#98c4a8', '#b0b0b0', '#acccb0', '#c4c0bc', '#cce0d0', '#f0f0f0', '#1c1008', '#28180c', '#341008', '#34200c', '#381020', '#342820', '#443408', '#483018', '#600000', '#542820', '#504014', '#5c5414', '#840404', '#684c34', '#7c3830', '#706420', '#7c5050', '#a4341c', '#946c00', '#985c40', '#8c8034', '#987454', '#b85444', '#b09018', '#b0745c', '#f40404', '#c87854', '#fc6854', '#e0a484', '#fc9468', '#fccc2c', '#10fc18', '#0c0020', '#1c1c2c', '#24244c', '#282c68', '#2c3084', '#2018b8', '#343cac', '#686894', '#6490fc', '#7cacfc', '#00e4fc', '#9c9040', '#a89454', '#bca45c', '#ccb860', '#e8d880', '#ecc4b0', '#fcfc38', '#fcfc7c', '#fcfca4', '#080808', '#101010', '#181818', '#282828', '#343434', '#4c3c38', '#444444', '#484858', '#585868', '#746838', '#78645c', '#60607c', '#847474', '#84849c', '#ac8c7c', '#ac9894', '#9090b8', '#b8b8e8', '#f88c14', '#10543c', '#209070', '#2cb494', '#042064', '#481c50', '#083498', '#683078', '#88409c', '#0c48cc', '#bcb834', '#dcdc3c', '#100000', '#240000', '#340000', '#480000', '#601804', '#8c2808', '#c81818', '#e02c2c', '#e82020', '#e85014', '#fc2020', '#e87824', '#f8ac3c', '#001400', '#002800', '#004400', '#006400', '#088008', '#249824', '#3c9c3c', '#58b058', '#68b868', '#80c480', '#94d494', '#0c1424', '#243c64', '#305084', '#385c94', '#4874b4', '#5484c4', '#6094d4', '#78b4ec', '#080400', '#140804', '#281008', '#34180c', '#3c180c', '#402010', '#502c10', '#542410', '#543014', '#643818', '#783418', '#8c5020', '#985824', '#a05c24', '#a86028', '#8c8068', '#040000', '#180c04', '#2c140c', '#301408', '#38180c', '#381c10', '#441c0c', '#442810', '#482810', '#4c2010', '#4c2c10', '#582818', '#602c18', '#682c14', '#683018', '#704018', '#743c20', '#804820', '#8c4c28', '#905028', '#945420', '#20181c', '#281c20', '#3c2c34', '#403c30', '#443440', '#503c48', '#685c4c', '#847460', '#948874', '#2323ff', '#2323ff', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#ffffff'],
            ['#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#ff00ff', '#de00de', '#bd00bd', '#9c009c', '#7c007c', '#5b005b', '#3a003a', '#190019', '#2c2418', '#482414', '#5c2c14', '#703014', '#683c24', '#7c4018', '#784c2c', '#a80808', '#8c5430', '#846044', '#a0541c', '#c44c18', '#bc6824', '#b4703c', '#d06420', '#dc9434', '#e09454', '#ecc454', '#344428', '#406c3c', '#486c50', '#4c8050', '#508c5c', '#5ca078', '#000018', '#001034', '#000850', '#243448', '#304054', '#14347c', '#344c6c', '#405874', '#48688c', '#00709c', '#5880a4', '#4068d4', '#18acb8', '#2424fc', '#6494bc', '#70a8cc', '#8cc0d8', '#94dcf4', '#acdce8', '#acfcfc', '#ccf8f8', '#fcfc00', '#f4e490', '#fcfcc0', '#0c0c0c', '#181410', '#1c1c20', '#282830', '#383024', '#383c44', '#4c4030', '#4c4c4c', '#5c5040', '#585858', '#686868', '#78846c', '#68946c', '#74a47c', '#98948c', '#90b894', '#98c4a8', '#b0b0b0', '#acccb0', '#c4c0bc', '#cce0d0', '#f0f0f0', '#1c1008', '#28180c', '#341008', '#34200c', '#381020', '#342820', '#443408', '#483018', '#600000', '#542820', '#504014', '#5c5414', '#840404', '#684c34', '#7c3830', '#706420', '#7c5050', '#a4341c', '#946c00', '#985c40', '#8c8034', '#987454', '#b85444', '#b09018', '#b0745c', '#f40404', '#c87854', '#fc6854', '#e0a484', '#fc9468', '#fccc2c', '#10fc18', '#0c0020', '#1c1c2c', '#24244c', '#282c68', '#2c3084', '#2018b8', '#343cac', '#686894', '#6490fc', '#7cacfc', '#00e4fc', '#9c9040', '#a89454', '#bca45c', '#ccb860', '#e8d880', '#ecc4b0', '#fcfc38', '#fcfc7c', '#fcfca4', '#080808', '#101010', '#181818', '#282828', '#343434', '#4c3c38', '#444444', '#484858', '#585868', '#746838', '#78645c', '#60607c', '#847474', '#84849c', '#ac8c7c', '#ac9894', '#9090b8', '#b8b8e8', '#f88c14', '#10543c', '#209070', '#2cb494', '#042064', '#481c50', '#083498', '#683078', '#88409c', '#0c48cc', '#bcb834', '#dcdc3c', '#100000', '#240000', '#340000', '#480000', '#601804', '#8c2808', '#c81818', '#e02c2c', '#e82020', '#e85014', '#fc2020', '#e87824', '#f8ac3c', '#001400', '#002800', '#004400', '#006400', '#088008', '#249824', '#3c9c3c', '#58b058', '#68b868', '#80c480', '#94d494', '#0c1424', '#243c64', '#305084', '#385c94', '#4874b4', '#5484c4', '#6094d4', '#78b4ec', '#302818', '#382c1c', '#182408', '#182c08', '#202c0c', '#1c3408', '#283410', '#203c08', '#28400c', '#204c04', '#202010', '#606060', '#707070', '#787878', '#888888', '#9c9c9c', '#100c08', '#18140c', '#201810', '#282014', '#0c1404', '#102004', '#0c1018', '#242838', '#080804', '#202020', '#282024', '#20202c', '#30281c', '#30242c', '#303030', '#2c3038', '#382c34', '#303440', '#383838', '#40343c', '#404040', '#3c4050', '#4c5060', '#646464', '#6c6c6c', '#7c7c7c', '#949498', '#a4a4a8', '#b8b8b8', '#cccccc', '#2323ff', '#2323ff', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#ffffff'],
            ['#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#ff00ff', '#de00de', '#bd00bd', '#9c009c', '#7c007c', '#5b005b', '#3a003a', '#190019', '#2c2418', '#482414', '#5c2c14', '#703014', '#683c24', '#7c4018', '#784c2c', '#a80808', '#8c5430', '#846044', '#a0541c', '#c44c18', '#bc6824', '#b4703c', '#d06420', '#dc9434', '#e09454', '#ecc454', '#344428', '#406c3c', '#486c50', '#4c8050', '#508c5c', '#5ca078', '#000018', '#001034', '#000850', '#243448', '#304054', '#14347c', '#344c6c', '#405874', '#48688c', '#00709c', '#5880a4', '#4068d4', '#18acb8', '#2424fc', '#6494bc', '#70a8cc', '#8cc0d8', '#94dcf4', '#acdce8', '#acfcfc', '#ccf8f8', '#fcfc00', '#f4e490', '#fcfcc0', '#0c0c0c', '#181410', '#1c1c20', '#282830', '#383024', '#383c44', '#4c4030', '#4c4c4c', '#5c5040', '#585858', '#686868', '#78846c', '#68946c', '#74a47c', '#98948c', '#90b894', '#98c4a8', '#b0b0b0', '#acccb0', '#c4c0bc', '#cce0d0', '#f0f0f0', '#1c1008', '#28180c', '#341008', '#34200c', '#381020', '#342820', '#443408', '#483018', '#600000', '#542820', '#504014', '#5c5414', '#840404', '#684c34', '#7c3830', '#706420', '#7c5050', '#a4341c', '#946c00', '#985c40', '#8c8034', '#987454', '#b85444', '#b09018', '#b0745c', '#f40404', '#c87854', '#fc6854', '#e0a484', '#fc9468', '#fccc2c', '#10fc18', '#0c0020', '#1c1c2c', '#24244c', '#282c68', '#2c3084', '#2018b8', '#343cac', '#686894', '#6490fc', '#7cacfc', '#00e4fc', '#9c9040', '#a89454', '#bca45c', '#ccb860', '#e8d880', '#ecc4b0', '#fcfc38', '#fcfc7c', '#fcfca4', '#080808', '#101010', '#181818', '#282828', '#343434', '#4c3c38', '#444444', '#484858', '#585868', '#746838', '#78645c', '#60607c', '#847474', '#84849c', '#ac8c7c', '#ac9894', '#9090b8', '#b8b8e8', '#f88c14', '#10543c', '#209070', '#2cb494', '#042064', '#481c50', '#083498', '#683078', '#88409c', '#0c48cc', '#bcb834', '#dcdc3c', '#100000', '#240000', '#340000', '#480000', '#601804', '#8c2808', '#c81818', '#e02c2c', '#e82020', '#e85014', '#fc2020', '#e87824', '#f8ac3c', '#001400', '#002800', '#004400', '#006400', '#088008', '#249824', '#3c9c3c', '#58b058', '#68b868', '#80c480', '#94d494', '#0c1424', '#243c64', '#305084', '#385c94', '#4874b4', '#5484c4', '#6094d4', '#78b4ec', '#08080c', '#080810', '#0c0c14', '#10101c', '#141420', '#141824', '#181828', '#1c1c34', '#20243c', '#282c40', '#282c4c', '#303450', '#38405c', '#040404', '#102020', '#202430', '#040408', '#0c0c18', '#101018', '#0c1418', '#101020', '#101420', '#141424', '#181824', '#141828', '#1c202c', '#242848', '#343c58', '#444c68', '#0c0c10', '#081010', '#0c1014', '#10181c', '#141c20', '#20181c', '#142024', '#241c20', '#182428', '#2c2028', '#1c2c30', '#282c38', '#382c34', '#303440', '#443440', '#3c4050', '#503c48', '#2323ff', '#2323ff', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#000000', '#ffffff']
        ]

        var defaultAvailableColors = [
            0x87, 0x75, 0x8a, 0xa5, 0xa2, 0xa0, 0x29, 0xae, 0x17, 0x62, 0xa4, 0xa3, 0xa1, 0x9c, 0xb1, 0x1a, 0x00,
            97 /*a*/, 44 /*,*/, 49 /*1*/
        ]

        var mapnameEnabledColors = [];

        var colorTagMap = colorTagTable[wf_settings["tileset_index"]];
        var chosenColors = [85, 128, 134, 191];
        var chosenColorsForUse = [];

        // Create the color options
        function createColorOption(color, checked = false, fixed = false) {
            const checkboxAttributes = (fixed ? 'disabled ' : '') + (checked ? 'checked ' : '');
            return `
                <div class="color-option">
                    <div class="color-indicator" style="background-color: ${colorTagMap[color]};"></div>
                    <span class="color-number">${color}</span>
                    <input type="checkbox" id="color${color}" ${checkboxAttributes} onchange="checkChanged(this, ${color})">
                </div>
            `;
        }

        function checkChanged(checkbox, color) {
            if (checkbox.checked) {
                chosenColorsForUse.push(color);
            } else {
                chosenColorsForUse = chosenColorsForUse.filter(c => c !== color);
            }
            refreshRequirements();
        }

        var defaultAvailable = defaultAvailableColors.sort((a, b) => a - b).map(color => createColorOption(color, true, true));
        var defaultAvailableHTML = defaultAvailable.join('');
        document.getElementById('default-available-colors').innerHTML = defaultAvailableHTML;

        function refreshColorAvailability() {
            // get new map name
            var newMapName = unescapeMapName(document.getElementById("new-map-name-input").value);
            // replace ascii code 0-31 into blank for unescapeMapName(newMapName)
            document.getElementById("new-map-name-unescaped-and-cut").innerText = newMapName.replace(/[\x00-\x1F]/g, '');
            var newMapNameBytes = new TextEncoder().encode(newMapName);
            var new_map_name_length = newMapNameBytes.length;
            // if length is at least 32, make the length red
            if (newMapNameBytes.length >= 32) {
                document.getElementById('new-map-name-length').style.color = 'red';
            } else {
                document.getElementById('new-map-name-length').style.color = 'black';
            }
            document.getElementById('new-map-name-length').innerHTML = newMapNameBytes.length;

            // get the list of available colors by map name
            // discard all but the first 31 items of newMapNameBytes
            // and then convert to list while removing duplicants
            mapnameEnabledColors = [...new Set(newMapNameBytes.slice(0, 31))].filter(color => color >= 14);
            // remove overlap with default available colors
            mapnameEnabledColors = mapnameEnabledColors.filter(color => !defaultAvailableColors.includes(color));
            var mapnameEnabledColorOptions = mapnameEnabledColors.sort((a, b) => a - b).map(color => createColorOption(color, true, true));
            var mapnameEnabledColorOptionsHTML = mapnameEnabledColorOptions.join('');
            document.getElementById('available-colors-by-map').innerHTML = mapnameEnabledColorOptionsHTML;

            // additional colors
            var additionalColorOptions = chosenColors.filter(color => !mapnameEnabledColors.includes(color)).sort((a, b) => a - b)
            additionalColorOptions = additionalColorOptions.map(color => createColorOption(color, chosenColorsForUse.includes(color), false));
            var additionalColorOptionsHTML = additionalColorOptions.join('');
            document.getElementById('additional-colors').innerHTML = additionalColorOptionsHTML;

            // refresh dropdown
            refreshDropdown();

            // refresh requirements
            refreshRequirements();

            // update output
            updateOutput();
        }

        function chooseDropdownColor(color) {
            if (!chosenColors.includes(color)) {
                chosenColors.push(color);
            }
            refreshColorAvailability();
        }

        function refreshDropdown() {
            // Save the current scroll position
            var scrollPosition = window.pageYOffset || document.documentElement.scrollTop;

            // Get the dropdown content container
            var dropdownContent = document.querySelector('.dropdown .dropdown-content');
            dropdownContent.innerHTML = '';
            // Generate the color options
            for (var colorIndex in colorTagMap) {
                // convert to int
                colorIndexInt = parseInt(colorIndex);
                if (chosenColors.includes(colorIndexInt) ||
                    defaultAvailableColors.includes(colorIndexInt) ||
                    mapnameEnabledColors.includes(colorIndexInt) ||
                    colorIndexInt < 14 || // color not represented correctly in SC
                    colorIndexInt >= 0b11111000 || // not representable by utf-8
                    colorIndexInt >= 192) // not worth the effort to support this
                    continue;

                var colorCode = colorTagMap[colorIndex];

                // Create a new color option
                var colorOption = document.createElement('a');
                colorOption.id = 'dropdown-color-' + colorIndex;
                colorOption.setAttribute('data-value', colorCode);
                colorOption.setAttribute('onClick', 'chooseDropdownColor(' + colorIndex + ')');
                colorOption.setAttribute('href', '#');

                // Create the color indicator
                var colorIndicator = document.createElement('span');
                colorIndicator.className = 'color-indicator';
                colorIndicator.style.backgroundColor = colorCode;

                // Add the color indicator and color name to the color option
                colorOption.appendChild(colorIndicator);
                colorOption.appendChild(document.createTextNode(colorIndex));

                // Add the color option to the dropdown content
                dropdownContent.appendChild(colorOption);
            }
            // Restore the scroll position after 1 second
            setTimeout(function () { window.scrollTo(0, scrollPosition); }, 50); // could be made better...
        }

        function requirementButtonClick(character) {
            document.getElementById('new-map-name-input').value += escapeMapName(character);
            refreshColorAvailability();
        }

        // Create the refreshment bar
        function createRequirement(color) {
            var corresponding_character = '';
            if (color < 128) {
                corresponding_character = escapeMapName(String.fromCharCode(color));
            } else if (color == 128) {
                // return blank character
                corresponding_character = String.fromCharCode(0x3000);
            } else /* if (color < 192) */ {
                corresponding_character = String.fromCharCode(0x2500 + color - 128);
            }
            return `
                <div class="requirement">
                    <span style="color: red;">* ${color}번에 대응되는 글자가 없습니다.</span>
                    <button onclick="requirementButtonClick('${corresponding_character}')">연관 글자 ${corresponding_character} 추가하기</button>
                </div>
            `;
        }

        function refreshRequirements() {
            // get a list of chosenColorsForUse that are not in mapnameEnabledColors
            var missingColors = chosenColorsForUse.filter(color => !mapnameEnabledColors.includes(color)).map(color => createRequirement(color));
            var missingColorsHTML = missingColors.join('');
            document.getElementById('required-characters').innerHTML = missingColorsHTML;
        }

        // PART TWO: TABLES
        function createColorTable(id, full_name, row_count) {
            var headers = '';
            for (var i = 0; i < row_count; i++) {
                headers += `<th>${i + 1}번 색상</th>`;
            }
            return `
                <h3>${full_name}</h3>
                <button onclick="addRow('${id}', ${row_count})" id="${id}-button">행 추가</button>
                <br><br>
                <table class="color-table" id="${id}-table">
                    <thead>
                        <tr>
                            <th>번호</th>
                            ${headers}
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                    </tbody>
                </table>
            `;
        }

        document.getElementById("right").innerHTML += createColorTable('tp', "테란/프로토스", 4);
        document.getElementById("right").innerHTML += createColorTable('z', "저그", 4);
        document.getElementById("right").innerHTML += createColorTable('s', "실드", 2);

        function ColorAssignment(index, colors) {
            this.index = index;
            this.colors = colors;
        }

        assignment_table = wf_settings["assignment_table"];

        function createRow(tableId, index, numColumns, assignment) {
            var table = document.getElementById(tableId + "-table");
            var row = table.insertRow(-1);
            row.id = `${tableId}-row-${index}`;
            for (var i = 0; i < numColumns + 2; i++) {
                var cell = row.insertCell(i);
                switch (i) {
                    case 0:
                        cell.innerHTML = `<span id=${tableId}-row-${index}-sign>${index}</span>`;
                        break;
                    case numColumns + 1:
                        cell.innerHTML = `<button onclick="removeRow('${tableId}', ${index})">제거</button>`;
                        break;
                    default:
                        cell.innerHTML = `<input type="number" id="${tableId}-row-${index}-color-${i - 1}" min="0" max="255" value="${assignment.colors[i - 1]}" style="width: 50px;"
                                           onchange="assignmentColorChanged('${tableId}', '${tableId}-row-${index}-color-${i - 1}', ${index}, ${i - 1})">
                                          <div class="color-indicator" id="${tableId}-row-${index}-color-${i - 1}-indicator" style="background-color: ${colorTagMap[assignment.colors[i - 1]]};"></div>`;
                        break;
                }
            }
        }

        function addInitialRows() {
            console.log(assignment_table);
            for (var tableId in assignment_table) {
                var table = assignment_table[tableId];
                for (var [index, assignment] of table) {
                    createRow(tableId, index, assignment.colors.length, assignment);
                }
            }
        }

        function addRow(tableId, numColumns) {
            existing_assignments = assignment_table[tableId];
            var nextIndex = 0;
            for (var i = 0; i < 30; i++) {
                if (!existing_assignments.has(i)) {
                    nextIndex = i;
                    break;
                }
            }
            if (i == 30) {
                alert("Cannot add more rows.");
                return;
            }

            var newAssignment = new ColorAssignment(nextIndex, Array(numColumns).fill(135));
            existing_assignments.set(nextIndex, newAssignment);

            createRow(tableId, nextIndex, numColumns, newAssignment);

            updateOutput();
        }

        function removeRow(tableId, index) {
            assignment_table[tableId].delete(index);
            var table = document.getElementById(tableId + "-table");
            var row = document.getElementById(`${tableId}-row-${index}`);
            table.deleteRow(row.rowIndex);
            updateOutput();
        }

        function assignmentColorChanged(tableId, inputId, index, colorIndex) {
            var color = parseInt(document.getElementById(inputId).value);
            if (color < 0 || color > 255) {
                return;
            }
            assignment_table[tableId].get(index).colors[colorIndex] = color;
            document.getElementById(inputId + "-indicator").style.backgroundColor = colorTagMap[color];
            updateOutput();
        }

        function checkTableValidity() {
            var valid = true;
            for (var tableId in assignment_table) {
                var table = assignment_table[tableId];
                for (var [index, assignment] of table) {
                    var this_index_is_valid = true;
                    for (var color of assignment.colors) {
                        if (!mapnameEnabledColors.includes(color) && !defaultAvailableColors.includes(color)) {
                            valid = false;
                            this_index_is_valid = false;
                            // make corresponding sign red
                            document.getElementById(`${tableId}-row-${index}-sign`).style.color = 'red';
                        }
                    }
                    if (this_index_is_valid) {
                        document.getElementById(`${tableId}-row-${index}-sign`).style.color = 'black';
                    }
                }
            }
            return valid;
        }

        var hpMap = new Map();
        hpMap['tp'] =
            [[318815, 34, 27], [318818, 34, 27], [318822, 34, 27], [318826, 34, 27], [318830, 34, 27], [318834, 34, 27], [318837, 34, 27], [318841, 34, 27], [318845, 34, 27], [318849, 34, 27], [318852, 34, 27], [318856, 34, 27], [318860, 34, 27], [318864, 34, 27], [318868, 34, 27], [318871, 34, 27], [318875, 34, 27], [318879, 34, 27], [318883, 34, 27], [318886, 34, 27], [318890, 34, 27], [318894, 34, 27], [318898, 34, 27], [318902, 34, 27], [318905, 34, 27], [318909, 34, 27], [318913, 34, 27], [318917, 34, 27], [318920, 34, 27], [318924, 34, 27], [318928, 34, 27]];
        hpMap['z'] =
            [[573929, 34, 27], [573945, 34, 27], [573950, 34, 27], [573956, 34, 27], [573961, 34, 27], [573968, 34, 27], [573975, 34, 27], [573982, 34, 27], [573988, 34, 27], [573995, 34, 27], [574002, 34, 27], [574009, 34, 27], [574016, 34, 27], [574022, 34, 27], [574029, 34, 27], [574036, 34, 27], [574043, 34, 27], [574050, 34, 27], [574056, 34, 27], [574063, 34, 27], [574070, 34, 27], [574077, 34, 27], [574084, 34, 27], [574090, 34, 27], [574097, 34, 27], [574104, 34, 27], [574111, 34, 27], [574118, 34, 27], [574124, 34, 27], [574131, 34, 27], [574138, 34, 27]];
        hpMap['s'] =
            [[820246, 34, 27], [820255, 34, 27], [820265, 34, 27], [820275, 34, 27], [820284, 34, 27], [820294, 34, 27], [820304, 34, 27], [820314, 34, 27], [820323, 34, 27], [820333, 34, 27], [820343, 34, 27], [820352, 34, 27], [820362, 34, 27], [940491, 39, 31], [940502, 39, 31], [940524, 39, 31], [941015, 39, 31], [941026, 39, 31], [941037, 39, 31], [941048, 39, 31], [941059, 39, 31], [941070, 39, 31], [941098, 39, 31], [941134, 39, 31], [941178, 39, 31], [941222, 39, 31], [941267, 39, 31], [941311, 39, 31], [941355, 39, 31], [941488, 39, 31], [941532, 39, 31]];

        function updateOutput() {
            if (!checkTableValidity()) {
                document.getElementById('output').innerText = '색상이 잘못되었습니다.';
                return;
            }

            var output =
                `[wf_colors]

:: 편집 창을 다시 띄우고 싶다면 아래 부분을 지우거나 False를 True로 바꾸세요.
config_mode: False


`;
            // add new map name to output
            output += `:: 새로운 맵 제목
new_map_title:${document.getElementById("new-map-name-input").value}\n\n`;
            // output color assignments
            for (var tableId in assignment_table) {
                var table = assignment_table[tableId];
                for (var [index, assignment] of table) {
                    var hpInfo = hpMap[tableId][index];
                    output += `:: 현재 체/실: ${hpInfo[0]}, 32비트 최대 체/실: ${hpInfo[1]}, 64비트 최대 체/실: ${hpInfo[2]}\n`;
                    output += `${tableId}_${index}: `;
                    output += assignment.colors.join(',');
                    output += '\n\n';
                }
            }
            document.getElementById('output').innerText = output;
        }

        addInitialRows();
        refreshColorAvailability();


        function copyToClipboard() {
            var outputText = document.getElementById('output').innerText;
            navigator.clipboard.writeText(outputText)
                .then(() => {
                    var copySuccess = document.getElementById('copy-success');
                    copySuccess.innerText = '복사 완료!';
                    setTimeout(() => {
                        copySuccess.innerText = '';
                    }, 1000);
                })
                .catch(err => {
                    console.error('Failed to copy: ', err);
                });
        }

    </script>
</body>

</html>"""
