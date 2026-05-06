"""
用于快速测试某个agent，也用于codex/cc向github_reader_agent询问agno相关事宜，只返回最终结果，不输出流式内容（避免占用过多的codex/cc上下文）

使用示例：python agent_chat.py --agent_id "github_reader_agent" --message "你好"
"""
#!/usr/bin/env python3
"""Agent chat script that calls an agent via HTTP and extracts the RunCompleted content."""

import argparse
import json
import sys

try:
    import requests
except ImportError:
    print("请先安装 requests 库: pip install requests", file=sys.stderr)
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="Chat with an agent via HTTP API")
    parser.add_argument("--agent_id", required=True, help="The agent ID to use")
    parser.add_argument("--message", required=True, help="The message to send")
    return parser.parse_args()


def call_agent(agent_id: str, message: str) -> str:
    """Call the agent API using requests and return the response text."""
    url = f"http://localhost:8005/agents/{agent_id}/runs"

    data = {
        "message": message,
        "stream": "false",
        "user_id": "john@example.com",
        # "file": r"@C:\Users\WUJIEAI\PycharmProjects\ai_pc\pdf_service\test\document.pdf"
    }

    try:
        response = requests.post(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=120,
        )
        response.raise_for_status()
        # requests 自动处理编码，强制使用 utf-8 以防万一
        response.encoding = "utf-8"
        return response.text
    except requests.exceptions.ConnectionError:
        print(f"无法连接到 {url}，请确认 agent 服务已启动", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("请求超时", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"HTTP 错误: {e}", file=sys.stderr)
        sys.exit(1)


def extract_run_completed_content(response: str) -> str:
    """Parse SSE response and extract content from RunCompleted event."""
    if not response or not response.strip():
        print("响应为空", file=sys.stderr)
        sys.exit(1)

    lines = response.strip().split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 找到 RunCompleted 事件
        if line == "event: RunCompleted":
            i += 1
            while i < len(lines):
                data_line = lines[i].strip()
                if data_line.startswith("data: "):
                    json_str = data_line[6:]  # 去掉 "data: " 前缀
                    try:
                        data = json.loads(json_str)
                        if "content" in data:
                            return data["content"]
                    except json.JSONDecodeError as e:
                        print(f"JSON 解析失败: {e}", file=sys.stderr)
                        print(f"原始数据: {json_str}", file=sys.stderr)
                        sys.exit(1)
                elif data_line:
                    break
                i += 1
        i += 1

    # 兜底：尝试直接解析为 JSON（非 SSE 格式）
    try:
        data = json.loads(response)
        if isinstance(data, dict):
            if data.get("event") == "RunCompleted" and "content" in data:
                return data["content"]
            if "content" in data:
                return data["content"]
    except json.JSONDecodeError:
        pass

    print("在响应中找不到 RunCompleted 事件或 content 字段", file=sys.stderr)
    print(f"原始响应:\n{response}", file=sys.stderr)
    sys.exit(1)


def main():
    args = parse_args()
    response = call_agent(args.agent_id, args.message)
    content = extract_run_completed_content(response)
    print(content)


if __name__ == "__main__":
    main()



