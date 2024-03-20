"""Opt-in live provider smoke test against a running API.

Not part of the deterministic test suite: it makes real network traffic (or
local Ollama traffic) and therefore requires explicit consent.

Example (local Ollama, no credentials required):

    # Terminal 1
    uvicorn app.api.main:app --host 127.0.0.1 --port 8000

    # Terminal 2
    python scripts/live_provider_smoke.py \
        --name ollama-local --kind ollama \
        --base-url http://localhost:11434 --model gemma:2b

For hosted providers, set the key in the server environment first and pass
``--key-env`` (the variable name, never the secret value):

    AI_API_KEY=sk-... uvicorn app.api.main:app --port 8000
    python scripts/live_provider_smoke.py \
        --name openai-prod --kind openai \
        --base-url https://api.openai.com/v1 --key-env AI_API_KEY \
        --model gpt-4o-mini
"""

import argparse
import json
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--name", default="ollama-local")
    parser.add_argument(
        "--kind",
        default="ollama",
        choices=["offline", "compatible", "openai", "anthropic", "openrouter", "ollama"],
    )
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--key-env", default="AI_API_KEY")
    parser.add_argument("--model", default="")
    parser.add_argument("--benchmark", default="sales_total")
    parser.add_argument("--cases", type=int, default=10)
    parser.add_argument(
        "--prompt",
        default=(
            "Return one Excel formula that totals every revenue value in column B "
            "of sheet Data starting at row 2, including future rows."
        ),
    )
    args = parser.parse_args()

    with httpx.Client(base_url=args.api, timeout=240) as client:
        client.get("/health").raise_for_status()
        profile = {
            "name": args.name,
            "kind": args.kind,
            "base_url": args.base_url,
            "key_env": args.key_env,
            "model": args.model,
            "max_tokens": 256,
            "temperature": 0,
            "timeout": 60,
            "request_limit": 5,
            "default": True,
        }
        saved = client.put("/providers", json=profile)
        saved.raise_for_status()
        print("profile saved:", saved.json())

        discovery = client.post("/providers/test", json={"provider": args.name, "opt_in": True})
        print("discovery:", discovery.status_code, discovery.json())
        discovery.raise_for_status()

        generated = client.post(
            "/generate",
            json={"provider": args.name, "prompt": args.prompt, "opt_in": True},
        )
        generated.raise_for_status()
        evidence = generated.json()
        print("generated:", json.dumps(evidence, indent=2))

        evaluated = client.post(
            "/evaluate",
            json={
                "benchmark": args.benchmark,
                "candidate": evidence["formula"],
                "provider": args.name,
                "model": evidence["model"],
                "cases": args.cases,
                "generation": {
                    "latency_seconds": evidence["latency_seconds"],
                    "usage": evidence["usage"],
                    "estimated_cost_usd": evidence["estimated_cost_usd"],
                },
            },
        )
        evaluated.raise_for_status()
        result = evaluated.json()
        print(
            "evaluation:",
            json.dumps(
                {
                    "run_id": result["id"],
                    "status": result["status"],
                    "passed": result["passed"],
                    "failed": result["failed"],
                    "counterexample": bool(result["counterexample"]),
                },
                indent=2,
            ),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
