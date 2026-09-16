import asyncio
import json
import app

async def main():
    await app.research()
    print('MRC_RESEARCH_RESULT=' + json.dumps(app.STATE, separators=(',', ':'), default=str), flush=True)

if __name__ == '__main__':
    asyncio.run(main())
