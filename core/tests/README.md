# tests - C++ 测试

## 目录说明

本目录包含 AAM Core 的所有测试代码，包括单元测试、集成测试和性能基准。

## 目录结构

```
tests/
├── integration/           # 跨层集成测试
│   └── test_l0_to_l2_pipeline.cpp
└── benchmarks/            # 性能基准测试
    └── benchmark_capture_latency.cpp
```

## 测试框架

使用 Google Test (GTest) 框架:

```cmake
find_package(GTest REQUIRED)
enable_testing()

add_executable(aam_core_tests
    integration/test_l0_to_l2_pipeline.cpp
)

target_link_libraries(aam_core_tests
    GTest::gtest_main
    aam_core
)

include(GoogleTest)
gtest_discover_tests(aam_core_tests)
```

## 单元测试

单元测试位于各层 `src/` 目录的 `tests/` 子目录中:
- `src/l0_sensing/tests/`
- `src/l1_perception/tests/`
- `src/l2_motor/tests/`
- `src/l3_tactical/tests/`
- `src/l4_state/tests/`

### 示例
```cpp
#include <gtest/gtest.h>
#include "aam/l0/capture_backend.hpp"

TEST(ADBCaptureTest, BasicCapture) {
    auto backend = std::make_unique<ADBCapture>();
    backend->start();
    
    auto frame = backend->capture();
    EXPECT_FALSE(frame.data.empty());
    EXPECT_GT(frame.timestamp, 0);
    
    backend->stop();
}
```

## 集成测试

### test_l0_to_l2_pipeline.cpp
验证 L0→L1→L2 完整流水线:

```cpp
TEST_F(PipelineTest, EndToEndLatency) {
    // 测量 L0 捕获到 L2 执行的完整延迟
    auto start = Timer::now();
    
    auto frame = l0.capture();
    auto perception = l1.process(frame);
    l2.execute(perception.actions);
    
    auto latency = Timer::elapsed_ms(start);
    EXPECT_LT(latency, 50);  // < 50ms
}
```

## 性能基准

### benchmark_capture_latency.cpp

使用 Google Benchmark:

```cpp
#include <benchmark/benchmark.h>

static void BM_CaptureLatency(benchmark::State& state) {
    ADBCapture capture;
    capture.start();
    
    for (auto _ : state) {
        auto frame = capture.capture();
        benchmark::DoNotOptimize(frame);
    }
    
    capture.stop();
}

BENCHMARK(BM_CaptureLatency)
    ->Unit(benchmark::kMillisecond)
    ->Iterations(1000);
```

## 运行测试

```bash
# 所有测试
ctest --output-on-failure

# 特定测试
./aam_core_tests --gtest_filter="ADBCaptureTest.*"

# 性能测试
./aam_benchmarks --benchmark_format=json > benchmark.json

# 带覆盖率
ctest -T Coverage
```

## 测试数据

测试数据存储于 `tests/fixtures/`:
- `screenshots/`: 测试截图
- `recordings/`: 录屏数据

## CI 集成

```yaml
- name: Run Tests
  run: ctest --output-on-failure -j$(nproc)
  
- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
```

## 覆盖率目标

| 类型 | 目标 |
|---|---|
| 单元测试 | > 90% |
| 集成测试 | > 80% |
| 分支覆盖 | > 85% |

## 相关目录

- [tests/](../../tests/): 端到端测试
- [src/*/tests/](../src/): 层内单元测试
