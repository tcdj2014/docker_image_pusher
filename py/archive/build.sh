#!/bin/bash
# WMS归档工具构建脚本

echo "WMS 归档工具 - 可执行文件构建脚本"
echo "====================================="

# 检查是否安装了Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 Python3，请先安装 Python3"
    exit 1
fi

# 检查是否安装了pip
if ! command -v pip3 &> /dev/null; then
    echo "错误: 未找到 pip3，请先安装 pip3"
    exit 1
fi

echo "正在安装依赖..."
pip3 install -r requirements.txt
pip3 install pyinstaller

echo ""
echo "开始构建可执行文件..."

# 根据操作系统设置输出文件名
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    # Windows
    pyinstaller --onefile --name wms-archive-tool.exe --add-data "config.yaml;." --console --clean main.py
    TARGET_DIR="dist/windows"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    pyinstaller --onefile --name wms-archive-tool-mac --add-data "config.yaml:." --console --clean main.py
    TARGET_DIR="dist/mac"
else
    # Linux
    pyinstaller --onefile --name wms-archive-tool-linux --add-data "config.yaml:." --console --clean main.py
    TARGET_DIR="dist/linux"
fi

# 创建目标目录
mkdir -p "$TARGET_DIR"

# 移动生成的可执行文件到目标目录
EXECUTABLE_FILE=$(basename "$(find dist -maxdepth 1 -type f -executable -print)" 2>/dev/null)
if [ ! -z "$EXECUTABLE_FILE" ]; then
    mv "dist/$EXECUTABLE_FILE" "$TARGET_DIR/"
    echo "可执行文件已保存到: $TARGET_DIR/$EXECUTABLE_FILE"
fi

# 复制配置文件模板
cp config.yaml "$TARGET_DIR/config.yaml.example"
echo "配置文件模板已保存到: $TARGET_DIR/config.yaml.example"

echo ""
echo "构建完成！"
echo "可在 $TARGET_DIR/ 目录下找到可执行文件"