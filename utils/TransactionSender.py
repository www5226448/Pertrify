from typing import Optional, List, Tuple
from starknet_py.hash.selector import get_selector_from_name




Call = Tuple[str, str, List]

def from_call_to_call_array(calls: List[Call]):
    call_array = []
    calldata = []
    for call in calls:
        assert len(call) == 3, "Invalid call parameters"
        entry = {'to':call[0], 
                 'selector':get_selector_from_name(call[1]), 
                 'data_offset':len(calldata), 
                 'data_len':len(call[2])}
        call_array.append(entry)
        calldata.extend(call[2])

    return call_array, calldata

