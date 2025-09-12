# IntraScribe

可完全本地化的，面向企业、学校与机关等内网环境的本地优先语音转写与协作平台：支持实时转写、说话人分离、高质量批处理、AI 总结与标题生成。默认提供浏览器 WebRTC 接入与 SSE 实时返回，也支持边缘设备/硬件作为前端，架构解耦、可替换任意采集与传输方案；数据全程留在内网，重视隐私与合规。

点击图片观看bilibili演示视频

[![Watch the video](doc/cover.png)](https://www.bilibili.com/video/BV14AbhzXEKc/)



---

# 功能特性

- 内网优先与隐私保护：可在内网/离线环境独立部署，数据不外发，满足隐私与合规要求。
- 团队与组织协作：账号体系、模板共享与编辑流程，适配企业/学校多用户协作。
- 硬件友好与可插拔前端：支持浏览器或边缘设备/硬件作为采集端，传输方案可替换。（硬件功能开发中。。。）
- 实时转写（ASR微服务，可替换）：浏览器或硬件端录音，低延迟推流到后端，webrtc实时返回转写片段；支持断字清理与时间戳格式化。
- 批处理高质量转写：会话结束后整合缓存音频，自动上传至 内部Supabase Storage，调用通用音频处理服务进行说话人分离与重转写，提升质量与结构化程度。
- 说话人分离与重命名：基于 pyannote.audio 的说话人分离，完成后在前端可双击标签重命名，并同步更新数据库中的转写 segments。
- AI 总结与标题生成：集成 LiteLLM，支持按模板生成结构化 Markdown 总结，并自动生成简洁标题；支持回退策略。
- 模板管理：支持用户模板与系统模板，设为默认、复制系统模板到用户侧、统计使用次数等。
- 录音会话管理：创建、完成、删除、重新转写、查看音频文件/转写/总结等；提供当前活跃会话状态与内存缓存状态查询。
- 数据存储与实时订阅：基于 Supabase（Postgres + Auth + Storage + Realtime）；前端通过频道订阅感知会话/转写的变化并刷新界面。
- 可编辑的转写：在前端对转写进行局部编辑并保存回后端，保留/合成时间戳与说话人信息。
- 注册登录等的管理界面。

---

# 适用场景

- 企业/事业单位内网部署的会议记录与知识沉淀
- 学校/研究机构的课堂与研讨记录（支持多人与说话人标注）
- 会议室/指挥中心/生产现场等对隐私与延迟敏感的场景
- 涉及敏感数据的法务、医疗、研发等不允许数据外发的团队

不适用：
- 已有飞书、钉钉等的协作工具，不在乎数据放到公网服务器的团队。
- 个人本地电脑使用。本地可使用更加轻量的方案。

---

# 技术栈

- 前端：Next.js (App Router) + React + TypeScript + Tailwind CSS
- 后端架构：微服务架构，基于 FastAPI（Python，使用 uv 管理依赖与运行）
- 实时音视频：LiveKit WebRTC 平台，支持高质量音频流处理
- 微服务组件：
  - **API Service** (8000)：主要业务逻辑、会话管理、AI 服务集成
  - **STT Service** (8001)：专用语音转文字服务，FunASR 模型（可 GPU 加速），模型可切换。
  - **Diarization Service** (8002)：专用说话人分离服务，pyannote.audio（可 GPU 加速）
  - **Agent Service**：轻量级实时音频处理代理，连接 LiveKit 与后端服务
- 消息与缓存：Redis（服务间通信、实时数据缓存）
- AI 能力：LiteLLM（集成到 API Service，支持多模型与回退策略）
- 存储与数据：Supabase（Auth、Postgres、Storage、Realtime）
- 容器化：Docker Compose 统一管理所有微服务
- 多媒体工具：FFmpeg（音频转码、分割、信息读取）
- nginx 反向代理

---

# 目录结构

```text
intrascribe/
  backend/                        # 微服务后端
    api_service/                  # 主 API 服务 (端口 8000)
      routers/                    # API 路由定义（会话、模板、音频等）
      services/                   # 业务服务层（AI 集成）
      repositories/               # 数据访问层
      core/                       # 核心组件（认证、数据库、Redis）
      schemas.py                  # API 数据模型
      main.py                     # 服务入口
      
    stt_service/                  # 语音转文字微服务 (端口 8001)
      main.py                     # FunASR 模型服务
      models.py                   # STT 数据模型
      
    diarization_service/          # 说话人分离微服务 (端口 8002)
      main.py                     # pyannote.audio 模型服务
      models.py                   # 分离数据模型
      
    agent_service/                # LiveKit 代理服务
      transcribe_agent/           # 实时转写代理
        agent.py                  # LiveKit 音频处理逻辑
        
    shared/                       # 共享组件
      config.py                   # 通用配置
      models.py                   # 共享数据模型
      logging.py                  # 日志配置
      
    docker-compose.yml            # 微服务编排
    ai_config.yaml                # AI 模型配置
    Makefile                      # 服务管理命令
    
  web/                            # 前端应用
    app/                          # Next.js 路由与 API 代理
    components/, hooks/, lib/     # UI、业务组件与客户端库
    
  supabase/                       # 数据库与认证
    database_schema.sql           # 数据库结构（表、RLS、视图、函数）
    migrations/                   # 数据库迁移文件
    
  README.md
```

---

# 快速开始

## 1. 安装依赖
此项目有大量的依赖需要安装：
- 需要nvidia GPU 电脑，并cuda驱动升级到最新版本。
- Node.js 18+
- Python 3.12 与 uv（python 包管理/运行器），参考：https://docs.astral.sh/uv/getting-started/installation/#installation-methods

  ```sh
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- ollama qwen3:8b。（可选其他模型，需要修改 backend/ai_config.yaml文件中的模型配置）
- FFmpeg

  ```
  sudo apt install ffmpeg
  ```
- supabase。参考链接： https://supabase.com/docs/guides/local-development ，进行安装。

  ```sh
  npm install supabase --save-dev
  ```
  安装过程中，npm 需要从github 下载二进制包，如果一直卡着不动，可手动下载和安装： https://github.com/supabase/cli/releases

- livekit。  https://github.com/livekit/livekit

  ```sh
  curl -sSL https://get.livekit.io | bash
  ```
- redis。 

  ```sh
  sudo apt install redis-server -y
  ```
  安装完成后检查是否在运行：

  ```sh
  sudo systemctl status redis-server
  ```
- nginx
- huggingface token

## 2. 克隆项目到本地
```bash
git clone https://github.com/weynechen/intrascribe.git
cd intrascribe
```
## 3. 配置环境
若此步不知道密钥从哪里来，可先运行第4步，根据脚本报错信息来填写。
```bash
cd backend
cp .env.example .env
```
修改.env中的密钥

同样的，配置前端的密钥
```bash
cd web
cp .env.local.example .env
```
修改密钥。

## 4. 运行脚本
直接运行脚本
```bash
./run.sh
```
此脚本会检查环境是否满足，提示安装，最后运行完成。

备注：
当前我仅在ubuntu 22.04上进行开发和测试，其余Linux平台理论上也支持。windows和mac暂不支持部署。


# 手动运行
如果执行上述脚本出问题，可按如下步骤逐步运行测试。

## 启动数据库
```bash
cd supabase
# 启动 Supabase 套件
sudo supabase start -x edge-runtime
```

Supabase 会下载一系列的 Docker 镜像，耗时较久，请耐心等待。

启动成功后，会显示连接信息：
```txt
         API URL: http://127.0.0.1:54321
     GraphQL URL: http://127.0.0.1:54321/graphql/v1
 S3 Storage URL: http://127.0.0.1:54321/storage/v1/s3
          DB URL: postgresql://postgres:postgres@127.0.0.1:54322/postgres
      Studio URL: http://127.0.0.1:54323
    Inbucket URL: http://127.0.0.1:54324
      JWT secret: super-secret-jwt-token-with-at-least-32-characters-long
        anon key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
service_role key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

启动成功后，执行数据库初始化
```bash
supabase db reset
```
访问 http://127.0.0.1:54323/project/default 查看数据是否存在。

注：reset操作只需操作一次即可，否则数据库会被清理掉。

如果需要重启supabase，运行
```bash
supabase stop
supabase start
```

## 启动livekit-server
运行 
```bash
livekit-server --dev
```

## 配置前后端的环境变量
在web页面下有 .env.local.example，将其拷贝为.env.local。同样backend页面下有 .env.example，将其拷贝为.env 。

随后，修改配置，将其中的 `your-key`和`your-token` 替换成真实的值。


## 启动服务

```bash
# 启动所有服务
./start-dev.sh

# 检查服务状态
./start-dev.sh status

# 停止所有服务
./start-dev.sh stop

# 停止特定服务
./start-dev.sh stop api      # 停止 API 服务
./start-dev.sh stop web      # 停止 Web 应用
./start-dev.sh stop stt      # 停止 STT 服务
./start-dev.sh stop diarization  # 停止说话人分离服务
./start-dev.sh stop redis    # 停止 Redis 服务

# 查看帮助
./start-dev.sh help
```

# 关于docker
此项目依赖巨多，docker部分暂不做开发。如有需要，backend 和web下有Dockerfile，可自行修改使用。其中backend为缩小image 尺寸，做了聚合的，没有为每个微服务写Dockerfile。



---
# 常见问题（FAQ）
- 实时转写没有输出？
  - 检查浏览器是否授权麦克风；
- 说话人分离不可用？
  - 检查 `HUGGINGFACE_TOKEN` 是否配置（初次运行服务的时候需要，后续可以断网使用）；pyannote 模型需要授权；若不可用系统会回退为单一说话人。
- 音频无法转码或处理失败？
  - 确认 FFmpeg 安装并在 PATH 中；查看后端日志中的命令与错误消息。
- 无法生成总结/标题？
  - 检查后端是否已正确配置模型与 API Key（LiteLLM）。
- CUDA警告？
  - 检查pytorch cuda版本与系统的NVIDIA 驱动版本

# License
MIT

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=weynechen/intrascribe&type=Date)](https://www.star-history.com/#weynechen/intrascribe&Date)

# TODO
## 手机APP
开发中...

## 硬件

- 增加麦克风阵列硬件接入
- 增加AI对话功能，使用RAG实时回答记录相关的问题

## 其他功能
TBD

