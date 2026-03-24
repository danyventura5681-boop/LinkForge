import asyncio
from keep_alive import keep_alive
from main import main

keep_alive()
asyncio.run(main())