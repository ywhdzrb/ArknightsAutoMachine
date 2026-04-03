# l4_state - L4 状态层实现

## 目录说明

本目录包含游戏状态机实现和对局存档系统。

## 文件说明

### hfsm_impl.cpp
**分层状态机实现**

基于 Boost.MSM 的分层状态机:
- 顶层: GameState (Preparation/Combat/Paused/Ended)
- 中层: WaveState (波次管理)
- 底层: OperatorState/EnemyState (实体状态)

### sqlite_storage.cpp
**SQLite 存储**

本地数据持久化:
- 关卡数据缓存
- 对局历史记录
- 配置存储

### delta_encoder.cpp
**增量编码**

高效快照存储:
- 仅记录变化（Delta Encoding）
- MessagePack 二进制格式
- 每秒存储 < 10KB

### prts_data_loader.cpp
**PRTS 数据加载器**

明日方舟游戏数据解析:
- 关卡数据 (level.json)
- 区域数据 (zone.json)
- 敌人数据 (enemy.json)

## 状态机架构

```
┌─────────────────────────────────────────┐
│           GameStateMachine              │
│           (顶层状态机)                   │
├─────────────────────────────────────────┤
│                                         │
│   ┌──────────┐    开始    ┌──────────┐ │
│   │ PREP    │ ─────────► │ COMBAT   │ │
│   │ 准备阶段 │            │ 战斗阶段  │ │
│   └──────────┘            └────┬─────┘ │
│        ▲                       │       │
│        │      暂停/恢复         │       │
│        └───────────────────────┘       │
│                       │                │
│                       ▼                │
│                  ┌──────────┐          │
│                  │  PAUSED  │          │
│                  │ 暂停阶段  │          │
│                  └──────────┘          │
│                       │                │
│                       ▼ 结束           │
│                  ┌──────────┐          │
│                  │  ENDED   │          │
│                  │ 结算阶段  │          │
│                  └──────────┘          │
│                                         │
└─────────────────────────────────────────┘
```

## 状态定义

### 游戏状态
```cpp
enum class GameState {
    PREPARATION,    // 选卡/部署前
    COMBAT,         // 战斗中
    PAUSED,         // 暂停（战术规划）
    ENDED           // 结算
};
```

### 波次状态
```cpp
struct WaveState {
    int current_wave;
    int total_waves;
    int enemies_remaining;
    std::chrono::seconds time_to_next;
};
```

### 干员状态
```cpp
struct OperatorState {
    std::string id;
    Point2D position;
    Direction facing;
    float hp_percent;
    float sp_percent;       // 技力
    bool skill_ready;
    OperatorStatus status;  // 部署/撤退/待机
};
```

## 快照系统

### 完整快照
```cpp
struct GameSnapshot {
    std::string snapshot_id;        // UUID
    Timestamp timestamp;
    GameState state;
    WaveState wave;
    std::vector<OperatorState> operators;
    std::vector<EnemyState> enemies;
    GameResources resources;
};
```

### 增量快照
```cpp
struct DeltaSnapshot {
    std::string base_snapshot_id;
    std::vector<FieldChange> changes;
    
    // 编码后大小: 通常 < 1KB
    std::vector<uint8_t> encode() const;
};
```

### 时间旅行
```cpp
class TimeTravel {
    // 回退到任意历史状态
    GameSnapshot restore(const std::string& snapshot_id);
    
    // 分支模拟（What-if 分析）
    void branch(const GameSnapshot& state);
};
```

## 数据库存储

### 表结构
```sql
-- 关卡数据
CREATE TABLE levels (
    level_id TEXT PRIMARY KEY,
    name TEXT,
    zone_id TEXT,
    grid_data BLOB,
    wave_data BLOB
);

-- 对局历史
CREATE TABLE matches (
    match_id TEXT PRIMARY KEY,
    level_id TEXT,
    start_time INTEGER,
    end_time INTEGER,
    result TEXT,
    snapshots BLOB  -- MessagePack
);

-- 状态快照
CREATE TABLE snapshots (
    snapshot_id TEXT PRIMARY KEY,
    match_id TEXT,
    timestamp INTEGER,
    delta_data BLOB,
    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);
```

## PRTS 数据同步

### 自动更新
```yaml
# .github/workflows/prts-sync.yml
name: PRTS Data Sync
on:
  schedule:
    - cron: '0 0 * * *'  # 每日同步
```

### 数据结构
```cpp
struct LevelData {
    std::string level_id;
    std::vector<Tile> tiles;
    std::vector<Route> routes;
    std::vector<Wave> waves;
    std::vector<PredefinedOperator> predefines;
};
```

## 性能指标

| 操作 | 延迟 | 存储 |
|---|---|---|
| 状态查询 | < 1ms | - |
| 完整快照 | < 5ms | ~50KB |
| 增量快照 | < 2ms | ~1KB |
| 状态恢复 | < 10ms | - |

## 相关目录

- [include/aam/l4/](../../include/aam/l4/): 接口定义
- [scripts/db_migrate/](../../../scripts/db_migrate/): 数据迁移工具
