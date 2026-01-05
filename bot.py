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
        self.REF_CODE = "2BHlBH"

    def log(self, message, color=Fore.WHITE):
        now = datetime.now().astimezone(wib).strftime('%x %X %Z')
        print(f"{Fore.CYAN}[ {now} ]{Style.RESET_ALL} | {color}{message}")

    # ပေးထားသော Screenshot ပါအတိုင်း Header ကို အတိအကျ ပြင်ဆင်ခြင်း
    def get_headers(self, token=None, address=None, sid=None):
        headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://app.polarise.org",
            "Referer": "https://app.polarise.org/",
            "Sec-Ch-Ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Herond";v="138"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }
        if token and address and sid:
            # Screenshot အရ format: Bearer <auth_token> <sid> <wallet_address> polarise
            headers["Authorization"] = f"Bearer {token} {sid} {address} polarise"
            headers["Accesstoken"] = sid
        return headers

    async def get_nonce(self, session, address):
        url = f"{self.BASE_API}/profile/getnonce"
        try:
            async with session.post(url, headers=self.get_headers(), json={"wallet": address, "chain_name": "polarise"}) as resp:
                data = await resp.json()
                return data.get("signed_nonce") if data.get("code") == "200" else None
        except: return None

    async def login(self, session, account_key, address, nonce):
        msg = f"Nonce to confirm: {nonce}"
        encoded_msg = encode_defunct(text=msg)
        signed_msg = Account.sign_message(encoded_msg, private_key=account_key)
        signature = to_hex(signed_msg.signature)
        
        sid = str(uuid.uuid4())
        payload = {
            "signature": signature,
            "chain_name": "polarise",
            "name": address[:6],
            "nonce": nonce,
            "wallet": address,
            "sid": sid,
            "sub_id": "",
            "inviter_code": self.REF_CODE
        }
        
        try:
            async with session.post(f"{self.BASE_API}/profile/login", headers=self.get_headers(), json=payload) as resp:
                data = await resp.json()
                if data.get("code") == "200":
                    token = data["data"]["auth_token_info"]["auth_token"]
                    return token, sid
                return None, None
        except: return None, None

    async def process_accounts(self):
        try:
            with open('accounts.txt', 'r') as f:
                accounts = [line.strip() for line in f if line.strip()]
        except: return

        async with ClientSession(timeout=ClientTimeout(total=30)) as session:
            for p_key in accounts:
                try:
                    acc = Account.from_key(p_key)
                    address = acc.address.lower()
                    self.log(f"စစ်ဆေးနေသည်: {address[:10]}...", Fore.YELLOW)

                    nonce = await self.get_nonce(session, address)
                    if not nonce: continue

                    auth_token, sid = await self.login(session, p_key, address, nonce)
                    if not auth_token:
                        self.log("Login မရပါ", Fore.RED)
                        continue

                    # Header အသစ်ဖြင့် Profile စစ်ခြင်း
                    headers = self.get_headers(auth_token, address, sid)
                    async with session.post(f"{self.BASE_API}/profile/profileinfo", headers=headers, json={"chain_name": "polarise"}) as resp:
                        if resp.status == 200:
                            p_data = await resp.json()
                            points = p_data["data"]["exchange_total_points"]
                            self.log(f"Points: {points}", Fore.CYAN)

                            if points >= 100:
                                self.log(f"Swap ကြိုးစားနေသည်...", Fore.GREEN)
                                msg = f"Nonce to confirm: {nonce}"
                                signature = to_hex(Account.sign_message(encode_defunct(text=msg), private_key=p_key).signature)
                                
                                s_payload = {
                                    "user_id": p_data["data"]['id'],
                                    "user_name": p_data["data"]['user_name'],
                                    "user_wallet": address,
                                    "used_points": 100,
                                    "token_symbol": "GRISE",
                                    "chain_name": "polarise",
                                    "signature": signature,
                                    "sign_msg": msg
                                }
                                async with session.post(f"{self.BASE_API}/profile/swappoints", headers=headers, json=s_payload) as s_resp:
                                    s_data = await s_resp.json()
                                    if s_data.get("code") == "200":
                                        self.log(f"Swap Success! Tx: {s_data['data'].get('tx_hash')}", Fore.GREEN)
                                    else:
                                        self.log(f"Swap Fail: {s_data.get('msg')}", Fore.RED)
                        else:
                            self.log(f"Error {resp.status}", Fore.RED)
                except Exception as e:
                    self.log(f"Error: {e}", Fore.RED)
                await asyncio.sleep(1)

    async def main(self):
        while True:
            await self.process_accounts()
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(PolariseSwapper().main())
