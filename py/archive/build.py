#!/usr/bin/env python3
"""
WMS归档工具 - 可执行文件构建脚本
用于将Python脚本打包为单个可执行文件
"""

import os
import platform
import subprocess
import sys
from pathlib import Path
import shutil

def install_dependencies():
    """安装所需的依赖包"""
    print("正在安装依赖包...")
    try:
        # 尝试安装依赖，如果失败则使用 --break-system-packages
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        except subprocess.CalledProcessError:
            print("尝试使用 --break-system-packages 参数安装依赖...")
            subprocess.run([sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"], check=True)
        
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        except subprocess.CalledProcessError:
            print("尝试使用 --break-system-packages 参数安装 PyInstaller...")
            subprocess.run([sys.executable, "-m", "pip", "install", "--break-system-packages", "pyinstaller"], check=True)
        
        print("依赖包安装成功！")
    except subprocess.CalledProcessError as e:
        print(f"依赖包安装失败: {e}")
        sys.exit(1)

def create_dist_directory():
    """创建分发目录"""
    dist_dir = Path("dist")
    dist_dir.mkdir(exist_ok=True)
    return dist_dir

def build_executable():
    """构建可执行文件"""
    print(f"正在为 {platform.system()} 平台构建可执行文件...")
    
    # 确定输出的可执行文件名
    if platform.system() == "Windows":
        exe_name = "wms-archive-tool.exe"
    elif platform.system() == "Darwin":  # macOS
        exe_name = "wms-archive-tool-mac"
    else:  # Linux及其他类Unix系统
        exe_name = "wms-archive-tool-linux"
    
    # PyInstaller命令
    cmd = [
        "python",
        "-m",
        "pyinstaller",
        "--onefile",  # 打包成单个可执行文件
        "--name", exe_name,  # 输出文件名
        "--add-data", "config.yaml:.",  # 包含配置文件
        "--console",  # 控制台应用程序
        "--clean",  # 清理临时文件
        "main.py"  # 主脚本
    ]
    
    try:
        result = subprocess.run(cmd, check=True)
        print(f"可执行文件构建成功: {exe_name}")
        return exe_name
    except subprocess.CalledProcessError as e:
        print(f"构建失败: {e}")
        return None

def organize_distribution(exe_name):
    """整理发布目录"""
    dist_dir = create_dist_directory()
    
    # 创建平台特定的子目录
    platform_name = platform.system().lower()
    platform_dir = dist_dir / platform_name
    platform_dir.mkdir(exist_ok=True)
    
    # 移动可执行文件到平台目录
    src_exe = Path("dist") / exe_name
    dst_exe = platform_dir / exe_name
    
    if src_exe.exists():
        shutil.move(str(src_exe), str(dst_exe))
        print(f"可执行文件已移动到: {dst_exe}")
    
    # 复制配置文件模板
    dst_config = platform_dir / "config.yaml.example"
    if Path("config.yaml").exists():
        shutil.copy("config.yaml", dst_config)
        print(f"配置文件模板已复制到: {dst_config}")
    
    # 创建README
    readme_content = f"""WMS 归档工具
================

这是一个用于自动化归档操作的工具，支持WMS系统的数据归档功能。

使用方法：
1. 修改 config.yaml 文件以配置数据库、Redis和其他设置
2. 运行可执行文件

注意：
- 在首次运行前，请确保配置文件中的数据库和Redis连接信息正确
- 如果在某些系统上遇到权限问题，可能需要给可执行文件添加执行权限：
  chmod +x {exe_name}

文件说明：
- {exe_name}: 主程序可执行文件
- config.yaml.example: 配置文件模板，请复制并修改为 config.yaml
"""
    
    readme_path = platform_dir / "README.txt"
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print(f"说明文档已创建: {readme_path}")

def main():
    print("WMS 归档工具 - 可执行文件构建器")
    print("=" * 50)
    print(f"当前平台: {platform.system()} {platform.machine()}")
    print(f"Python版本: {platform.python_version()}")
    
    # 安装依赖
    install_dependencies()
    
    # 构建可执行文件
    exe_name = build_executable()
    if not exe_name:
        print("构建失败，退出。")
        sys.exit(1)
    
    # 整理发布目录
    organize_distribution(exe_name)
    
    print("\n" + "=" * 50)
    print("构建完成！")
    print(f"可在 dist/{platform.system().lower()}/ 目录下找到可执行文件")
    print("请确保在运行前配置好 config.yaml 文件")

if __name__ == "__main__":
    main()