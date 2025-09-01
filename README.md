# IntraScribe

可完全本地化的，面向企业、学校与机关等内网环境的本地优先语音转写与协作平台：支持实时转写、说话人分离、高质量批处理、AI 总结与标题生成。默认提供浏览器 WebRTC 接入与 SSE 实时返回，也支持边缘设备/硬件作为前端，架构解耦、可替换任意采集与传输方案；数据全程留在本地，重视隐私与合规。

点击图片观看bilibili演示视频

[![Watch the video](doc/cover.png)](https://www.bilibili.com/video/BV14AbhzXEKc/)



---

# 功能特性

- 本地优先与隐私保护：可在内网/离线环境独立部署，数据不外发，满足隐私与合规要求。
- 团队与组织协作：账号体系、模板共享与编辑流程，适配企业/学校多用户协作。
- 硬件友好与可插拔前端：支持浏览器或边缘设备/硬件作为采集端，传输方案可替换。
- 实时转写（本地 ASR）：浏览器或硬件端录音，低延迟推流到后端，SSE 实时返回转写片段；支持断字清理与时间戳格式化。
- 批处理高质量转写：会话结束后整合缓存音频，自动上传至 Supabase Storage，调用通用音频处理服务进行说话人分离与重转写，提升质量与结构化程度。
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

---

# 技术栈

- 前端：Next.js (App Router) + React + TypeScript + Tailwind CSS
- 后端架构：微服务架构，基于 FastAPI（Python，使用 uv 管理依赖与运行）
- 实时音视频：LiveKit WebRTC 平台，支持高质量音频流处理
- 微服务组件：
  - **API Service** (8000)：主要业务逻辑、会话管理、AI 服务集成
  - **STT Service** (8001)：专用语音转文字服务，FunASR 模型（可 GPU 加速）
  - **Diarization Service** (8002)：专用说话人分离服务，pyannote.audio（可 GPU 加速）
  - **Agent Service**：轻量级实时音频处理代理，连接 LiveKit 与后端服务
- 消息与缓存：Redis（服务间通信、实时数据缓存）
- AI 能力：LiteLLM（集成到 API Service，支持多模型与回退策略）
- 存储与数据：Supabase（Auth、Postgres、Storage、Realtime）
- 容器化：Docker Compose 统一管理所有微服务
- 多媒体工具：FFmpeg（音频转码、分割、信息读取）

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
当前我仅在ubuntu 22.04上进行开发和测试，其余Linux平台理论上也支持。但windows和mac可能异常较多。
## 前置条件

- nvidia GPU 电脑，cuda驱动升级到最新版本。（理论上也支持纯CPU，但我没有测试过）
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

- 访问huggingface，获取自己的token。

## 克隆项目到本地
随后，将本项目clone到本地。

```bash
git clone https://github.com/weynechen/intrascribe.git
cd intrascribe
```


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


## 使用一键启动脚本

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

## 使用docker（未测试）

进入后端目录并启动所有微服务：
```sh
docker-compose up
```


启动成功后，服务端点如下：
- **API 服务**：http://localhost:8000 （主要业务逻辑）
- **STT 服务**：http://localhost:8001 （语音转文字）
- **说话人分离服务**：http://localhost:8002 （说话人分离）
- **Web 应用**：http://localhost:3000 （前端界面）



备注：
1. 目前我只在 ubuntu22.04 进行过安装测试。
2. 如默认端口更改，需要修改 `next.config.js` 中的代理。
3. 在局域网内使用，最好搭配 nginx 做https代理（没有在仓库中，需自行搭建）。本项目提供next.js代理方式，操作如下：


##  局域网访问
上述启动启动是http的服务，涉及麦克风权限，从其他PC上访问时，浏览器会拒绝访问。因此需要配置为https。当前项目支持next.js自身的代理服务。（生产需要自行替换为nginx作为代理）

### 安装mkcert

``` bash
cd web

# 1. 安装依赖
sudo apt update
sudo apt install libnss3-tools

# 2. 下载mkcert
wget https://github.com/FiloSottile/mkcert/releases/download/v1.4.4/mkcert-v1.4.4-linux-amd64

# 3. 添加执行权限并移动到系统路径
chmod +x mkcert-v1.4.4-linux-amd64
sudo mv mkcert-v1.4.4-linux-amd64 /usr/local/bin/mkcert

# 4. 验证安装
mkcert -version
```

### 创建本地CA和证书

```bash
# 1. 安装本地CA到系统信任存储
mkcert -install

# 2. 为localhost生成证书
mkcert localhost 127.0.0.1 ::1
```
执行后会生成两个文件：
localhost+2.pem (证书文件)
localhost+2-key.pem (私钥文件)

随后运行

```bash
npm run dev_https
```
随后可在局域网内通过 https://you_machine_ip:3000 访问

如果是一键脚本启动的，可将`npm run dev` 替换为上述。


# 运行流程（端到端）
- **登录认证**：使用 Supabase Auth 进行用户登录验证，获取 JWT Token。
- **创建会话**：
  - 前端调用 API 服务 `POST /api/v1/sessions` 创建新的录音会话。
  - 同时调用 `POST /api/v1/livekit/connection-details` 获取 LiveKit 连接信息（房间名、参与者令牌等）。
- **开始实时录音**：
  - 前端使用 LiveKit WebRTC SDK 连接到 LiveKit 房间，开始音频流传输。
  - LiveKit 代理服务自动加入房间，接收音频流并调用 STT 微服务进行实时转写。
  - 转写结果通过 Redis 缓存，前端通过 Supabase Realtime 订阅获得实时更新。
- **停止录音与后处理**：
  - 前端断开 LiveKit 连接，调用 `POST /api/v1/sessions/{session_id}/finalize` 完成会话。
  - API 服务将音频数据上传到 Supabase Storage，并调用说话人分离微服务。
  - 执行高质量批处理转写，会话状态更新为 `processing` → `completed`。
- **AI 增强功能**：
  - 生成总结：调用 `POST /api/v1/sessions/{id}/summarize`（可指定模板）。
  - 生成标题：调用 `POST /api/v1/generate-title` 基于转写或总结内容。
- **编辑与管理**：
  - 转写编辑：`PUT /api/v1/transcriptions/{id}` 支持局部编辑并保留时间戳。
  - 说话人重命名：`POST /api/v1/sessions/{id}/rename-speaker` 批量更新说话人标签。

---

# API 服务概览

## 主 API 服务 (端口 8000)
**核心业务逻辑与集成服务**

- **健康检查与信息**
  - `GET /health` - 服务健康状态
  - `GET /info` - 服务信息与版本

- **会话管理**
  - `POST /api/v1/sessions` - 创建录音会话
  - `GET /api/v1/sessions/{id}` - 获取会话详情（含音频/转写/总结）
  - `POST /api/v1/sessions/{id}/finalize` - 完成会话（触发批处理）
  - `POST /api/v1/sessions/{id}/retranscribe` - 重新转写
  - `DELETE /api/v1/sessions/{id}` - 删除会话

- **LiveKit 集成**
  - `POST /api/v1/livekit/connection-details` - 获取 LiveKit 连接信息
  - `GET /api/v1/livekit/rooms` - 获取活跃房间列表

- **AI 服务（集成）**
  - `POST /api/v1/summarize` - 生成文本总结
  - `POST /api/v1/generate-title` - 生成标题
  - `POST /api/v1/sessions/{id}/summarize` - 为会话生成总结

- **转写管理**
  - `POST /api/v1/transcriptions` - 保存转写结果
  - `PUT /api/v1/transcriptions/{id}` - 更新转写内容
  - `POST /api/v1/sessions/{id}/rename-speaker` - 重命名说话人

- **实时数据**
  - `GET /api/v1/realtime/sessions/{id}/transcription` - 获取实时转写数据
  - `GET /api/v1/realtime/sessions/{id}/status` - 获取会话实时状态

## STT 微服务 (端口 8001)
**专用语音转文字服务**

- `GET /health` - 服务健康检查
- `GET /info` - 模型信息与配置
- `POST /transcribe` - 音频转写（同步）
- `POST /transcribe-batch` - 批量音频处理

## 说话人分离微服务 (端口 8002)
**专用说话人分离服务**

- `GET /health` - 服务健康检查  
- `GET /info` - 模型信息与配置
- `POST /diarize` - 音频说话人分离
- `POST /diarize-file` - 文件上传分离

**说明**：
- 所有 API 服务端点需要携带 Supabase JWT Token 认证
- 微服务间通过 HTTP 调用进行通信（localhost 环境下延迟 < 5ms）
- Redis 用于缓存实时数据和服务间状态同步

---

# 开发与部署要点

## 微服务架构优势
- **服务隔离**：各微服务独立部署、扩缩容，故障隔离性强
- **资源优化**：STT 和说话人分离服务预加载模型，避免重复初始化
- **技术栈灵活**：每个服务可使用最适合的技术栈和优化策略
- **开发效率**：团队可并行开发不同服务，降低耦合度

## 容器化部署
- **Docker Compose**：统一管理所有微服务的生命周期
- **GPU 支持**：STT 和说话人分离服务可配置 GPU 加速，显著提升性能
- **资源限制**：每个服务可独立配置 CPU、内存资源限制
- **健康检查**：内置健康检查机制，确保服务可用性

## 性能优化
- **模型预加载**：FunASR 和 pyannote.audio 模型在服务启动时预加载，避免延迟
- **Redis 缓存**：实时数据通过 Redis 缓存，提升响应速度
- **异步处理**：批处理任务异步执行，不阻塞实时功能
- **连接复用**：微服务间 HTTP 连接复用，减少延迟

## 配置管理
- **环境变量**：通过 `.env` 文件统一管理配置，支持不同环境
- **AI 配置**：`backend/ai_config.yaml` 配置多模型、超时与回退策略
- **LiveKit 集成**：支持 LiveKit Cloud 或自建服务器
- **FFmpeg 依赖**：容器内预装 FFmpeg，支持音频转码与切分

## 开发工作流
- **服务管理**：使用脚本统一管理服务启动、停止、日志查看
- **热重载**：开发模式下支持代码变更自动重启服务
- **日志聚合**：所有服务日志统一收集，便于调试
- **健康监控**：实时监控各服务健康状态

---
# 常见问题（FAQ）
- 实时转写没有输出？
  - 检查浏览器是否授权麦克风；
- 说话人分离不可用？
  - 检查 `HUGGINGFACE_TOKEN` 是否配置；pyannote 模型需要授权；若不可用系统会回退为单一说话人。
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

## 硬件

- 增加麦克风阵列硬件接入
- 增加AI对话功能，使用RAG实时回答记录相关的问题

## 其他功能
TBD

