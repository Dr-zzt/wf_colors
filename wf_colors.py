from eudplib import *
from eudplib.core.mapdata.stringmap import strmap
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass, asdict

import webbrowser
import os
import locale
import json


## Translation
using_korean = locale.getlocale()[0] == 'Korean_Korea'

def __(text: str):
    if not using_korean:
        return text
    
    match text:
        case "Wireframe Color Settings":
            return "와이어프레임 색상 설정"
        case "Configuration complete. Please change the plugin settings and re-run euddraft.":
            return "설정이 완료되었습니다. 플러그인 설정을 변경하고 euddraft를 다시 실행하십시오."
        case _:
            return text

settings: dict[str]
if TYPE_CHECKING:
    settings = {}


@dataclass
class WFSettings:
    scenario_name_original: str
    scenario_name_new: Optional[str]
    tileset_index: int
    dimensions_are_256_256: bool
    human_plus_computer_is_eight: bool


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
            
    scenario_name_new = settings.get("scenario_name_new", None)
    
    # tileset
    tileset_index = b2i2(chkt.getsection("ERA ")) & 7

    # dimensions
    dimensions_are_256_256 = list(chkt.getsection("DIM ")) == [1, 0, 1, 0]

    # count the human and computer player numbers
    human_plus_computer_is_eight = {*chkt.getsection("OWNR")[:8]}.issubset({5, 6})

    return WFSettings(
        scenario_name_original=scenario_name_original,
        scenario_name_new=scenario_name_new,
        tileset_index=tileset_index,
        dimensions_are_256_256=dimensions_are_256_256,
        human_plus_computer_is_eight=human_plus_computer_is_eight
    )

# GUI for configuration mode

def show_config_dialog(wf_settings: WFSettings):
    html_content_en = r"""
<html>
<body>
<h1>Configuration</h1>
<p>Please change the plugin settings and re-run euddraft.</p>
<p id="params"></p>

<script>
// Get the fragment identifier
var fragment = window.location.hash.substring(1);

// Create a URLSearchParams object
var urlParams = new URLSearchParams(fragment);

// Create a string to hold the parameters
var paramString = '';

// Loop through all parameters
for (var pair of urlParams.entries()) {
    paramString += pair[0]+ ': ' + pair[1] + '<br>';
}

// Insert the parameters into the HTML
document.getElementById('params').innerHTML = paramString;
</script>

</body>
</html>
    """

    # Write the HTML content to a temporary file
    temp_html_file = 'temp.html'
    with open(temp_html_file, 'w') as f:
        f.write(html_content_en)

    
    wf_json = json.dumps(asdict(wf_settings), indent=4)
    
    webbrowser.open(f'file://{os.path.realpath(temp_html_file)}')



class ConfigurationCompleteException(Exception):
    # exception to stop EUDDraft compilation
    pass


def onPluginStart():
    if settings.get("config_mode", "True") != "False": # config mode
        wf_settings = make_wf_settings()
        show_config_dialog(wf_settings)
        raise ConfigurationCompleteException("\n" + __("Configuration complete. Please change the plugin settings and re-run euddraft.") + "\n")
