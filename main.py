import asyncio
import sys
from core.loader import load_team


def main():
    engine = asyncio.run(load_team('teams/starter'))

    web_mode = '--web' in sys.argv

    if web_mode:
        import uvicorn
        from web.app import app, set_engine
        set_engine(engine)
        print(f"Team loaded: {engine.name}")
        print("Starting web UI at http://127.0.0.1:8000")
        uvicorn.run(app, host='127.0.0.1', port=8000, log_level='info')
    else:
        print(f"Team loaded: {engine.name}")
        print(f"Tools: {[getattr(t, '__tool_name__', '') or getattr(t, '__name__', '') or getattr(t, 'name', '') for t in engine.tools]}")
        print("Starting chat loop (type 'exit' or 'quit' to stop)")

        while True:
            user_input = input('User: ').strip()
            if user_input.lower() in ('exit', 'quit'):
                break
            answer = engine.invoke(user_input)
            print(f'Answer: {answer}')


if __name__ == '__main__':
    main()

