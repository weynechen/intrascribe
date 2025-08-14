### IntraScribe

面向企业、学校与机关等内网环境的本地优先语音转写与协作平台：支持实时转写、说话人分离、高质量批处理、AI 总结与标题生成。默认提供浏览器 WebRTC 接入与 SSE 实时返回，也支持边缘设备/硬件作为前端，架构解耦、可替换任意采集与传输方案；数据全程留在本地，重视隐私与合规。

点击图片观看bilibili演示视频

[![Watch the video](doc/cover.png)](https://www.bilibili.com/video/BV14AbhzXEKc/)



---

### 功能特性

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

### 适用场景

- 企业/事业单位内网部署的会议记录与知识沉淀
- 学校/研究机构的课堂与研讨记录（支持多人与说话人标注）
- 会议室/指挥中心/生产现场等对隐私与延迟敏感的场景
- 涉及敏感数据的法务、医疗、研发等不允许数据外发的团队

---

### 技术栈

- 前端：Next.js (App Router) + React + TypeScript + Tailwind CSS
- 后端：FastAPI（Python，使用 uv 管理依赖与运行）
- 实时：默认 WebRTC（浏览器推流）+ SSE（服务端事件流返回转写输出）；架构解耦，可替换其他采集/传输方案
- ASR：FunASR（本地模型，可 GPU 加速），适配器 `LocalFunASR`
- 说话人分离：pyannote.audio（需 HuggingFace token登录下载，可 GPU 加速）
- AI 总结/标题：LiteLLM（可配置多模型与回退策略）
- 存储与数据：Supabase（Auth、Postgres、Storage、Realtime）
- 多媒体工具：FFmpeg（音频转码、分割、信息读取）

---

### 目录结构

```text
intrascribe/
  backend/
    app/
      api.py                       # API 路由与端点定义（/api/v1/...）
      services.py                  # 会话、转写、AI、缓存等业务服务
      stt_adapter.py               # FunASR 本地模型适配
      speaker_diarization.py       # 说话人分离服务（pyannote）
      batch_transcription.py       # 批量转写任务封装
      audio_processing_service.py  # 通用音频处理（转码、分段等）
      audio_converter.py           # FFmpeg 封装
      schemas.py, models.py        # DTO 与领域模型
      clients.py, repositories.py  # 外部服务与数据访问
    main_v1.py                     # 实时音频流入口（默认 WebRTC 接入实现）
    config.yaml                    # AI 总结与 STT 相关配置
    pyproject.toml                 # 后端依赖
  web/
    app/                           # 路由与 API 代理（/app/api/...）
    components/, hooks/, lib/      # UI、业务组件与 Supabase 客户端
  supabase/
    database_schema.sql            # 数据库结构（表、RLS、视图、函数）
    migrations/20250814090000_all_in_one.sql  # 单文件迁移
  README.md
```

---

### 快速开始

#### 1) 前置条件
- Node.js 18+
- Python 3.10+ 与 uv（python 包管理/运行器）
- FFmpeg
- ollama qwen3:8b。（可选。如果不用这个模型，需要在后端的config.yaml中修改）

```bash
sudo apt install ffmpeg
```
- supabase。参考链接： https://supabase.com/docs/guides/local-development 。进行安装。

#### 2) clone项目到本地
```
git clone 
```

#### 3) 启动数据库

```bash
cd supabase
# 启动套件
supabase start
```
启动成功后，会出现信息：
```txt
         API URL: http://127.0.0.1:54321
     GraphQL URL: http://127.0.0.1:54321/graphql/v1
  S3 Storage URL: http://127.0.0.1:54321/storage/v1/s3
          DB URL: postgresql://postgres:postgres@127.0.0.1:54322/postgres
      Studio URL: http://127.0.0.1:54323
    Inbucket URL: http://127.0.0.1:54324
      JWT secret: super-secret-jwt-token-with-at-least-32-characters-long
        anon key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0
service_role key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU
   S3 Access Key: 625729a08b95bf1b7ff351a663f3a23c
   S3 Secret Key: 850181e4652dd023b7a98c58ae0d2d34bd487ee0cc3254aed6eda37307425907
       S3 Region: local
```
如果过程中出现502错误，可以选择部分启动
```bash
sudo supabase start -x edge-runtime
```
启动成功后，执行数据库初始化
```bash
# 初始化数据库
supabase db reset
```

#### 2) 配置环境变量（请自行创建/修改文件）
- 前端 `web/.env.local`（示例内容）：
```bash
NEXT_PUBLIC_SUPABASE_URL=你的Supabase项目URL
NEXT_PUBLIC_SUPABASE_ANON_KEY=你的Supabase匿名Key
# 后端 FastAPI 的对外地址（前端API代理会调用它）
BACKEND_URL=http://localhost:8000
```
- 后端 `backend/.env`（示例内容）：
```bash
SUPABASE_URL=你的Supabase项目URL

SUPABASE_ANON_KEY = 你的Supabase匿名Key
SUPABASE_SERVICE_ROLE_KEY = 你的Supabase ROLE Key
HUGGINGFACE_TOKEN=你的huggingface token
PYANNOTE_MODEL=pyannote/speaker-diarization-3.1
```
提示：请根据你的实际部署地址与密钥填写，以上仅为示例。请不要把密钥提交到仓库。

#### 4) 启动后端（FastAPI）
```bash
cd backend
uv sync
uv run main_v1.py
```
默认监听 `http://localhost:8000`。

#### 5) 启动前端（Next.js）
```bash
cd web
npm install
npm run dev
```
默认访问 `http://localhost:3000`。

---

### 运行流程（端到端）
- 登录（Supabase Auth）后进入首页。
- 点击“开始录音”：
  - 前端调用后端 `POST /api/v1/sessions` 创建会话，得到 `session_id`。
  - 默认实现：浏览器用 `session_id` 作为 `webrtc_id` 调用 `/webrtc/offer` 建立 WebRTC 音频通道（也可替换为其他传输方案）。
  - 前端通过 SSE 订阅 `/transcript?webrtc_id=...&token=...`，实时接收转写片段。
- 点击“停止录音”：
  - 断开 WebRTC，调用 `POST /api/v1/sessions/{session_id}/finalize`。
  - 后端将缓存的音频整合、转码、上传到 Storage，并异步执行说话人分离与高质量批处理转写；会话状态变为 `processing`，完成后切回 `completed`。
- 生成总结/标题：在会话详情中触发一次 `POST /api/v1/sessions/{id}/summarize`（可带模板），前端再调用生成标题接口。
- 编辑与重命名：在转写视图中可局部编辑并保存（`PUT /api/v1/transcriptions/{id}`）；可以重命名说话人（`POST /api/v1/sessions/{id}/rename-speaker`）。

---

### 后端 API 概览（/api/v1）

- 健康检查
  - `GET /health`
- 会话管理
  - `POST /sessions` 创建录音会话
  - `GET /sessions/{id}` 获取详情（含音频/转写/总结）
  - `POST /sessions/{id}/finalize` 完成会话（触发批处理）
  - `POST /sessions/{id}/retranscribe` 重新转写
  - `DELETE /sessions/{id}` 删除会话
  - `PUT /sessions/{id}/template` 更新会话模板选择
  - `POST /sessions/{id}/summarize?force=true&template_id=...` 生成并保存 AI 总结
  - `POST /sessions/{id}/rename-speaker` 重命名说话人
  - `GET /sessions/{id}/audio_files` / `GET /sessions/{id}/audio_files/{file_id}`
- 转写
  - `POST /transcriptions` 保存转写
  - `PUT /transcriptions/{id}` 基于 segments 更新转写
- AI
  - `POST /summarize` 基于文本直接生成总结
  - `POST /generate-title` 基于文本/总结生成标题
- 音频与缓存
  - `POST /batch-transcription` 上传单个音频文件并完成整套处理
  - `GET /audio/session/current` 当前活跃会话
  - `GET /audio/cache/status` 缓存状态
- 模板
  - `POST /templates` / `GET /templates` / `GET /templates/{id}` / `PUT /templates/{id}` / `DELETE /templates/{id}`
  - `GET /templates/system` / `POST /templates/system/{system_template_id}/copy`

说明：大多数端点需要携带 Supabase 的 Bearer Token（前端已集成）。

---

### 开发与部署要点
- 需要安装 FFmpeg，后端会调用其命令行进行转码与切分。
- FunASR 与 pyannote.audio 在 GPU 上可显著加速；若无 GPU 也可在 CPU 上运行（速度会降低）。
- LiteLLM 可在 `backend/config.yaml` 配置多模型、超时与回退策略。
- Web 前端通过 `/app/api/*` 作为轻量代理将请求转发到后端 `BACKEND_URL`，避免跨域与密钥暴露。
- 数据库与迁移脚本在 `supabase/` 目录下进行版本化管理，推荐使用仓库内的结构脚本初始化，保持与代码一致。

---

### 常见问题（FAQ）
- 实时转写没有输出？
  - 检查浏览器是否授权麦克风；确认后端 `http://localhost:8000/transcript` 可达；控制台中是否有 SSE 连接日志。
- 说话人分离不可用？
  - 检查 `HUGGINGFACE_TOKEN` 是否配置；pyannote 模型需要授权；若不可用系统会回退为单一说话人。
- 音频无法转码或处理失败？
  - 确认 FFmpeg 安装并在 PATH 中；查看后端日志中的命令与错误消息。
- 无法生成总结/标题？
  - 检查后端是否已正确配置模型与 API Key（LiteLLM）。

---

### License
MIT

### TODO
展成会议助手功能

- 增加硬件接入
- 增加AI对话
