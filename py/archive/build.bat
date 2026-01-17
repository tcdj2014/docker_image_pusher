@echo off
REM WMS归档工具Windows构建脚本

echo WMS 归档工具 - 可执行文件构建脚本
echo =====================================

REM 检查是否安装了Python
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python，请先安装 Python
    pause
    exit /b 1
)

REM 检查是否安装了pip
pip --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 pip，请先安装 pip
    pause
    exit /b 1
)

echo 正在安装依赖...
pip install -r requirements.txt
pip install pyinstaller

echo.
echo 开始构建可执行文件...

REM 构建可执行文件
pyinstaller --onefile --name wms-archive-tool.exe --add-data "config.yaml;." --console --clean main.py

REM 创建目标目录
if not exist "dist\windows" mkdir dist\windows

REM 移动生成的可执行文件到目标目录
if exist "dist\wms-archive-tool.exe" (
    move "dist\wms-archive-tool.exe" "dist\windows\"
    echo 可执行文件已保存到: dist\windows\wms-archive-tool.exe
)

REM 复制配置文件模板
copy "config.yaml" "dist\windows\config.yaml.example"
echo 配置文件模板已保存到: dist\windows\config.yaml.example

echo.
echo 构建完成！
echo 可在 dist\windows\ 目录下找到可执行文件
pause