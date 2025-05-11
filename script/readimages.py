import subprocess
import os
import re


# Docker登录到阿里云镜像仓库
def docker_login():
    try:
        # 从环境变量获取用户名、密码和注册表地址
        username = os.getenv('ALIYUN_REGISTRY_USER')
        password = os.getenv('ALIYUN_REGISTRY_PASSWORD')
        registry = os.getenv('ALIYUN_REGISTRY')

        # 构建docker login命令并执行
        subprocess.run(
            ['docker', 'login', '-u', username, '-p', password, registry],
            check=True
        )
        print("Docker登录成功。")
    except subprocess.CalledProcessError as e:
        print(f"Docker登录失败：{e}")
        raise
    except KeyError as e:
        print(f"环境变量缺失：{e}")
        raise


# 数据预处理，检查镜像名称是否重复
def preprocess_images():
    duplicate_images = set()  # 存储重复的镜像名
    temp_map = {}  # 临时映射：镜像名 -> 命名空间

    with open('images.txt', 'r') as file:
        for line in file:
            line = line.strip()
            # 跳过空行和注释行
            if not line or re.match(r'^\s*#', line):
                continue

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


# 处理镜像：拉取、重标签、推送、清理
def process_images(duplicate_images):
    aliyun_registry = os.getenv('ALIYUN_REGISTRY')
    aliyun_namespace = os.getenv('ALIYUN_NAME_SPACE')

    with open('images.txt', 'r') as file:
        for line in file:
            line = line.strip()
            # 跳过空行和注释行
            if not line or re.match(r'^\s*#', line):
                continue

            # 提取平台参数（如linux/amd64）
            platform = None
            platform_match = re.search(r'--platform[= ](\S+)', line)
            if platform_match:
                platform = platform_match.group(1)
            platform_prefix = f"{platform.replace('/', '_')}_" if platform else ''

            # 解析镜像名称
            parts = line.split()
            image = parts[-1].split('@')[0]

            # 分割镜像名标签和命名空间
            image_name_tag = image.split('/')[-1]
            segments = image.split('/')
            if len(segments) == 3:
                namespace = segments[1]
            elif len(segments) == 2:
                namespace = segments[0]
            else:
                namespace = ''
            namespace = f"{namespace}_"  # 与原逻辑一致添加下划线

            # 提取纯镜像名
            image_name = image_name_tag.split(':')[0]

            # 构造命名空间前缀（如果重复且命名空间非空）
            name_space_prefix = ''
            if image_name in duplicate_images and namespace.strip('_'):
                name_space_prefix = namespace

            # 构造新镜像名
            new_image = f"{aliyun_registry}/{aliyun_namespace}/{platform_prefix}{name_space_prefix}{image_name_tag}"
            print("新镜像名:" + new_image)

            # 执行docker命令
            try:
                # 拉取镜像
                subprocess.run(['docker', 'pull', parts[-1]], check=True)

                # 重标签镜像
                subprocess.run(['docker', 'tag', image, new_image], check=True)

                # 推送镜像
                subprocess.run(['docker', 'push', new_image], check=True)

                # 清理原镜像和新标签
                subprocess.run(['docker', 'rmi', image], check=True)
                subprocess.run(['docker', 'rmi', new_image], check=True)

                # 打印磁盘空间信息
                print("开始清理磁盘空间...")
                subprocess.run(['df', '-hT'])
                print("磁盘空间清理完毕。")
                subprocess.run(['df', '-hT'])

            except subprocess.CalledProcessError as e:
                print(f"命令执行失败：{e}")
                raise


# 主函数
def main():
    try:
        docker_login()  # 步骤1：登录Docker
        duplicates = preprocess_images()  # 步骤2：预处理镜像
        process_images(duplicates)  # 步骤3：处理镜像
    except Exception as e:
        print(f"脚本执行失败：{e}")
        exit(1)


if __name__ == "__main__":
    main()
