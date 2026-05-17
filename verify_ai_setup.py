import os
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get("TOKEN")
if token:
    print(f"TOKEN found: {token[:5]}...{token[-5:] if len(token)>10 else ''}")
else:
    print("TOKEN NOT FOUND in .env or environment!")

secret = os.environ.get("SECRET_KEY")
if secret:
    print("SECRET_KEY found.")
else:
    print("SECRET_KEY NOT FOUND!")
