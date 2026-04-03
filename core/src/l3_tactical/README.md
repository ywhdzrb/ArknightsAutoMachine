# l3_tactical - L3 战术层实现

## 目录说明

本目录包含战术执行引擎，实现游戏战术原语的编译和执行。

## 文件说明

### tactical_vm.cpp
**战术虚拟机**

执行战术字节码的沙箱环境:
- 基于栈的虚拟机
- 指令级超时控制
- 异常安全执行

### bytecode/
字节码定义目录:
- **opcodes.hpp**: 操作码枚举
- **assembler.cpp**: 汇编器（DSL → 字节码）

### cost_manager.cpp
**费用管理器**

实时追踪游戏费用:
- OCR 费用数字识别
- 费用速率估算
- 部署时机决策

### collision_predictor.cpp
**碰撞检测与路径规划**

游戏机制模拟:
- 敌人路径预测
- 干员攻击范围计算
- 碰撞检测（阻挡、位移）

## 战术 DSL

### 语法示例
```python
# 部署干员
deploy("能天使", tile=(3,4), direction=RIGHT, cost_threshold=14)

# 释放技能
use_skill("能天使", wait_for_cd=True)

# 撤退干员
retreat("能天使", condition=hp_below(0.3))

# 条件判断
if enemy_approaching("红刀哥"):
    use_skill("史尔特尔")
```

### 编译流程
```
DSL 源码
    │
    ▼
┌─────────────┐
│ 词法分析     │
│ (Lexer)     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 语法分析     │
│ (Parser)    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 语义分析     │
│ (Analyzer)  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 字节码生成   │
│ (Codegen)   │
└──────┬──────┘
       │
       ▼
字节码文件 (.tac)
```

## 字节码指令集

```cpp
enum class Opcode : uint8_t {
    // 控制流
    NOP = 0x00,
    HALT = 0x01,
    
    // 栈操作
    PUSH = 0x10,
    POP = 0x11,
    DUP = 0x12,
    
    // 战术原语
    DEPLOY = 0x20,
    USE_SKILL = 0x21,
    RETREAT = 0x22,
    CHANGE_SPEED = 0x23,
    
    // 条件判断
    JMP = 0x30,
    JZ = 0x31,
    JNZ = 0x32,
    
    // 算术逻辑
    ADD = 0x40,
    SUB = 0x41,
    EQ = 0x42,
    LT = 0x43,
    GT = 0x44,
};
```

## 虚拟机架构

```
┌─────────────────────────────────────┐
│           TacticalVM                │
├─────────────────────────────────────┤
│  PC │ 指令指针                       │
│  SP │ 栈指针                         │
│  FP │ 帧指针                         │
├─────────────────────────────────────┤
│  操作数栈 (256 slots)               │
├─────────────────────────────────────┤
│  局部变量表 (64 vars)               │
├─────────────────────────────────────┤
│  字节码存储区                        │
└─────────────────────────────────────┘
```

## 费用管理

### 费用追踪
```cpp
class CostManager {
    int getCurrentCost();           // OCR 识别
    float getCostRate();            // 速率估算
    bool canDeploy(const Operator& op);
    int predictCost(int seconds);   // 未来费用预测
};
```

### 部署时机
```cpp
class DeploymentOptimizer {
    // 基于费用曲线的最优部署时机
    int findOptimalDeployTime(
        const Operator& op,
        const WaveTimeline& wave
    );
};
```

## 碰撞检测

### 地图网格
```cpp
class MapGrid {
    bool isWalkable(Point2D pos);
    bool isDeployable(Point2D pos, TileType type);
    std::vector<Point2D> getEnemyPath(int route_id);
};
```

### 攻击范围
```cpp
class AttackRange {
    std::vector<Point2D> getCoveredTiles(
        Point2D operator_pos,
        Direction facing,
        const AttackPattern& pattern
    );
};
```

## 相关目录

- [include/aam/l3/](../../include/aam/l3/): 接口定义
- [src/l4_state/](../l4_state/): 状态查询
