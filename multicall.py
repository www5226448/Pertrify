from starknet_py.contract import Contract
from starknet_py.net.gateway_client import GatewayClient
from starknet_py.net.full_node_client import FullNodeClient

client=FullNodeClient(node_url="https://starknet-mainnet.infura.io/v3/64a79ef8e56f495f88e51ca743935fec",net="mainnet")


from utils.TransactionSender import from_call_to_call_array





myRouter_ABI = eval(open('ABI/myRouter.abi').read())

multicall_ABI = eval(open('ABI/multicall.abi').read())



spell = eval(open('ABI/spell.json').read())


def decode_spell(spell):
    jedi = []
    one = []
    my = []
    for dexs in spell.values():
        for k, v in dexs.items():
            
            if k == 'jedipair':
                jedi.append((v, 'get_reserves', []))
            elif k == 'onepair':
                one.append((v, 'getReserves', []))

            else:
                assert k == 'myPoolId'
                my.append((0x010884171baf1914edc28d7afb619b40a4051cfae78a094a55d230f19e944a28, 'get_pool', [v]))
    
    
    return jedi, one, my


aggregated_data=decode_spell(spell)


async def retrieve(client):

    multicall = Contract(address=0x05754af3760f3356da99aea5c3ec39ccac7783d925a19666ebbeca58ff0087f4,
                     abi=multicall_ABI, provider=client)
    states_cache = {}
    jedi, one, my = aggregated_data
    
    l_jedi, l_one, l_my = len(jedi), len(one), len(my)

    call_array, calldata = from_call_to_call_array([*jedi, *one, *my])
    

    raw_return = await multicall.functions['aggregate'].call(call_array, calldata)


    states = []
    jedi_fragments = 6
    from_index, to_index = 0, l_jedi*jedi_fragments

    for i in range(from_index, to_index, jedi_fragments):

        s1 = raw_return[1][i+1]
        s2 = raw_return[1][i+3]

       
        states.append((s1, s2))

    for j, s in zip(jedi, states):
        dexName = 'jedipair '+str(j[0])
        states_cache[dexName] = int(j[0]), s

    states = []
    one_fragments = 4
    


    from_index, to_index = to_index, to_index+l_one*one_fragments

    for i in range(from_index, to_index, one_fragments):

        s1 = raw_return[1][i+1]
        s2 = raw_return[1][i+2]

        states.append((s1, s2))

    for j, s in zip(one, states):
        dexName = 'onepair '+str(j[0])
        states_cache[dexName] = int(j[0]), s

    states = []
    my_fragments = 11
    
    from_index, to_index = to_index, to_index+l_my*my_fragments
    for i in range(from_index, to_index, my_fragments):

        s1 = raw_return[1][i+3]
        s2 = raw_return[1][i+6]

        states.append((s1, s2))
    for j, s in zip(my, states):
        dexName = 'myPoolId '+str(j[2][0])
        states_cache[dexName] = j[2][0], s

    return states_cache






