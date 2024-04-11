from starknet_py.contract import Contract
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_py.net.account.account import Account
from starknet_py.net.gateway_client import GatewayClient
from starknet_py.net.models import StarknetChainId
from starknet_py.net.signer.stark_curve_signer import StarkCurveSigner
import asyncio
import numpy as np
import random


isApproval = 1  # 当此值为0时，运行为关闭，为1时运行为打开权限
INTERVAL = 200  # 每个地址运行时间间隔，600秒为每10分钟


token_info = {"DAI": 385291772725090318157700937045086145273563247402457518748197066808155336371,
              "USDT": 2967174050445828070862061291903957281356339325911846264948421066253307482040,
              "USDC": 2368576823837625528275935341135881659748932889268308403712618244410713532584,
              "ETH": 2087021424722619777119509474943472645767659996348769578120564519014510906823,
              "WBTC": 1806018566677800621296032626439935115720767031724401394291089442012247156652,
              "wstETH": 1886212889629631188189497155848883534738756148921111726686756987927630157522,
              }





def randomInt(baseInt):
    return int((np.random.randn()/30+1)*baseInt)


def gasFee():
    return int((np.random.randn()/15+1)*1285000000000000)


ERC20 = eval(open('ABI/ERC20.abi').read())


def decode_accounts():
    accounts = []
    keys = open('./ABI/setting.config').read().split('\n')

    pks = [k.split(",") for k in keys]
    for privateKey, address in pks:

        key_pair = KeyPair.from_private_key(eval(privateKey))
        account = Account(
            address=eval(address),
            client=GatewayClient(net='mainnet'),
            signer=StarkCurveSigner(
                account_address=eval(address),
                key_pair=key_pair,
                chain_id=StarknetChainId.MAINNET,),)
        accounts.append(account)
    return accounts


myRouter_ABI = eval(open('ABI/myRouter.abi').read())
myRouter = Contract(address=0x010884171baf1914edc28d7afb619b40a4051cfae78a094a55d230f19e944a28,
                    abi=myRouter_ABI, provider=GatewayClient(net='mainnet'))


async def approval(address):
    client = GatewayClient(net='mainnet')
    USDC = Contract(address=2368576823837625528275935341135881659748932889268308403712618244410713532584,
                    abi=ERC20, provider=client)
    result = await USDC.functions['allowance'].prepare(address, myRouter.address).call()

    return bool(result.remaining)


async def main(from_index=0):
    accounts = decode_accounts()

    index = from_index

    while True:

        account = accounts[index]

        approvalValue = await approval(account.address)

        if isApproval == approvalValue:
            print("{} {} continued".format(index,hex(account.address)))
            index += 1
            continue

        value = randomInt(200000e18) if isApproval else 0

        calls = []
        for k, v in token_info.items():

            ALT = Contract(address=v, abi=ERC20,
                           provider=GatewayClient(net="mainnet"))
            c1 = ALT.functions['approve'].prepare(
                0x041fd22b238fa21cfcf5dd45a8548974d8263b3a531a60388411c5e230f97023, int(value))
            c2 = ALT.functions['approve'].prepare(
                0x07a6f98c03379b9513ca84cca1373ff452a7462a3b61598f0af5bb27ad7f76d1, int(value))
            c3 = ALT.functions['approve'].prepare(
                0x010884171baf1914edc28d7afb619b40a4051cfae78a094a55d230f19e944a28, int(value))
            calls.extend([c1, c2, c3])
        random.shuffle(calls)
        try:

            tx = await account.execute(calls, max_fee=gasFee())
            print(index, hex(account.address), hex(tx.transaction_hash))
            index += 1
            await asyncio.sleep(INTERVAL)
        except BaseException as e:
            errorType = type(e).__name__
            print("triggered an exception {}".format(errorType),e)
            await asyncio.sleep(30)


asyncio.run(main(from_index=0))
