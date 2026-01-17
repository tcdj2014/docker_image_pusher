#!/usr/bin/env python3
"""
多平台可执行文件编译脚本
此脚本将使用PyInstaller将main.py编译为多个平台的可执行文件
"""

import os
import platform
import subprocess
import sys
from pathlib import Path

def install_pyinstaller():
    """安装PyInstaller"""
    print("正在安装PyInstaller...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        print("PyInstaller安装成功！")
    except subprocess.CalledProcessError as e:
        print(f"PyInstaller安装失败: {e}")
        sys.exit(1)

def create_spec_file():
    """创建PyInstaller spec文件以进行高级配置"""
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-
import sys
import os

# 确定运行的操作系统
platform_system = sys.platform

# 根据操作系统设置可执行文件名称
if platform_system.startswith('win'):
    exe_name = 'archive_tool.exe'
elif platform_system.startswith('darwin'):  # macOS
    exe_name = 'archive_tool_mac'
else:  # Linux及其他类Unix系统
    exe_name = 'archive_tool_linux'

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.yaml', '.'),  # 包含配置文件
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
'''
    with open('archive_tool.spec', 'w', encoding='utf-8') as f:
        f.write(spec_content)
    print("Spec文件创建成功: archive_tool.spec")

def build_current_platform():
    """为当前平台构建可执行文件"""
    current_platform = platform.system().lower()
    print(f"正在为当前平台 {current_platform} 构建可执行文件...")
    
    try:
        # 使用spec文件构建
        subprocess.run(['pyinstaller', 'archive_tool.spec', '--clean'], check=True)
        print(f"当前平台({current_platform})的可执行文件构建成功！")
        
        # 移动到特定平台目录
        dist_path = Path('dist')
        exe_files = list(dist_path.glob('*archive_tool*'))
        
        platform_dir = Path(f'dist/{current_platform}')
        platform_dir.mkdir(exist_ok=True)
        
        for exe_file in exe_files:
            target_path = platform_dir / exe_file.name
            exe_file.rename(target_path)
            print(f"已将可执行文件移动到: {target_path}")
            
        # 创建包含配置文件的目录
        (platform_dir / 'config.yaml').parent.mkdir(parents=True, exist_ok=True)
        if Path('config.yaml').exists():
            import shutil
            shutil.copy('config.yaml', platform_dir)
            print(f"已复制配置文件到: {platform_dir}/config.yaml")
        
    except subprocess.CalledProcessError as e:
        print(f"构建失败: {e}")
        return False
    
    return True

def build_cross_platform():
    """尝试为其他平台构建（需要Docker）"""
    platforms = {
        'linux': 'python:3.9-slim',
        'windows': 'python:3.9-windowsservercore',
        'macos': 'ghcr.io/pyo3/maturin:latest'  # 仅作示例，实际上需要特殊的macOS环境
    }
    
    print("跨平台构建需要Docker支持，以下是构建命令参考：")
    
    # Linux
    print("\\nLinux构建命令 (在Linux环境下):")
    print("docker run --rm -v $(pwd):/app -w /app python:3.9-slim bash -c \\")
    print("  \"pip install -r requirements.txt && pip install pyinstaller && \\")
    print("  pyinstaller main.py --onefile --add-data 'config.yaml:.'\"")
    
    # Windows
    print("\\nWindows构建命令 (在Windows环境下):")
    print("pip install -r requirements.txt")
    print("pip install pyinstaller")
    print("pyinstaller main.py --onefile --add-data \"config.yaml;.\"")
    
    # 注意：真正的跨平台构建需要特定的交叉编译环境，这很复杂
    print("\\n注意：真正的跨平台构建需要在目标平台上运行，或者使用Docker等容器技术。")
    print("目前，PyInstaller不支持真正的交叉编译。您需要在每个目标平台上运行构建命令。")

def main():
    print("WMS归档工具 - 多平台可执行文件编译脚本")
    print("="*50)
    
    # 检查是否已安装PyInstaller
    try:
        import PyInstaller
        print("PyInstaller已安装")
    except ImportError:
        install_pyinstaller()
    
    # 创建spec文件
    create_spec_file()
    
    # 为当前平台构建
    if build_current_platform():
        print("\\n当前平台构建完成！")
        print(f"可执行文件位置: dist/{platform.system().lower()}/")
        
        # 显示构建的文件
        platform_dir = Path(f'dist/{platform.system().lower()}')
        if platform_dir.exists():
            for item in platform_dir.iterdir():
                if item.is_file():
                    size_mb = item.stat().st_size / (1024 * 1024)
                    print(f"  - {item.name} ({size_mb:.2f} MB)")
    
    # 显示跨平台构建说明
    print("\\n" + "="*50)
    build_cross_platform()
    
    print("\\n构建完成！")

if __name__ == "__main__":
    main()