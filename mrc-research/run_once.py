import asyncio
import json
import app

async def monitor():
    while True:
        await asyncio.sleep(10)
        print('MRC_RESEARCH_PROGRESS=' + json.dumps({
            'status': app.STATE.get('status'),
            'progress': app.STATE.get('progress'),
            'error': app.STATE.get('error'),
        }, separators=(',', ':'), default=str), flush=True)

async def main():
    mon = asyncio.create_task(monitor())
    try:
        await app.research()
    finally:
        mon.cancel()
    print('MRC_RESEARCH_RESULT=' + json.dumps(app.STATE, separators=(',', ':'), default=str), flush=True)

if __name__ == '__main__':
    asyncio.run(main())
