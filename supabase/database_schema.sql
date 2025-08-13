-- ================================================================
-- intrascribe 音频转录系统数据库结构
-- 支持用户管理、音频文件存储、转录内容和AI总结功能
-- ================================================================

-- 启用必要的扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ================================================================
-- 1. 用户表 (users)
-- ================================================================
CREATE TABLE users (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name VARCHAR(200),
    avatar_url TEXT,
    phone VARCHAR(20),
    is_active BOOLEAN DEFAULT true,
    is_verified BOOLEAN DEFAULT false,
    email_verified_at TIMESTAMP WITH TIME ZONE,
    last_login_at TIMESTAMP WITH TIME ZONE,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 用户表索引
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_is_active ON users(is_active);

-- ================================================================
-- 2. 录音会话表 (recording_sessions)
-- ================================================================
CREATE TABLE recording_sessions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL DEFAULT '未命名录音',
    description TEXT,
    
    -- 录音基本信息
    webrtc_id VARCHAR(100), -- WebRTC会话ID
    status VARCHAR(50) DEFAULT 'draft', -- draft, recording, completed, failed
    
    -- 时间信息
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER DEFAULT 0,
    
    -- 元数据
    metadata JSONB DEFAULT '{}', -- 额外的元数据信息
    tags TEXT[], -- 标签数组
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 录音会话表索引
CREATE INDEX idx_recording_sessions_user_id ON recording_sessions(user_id);
CREATE INDEX idx_recording_sessions_status ON recording_sessions(status);
CREATE INDEX idx_recording_sessions_created_at ON recording_sessions(created_at DESC);
CREATE INDEX idx_recording_sessions_webrtc_id ON recording_sessions(webrtc_id);

-- ================================================================
-- 3. 音频文件表 (audio_files)
-- ================================================================
CREATE TABLE audio_files (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES recording_sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- 文件基本信息
    original_filename VARCHAR(500), -- 原始文件名
    storage_path TEXT NOT NULL, -- Supabase Storage中的文件路径
    storage_bucket VARCHAR(100) DEFAULT 'audio-recordings', -- Storage桶名
    public_url TEXT, -- 公开访问URL（如果设置为公开）
    
    -- 文件属性
    file_size_bytes BIGINT NOT NULL, -- 文件大小(字节)
    duration_seconds DECIMAL(10,3), -- 音频时长(秒，精确到毫秒)
    format VARCHAR(20) NOT NULL, -- 音频格式 (webm, mp3, wav, etc.)
    mime_type VARCHAR(100), -- MIME类型
    
    -- 音频技术参数
    sample_rate INTEGER, -- 采样率 (Hz)
    bit_rate INTEGER, -- 比特率 (bps)
    channels INTEGER DEFAULT 1, -- 声道数 (1=单声道, 2=立体声)
    encoding VARCHAR(50), -- 编码格式 (PCM, AAC, Opus, etc.)
    
    -- 文件状态
    upload_status VARCHAR(50) DEFAULT 'uploading', -- uploading, completed, failed
    processing_status VARCHAR(50) DEFAULT 'pending', -- pending, processing, completed, failed
    
    -- 校验和安全
    file_hash VARCHAR(64), -- 文件SHA-256哈希值，用于完整性校验
    encryption_key_id VARCHAR(100), -- 加密密钥ID（如果文件加密）
    
    -- 元数据和质量
    quality_level VARCHAR(20), -- low, medium, high, lossless
    metadata JSONB DEFAULT '{}', -- 额外的音频元数据
    
    -- 错误处理
    error_message TEXT, -- 上传或处理错误信息
    retry_count INTEGER DEFAULT 0, -- 重试次数
    
    -- 访问控制
    is_public BOOLEAN DEFAULT false, -- 是否公开访问
    access_level VARCHAR(20) DEFAULT 'private', -- private, shared, public
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 音频文件表索引
CREATE INDEX idx_audio_files_session_id ON audio_files(session_id);
CREATE INDEX idx_audio_files_user_id ON audio_files(user_id);
CREATE INDEX idx_audio_files_storage_path ON audio_files(storage_path);
CREATE INDEX idx_audio_files_upload_status ON audio_files(upload_status);
CREATE INDEX idx_audio_files_processing_status ON audio_files(processing_status);
CREATE INDEX idx_audio_files_file_hash ON audio_files(file_hash);
CREATE INDEX idx_audio_files_created_at ON audio_files(created_at DESC);

-- ================================================================
-- 4. 转录记录表 (transcriptions)
-- ================================================================
CREATE TABLE transcriptions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES recording_sessions(id) ON DELETE CASCADE,
    
    -- 转录内容
    content TEXT NOT NULL, -- 完整的转录文本
    segments JSONB DEFAULT '[]', -- 分段转录数据，包含时间戳和说话人信息
    
    -- 转录元数据
    language VARCHAR(10) DEFAULT 'zh-CN', -- 识别的语言
    confidence_score DECIMAL(3,2), -- 整体置信度 (0.00-1.00)
    processing_time_ms INTEGER, -- 处理耗时(毫秒)
    
    -- STT模型信息
    stt_model VARCHAR(100), -- 使用的语音识别模型
    stt_version VARCHAR(50), -- 模型版本
    
    -- 状态和质量
    status VARCHAR(50) DEFAULT 'completed', -- processing, completed, failed
    quality_score DECIMAL(3,2), -- 转录质量评分
    word_count INTEGER, -- 词数统计
    
    -- 错误处理
    error_message TEXT, -- 错误信息
    retry_count INTEGER DEFAULT 0, -- 重试次数
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 转录记录表索引
CREATE INDEX idx_transcriptions_session_id ON transcriptions(session_id);
CREATE INDEX idx_transcriptions_status ON transcriptions(status);
CREATE INDEX idx_transcriptions_language ON transcriptions(language);
CREATE INDEX idx_transcriptions_confidence_score ON transcriptions(confidence_score);

-- ================================================================
-- 5. AI总结表 (ai_summaries)
-- ================================================================
CREATE TABLE ai_summaries (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES recording_sessions(id) ON DELETE CASCADE,
    transcription_id UUID NOT NULL REFERENCES transcriptions(id) ON DELETE CASCADE,
    
    -- 总结内容
    summary TEXT NOT NULL, -- AI生成的总结内容
    key_points JSONB DEFAULT '[]', -- 关键要点数组
    action_items JSONB DEFAULT '[]', -- 行动项数组
    participants JSONB DEFAULT '[]', -- 参与者信息
    
    -- AI模型信息
    ai_model VARCHAR(100) NOT NULL, -- 使用的AI模型
    ai_provider VARCHAR(50), -- AI服务提供商 (openai, anthropic, etc.)
    model_version VARCHAR(50), -- 模型版本
    
    -- 处理信息
    processing_time_ms INTEGER, -- 处理耗时(毫秒)
    token_usage JSONB DEFAULT '{}', -- token使用情况
    cost_cents INTEGER, -- 成本(分)
    
    -- 质量和状态
    status VARCHAR(50) DEFAULT 'completed', -- processing, completed, failed
    quality_rating INTEGER CHECK (quality_rating >= 1 AND quality_rating <= 5), -- 1-5星评级
    
    -- 错误处理
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- AI总结表索引
CREATE INDEX idx_ai_summaries_session_id ON ai_summaries(session_id);
CREATE INDEX idx_ai_summaries_transcription_id ON ai_summaries(transcription_id);
CREATE INDEX idx_ai_summaries_ai_model ON ai_summaries(ai_model);
CREATE INDEX idx_ai_summaries_status ON ai_summaries(status);

-- ================================================================
-- 6. 用户设置表 (user_settings)
-- ================================================================
CREATE TABLE user_settings (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- 录音设置
    default_audio_quality VARCHAR(20) DEFAULT 'high', -- low, medium, high
    auto_start_recording BOOLEAN DEFAULT false,
    auto_pause_detection BOOLEAN DEFAULT true,
    
    -- 转录设置
    preferred_language VARCHAR(10) DEFAULT 'zh-CN',
    enable_speaker_identification BOOLEAN DEFAULT true,
    enable_punctuation BOOLEAN DEFAULT true,
    
    -- AI设置
    preferred_ai_model VARCHAR(100),
    auto_generate_summary BOOLEAN DEFAULT true,
    auto_generate_title BOOLEAN DEFAULT true,
    summary_style VARCHAR(50) DEFAULT 'concise', -- brief, concise, detailed
    
    -- 通知设置
    email_notifications BOOLEAN DEFAULT true,
    summary_complete_notification BOOLEAN DEFAULT true,
    
    -- 存储设置
    auto_delete_recordings_days INTEGER, -- 自动删除录音的天数
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 用户设置表索引
CREATE INDEX idx_user_settings_user_id ON user_settings(user_id);

-- ================================================================
-- 7. 分享链接表 (shared_recordings)
-- ================================================================
CREATE TABLE shared_recordings (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES recording_sessions(id) ON DELETE CASCADE,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- 分享配置
    share_token VARCHAR(100) UNIQUE NOT NULL, -- 分享链接token
    share_type VARCHAR(20) DEFAULT 'view', -- view, edit
    is_public BOOLEAN DEFAULT false,
    requires_password BOOLEAN DEFAULT false,
    password_hash TEXT, -- 访问密码hash
    
    -- 权限控制
    allowed_emails TEXT[], -- 允许访问的邮箱列表
    max_views INTEGER, -- 最大查看次数
    current_views INTEGER DEFAULT 0, -- 当前查看次数
    
    -- 时间控制
    expires_at TIMESTAMP WITH TIME ZONE, -- 过期时间
    
    -- 内容控制
    include_transcript BOOLEAN DEFAULT true,
    include_summary BOOLEAN DEFAULT true,
    include_audio BOOLEAN DEFAULT false,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 分享链接表索引
CREATE INDEX idx_shared_recordings_session_id ON shared_recordings(session_id);
CREATE INDEX idx_shared_recordings_share_token ON shared_recordings(share_token);
CREATE INDEX idx_shared_recordings_owner_id ON shared_recordings(owner_id);

-- ================================================================
-- 8. 访问日志表 (access_logs)
-- ================================================================
CREATE TABLE access_logs (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    session_id UUID REFERENCES recording_sessions(id) ON DELETE CASCADE,
    
    -- 访问信息
    action VARCHAR(100) NOT NULL, -- create, view, edit, delete, share, etc.
    ip_address INET,
    user_agent TEXT,
    referer TEXT,
    
    -- 地理位置 (可选)
    country VARCHAR(5),
    city VARCHAR(100),
    
    -- 额外信息
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 访问日志表索引
CREATE INDEX idx_access_logs_user_id ON access_logs(user_id);
CREATE INDEX idx_access_logs_session_id ON access_logs(session_id);
CREATE INDEX idx_access_logs_action ON access_logs(action);
CREATE INDEX idx_access_logs_created_at ON access_logs(created_at DESC);

-- ================================================================
-- 9. 系统统计表 (system_stats)
-- ================================================================
CREATE TABLE system_stats (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    stat_date DATE NOT NULL,
    
    -- 用户统计
    total_users INTEGER DEFAULT 0,
    active_users INTEGER DEFAULT 0,
    new_users INTEGER DEFAULT 0,
    
    -- 录音统计
    total_recordings INTEGER DEFAULT 0,
    new_recordings INTEGER DEFAULT 0,
    total_duration_minutes INTEGER DEFAULT 0,
    
    -- 转录统计
    total_transcriptions INTEGER DEFAULT 0,
    avg_transcription_time_ms INTEGER DEFAULT 0,
    avg_confidence_score DECIMAL(3,2),
    
    -- AI统计
    total_summaries INTEGER DEFAULT 0,
    avg_summary_time_ms INTEGER DEFAULT 0,
    total_ai_cost_cents INTEGER DEFAULT 0,
    
    -- 存储统计
    total_storage_bytes BIGINT DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 系统统计表索引
CREATE INDEX idx_system_stats_stat_date ON system_stats(stat_date DESC);

-- ================================================================
-- 创建更新时间触发器函数
-- ================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 为需要的表添加更新时间触发器
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_recording_sessions_updated_at BEFORE UPDATE ON recording_sessions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_audio_files_updated_at BEFORE UPDATE ON audio_files FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_transcriptions_updated_at BEFORE UPDATE ON transcriptions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_ai_summaries_updated_at BEFORE UPDATE ON ai_summaries FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_user_settings_updated_at BEFORE UPDATE ON user_settings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_shared_recordings_updated_at BEFORE UPDATE ON shared_recordings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ================================================================
-- Row Level Security (RLS) 策略
-- ================================================================

-- 启用RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE recording_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE audio_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE transcriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared_recordings ENABLE ROW LEVEL SECURITY;

-- 用户表策略：用户只能访问自己的数据
CREATE POLICY users_policy ON users FOR ALL USING (auth.uid() = id);

-- 允许公开查询用户名是否存在（用于注册验证，限制只能查询 username 字段）
CREATE POLICY users_username_check_policy ON users 
FOR SELECT USING (true);

-- 录音会话策略：用户只能访问自己创建的会话
CREATE POLICY recording_sessions_policy ON recording_sessions FOR ALL USING (auth.uid() = user_id);

-- 音频文件策略：前端只能查看和创建，后端可完整操作
CREATE POLICY audio_files_select_policy ON audio_files 
FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY audio_files_insert_policy ON audio_files 
FOR INSERT WITH CHECK (auth.uid() = user_id);

-- 注意：UPDATE和DELETE权限仅限service_role，前端无法直接修改文件状态

-- 转录记录策略：用户可查看自己会话的转录
CREATE POLICY transcriptions_policy ON transcriptions FOR SELECT USING (
    auth.uid() IN (
        SELECT user_id FROM recording_sessions WHERE id = transcriptions.session_id
    )
);

-- AI总结策略：用户可查看自己会话的AI总结
CREATE POLICY ai_summaries_policy ON ai_summaries FOR SELECT USING (
    auth.uid() IN (
        SELECT user_id FROM recording_sessions WHERE id = ai_summaries.session_id
    )
);

-- 用户设置策略：用户只能访问自己的设置
CREATE POLICY user_settings_policy ON user_settings FOR ALL USING (auth.uid() = user_id);

-- 分享链接策略：用户只能管理自己创建的分享
CREATE POLICY shared_recordings_policy ON shared_recordings FOR ALL USING (auth.uid() = owner_id);

-- 公开分享访问策略：允许访问公开分享的录音
CREATE POLICY public_shared_recordings_policy ON recording_sessions 
FOR SELECT USING (
    id IN (
        SELECT session_id FROM shared_recordings 
        WHERE is_public = true 
        AND (expires_at IS NULL OR expires_at > NOW())
    )
);

-- 通过分享token访问策略
CREATE POLICY shared_token_access_policy ON recording_sessions 
FOR SELECT USING (
    id IN (
        SELECT session_id FROM shared_recordings 
        WHERE share_token = current_setting('app.current_share_token', true)
        AND (expires_at IS NULL OR expires_at > NOW())
    )
);

-- ================================================================
-- 初始化数据
-- ================================================================

-- 插入系统默认设置（可选）
-- INSERT INTO system_stats (stat_date) VALUES (CURRENT_DATE);

-- ================================================================
-- 视图定义
-- ================================================================

-- 录音会话详情视图
CREATE VIEW recording_sessions_detailed AS
SELECT 
    rs.*,
    af.id as audio_file_id,
    af.original_filename,
    af.storage_path,
    af.public_url,
    af.file_size_bytes,
    af.format as audio_format,
    af.duration_seconds as audio_duration_seconds,
    af.quality_level,
    af.upload_status,
    af.processing_status,
    t.content as transcript_content,
    t.word_count,
    t.confidence_score,
    ais.summary,
    ais.ai_model,
    ais.quality_rating,
    u.username,
    u.full_name
FROM recording_sessions rs
LEFT JOIN audio_files af ON rs.id = af.session_id
LEFT JOIN transcriptions t ON rs.id = t.session_id
LEFT JOIN ai_summaries ais ON rs.id = ais.session_id
LEFT JOIN users u ON rs.user_id = u.id;

-- 用户统计视图
CREATE VIEW user_statistics AS
SELECT 
    u.id,
    u.username,
    u.full_name,
    COUNT(rs.id) as total_recordings,
    SUM(rs.duration_seconds) as total_duration_seconds,
    AVG(t.confidence_score) as avg_confidence_score,
    COUNT(ais.id) as total_summaries,
    u.created_at as user_created_at,
    MAX(rs.created_at) as last_recording_at
FROM users u
LEFT JOIN recording_sessions rs ON u.id = rs.user_id
LEFT JOIN transcriptions t ON rs.id = t.session_id
LEFT JOIN ai_summaries ais ON rs.id = ais.session_id
GROUP BY u.id, u.username, u.full_name, u.created_at;

-- ================================================================
-- 函数定义
-- ================================================================

-- 自动创建用户记录的触发器函数
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, email, username, full_name)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'username', split_part(NEW.email, '@', 1)),
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'username', split_part(NEW.email, '@', 1))
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 创建触发器：当 auth.users 表插入新记录时自动创建 public.users 记录
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 获取用户录音统计
CREATE OR REPLACE FUNCTION get_user_recording_stats(user_uuid UUID)
RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    SELECT json_build_object(
        'total_recordings', COUNT(rs.id),
        'total_duration_seconds', COALESCE(SUM(rs.duration_seconds), 0),
        'total_transcriptions', COUNT(t.id),
        'total_summaries', COUNT(ais.id),
        'avg_confidence_score', ROUND(AVG(t.confidence_score), 2),
        'latest_recording', MAX(rs.created_at)
    )
    INTO result
    FROM recording_sessions rs
    LEFT JOIN transcriptions t ON rs.id = t.session_id
    LEFT JOIN ai_summaries ais ON rs.id = ais.session_id
    WHERE rs.user_id = user_uuid;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- 清理过期的分享链接
CREATE OR REPLACE FUNCTION cleanup_expired_shares()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM shared_recordings 
    WHERE expires_at < NOW() AND expires_at IS NOT NULL;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- 获取用户存储使用统计
CREATE OR REPLACE FUNCTION get_user_storage_stats(user_uuid UUID)
RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    SELECT json_build_object(
        'total_files', COUNT(af.id),
        'total_size_bytes', COALESCE(SUM(af.file_size_bytes), 0),
        'total_duration_seconds', COALESCE(SUM(af.duration_seconds), 0),
        'avg_file_size_mb', ROUND(AVG(af.file_size_bytes) / 1024.0 / 1024.0, 2),
        'formats', json_agg(DISTINCT af.format),
        'upload_pending', COUNT(af.id) FILTER (WHERE af.upload_status = 'uploading'),
        'processing_pending', COUNT(af.id) FILTER (WHERE af.processing_status = 'processing')
    )
    INTO result
    FROM audio_files af
    WHERE af.user_id = user_uuid;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- 清理失败的音频文件记录
CREATE OR REPLACE FUNCTION cleanup_failed_audio_files(days_old INTEGER DEFAULT 7)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM audio_files 
    WHERE (upload_status = 'failed' OR processing_status = 'failed')
    AND created_at < NOW() - INTERVAL '1 day' * days_old;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- 计算录音会话的总时长（基于音频文件）
CREATE OR REPLACE FUNCTION update_session_duration(session_uuid UUID)
RETURNS BOOLEAN AS $$
DECLARE
    total_duration DECIMAL(10,3);
BEGIN
    SELECT COALESCE(SUM(duration_seconds), 0)
    INTO total_duration
    FROM audio_files
    WHERE session_id = session_uuid AND upload_status = 'completed';
    
    UPDATE recording_sessions 
    SET duration_seconds = total_duration,
        updated_at = NOW()
    WHERE id = session_uuid;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- ================================================================
-- 权限设置 (如果使用Supabase的认证系统)
-- ================================================================

-- 为认证用户授予必要的权限
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO authenticated;

-- 为匿名用户授予有限权限（如果需要）
GRANT USAGE ON SCHEMA public TO anon;
GRANT SELECT ON shared_recordings TO anon; -- 允许访问公开分享的录音

-- ================================================================
-- 完成
-- ================================================================

-- 创建完成提示
DO $$
BEGIN
    RAISE NOTICE '数据库表结构创建完成！';
    RAISE NOTICE '包含以下主要表：';
    RAISE NOTICE '1. users - 用户管理';
    RAISE NOTICE '2. recording_sessions - 录音会话';
    RAISE NOTICE '3. audio_files - 音频文件';
    RAISE NOTICE '4. transcriptions - 转录记录';
    RAISE NOTICE '5. ai_summaries - AI总结';
    RAISE NOTICE '6. user_settings - 用户设置';
    RAISE NOTICE '7. shared_recordings - 分享链接';
    RAISE NOTICE '8. access_logs - 访问日志';
    RAISE NOTICE '9. system_stats - 系统统计';
END $$; 