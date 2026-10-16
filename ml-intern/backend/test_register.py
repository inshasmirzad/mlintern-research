import asyncio
from auth_local import auth_handler, UserCreate

async def main():
    try:
        user = UserCreate(username="malli", email="malli@gmail.com", password="password")
        res = await auth_handler.create_user(user)
        print("Success:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
