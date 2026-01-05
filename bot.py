import asyncio
import json
import uuid
import time
from datetime import datetime
import pytz
from aiohttp import ClientSession, ClientTimeout
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import to_hex
from colorama import Fore, Style, init

init(autoreset=True)
wib = pytz.timezone('Asia/Jakarta')

class PolariseSwapper:
    def __init__(self):
        self.BASE_API = "https://apia.polarise.org/api/app/v1"
        self.EXPLORER = "https://explorer.polarise.org/tx/"
        self.REF_CODE = "2BHlBH"

    def log(self, message, color=Fore.WHITE):
        now = datetime.now().astimezone(wib).strftime('%x %X %Z')
        print(f"{Fore.CYAN}[ {now} ]{Style.RESET_ALL} | {color}{message}")

    async def get_nonce(self, session, address, headers):
        url = f"{self.BASE_API}/profile/getnonce"
        data = {"wallet": address, "chain_name": "polarise"}
        async with session.post(url, headers=headers, json=data) as resp:
            res = await resp.json()
            return res.get("signed_nonce") if res.get("code") == "200" else None

    async def login(self, session, account_key, address, nonce, headers):
        msg = f"Nonce to confirm: {nonce}"
        encoded_msg = encode_defunct(text=msg)
        signed_msg = Account.sign_message(encoded_msg, private_key=account_key)
        signature = to_hex(signed_msg.signature)

        payload = {
            "signature": signature,
            "chain_name": "polarise",
            "name": address[:6],
            "nonce": nonce,
            "wallet": address,
            "sid": str(uuid.uuid4()),
            "sub_id": "", # စစချင်း login မှာ ဗလာထားနိုင်ပါတယ်
            "inviter_code": self.REF_CODE
        }
        
        async with session.post(f"{self.BASE_API}/profile/login", headers=headers, json=payload) as resp:
            res = await resp.json()
            if res.get("code") == "200":
                return res["data"]["auth_token_info"]["auth_token"]
            return None

    async def swap(self, session, account_key, address, user_data, auth_token, headers):
        msg = f"Nonce to confirm: {user_data['nonce']}"
        encoded_msg = encode_defunct(text=msg)
        signed_msg = Account.sign_message(encoded_msg, private_key=account_key)
        signature = to_hex(signed_msg.signature)

        payload = {
            "user_id": user_data['id'],
            "user_name": user_data['user_name'],
            "user_wallet": address,
            "used_points": 100, # Point ၁၀၀ စီ swap မည်
            "token_symbol": "GRISE",
            "chain_name": "polarise",
            "signature": signature,
            "sign_msg": msg
        }
        
        # Header မှာ Bearer token ထည့်ရပါမယ်
        headers["Authorization"] = f"Bearer {auth_token} {payload['sid']} {address} polarise"
        
        async with session.post(f"{self.BASE_API}/profile/swappoints", headers=headers, json=payload) as resp:
            return await resp.json()

    async def process_all_accounts(self):
        try:
            with open('accounts.txt', 'r') as f:
                accounts = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            self.log("accounts.txt မတွေ့ပါ", Fore.RED)
            return

        async with ClientSession(timeout=ClientTimeout(total=30)) as session:
            for p_key in accounts:
                try:
                    acc = Account.from_key(p_key)
                    address = acc.address
                    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

                    self.log(f"စစ်ဆေးနေသည့်အကောင့်: {address[:10]}...", Fore.YELLOW)

                    # 1. Get Nonce
                    nonce = await self.get_nonce(session, address, headers)
                    if not nonce: continue

                    # 2. Login
                    auth_token = await self.login(session, p_key, address, nonce, headers)
                    if not auth_token: continue

                    # 3. Check Profile/Points
                    auth_header = {"Authorization": f"Bearer {auth_token} {str(uuid.uuid4())} {address} polarise"}
                    async with session.post(f"{self.BASE_API}/profile/profileinfo", headers=headers, json={"chain_name": "polarise"}, auth=None) as resp:
                        # မှတ်ချက်- profileinfo အတွက် auth_header ပြန်ပြင်ရပါမယ်
                        profile_headers = headers.copy()
                        profile_headers["Authorization"] = f"Bearer {auth_token}"
                        
                        # Profile Info ပြန်ခေါ်ခြင်း
                        async with session.post(f"{self.BASE_API}/profile/profileinfo", headers=profile_headers, json={"chain_name": "polarise"}) as p_resp:
                            p_data = await p_resp.json()
                            if p_data.get("code") == "200":
                                points = p_data["data"]["exchange_total_points"]
                                user_info = p_data["data"]
                                user_info['nonce'] = nonce # swap အတွက် သုံးရန်
                                
                                self.log(f"လက်ရှိ Point: {points}", Fore.CYAN)
                                
                                if points >= 100:
                                    self.log("Point ၁၀၀ ပြည့်ပြီ၊ Swap နေသည်...", Fore.GREEN)
                                    res = await self.swap(session, p_key, address, user_info, auth_token, headers)
                                    if res.get("code") == "200":
                                        self.log(f"Swap အောင်မြင်ပါသည်! Tx: {res['data'].get('tx_hash')}", Fore.GREEN)
                                    else:
                                        self.log(f"Swap မအောင်မြင်ပါ: {res.get('msg')}", Fore.RED)
                                else:
                                    self.log("Point ၁၀၀ မပြည့်သေးပါ၊ ကျော်သွားပါမည်။", Fore.LIGHTBLACK_EX)
                except Exception as e:
                    self.log(f"Error: {str(e)}", Fore.RED)
                
                await asyncio.sleep(2) # အကောင့်တစ်ခုနဲ့တစ်ခုကြား ၂ စက္ကန့်နားမယ်

    async def main_loop(self):
        while True:
            self.log("=== Cycle အသစ် စတင်နေသည် ===", Fore.MAGENTA)
            await self.process_all_accounts()
            self.log("=== Cycle ပြီးဆုံးပြီ၊ ချက်ချင်း ပြန်စပါမည် ===", Fore.MAGENTA)
            await asyncio.sleep(5) # အကောင့်စာရင်းကုန်သွားရင် ၅ စက္ကန့်ပဲနားပြီး ပြန်စမယ်

if __name__ == "__main__":
    swapper = PolariseSwapper()
    asyncio.run(swapper.main_loop())
