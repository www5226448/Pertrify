import asyncio
import datetime
import random
import time
from asyncio.exceptions import CancelledError

import numpy as np
from starknet_py.contract import Contract
from starknet_py.net.account.account import Account
from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.gateway_client import GatewayClient
from starknet_py.net.models import StarknetChainId
from starknet_py.net.signer.stark_curve_signer import KeyPair, StarkCurveSigner

from multicall import retrieve


async def main():

    INTERVAL = 0  # 每多久执行一次套利机会任务
    THRESHOLD = 514043550034794
    SWITCH = 0  # 当设置为1时，自动切换连接需要key的节点（需要在ABI/infura.txt 填入节点key），当设置为0 时，使用默认官方节点

    client_switcher = Updater.switch_client()
    account_switcher = Updater.switch_account()

    while True:

        try:
            await runforever(client_switcher, account_switcher, SWITCH, INTERVAL, THRESHOLD)
        except CancelledError:
            pass

        except KeyboardInterrupt:
            pass

        except BaseException as e:

            errorType = type(e).__name__
            Updater.write_text("exception.txt", now(), errorType,e)

            # await asyncio.sleep(0)


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))


spells = eval(open('ABI/spell.json', 'r').read())


paths = ["DAI-ETH,DAI-USDC,ETH-USDC", "ETH-USDC,USDC-USDT,USDT-ETH"]


onePairABI = eval(open('ABI/onePair.abi').read())
jediPairABI = eval(open('ABI/jediPair.abi').read())

jediRouterABI = eval(open('ABI/jediRouter.abi').read())
oneRouterABI = eval(open('ABI/oneRouter.abi').read())

myRouter_ABI = eval(open('ABI/myRouter.abi').read())

client = GatewayClient(net="mainnet")

jediswap = Contract(address=0x041fd22b238fa21cfcf5dd45a8548974d8263b3a531a60388411c5e230f97023,
                    abi=jediRouterABI, provider=client)

oneswap = Contract(address=0x07a6f98c03379b9513ca84cca1373ff452a7462a3b61598f0af5bb27ad7f76d1,
                   abi=oneRouterABI, provider=client)

myRouter = Contract(address=0x010884171baf1914edc28d7afb619b40a4051cfae78a094a55d230f19e944a28,
                    abi=myRouter_ABI, provider=client)


def getAmountOut(amountIn, tokenFrom, token0, token1, reserveIn, reserveOut):

    if tokenFrom != token0:
        assert tokenFrom == token1
        reserveIn, reserveOut = reserveOut, reserveIn

    amountInWithFee = amountIn * 997  # amountInWithFee = amountIn.mul(997);
    # numerator = amountInWithFee.mul(reserveOut);
    numerator = amountInWithFee*reserveOut
    denominator = reserveIn*1000 + amountInWithFee
    # denominator = reserveIn.mul(1000).add(amountInWithFee);
    amountOut = numerator // denominator
    # print(amountIn,tokenFrom,token0,token1,reserveIn,reserveOut,amountOut)
    return amountOut


class BlockStates:

    states_cashe = {}

    @classmethod
    def retrieve_reserves(cls, k, v):

        return cls.states_cashe[k+' '+str(v)]


async def searchBestPath(account, nonce, amountIn, threshold, token_path, deadline):

    token_path = token_path.split(',')
    dex_data = [spells[p] for p in token_path]

    tokenFrom = 'ETH'

    steps = []

    S = []

    assert len(dex_data) == 3
    _amount_in = amountIn
    for symbol, e in zip(token_path, dex_data):

        token0, token1 = symbol.split('-')

        states = [BlockStates.retrieve_reserves(k, v) for k, v in e.items()]
        dexNames = [k for k in e.keys()]

        S.append(states)
        poolIds = [s[0] for s in states]
        states = [s[1] for s in states]

        mediums = [getAmountOut(_amount_in, tokenFrom,
                                token0, token1, *s) for s in states]
        dexIndex = np.argmax(mediums)
        dexName = dexNames[dexIndex]

        newTokenFrom = token1 if token0 == tokenFrom else token0
        steps.append([dexName, poolIds[dexIndex], tokenFrom,
                     newTokenFrom, _amount_in, mediums[dexIndex]])
        tokenFrom = newTokenFrom
        _amount_in = mediums[dexIndex]

    payoff = steps[-1][-1]-steps[0][-2]

    if payoff > threshold:
        await execute(account, nonce, steps, payoff, deadline)
        return
    # reverse

    tokenFrom = 'ETH'
    token_path = token_path[::-1]
    dex_data = [spells[p] for p in token_path]
    steps = []
    S = S[::-1]
    _amount_in = amountIn
    for symbol, e, states in zip(token_path, dex_data, S):

        dexNames = [k for k in e.keys()]
        token0, token1 = symbol.split('-')

        poolIds = [s[0] for s in states]
        states = [s[1] for s in states]

        mediums = [getAmountOut(_amount_in, tokenFrom,
                                token0, token1, *s) for s in states]
        dexIndex = np.argmax(mediums)
        dexName = dexNames[dexIndex]

        newTokenFrom = token1 if token0 == tokenFrom else token0
        steps.append([dexName, poolIds[dexIndex], tokenFrom,
                     newTokenFrom, _amount_in, mediums[dexIndex]])
        tokenFrom = newTokenFrom
        _amount_in = mediums[dexIndex]

    payoff = steps[-1][-1]-steps[0][-2]

    if payoff > threshold:
        await execute(account, nonce, steps, payoff, deadline)
        return


async def searchBestPath2(account, nonce, amountIn, threshold, tokenPath, deadline):
    path0, path1 = tokenPath.split(',')
    dex_data = [spells[p] for p in [path0, path1]][0]

    dexNames = [k for k in dex_data.keys()]
    pairs = [v for v in dex_data.values()]
    token0, token1 = path0.split('-')

    tokenFrom = 'ETH'
    tokenMedium = token0 if token0 != tokenFrom else token1

    _ways, payoffs = [], []

    l = len(dexNames)

    for i in range(0, l):
        for j in range(i+1, l):
            dexName1 = dexNames[i]
            dexName2 = dexNames[j]

            pair1 = pairs[i]
            pair2 = pairs[j]

            _, state1 = BlockStates.retrieve_reserves(dexName1, pair1)
            _, state2 = BlockStates.retrieve_reserves(dexName2, pair2)
            medium = getAmountOut(amountIn, tokenFrom, token0, token1, *state1)
            back = getAmountOut(medium, tokenMedium, token0, token1, *state2)

            step1 = [dexName1, pair1, tokenFrom, tokenMedium, amountIn, medium]
            step2 = [dexName2, pair2, tokenMedium, tokenFrom, medium, back]
            _ways.append([step1, step2])
            profit = back-amountIn
            payoffs.append(profit)

            # reverse the dex path
            dexName1, dexName2 = dexName2, dexName1
            pair1, pair2 = pair2, pair1
            state1, state2 = state2, state1

            medium = getAmountOut(amountIn, tokenFrom, token0, token1, *state1)
            back = getAmountOut(medium, tokenMedium, token0, token1, *state2)

            step1 = [dexName1, pair1, tokenFrom, tokenMedium, amountIn, medium]
            step2 = [dexName2, pair2, tokenMedium, tokenFrom, medium, back]
            _ways.append([step1, step2])
            profit = back-amountIn
            payoffs.append(profit)

    stepIndex = np.argmax(payoffs)
    payoff = payoffs[stepIndex]

    steps = _ways[stepIndex]

    if payoff > threshold:
        await execute(account, nonce, steps, payoff, deadline)


async def execute(account, nonce, steps, max_fee, deadline):
    token_info = {"DAI": 385291772725090318157700937045086145273563247402457518748197066808155336371,
                  "USDT": 2967174050445828070862061291903957281356339325911846264948421066253307482040,
                  "USDC": 2368576823837625528275935341135881659748932889268308403712618244410713532584,
                  "ETH": 2087021424722619777119509474943472645767659996348769578120564519014510906823,
                  "WBTC": 1806018566677800621296032626439935115720767031724401394291089442012247156652,
                  "wstETH": 1886212889629631188189497155848883534738756148921111726686756987927630157522,
                  }

    __in, __out = steps[0][-2], steps[-1][-1]
    assert (__out > __in)

    calls = []
    for i, s in enumerate(steps):

        dexName, poolId, tokenFrom, tokenTo, amountIn, amountOutMin = s
        amountIn = amountIn*3000//3001 if i != 0 else amountIn
        amountOutMin = amountOutMin*3000//3001
        T1, T2 = token_info[tokenFrom], token_info[tokenTo]
        if dexName == 'jedipair':

            c = jediswap.functions['swap_exact_tokens_for_tokens'].prepare(amountIn, amountOutMin, [T1, T2],
                                                                           account.address, deadline)
        elif dexName == 'onepair':
            c = oneswap.functions['swapExactTokensForTokens'].prepare(amountIn, amountOutMin, [T1, T2],

                                                                      account.address, deadline)
        elif dexName == 'myPoolId':

            c = myRouter.functions['swap'].prepare(
                poolId, T1, amountIn, amountOutMin)
        calls.append(c)


    

    tx = await account.execute(calls, nonce=nonce, max_fee=max_fee)

    Updater.write_text('transaction.log', now(), hex(
        account.address), steps,hex(tx.transaction_hash))


class Updater:

    def write_text(file_name, *logs):
        with open(file_name, "a+") as f:
            print(*logs, file=f)

    def switch_client():
        keys = open('ABI/infura.txt').read().split('\n')
        l = len(keys)
        i = 0
        while True:
            key = keys[i % l]
            yield FullNodeClient(node_url="https://starknet-mainnet.infura.io/v3/{}".format(key), net="mainnet")
            i += 1

    def switch_account():
        keys = open("ABI/setting.config", "r").read().split('\n')

        def select(client):
            pks = np.random.choice(keys)
            if pks:
                privateKey, account = pks.split(',')

                key_pair = KeyPair.from_private_key(eval(privateKey))

                account = Account(
                    address=eval(account),
                    client=client,
                    signer=StarkCurveSigner(
                        account_address=eval(account),
                        key_pair=key_pair,
                        chain_id=StarknetChainId.MAINNET,),)
                return account
            else:
                return select(client)

        return select

    async def update_nonce(mapping, client, account):
        if account.address not in mapping:

            n = await client.get_contract_nonce(account.address)
            balance = await account.get_balance(token_address=0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7, chain_id=StarknetChainId.MAINNET)
            balance = (balance//914043550034794) * 914043550034794
            percentage = float("8{}.{}".format(
                str(account.address)[-2], str(account.address)[-2:]))
            amount_in = int((balance*percentage)//100)

            t = time.time()
            mapping[account.address] = (t, n, amount_in)
            return t, n, amount_in
        else:
            lastestUpdateTime, n, amount_in = mapping[account.address]
            if time.time()-lastestUpdateTime < 300:
                return lastestUpdateTime, n, amount_in
            else:
                n = await client.get_contract_nonce(account.address)
                t = time.time()
                mapping[account.address] = (t, n, amount_in)
                return t, n, amount_in


async def runforever(client_switcher, account_switcher, switch, interval, threshold):
    # client_switcher = Updater.switch_client()

    mapping = {}
    # account_switcher = Updater.switch_account()

    while True:
        if switch:
            client = client_switcher.send(None)

        else:
            client = GatewayClient(net="mainnet")

        account = account_switcher(client)

        _, nonce, amount_in = await Updater.update_nonce(mapping, client, account)

        BlockStates.states_cashe = await retrieve(client)
        deadline = int(4500+(time.time()//1800 * 1800))

        tasks = [
            searchBestPath(account, nonce, amount_in, threshold,
                           'DAI-ETH,DAI-USDC,ETH-USDC', deadline),

            searchBestPath(account, nonce, amount_in, threshold,
                           'DAI-ETH,DAI-USDT,ETH-USDT', deadline),
            
            searchBestPath(account, nonce, amount_in, threshold,
                           'ETH-USDC,USDC-USDT,ETH-USDT', deadline),
            searchBestPath(account, nonce, amount_in, threshold,
                           'WBTC-ETH,WBTC-USDC,ETH-USDC', deadline),

            searchBestPath(account, nonce, amount_in, threshold,
                           'WBTC-ETH,WBTC-USDT,ETH-USDT', deadline),

                           
            searchBestPath2(account, nonce, amount_in,
                            threshold, 'ETH-USDC,ETH-USDC', deadline),
            searchBestPath2(account, nonce, amount_in,
                            threshold, 'DAI-ETH,DAI-ETH', deadline),
            searchBestPath2(account, nonce, amount_in,
                            threshold, 'ETH-USDT,ETH-USDT', deadline),


            searchBestPath2(account, nonce, amount_in,
                            threshold, 'WBTC-ETH,WBTC-ETH', deadline),
            searchBestPath2(account, nonce, amount_in,
                            threshold, 'wstETH-ETH,wstETH-ETH', deadline),

        

        ]

        random.shuffle(tasks)
        await asyncio.gather(*tasks)
        await asyncio.sleep(interval)


asyncio.run(main())
