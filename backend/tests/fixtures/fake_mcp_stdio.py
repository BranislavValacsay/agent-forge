#!/usr/bin/env python3
import json
import sys


for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "initialize":
        response = {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-stdio", "version": "1.0"},
            },
        }
    elif message.get("method") == "tools/call":
        arguments = message.get("params", {}).get("arguments", {})
        if arguments.get("fail"):
            result = {"content": [{"type": "text", "text": "requested failure"}], "isError": True}
        else:
            result = {"content": [{"type": "text", "text": "ok"}], "structuredContent": {"answer": arguments.get("value", "pong")}, "isError": False}
        response = {"jsonrpc": "2.0", "id": message["id"], "result": result}
    else:
        continue
    print(json.dumps(response), flush=True)
