"""Анализ уже скачанных PDF без обращения к Rusprofile/Глобасу — для проверки ИИ и промта.

    python -m scripts.analyze_local samples/globas_1655503631.pdf samples/rusprofile_1655503631.pdf --ai gigachat
"""
import argparse
import asyncio
import json
from pathlib import Path

from app.ai import get_provider
from app.ai.parse import parse_conclusion
from app.ai.prompt import SYSTEM_PROMPT, build_user_prompt


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--ai", default=None, help="gigachat | anthropic")
    args = ap.parse_args()

    provider = get_provider(args.ai)
    prompt = build_user_prompt([f.name for f in args.files], provider.name, provider.model)
    res = await provider.analyze(SYSTEM_PROMPT, prompt, args.files)
    print(res.text, "\n" + "=" * 60)
    print(json.dumps({"ИИ/МодельИИ": f"{res.ai_name} / {res.model}", **parse_conclusion(res.text)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
