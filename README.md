# Docker Images Pusher

使用Github Action将国外的Docker镜像转存到阿里云私有仓库，供国内服务器使用，免费易用<br>
- 支持DockerHub, gcr.io, k8s.io, ghcr.io等任意仓库<br>
- 支持最大40GB的大型镜像<br>
- 使用阿里云的官方线路，速度快<br>

视频教程：https://www.bilibili.com/video/BV1Zn4y19743/

作者：**[技术爬爬虾](https://github.com/tech-shrimp/me)**<br>
B站，抖音，Youtube全网同名，转载请注明作者<br>

## 使用方式
https://github.com/tech-shrimp/docker_image_pusher/blob/main/README.md

### 编译tengine-base
```shell
tag=v0.3
git tag -a $tag -m "调整dockerfile" \
&& git push origin $tag
```
