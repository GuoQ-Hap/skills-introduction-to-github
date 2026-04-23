# Multi-Model Agent Framework

该目录实现了一个可插拔的多模型智能 Agent 框架，核心目标是：

1. **中枢固定**：`CoreOrchestrator` 只维护阶段状态机，不绑定具体业务。
2. **能力插件化**：分类、检索、重排、路由、模型调用、评估、工具、提示模板全部通过插件替换。
3. **协议稳定**：统一 `TaskContext / ExecutionState / AnswerPacket / EvalReport` 协议，底层可替换不影响上层。
4. **数据分层**：`Session/Profile/FAQ/Knowledge` 四类存储独立。
5. **治理闭环**：配置、预算、审计、降级由 `GovernanceRuntime` 统一处理。

## 目录说明

- `contract.py`: 协议层（输入输出与中间状态）
- `core/orchestrator.py`: 中枢编排器（固定七阶段）
- `plugins/interfaces.py`: 插件接口协议
- `plugins/registry.py`: 插件注册、优先级、A/B、回退链
- `plugins/defaults.py`: 默认插件实现（可直接替换）
- `data/memory.py`: 四类存储与 MemoryPolicy
- `governance.py`: 配置中心、审计、预算、熔断/降级策略
- `bootstrap.py`: 从本地配置装配整个 Orchestrator
- `agent_framework.example.yaml`: 本地插件配置示例

## 快速开始

```python
from Base.Ai.agent_framework.bootstrap import quick_run

result = quick_run(
    config_path="Base/Ai/agent_framework/agent_framework.example.yaml",
    query="帮我排查接口 500 错误",
)
print(result["answer"])
print(result["next_action"])
```

## 升级路径

- 升级能力时，只替换对应阶段插件，不改 `CoreOrchestrator`。
- 模型切换、向量库切换、评估器切换，通过插件与协议层隔离完成。
- 治理参数统一在配置中调整，支持灰度发布和回退。
