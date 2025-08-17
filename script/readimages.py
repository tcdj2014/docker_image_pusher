import subprocess
import os
import re
import argparse
import logging
from typing import List, Dict, Set, Tuple
from multiprocessing import Pool, cpu_count, current_process

# 配置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(processName)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


# Docker登录到阿里云镜像仓库
def docker_login():
    try:
        logger.info("开始Docker登录...")
        subprocess.run(
            ['docker', 'login', '-u', username, '-p', password, registry],
            check=True
        )
        logger.info("Docker登录成功")
    except subprocess.CalledProcessError as e:
        logger.error(f"Docker登录失败: {e}")
        raise
    except KeyError as e:
        logger.error(f"环境变量缺失: {e}")
        raise


# 数据预处理，检查镜像名称是否重复
def preprocess_images(image_lines: List[str]) -> Set[str]:
    duplicate_images = set()  # 存储重复的镜像名
    temp_map = {}  # 临时映射：镜像名 -> 命名空间

    for line in image_lines:
        # 提取镜像完整名称（去除@sha256等部分）
        parts = line.split()
        image = parts[-1].split('@')[0]

        # 分割镜像名标签（如nginx:1.25.3）
        image_name_tag = image.split('/')[-1]

        # 解析命名空间
        segments = image.split('/')
        if len(segments) == 3:
            namespace = segments[1]
        elif len(segments) == 2:
            namespace = segments[0]
        else:
            namespace = ''
        namespace = f"{namespace}_"  # 添加下划线以处理空值

        # 提取纯镜像名（如nginx）
        image_name = image_name_tag.split(':')[0]

        # 检查重复镜像名
        if image_name in temp_map:
            if temp_map[image_name] != namespace:
                duplicate_images.add(image_name)
        else:
            temp_map[image_name] = namespace

    return duplicate_images


# 处理单个镜像
def process_single_image(args: Tuple[str, Set[str], str, str, str]):
    line, duplicate_images, aliyun_registry, aliyun_namespace, platform_prefix = args
    try:
        line = line.strip()
        if not line or re.match(r'^\s*#', line):
            return

        logger.info(f"处理镜像行: {line}")

        platform = None
        platform_match = re.search(r'--platform[= ](\S+)', line)
        if platform_match:
            platform = platform_match.group(1)
        logger.debug(f"检测到平台参数: {platform}")

        parts = line.split()
        image = parts[-1].split('@')[0]
        image_name_tag = image.split('/')[-1]
        segments = image.split('/')
        if len(segments) == 3:
            namespace = segments[1]
        elif len(segments) == 2:
            namespace = segments[0]
        else:
            namespace = ''
        namespace = f"{namespace}_"

        image_name = image_name_tag.split(':')[0]
        name_space_prefix = ''
        if image_name in duplicate_images and namespace.strip('_'):
            name_space_prefix = namespace

        new_image = f"{aliyun_registry}/{aliyun_namespace}/{platform_prefix}{name_space_prefix}{image_name_tag}"

        logger.info(f"拉取镜像: {image}")
        pull_command = ['docker', 'pull']
        if platform:
            pull_command.extend(['--platform', platform])
        pull_command.append(image)
        subprocess.run(pull_command, check=True)

        logger.info(f"重标签镜像: {new_image}")
        subprocess.run(['docker', 'tag', image, new_image], check=True)

        logger.info(f"推送镜像: {new_image}")
        subprocess.run(['docker', 'push', new_image], check=True)

        logger.info(f"清理镜像: {image}")
        subprocess.run(['docker', 'rmi', '-f', image], check=True)
        logger.info(f"清理镜像: {new_image}")
        subprocess.run(['docker', 'rmi', '-f', new_image], check=True)

        logger.debug("检查磁盘空间...")
        subprocess.run(['df', '-hT'])

    except subprocess.CalledProcessError as e:
        print(f"命令执行失败：{e}")
        raise
    except Exception as e:
        print(f"处理镜像时发生错误：{e}")
        raise


# 处理镜像：拉取、重标签、推送、清理
def process_images(image_lines: List[str], duplicate_images: Set[str]):
    aliyun_registry = os.getenv('ALIYUN_REGISTRY')
    aliyun_namespace = os.getenv('ALIYUN_NAME_SPACE')

    if not aliyun_registry or not aliyun_namespace:
        raise ValueError("环境变量 ALIYUN_REGISTRY 或 ALIYUN_NAME_SPACE 未设置")

    pool_size = cpu_count() * 2
    logger.info(f"使用 {pool_size} 个并发进程处理镜像")

    args_list = [(line, duplicate_images, aliyun_registry, aliyun_namespace, '') for line in image_lines]

    with Pool(pool_size) as pool:
        logger.info("开始并行处理镜像")
        pool.map(process_single_image, args_list)
        logger.info("完成镜像处理")


# 解析命令行参数
def parse_arguments():
    parser = argparse.ArgumentParser(description='Docker镜像拉取推送工具')
    parser.add_argument('--image-file', default='images.txt', help='镜像列表文件路径，默认为images.txt')
    return parser.parse_args()


# 读取镜像文件行
def read_image_lines(file_path: str) -> List[str]:
    """读取镜像列表文件，返回非空且非注释的行"""
    image_lines = []
    try:
        logger.info(f"开始读取镜像文件: {file_path}")
        with open(file_path, 'r') as file:
            for line_number, line in enumerate(file, 1):
                line = line.strip()
                if not line or re.match(r'^\s*#', line):
                    continue
                image_lines.append(line)
        logger.info(f"成功读取 {len(image_lines)} 行有效镜像信息")
        return image_lines
    except FileNotFoundError:
        logger.error(f"错误: 找不到文件 {file_path}")
        exit(1)
    except Exception as e:
        logger.error(f"读取文件 {file_path} 时出错: {e}")
        exit(1)


# 主函数
def main():
    try:
        logger.info("开始执行镜像处理流程")
        args = parse_arguments()
#         docker_login()
        image_lines = read_image_lines(args.image_file)
        duplicates = preprocess_images(image_lines)
        process_images(image_lines, duplicates)
        logger.info("镜像处理流程完成")
    except Exception as e:
        logger.error(f"脚本执行失败: {e}")
        exit(1)


if __name__ == "__main__":
    main()