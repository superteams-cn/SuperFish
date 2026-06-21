# 叙事引擎设计（剧本拆解 P1–P2）

> 状态：草案 / 待评审。本文件是 `feat/script-breakdown` 分支上「剧本剧情拆解 + 推演」
> 第二三阶段（P1 叙事引擎单线 MVP、P2 分支推演）的架构基准。
> 背景与产品取向见提交 `feat: 剧本拆解 P0`。

## 0. 一句话目标

在 SuperFish 现有「抽取链 + 报告外壳」之上，新增一个**叙事引擎**：让 P0 拆解出的
「带动机的角色 + 戏剧关系网」在**场景**里通过对话与行动「演一遍」，支持
**忠实复演**（验证拆解）与**自由推演**（探索走向），并以 **event-sourced 状态**
为地基，让 **续跑（resume）与分支（fork）由同一套机制掉出来**。

## 1. 范围分期

| 阶段 | 交付 | 不做 |
| --- | --- | --- |
| **P1（本文件主体）** | 单条时间线的叙事引擎 MVP：Scene / Director / Character + 两种模式 + event-sourced 状态 | 分支、上帝视角注入、编剧专业报告 |
| **P2** | checkpoint / fork + 上帝视角注入变量 + 多结局对比 | — |
| **P3** | 编剧专业拆解模板 + 叙事报告章节 + Step5 多结局追问 | — |

> ⚠️ 顺序铁律：fork 无法建在跑不起来的时间线上。**P1 必须把 event-sourced 地基打对**，
> P2 的分支才是「加功能」而非「重构状态」。

## 2. 与现有系统的接缝（复用边界）

P0 已确立「按 `kind` 分派」。叙事引擎是 `kind == "narrative"` 时中段引擎的实现。

```
上传剧本 → ontology(narrative 模板) → graph_builder → entity_resolution   ← 复用，不改
  → [角色人设生成]   ← 复用 oasis_profile_generator，但 persona 维度偏戏剧（见 §6）
  → [叙事引擎 run_narrative_simulation.py]   ← 全新（本文件）
  → [报告 + 追问]   ← 复用 report/ 外壳，P3 加叙事章节
```

**关键复用发现**：现有 `simulation_runner` 的运行模型已经是「子进程把动作 append 进
`actions.jsonl`，主进程 `MonitorThread` 按 offset 续读 + `Reconciler` 接管 + owner 锁」
（见 `app/services/simulation/`、记忆 `stateless-recovery`）。
**这套 offset 续读的监控基础设施本身就是 event-sourcing 的运行时**。
叙事引擎只要把事件日志从 `actions.jsonl` 换成 `beats.jsonl`，即可**整套复用**监控/续跑/接管，
不必新写一套无状态恢复。fork 也因此几乎白送（§5）。

## 3. 核心抽象

```
WorldState        当前剧情世界：已发生 beat 的折叠结果（人物状态/关系变化/场景指针）
Character(agent)  一个可决策角色：persona + 动机/目标 + 长期记忆 + 当前情绪/处境
Scene             一幕：在场角色集合、地点、时刻、场景目标/冲突、进入与退出条件
Director(agent)   推进者：决定下一个 beat 由谁触发、何时切场、注入事件；执行模式策略
Beat              最小事件单元：一次「角色发声/行动」或「导演旁白/场景切换」
```

- **Character ≠ 社媒 agent**：它不发帖，它在场景里**对谁说什么 / 做什么 / 去哪**。
- **Director 是叙事引擎独有**：社媒模拟没有导演（信息流自组织）；剧情需要有人
  推进节奏、控制「忠实 vs 自由」的张力、判定一幕结束。

### 动作空间（Beat 类型）

| 类型 | 含义 | 关键字段 |
| --- | --- | --- |
| `SPEAK` | 角色对在场对象说话 | `speaker`, `to[]`, `content`, `subtext`(潜台词) |
| `ACT` | 物理/情节行动 | `actor`, `action`, `targets[]`, `effect` |
| `MOVE` | 角色进出场景 | `actor`, `from_scene`, `to_scene` |
| `ASIDE` | 内心独白 / 动机暴露（**供拆解**，不被其他角色感知） | `actor`, `inner` |
| `DIRECT` | 导演事件：切场、引入外部冲突、时间跳跃 | `kind`, `payload` |

## 4. Event-sourced 状态模型（地基，最重要）

### 4.1 三件套

1. **不变种子 `narrative_seed.json`**：初始 WorldState（角色集、关系网、初始场景、
   模式、推演需求）。来自 P0 的 graph + 角色人设。
2. **追加事件流 `beats.jsonl`**：一行一个 Beat，**只追加、不可变**，带单调递增 `seq`。
   这是唯一事实来源（source of truth）。
3. **周期快照 `snapshots/seq_<N>.json`**：把 seed + beats[0..N] 折叠出的 WorldState +
   各 Character 记忆，纯属**重放加速缓存**，丢失可由 seed+beats 重建。

```
WorldState(N) = fold(seed, beats[0..N])          # 纯函数，可重放
resume         = 读最近快照 → 重放其后的 beats     # 复用现有 offset 续读
```

### 4.2 为什么这是对的

- **续跑**：进程被 detach/重启 → 读最近快照，从其 `seq` 之后重放 beats。
  正是现有 `MonitorThread` 的 offset 续读语义，零新增。
- **分支（P2）**：fork = 选定 `seq=K` → 拷贝 `beats[0..K]` 到新 `branch_id` →
  （可选）追加一条 `DIRECT` 注入变量 → 用同一引擎续跑。
  **续跑与分支是同一动作的两种入口**，这就是 P1 打对地基换来的红利。
- **拆解可解释**：`ASIDE` 事件让「角色为什么这么做」显式留痕，报告可直接引用。

### 4.3 持久化落点（对齐 stateless-recovery）

- `beats.jsonl` / `snapshots/` 运行期在节点本地（与现有 `actions.jsonl` 同构），
  终态镜像到 S3；元数据进 Postgres（复用 `SimulationRow`，加 `kind` 已在 P0 完成，
  分支需要时 P2 再加 `branch_of` / `forked_at_seq` 列）。
- owner 锁 / detach 不杀 / reconcile 接管：**直接复用** `simulation/` 子包，不重写。

## 5. 两种模式（Director 策略）

| | 忠实复演 | 自由推演（默认，以推演为主） |
| --- | --- | --- |
| Director 锚点 | 原剧本的幕场与关键节点 | 仅锚初始设定 + 冲突，放手发挥 |
| 角色自由度 | 低：偏离剧本时校准回轨 | 高：动机驱动，允许偏离 |
| 用途 | 验证拆解（动机是否站得住、节奏、弧光断裂） | 探索不同走向 / 结局 |
| 实现 | Director 在每个 beat 前比对剧本提纲，约束候选动作 | Director 只在「卡死/跑题/该收束」时介入 |

模式存于 `narrative_seed.json`，由 Director 读取后切换提示词与介入强度。

## 6. 角色人设复用

复用 `oasis_profile_generator`，但：
- 输入实体已带 P0 抽出的 `motivation / goal / mental_state / arc / faction` 属性（实测《雷雨》已稳定产出）。
- persona 维度从「社媒运营特征（karma/粉丝/发帖频率）」改为「戏剧维度（动机/恐惧/底线/与各角色关系认知）」。
- ⚠️ 注意记忆 `oasis-profile-required-fields`：OASIS 引擎无条件读 reddit profile 的
  mbti/gender/age/country。叙事引擎是**独立 runner**，不走 OASIS，故无此约束；
  但若 P1 想偷懒复用 OASIS 的 agent 记忆原语，需补齐这些字段或解耦该读取。

## 7. P1 第一个垂直切片（建议先做）

最小可演示闭环，验证「引擎能演」再扩：

1. `domain/narrative.py`：WorldState / Character / Scene / Beat 纯数据类 + `fold()` 纯函数。
2. `services/narrative/seed_builder.py`：graph + 人设 → `narrative_seed.json`。
3. `scripts/run_narrative_simulation.py`：单场景循环 —— Director 选角色 → Character 产 beat
   → append `beats.jsonl` → 折叠更新 WorldState → 判定收场。先只支持 `SPEAK`/`ASIDE`/`DIRECT`。
4. 接入 `simulation_runner` 的 `platform`/`kind` 分派：`narrative` → 跑新脚本，
   监控复用 `MonitorThread`（事件文件名参数化为 `beats.jsonl`）。
5. 前端 Step3 复用动作流面板，渲染 beat（说话/旁白/切场）。

**先不做**：多场景调度、MOVE/ACT 全动作空间、分支、报告章节。

## 8. 待定问题（评审时拍板）

1. **角色记忆**：自建轻量记忆（向量/摘要）还是复用 OASIS 的 `agent_memory`？
   后者省事但带 OASIS 耦合（§6 警告）。倾向：P1 先用「最近 N 个相关 beat + 角色摘要」最简方案。
2. **收场判定**：Director 用「场景目标达成 / beat 预算耗尽 / 冲突解决」哪个为主？
3. **beat 粒度的 LLM 成本**：每个 beat 一次 LLM 调用，长剧成本高。是否引入「一次产多 beat」批处理？
4. **快照频率**：每 N 个 beat 还是每次切场？影响 resume 重放成本与存储。
```
