from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HomeView:
    hero_title: str
    primary_action: str
    flow_steps: list[str] = field(default_factory=list)


def build_home_view(state: dict) -> HomeView:
    has_plan = state.get("study_plan") is not None
    return HomeView(
        hero_title="学习规划助手",
        primary_action="继续查看学习计划" if has_plan else "配置学习目标",
        flow_steps=["配置目标", "生成计划", "资料问答", "复盘调整", "导出计划"],
    )
