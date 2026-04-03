# tests - 端到端测试

## 目录说明

本目录包含 AAM 项目的端到端（E2E）测试，验证完整系统功能。

## 目录结构

```
tests/
├── e2e/                   # 端到端测试
│   ├── test_1_7_clear.py  # 1-7 关卡通关测试
│   └── test_crisis_contract.py  # 危机合约测试
└── fixtures/              # 测试数据
    ├── screenshots/       # 测试截图
    └── recordings/        # 录屏数据
```

## E2E 测试

### test_1_7_clear.py

验证 1-7 关卡全自动通关:

```python
import pytest
from aam_core import Core
from aam_inference import L5Controller

@pytest.mark.e2e
@pytest.mark.timeout(300)  # 5分钟超时
def test_1_7_clear():
    """测试 1-7 关卡全自动通关"""
    
    # 初始化系统
    core = Core()
    core.initialize()
    
    # 选择关卡
    core.select_mission("1-7")
    
    # 开始自动战斗
    result = core.start_auto_combat()
    
    # 验证结果
    assert result.success
    assert result.stars == 3
    assert result.no_leak  # 无漏怪
```

### test_crisis_contract.py

危机合约测试:

```python
@pytest.mark.e2e
@pytest.mark.crisis
@pytest.mark.parametrize("contract_level", [18, 24, 30])
def test_crisis_contract(contract_level):
    """测试危机合约指定等级"""
    
    core = Core()
    core.initialize()
    
    # 选择合约
    core.select_crisis_contract(
        map_name="切尔诺伯格",
        level=contract_level
    )
    
    # 执行
    result = core.start_auto_combat()
    
    assert result.success
```

## 测试数据

### fixtures/screenshots/

测试用截图:
```
screenshots/
├── 1-7_start.png          # 1-7 开始界面
├── 1-7_combat.png         # 1-7 战斗画面
├── 1-7_victory.png        # 1-7 胜利界面
├── main_menu.png          # 主菜单
└── operator_select.png    # 干员选择
```

### fixtures/recordings/

测试录屏:
```
recordings/
├── 1-7_success.mp4        # 成功通关录屏
├── 1-7_failure.mp4        # 失败场景录屏
└── network_lag.mp4        # 网络延迟场景
```

## 测试环境

### 要求
- Android 设备或模拟器
- ADB 连接正常
- 游戏已安装并登录
- 测试账号有指定关卡权限

### 配置
```yaml
# tests/e2e/config.yaml
e2e:
  device:
    id: "auto"              # 自动检测
    resolution: [1920, 1080]
  
  game:
    package: "com.hypergryph.arknights"
    activity: "com.u8.sdk.U8UnityContext"
  
  test_account:
    server: "官服"          # 官服/B服
    level_range: [1, 100]   # 账号等级范围
```

## 运行测试

```bash
# 所有 E2E 测试
pytest tests/e2e/ -v --e2e

# 特定测试
pytest tests/e2e/test_1_7_clear.py -v

# 带录屏
pytest tests/e2e/ -v --e2e --record

# 并行执行
pytest tests/e2e/ -v --e2e -n auto
```

## CI 集成

```yaml
# .github/workflows/e2e.yml
name: E2E Tests

on:
  schedule:
    - cron: '0 2 * * *'  # 每日凌晨2点

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Android Emulator
        uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: 33
          script: pytest tests/e2e/ -v
```

## 相关目录

- [core/tests/](../core/tests/): C++ 单元/集成测试
- [inference/tests/](../inference/tests/): Python 单元/集成测试
