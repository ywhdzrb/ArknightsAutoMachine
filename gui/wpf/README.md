# wpf - WPF 实现

## 目录说明

本目录包含基于 WPF 的 Windows 原生 GUI 实现，提供最佳的 Windows 平台体验。

## 技术栈

- **.NET 8**: 运行时
- **WPF**: UI 框架
- **C++/CLI**: 托管/非托管桥接
- **Windows 原生 API**: 系统集成

## 目录结构

```
gui/wpf/
├── AAM.WPF/                  # C# 主项目
│   ├── Views/
│   │   ├── MainWindow.xaml   # 主窗口
│   │   └── MapOverlay.xaml   # 悬浮地图层
│   ├── ViewModels/           # MVVM 模式
│   │   ├── MainViewModel.cs
│   │   └── MapViewModel.cs
│   └── App.xaml
└── AAM.Native/               # C++/CLI 桥接
    ├── include/
    └── src/
        ├── cpp_cli_bridge.cpp
        └── frame_pusher.cpp  # 零拷贝帧传递
```

## 架构设计

```
┌─────────────────────────────────────────┐
│           AAM.WPF (C#)                  │
│  ┌─────────────────────────────────┐   │
│  │  Views (XAML)                   │   │
│  │  - MainWindow                   │   │
│  │  - MapOverlay                   │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │  ViewModels                     │   │
│  │  - MainViewModel                │   │
│  │  - MapViewModel                 │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │  Services                       │   │
│  │  - NativeBridge                 │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
                    │
                    ▼ C++/CLI
┌─────────────────────────────────────────┐
│           AAM.Native (C++/CLI)          │
│  ┌─────────────────────────────────┐   │
│  │  CLI Bridge                     │   │
│  │  - 托管/非托管边界              │   │
│  │  - 类型转换                     │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │  Frame Pusher                   │   │
│  │  - WriteableBitmap 零拷贝       │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
                    │
                    ▼ 原生 C++
┌─────────────────────────────────────────┐
│           AAM Core (C++)                │
└─────────────────────────────────────────┘
```

## 主窗口

### XAML 定义
```xml
<!-- Views/MainWindow.xaml -->
<Window x:Class="AAM.WPF.Views.MainWindow"
        xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        Title="Arknights Auto Machine">
    <Grid>
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>      <!-- 地图 -->
            <ColumnDefinition Width="300"/>    <!-- 控制面板 -->
        </Grid.ColumnDefinitions>
        
        <!-- 地图视图 -->
        <Image x:Name="MapImage" 
               Source="{Binding MapSource}"/>
        
        <!-- 控制面板 -->
        <StackPanel Grid.Column="1">
            <TextBlock Text="{Binding Status}"/>
            <ListView ItemsSource="{Binding Operators}"/>
            <TextBox Text="{Binding LogOutput}"/>
        </StackPanel>
    </Grid>
</Window>
```

### ViewModel
```csharp
// ViewModels/MainViewModel.cs
public class MainViewModel : INotifyPropertyChanged
{
    private readonly INativeBridge _bridge;
    
    public BitmapSource MapSource { get; private set; }
    public string Status { get; private set; }
    public ObservableCollection<OperatorViewModel> Operators { get; }
    
    public MainViewModel(INativeBridge bridge)
    {
        _bridge = bridge;
        _bridge.FrameReceived += OnFrameReceived;
    }
    
    private void OnFrameReceived(IntPtr frameData, int width, int height)
    {
        // 零拷贝创建 BitmapSource
        MapSource = BitmapSource.Create(
            width, height, 96, 96,
            PixelFormats.Bgr32, null,
            frameData, width * height * 4, width * 4);
    }
}
```

## C++/CLI 桥接

### 类型转换
```cpp
// AAM.Native/src/cpp_cli_bridge.cpp
#include <msclr/marshal_cppstd.h>

using namespace System;
using namespace System::Runtime::InteropServices;

public ref class NativeBridge
{
public:
    void Initialize()
    {
        native_core_ = std::make_unique<aam::core::Core>();
        native_core_->initialize();
    }
    
    void StartCapture()
    {
        native_core_->startCapture();
    }
    
    event Action<IntPtr, int, int>^ FrameReceived;
    
private:
    std::unique_ptr<aam::core::Core> native_core_;
    
    void OnNativeFrame(const cv::Mat& frame)
    {
        // 锁定内存并传递指针
        auto handle = GCHandle::Alloc(frame.data, GCHandleType::Pinned);
        FrameReceived(handle.AddrOfPinnedObject(), frame.cols, frame.rows);
        handle.Free();
    }
};
```

## 零拷贝帧传递

```cpp
// AAM.Native/src/frame_pusher.cpp
class FramePusher
{
public:
    void pushFrame(const cv::Mat& frame)
    {
        // 直接传递内存指针，无拷贝
        cli_bridge_->onFrameReceived(
            frame.data,
            frame.cols,
            frame.rows
        );
    }
};
```

## Windows 集成

### 通知中心
```csharp
// Windows 原生通知
var toast = new ToastContentBuilder()
    .AddText("AAM")
    .AddText("关卡完成！")
    .Show();
```

### Xbox Game Bar
```csharp
// Xbox Game Bar Widget
public class AAMWidget : GameBarWidget
{
    // 游戏栏集成
}
```

## 构建

```bash
# 构建 C++/CLI 桥接
cmake -B build_native -S gui/wpf/AAM.Native
cmake --build build_native

# 构建 WPF 项目
dotnet build gui/wpf/AAM.WPF/AAM.WPF.csproj

# 运行
dotnet run --project gui/wpf/AAM.WPF
```

## 相关目录

- [gui/abstract/](../abstract/): 抽象接口
- [gui/qt/](../qt/): Qt6 实现
