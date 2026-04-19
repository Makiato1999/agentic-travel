"""Format orchestration results for CLI and API consumers."""

from __future__ import annotations

from io import StringIO
from typing import Dict, List

from rich.console import Console


class ResultFormatter:
    """Render orchestrator output consistently across interfaces."""

    AGENT_DISPLAY_NAMES = {
        "event_collection": "事项收集",
        "preference": "偏好管理",
        "itinerary_planning": "行程规划",
        "information_query": "信息查询",
        "rag_knowledge": "知识库查询",
        "memory_query": "记忆查询",
    }

    @classmethod
    def get_agent_display_name(cls, agent_name: str) -> str:
        return cls.AGENT_DISPLAY_NAMES.get(agent_name, agent_name)

    @classmethod
    def collect_agents_called(cls, result_data: Dict) -> List[Dict[str, str]]:
        agents_called = []
        for result in result_data.get("results", []):
            agent_name = result.get("agent_name", "")
            status = result.get("status", "")
            agents_called.append(
                {
                    "agent_name": agent_name,
                    "display_name": cls.get_agent_display_name(agent_name),
                    "status": status,
                }
            )
        return agents_called

    @classmethod
    def render_agents_called(cls, console: Console, result_data: Dict) -> None:
        agents_called = []
        for item in cls.collect_agents_called(result_data):
            if item["status"] == "success":
                agents_called.append(f"{item['display_name']} ✓")
            elif item["status"] == "error":
                agents_called.append(f"{item['display_name']} ✗")
            else:
                agents_called.append(f"{item['display_name']} ?")

        if agents_called:
            console.print()
            console.print(f"🤖 调用智能体: {', '.join(agents_called)}", style="dim")

    @classmethod
    def render_results(cls, console: Console, result_data: Dict) -> None:
        console.print()

        results = result_data.get("results", [])
        if not results:
            status = result_data.get("status", "unknown")
            if status == "no_agents":
                console.print("✓ 好的，我已记录下来。", style="green")
                console.print("\n💡 您可以继续补充信息，或者尝试：", style="dim")
                console.print("  • 规划行程：「帮我规划去北京的行程」", style="dim")
                console.print("  • 查询信息：「北京的天气怎么样」", style="dim")
                console.print("  • 问问题：「差旅标准是多少」", style="dim")
            else:
                console.print("未能获取有效结果，请重新描述您的需求。", style="yellow")
            console.print()
            return

        has_output = cls._generate_human_response(console, results)
        if not has_output:
            console.print("✓ 已处理您的请求。", style="green")

        console.print()

    @classmethod
    def render_to_text(cls, result_data: Dict) -> str:
        capture = StringIO()
        console = Console(file=capture, force_terminal=False, no_color=True)
        cls.render_agents_called(console, result_data)
        cls.render_results(console, result_data)
        return capture.getvalue().strip()

    @classmethod
    def _generate_human_response(cls, console: Console, results: List[Dict]) -> bool:
        has_output = False

        for result in results:
            agent_name = result.get("agent_name", "")
            status = result.get("status", "")
            data = result.get("data", {})
            current_agent_shown = False

            if status == "error":
                error_msg = data.get("error", "未知错误")
                agent_display_name = cls.get_agent_display_name(agent_name)
                console.print(f"❌ {agent_display_name}执行失败: {error_msg}", style="red")
                has_output = True
                continue

            if status != "success" and not (agent_name == "rag_knowledge" and status == "no_knowledge"):
                continue

            if agent_name == "itinerary_planning":
                itinerary = data.get("itinerary")
                if not itinerary and "data" in data and isinstance(data["data"], dict):
                    itinerary = data["data"].get("itinerary")

                if itinerary:
                    title = itinerary.get("title", "行程规划")
                    console.print(f"\n✈️  [bold cyan]{title}[/bold cyan]")
                    console.print(f"时长: {itinerary.get('duration', '未知')}\n")

                    for day_plan in itinerary.get("daily_plans", []):
                        day_num = day_plan.get("day", 1)
                        console.print(f"[bold yellow]第 {day_num} 天[/bold yellow]")
                        activities = day_plan.get("activities") or day_plan.get("time_slots") or []
                        for slot in activities:
                            time = slot.get("time", "")
                            activity = slot.get("activity") or slot.get("location") or ""
                            description = slot.get("description", "")
                            transport = slot.get("transport", "")

                            console.print(f"  {time} - {activity}")
                            if description:
                                console.print(f"    {description}", style="dim")
                            if transport:
                                console.print(f"    🚇 {transport}", style="dim")

                        meals = day_plan.get("meals", {})
                        if meals:
                            console.print()
                            if meals.get("lunch"):
                                console.print(f"  🍜 {meals['lunch']}", style="dim")
                            if meals.get("dinner"):
                                console.print(f"  🍽️  {meals['dinner']}", style="dim")
                        console.print()

                    notes = itinerary.get("notes", [])
                    if notes:
                        console.print("[bold]📌 注意事项[/bold]")
                        for note in notes:
                            console.print(f"  • {note}")
                    current_agent_shown = True

            elif agent_name == "preference":
                raw_prefs = data.get("preferences")
                if not raw_prefs and "data" in data and isinstance(data["data"], dict):
                    raw_prefs = data["data"].get("preferences")

                if isinstance(raw_prefs, dict):
                    prefs_list = raw_prefs.get("preferences", [])
                else:
                    prefs_list = raw_prefs if isinstance(raw_prefs, list) else []

                if prefs_list:
                    console.print("✓ [bold green]已更新您的偏好设置[/bold green]")
                    type_names = {
                        "home_location": "常驻地",
                        "transportation_preference": "交通偏好",
                        "hotel_brands": "酒店偏好",
                        "airlines": "航空公司偏好",
                        "seat_preference": "座位偏好",
                        "meal_preference": "餐食偏好",
                        "budget_level": "预算等级",
                    }
                    for pref in prefs_list:
                        pref_type = pref.get("type", "")
                        pref_value = pref.get("value", "")
                        action = pref.get("action", "replace")
                        display_type = type_names.get(pref_type, pref_type)
                        action_text = "追加" if action == "append" else "设置为"
                        console.print(f"  • {display_type} {action_text} [cyan]{pref_value}[/cyan]")
                    current_agent_shown = True
                    has_itinerary = any(r.get("agent_name") == "itinerary_planning" for r in results)
                    if not has_itinerary:
                        console.print("\n💡 下次规划行程时会参考这些偏好。", style="dim")
                else:
                    err = data.get("error", "")
                    if err:
                        console.print(f"偏好未保存: {err}", style="yellow")
                        current_agent_shown = True

            elif agent_name == "event_collection":
                nested_data = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
                origin = data.get("origin") or nested_data.get("origin")
                destination = data.get("destination") or nested_data.get("destination")
                start_date = data.get("start_date") or nested_data.get("start_date")
                end_date = data.get("end_date") or nested_data.get("end_date")
                missing_info = data.get("missing_info") or nested_data.get("missing_info") or []

                has_itinerary = any(r.get("agent_name") == "itinerary_planning" for r in results)
                info_shown = False
                if not has_itinerary and (destination or origin):
                    console.print("✓ [bold green]已收集行程信息[/bold green]")
                    if origin:
                        console.print(f"  • 出发地: [cyan]{origin}[/cyan]")
                    if destination:
                        console.print(f"  • 目的地: [cyan]{destination}[/cyan]")
                    if start_date:
                        console.print(f"  • 出发日期: [cyan]{start_date}[/cyan]")
                    if end_date:
                        console.print(f"  • 返程日期: [cyan]{end_date}[/cyan]")
                    info_shown = True

                if missing_info:
                    console.print(f"\n💡 还需要补充: {', '.join(missing_info)}", style="yellow")
                    info_shown = True

                if info_shown:
                    current_agent_shown = True

            elif agent_name == "information_query":
                query_results = data.get("results")
                if not query_results and "data" in data and isinstance(data["data"], dict):
                    query_results = data["data"].get("results")
                if not query_results:
                    query_results = data
                if not isinstance(query_results, dict):
                    query_results = {}

                summary = query_results.get("summary", "")
                sources = query_results.get("sources", []) or []
                message = query_results.get("message", "")
                error = query_results.get("error", "")

                if summary:
                    console.print(f"\n{summary}")
                    current_agent_shown = True
                elif message:
                    console.print(f"\n{message}", style="dim")
                    current_agent_shown = True
                elif error:
                    console.print(f"\n{error}", style="yellow")
                    current_agent_shown = True

                if sources:
                    console.print("\n[bold]参考来源[/bold]")
                    for i, source in enumerate(sources[:3], 1):
                        url = source.get("url", "") if isinstance(source, dict) else str(source)
                        console.print(f"  {i}. {url}", style="dim")
                    current_agent_shown = True

            elif agent_name == "rag_knowledge":
                nested_data = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
                answer = data.get("answer") or nested_data.get("answer")
                if not answer:
                    answer = data.get("content") or nested_data.get("content")

                if isinstance(answer, dict):
                    answer = answer.get("answer", str(answer))

                if isinstance(answer, str) and answer.strip().startswith("{") and answer.strip().endswith("}"):
                    try:
                        import json

                        json_obj = json.loads(answer)
                        if isinstance(json_obj, dict) and "answer" in json_obj:
                            answer = json_obj["answer"]
                    except Exception:
                        pass

                if answer:
                    console.print(f"\n{answer}")
                    current_agent_shown = True

            elif agent_name == "memory_query":
                query_result = data.get("answer") or data.get("result") or data.get("content")
                if not query_result and "data" in data and isinstance(data["data"], dict):
                    inner = data["data"]
                    query_result = inner.get("answer") or inner.get("result") or inner.get("content")

                if query_result:
                    console.print(f"\n{query_result}")
                    current_agent_shown = True

            if not current_agent_shown:
                common_keys = ["answer", "content", "result", "message", "summary", "text", "description"]
                fallback_content = ""

                for key in common_keys:
                    if key in data and isinstance(data[key], str) and data[key].strip():
                        fallback_content = data[key]
                        break

                if not fallback_content and "data" in data and isinstance(data["data"], dict):
                    for key in common_keys:
                        if key in data["data"] and isinstance(data["data"][key], str) and data["data"][key].strip():
                            fallback_content = data["data"][key]
                            break

                if fallback_content:
                    console.print(f"\n{fallback_content}")
                    current_agent_shown = True
                else:
                    agent_display_name = cls.get_agent_display_name(agent_name)
                    console.print(f"✓ {agent_display_name}已完成", style="green")
                    current_agent_shown = True

            if current_agent_shown:
                has_output = True

        return has_output

