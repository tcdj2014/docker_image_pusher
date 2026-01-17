# WMS 归档工具 - 构建说明

## 项目概述

WMS 归档工具是一个用于自动化归档操作的Python应用程序，支持与数据库和Redis交互，以及调用API进行归档操作。

## 构建要求

- Python 3.7 或更高版本
- pip 包管理器
- 约 200MB 可用磁盘空间用于构建过程

## 构建步骤

### 方法一：使用Python构建脚本

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   ```

2. 运行构建脚本：
   ```bash
   python build.py
   ```

### 方法二：使用Shell脚本（Linux/macOS）

1. 确保脚本具有执行权限：
   ```bash
   chmod +x build.sh
   ```

2. 运行构建脚本：
   ```bash
   ./build.sh
   ```

### 方法三：使用批处理脚本（Windows）

双击运行 `build.bat` 文件，或在命令提示符中运行：
```cmd
build.bat
```

## 输出文件

构建完成后，将在 `dist/[platform]/` 目录下生成以下文件：

- `[executable_name]` - 主程序可执行文件
- `config.yaml.example` - 配置文件模板
- `README.txt` - 使用说明

## 配置文件

在运行可执行文件之前，您需要：

1. 复制 `config.yaml.example` 为 `config.yaml`
2. 编辑 `config.yaml` 以配置数据库、Redis和其他设置

## 跨平台构建

由于 PyInstaller 不支持交叉编译，要为不同平台构建可执行文件，您需要在目标平台上运行构建脚本：

- **Windows**: 在 Windows 系统上运行 `build.bat`
- **macOS**: 在 macOS 系统上运行 `build.sh`
- **Linux**: 在 Linux 系统上运行 `build.sh`

## 构建脚本功能

构建脚本会自动执行以下操作：

1. 安装必要的依赖（PyInstaller 和项目依赖）
2. 使用 PyInstaller 将 Python 脚本打包为单个可执行文件
3. 包含 `config.yaml` 配置文件
4. 为生成的可执行文件创建平台特定的目录
5. 生成配置文件模板和说明文档

## 常见问题

### 构建过程中出现内存不足错误

- 确保系统有足够的可用内存（建议至少 2GB）
- 清理系统临时文件后再试

### 可执行文件过大

- PyInstaller 生成的单文件可执行文件通常较大，这是正常的
- 可以通过 UPX 压缩减小文件大小（需要单独安装 UPX）

### 运行时找不到配置文件

- 确保 `config.yaml` 文件与可执行文件在同一目录下
- 或者在可执行文件所在目录中创建 `config.yaml`

## 项目结构

```
archive/
├── main.py                 # 主程序
├── config.yaml             # 配置文件
├── requirements.txt        # Python依赖
├── build.py               # Python构建脚本
├── build.sh               # Linux/macOS构建脚本
├── build.bat              # Windows构建脚本
├── BUILDING.md            # 本文档
└── dist/                  # 构建输出目录
    ├── windows/           # Windows可执行文件
    ├── mac/               # macOS可执行文件
    └── linux/             # Linux可执行文件
```

## 自定义构建

如果需要自定义构建参数，可以直接编辑 `build.py` 中的 PyInstaller 命令，或创建自己的 `.spec` 文件。