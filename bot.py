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

    def get_headers(self, token=None):
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://app.polarise.org",
            "Referer": "https://app.polarise.org/",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120"',
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if token:
            # Screenshot အရ Authorization format ကို Bearer တစ်ခုတည်း သုံးထားပါတယ်
            headers["Authorization"] = f"Bearer {token}"
            headers["AccessToken"] = token # အချို့ API တွေမှာ AccessToken header ပါတောင်းတတ်လို့ ထည့်ပေးထားပါတယ်
        return headers

    async def get_nonce(self, session, address):
        url = f"{self.BASE_API}/profile/getnonce"
        payload = {"wallet": address, "chain_name": "polarise"}
        async with session.post(url, headers=self.get_headers(), json=payload) as resp:
            data = await resp.json()
            return data.get("signed_nonce") if data.get("code") == "200" else None

    async def login(self, session, account_key, address, nonce):
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
            "sub_id": "",
            "inviter_code": self.REF_CODE
        }
        
        async with session.post(f"{self.BASE_API}/profile/login", headers=self.get_headers(), json=payload) as resp:
            data = await resp.json()
            if data.get("code") == "200":
                return data["data"]["auth_token_info"]["auth_token"]
            return None

    async def perform_swap(self, session, account_key, address, user_data, auth_token, nonce):
        # Swap logic
        msg = f"Nonce to confirm: {nonce}"
        encoded_msg = encode_defunct(text=msg)
        signed_msg = Account.sign_message(encoded_msg, private_key=account_key)
        signature = to_hex(signed_msg.signature)

        payload = {
            "user_id": user_data['id'],
            "user_name": user_data['user_name'],
            "user_wallet": address,
            "used_points": 100,
            "token_symbol": "GRISE",
            "chain_name": "polarise",
            "signature": signature,
            "sign_msg": msg
        }
        
        async with session.post(f"{self.BASE_API}/profile/swappoints", headers=self.get_headers(auth_token), json=payload) as resp:
            return await resp.json()

    async def process_accounts(self):
        try:
            with open('accounts.txt', 'r') as f:
                accounts = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            self.log("accounts.txt file မရှိပါ", Fore.RED)
            return

        async with ClientSession(timeout=ClientTimeout(total=30)) as session:
            for p_key in accounts:
                try:
                    acc = Account.from_key(p_key)
                    address = acc.address
                    self.log(f"စစ်ဆေးနေသည်: {address[:10]}...", Fore.YELLOW)

                    # 1. Get Nonce
                    nonce = await self.get_nonce(session, address)
                    if not nonce:
                        self.log("Nonce ရယူ၍မရပါ (Server Down?)", Fore.RED)
                        continue

                    # 2. Login to get Auth Token
                    auth_token = await self.login(session, p_key, address, nonce)
                    if not auth_token:
                        self.log("Login မအောင်မြင်ပါ (Unauthorized)", Fore.RED)
                        continue

                    # 3. Check Profile Info
                    async with session.post(f"{self.BASE_API}/profile/profileinfo", 
                                            headers=self.get_headers(auth_token), 
                                            json={"chain_name": "polarise"}) as resp:
                        if resp.status == 200:
                            p_data = await resp.json()
                            points = p_data["data"]["exchange_total_points"]
                            self.log(f"Points: {points}", Fore.CYAN)

                            if points >= 100:
                                self.log(f"Point ၁၀၀ ပြည့်ပြီ၊ Swap ကြိုးစားနေသည်...", Fore.GREEN)
                                swap_res = await self.perform_swap(session, p_key, address, p_data["data"], auth_token, nonce)
                                
                                if swap_res.get("code") == "200":
                                    self.log(f"Swap အောင်မြင်! Tx: {swap_res['data'].get('tx_hash')}", Fore.GREEN)
                                else:
                                    # Server 503 ပြနေရင် ဒီနေရာမှာ Message ပြပါလိမ့်မယ်
                                    self.log(f"Swap မရသေးပါ: {swap_res.get('msg')}", Fore.YELLOW)
                            else:
                                self.log("Point မပြည့်သေးပါ", Fore.LIGHTBLACK_EX)
                        else:
                            self.log(f"Profile Error: Status {resp.status}", Fore.RED)

                except Exception as e:
                    self.log(f"Account Error: {str(e)}", Fore.RED)
                
                await asyncio.sleep(1) # Delay အနည်းငယ်ပေးခြင်း

    async def start_swapper(self):
        while True:
            self.log("=== စစ်ဆေးမှုအသစ် စတင်နေသည် ===", Fore.MAGENTA)
            await self.process_accounts()
            self.log("=== စာရင်းကုန်ပြီ၊ ၅ စက္ကန့်အတွင်း ပြန်စမည် ===", Fore.MAGENTA)
            await asyncio.sleep(5)

if __name__ == "__main__":
    swapper = PolariseSwapper()
    try:
        asyncio.run(swapper.start_swapper())
    except KeyboardInterrupt:
        print("\nပိတ်လိုက်ပါပြီ။")
