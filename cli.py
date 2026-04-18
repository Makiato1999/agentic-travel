#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Aligo 商旅助手 - CLI 交互界面
使用 Rich 库实现美观的终端交互
"""
import asyncio
import sys
import os
from typing import Optional

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
import json

# 导入系统组件
from config import LLM_CONFIG, RESILIENCE_CONFIG
from config_agentscope import init_agentscope
from services.result_formatter import ResultFormatter
from services.travel_assistant_service import TravelAssistantService
from utils.circuit_breaker import CircuitOpenError
from utils.llm_resilience import run_health_check as check_llm_health


class AligoCLI:
    """Aligo 商旅助手 CLI"""

    def __init__(self):
        """初始化 CLI"""
        self.console = Console()
        self.service = TravelAssistantService()

    def print_banner(self):
        """打印欢迎横幅"""
        self.console.print("\n[bold cyan]🌏 Aligo 商旅助手[/bold cyan] - 让差旅更简单\n", style="bold")

    def print_help(self):
        """打印帮助信息"""
        table = Table(title="命令列表", show_header=True, header_style="bold magenta")
        table.add_column("命令", style="cyan", width=20)
        table.add_column("说明", style="white")

        table.add_row("help", "显示此帮助信息")
        table.add_row("status", "查看当前状态和记忆")
        table.add_row("health", "检查 LLM 服务是否可用")
        table.add_row("clear", "清空当前任务（保留长期记忆）")
        table.add_row("history", "查看历史行程")
        table.add_row("preferences", "查看用户偏好")
        table.add_row("exit", "退出程序")
        table.add_row("", "")
        table.add_row("[自然语言]", "直接输入您的需求，如：")
        table.add_row("", "  - 我要从上海去北京出差")
        table.add_row("", "  - 北京的住宿标准是多少")
        table.add_row("", "  - 查询明天的天气")

        self.console.print(table)

    async def initialize_system(self):
        """初始化系统 - 使用懒加载优化启动速度"""
        user_id = Prompt.ask("用户ID", default="default_user")

        with self.console.status("初始化中...", spinner="dots"):
            session = await self.service.initialize(user_id=user_id)

        self.console.print(f"✓ 就绪 (用户: {session['user_id']}) - 输入 help 查看帮助\n", style="green")

    async def process_query(self, user_input: str):
        """处理用户查询"""
        with self.console.status("思考中...", spinner="dots"):
            response = await self.service.process_query(user_input)

        intention_data = response.get("intention", {})
        if intention_data.get("error"):
            self.console.print("❌ 无法理解您的需求，请重新描述", style="bold red")
            return

        result_data = response["result"]
        self._display_agents_called(result_data)
        self.console.print()
        self._display_results(result_data)

    def _display_agents_called(self, result_data: dict):
        """显示调用的智能体列表"""
        ResultFormatter.render_agents_called(self.console, result_data)

    def _display_results(self, result_data: dict):
        """显示执行结果 - 确保永远有回复"""
        ResultFormatter.render_results(self.console, result_data)

    def _get_agent_display_name(self, agent_name: str) -> str:
        """获取智能体的显示名称"""
        return ResultFormatter.get_agent_display_name(agent_name)

    def show_status(self):
        """显示当前状态"""
        status = self.service.get_status()
        short_term_stats = status["short_term"]["statistics"]
        long_term_stats = status["long_term"]["statistics"]

        memory_table = Table(title="记忆状态", show_header=True, header_style="bold magenta")
        memory_table.add_column("类型", style="cyan")
        memory_table.add_column("状态", style="white")

        memory_table.add_row(
            "短期记忆",
            f"{short_term_stats['total_messages']} 条消息"
        )
        memory_table.add_row(
            "长期记忆",
            f"{long_term_stats['total_trips']} 次行程"
        )
        memory_table.add_row(
            "已加载智能体",
            f"{status['loaded_agent_count']} 个"
        )

        self.console.print(memory_table)
        self.console.print()

        # 历史对话
        recent_messages = status["short_term"]["recent_dialogue"]
        if recent_messages:
            dialogue_table = Table(title="最近对话 (最多5轮)", show_header=True, header_style="bold cyan")
            dialogue_table.add_column("角色", style="cyan", width=8)
            dialogue_table.add_column("内容", style="white", width=60)
            dialogue_table.add_column("时间", style="dim", width=12)

            for msg in recent_messages:
                role_name = "👤 用户" if msg["role"] == "user" else "🤖 助手"
                content = msg["content"]

                # 截断过长的内容
                if len(content) > 100:
                    content = content[:100] + "..."

                # 格式化时间
                timestamp = msg.get("timestamp", "")
                if timestamp:
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(timestamp)
                        time_str = dt.strftime("%H:%M:%S")
                    except:
                        time_str = ""
                else:
                    time_str = ""

                dialogue_table.add_row(role_name, content, time_str)

            self.console.print(dialogue_table)
            self.console.print()

    async def run_health_check(self):
        """在会话内执行健康检查并显示熔断器状态"""
        status = await self.service.run_health_check()
        if status.get("circuit_breaker"):
            self.console.print(f"[bold]熔断器[/bold]: {status['circuit_breaker']['state']}", style="cyan")
        if status["ok"]:
            self.console.print("LLM 服务: [green]正常[/green]", style="bold")
        else:
            self.console.print(f"LLM 服务: [red]不可用[/red] - {status['message']}", style="bold")
        self.console.print()

    def show_history(self):
        """显示历史行程"""
        history = self.service.get_history(10)

        if not history:
            self.console.print("暂无历史行程", style="yellow")
            return

        table = Table(title="历史行程", show_header=True, header_style="bold magenta")
        table.add_column("ID", style="cyan")
        table.add_column("出发地", style="white")
        table.add_column("目的地", style="white")
        table.add_column("日期", style="white")
        table.add_column("目的", style="white")

        for trip in history:
            table.add_row(
                trip.get("trip_id", ""),
                trip.get("origin", ""),
                trip.get("destination", ""),
                trip.get("start_date", ""),
                trip.get("purpose", "")
            )

        self.console.print(table)

    def show_preferences(self):
        """显示用户偏好"""
        prefs = self.service.get_preferences()

        table = Table(title="用户偏好", show_header=True, header_style="bold magenta")
        table.add_column("类型", style="cyan")
        table.add_column("值", style="white")

        for key, value in prefs.items():
            if value:
                table.add_row(key, str(value))

        self.console.print(table)

    async def run(self):
        """运行 CLI"""
        # 打印横幅
        self.print_banner()

        # 初始化系统
        await self.initialize_system()

        # 主循环
        while True:
            try:
                # 获取用户输入
                user_input = Prompt.ask("\n[cyan]>[/cyan]")

                if not user_input.strip():
                    continue

                # 处理命令
                command = user_input.strip().lower()

                if command == "exit":
                    self.service.end_session()
                    self.console.print("再见！", style="cyan")
                    break
                elif command == "help":
                    self.print_help()
                elif command == "status":
                    self.show_status()
                elif command == "health":
                    await self.run_health_check()
                elif command == "clear":
                    self.service.clear_short_term_memory()
                    self.console.print("✓ 已清空短期记忆", style="green")
                elif command == "history":
                    self.show_history()
                elif command == "preferences":
                    self.show_preferences()
                else:
                    # 处理自然语言查询
                    await self.process_query(user_input)

            except KeyboardInterrupt:
                self.console.print("\n使用 'exit' 退出", style="dim")
            except CircuitOpenError:
                self.console.print("\n[bold yellow]⚠ 服务暂时不可用，请稍后再试。[/bold yellow]", style="dim")
            except Exception as e:
                self.console.print(f"\n错误: {e}", style="red")


def run_health_check_standalone() -> int:
    """
    独立执行健康检查（用于 `python cli.py health`）。
    不进入交互式 CLI，只检测 LLM 是否可达。
    Returns:
        0 成功，1 失败（便于脚本/监控）
    """
    import asyncio
    init_agentscope()
    ok, msg = asyncio.run(check_llm_health(
        base_url=LLM_CONFIG["base_url"],
        api_key=LLM_CONFIG["api_key"],
        model_name=LLM_CONFIG["model_name"],
        timeout_sec=RESILIENCE_CONFIG.get("health_check_timeout_sec", 10.0),
    ))
    if ok:
        print("OK")
        return 0
    print(f"FAIL: {msg}")
    return 1


def main():
    """主函数"""
    if len(sys.argv) > 1 and sys.argv[1].strip().lower() == "health":
        exit(run_health_check_standalone())
    cli = AligoCLI()
    asyncio.run(cli.run())


if __name__ == "__main__":
    main()
