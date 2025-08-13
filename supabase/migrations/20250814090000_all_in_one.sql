-- All-in-one migration: create all schema objects for ASR-FastRTC
-- 包含：扩展、所有表/索引/RLS/触发器/视图/函数、summary_templates、recording_sessions.template_id、ai_summaries.template_id、auth->public 用户触发器与回填

BEGIN;

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Core tables
CREATE TABLE IF NOT EXISTS public.users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email VARCHAR(255) NOT NULL,
  username VARCHAR(100) NOT NULL,
  password_hash TEXT,
  full_name VARCHAR(200),
  avatar_url TEXT,
  phone VARCHAR(20),
  is_active BOOLEAN DEFAULT TRUE,
  is_verified BOOLEAN DEFAULT FALSE,
  email_verified_at TIMESTAMPTZ,
  last_login_at TIMESTAMPTZ,
  preferences JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_policy ON public.users FOR ALL USING (auth.uid() = id);
CREATE POLICY users_username_check_policy ON public.users FOR SELECT USING (true);
CREATE INDEX IF NOT EXISTS idx_users_email ON public.users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON public.users(username);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON public.users(is_active);
CREATE UNIQUE INDEX IF NOT EXISTS users_pkey ON public.users(id);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_key ON public.users(email);
CREATE UNIQUE INDEX IF NOT EXISTS users_username_key ON public.users(username);

CREATE TABLE IF NOT EXISTS public.recording_sessions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  title VARCHAR(500) NOT NULL DEFAULT '未命名录音',
  description TEXT,
  webrtc_id VARCHAR(100),
  status VARCHAR(50) DEFAULT 'draft',
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  duration_seconds INTEGER DEFAULT 0,
  metadata JSONB DEFAULT '{}',
  tags TEXT[],
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.recording_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY recording_sessions_policy ON public.recording_sessions FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_recording_sessions_user_id ON public.recording_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_recording_sessions_status ON public.recording_sessions(status);
CREATE INDEX IF NOT EXISTS idx_recording_sessions_created_at ON public.recording_sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recording_sessions_webrtc_id ON public.recording_sessions(webrtc_id);

CREATE TABLE IF NOT EXISTS public.audio_files (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id UUID NOT NULL REFERENCES public.recording_sessions(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  original_filename VARCHAR(500),
  storage_path TEXT NOT NULL,
  storage_bucket VARCHAR(100) DEFAULT 'audio-recordings',
  public_url TEXT,
  file_size_bytes BIGINT NOT NULL,
  duration_seconds NUMERIC(10,3),
  format VARCHAR(20) NOT NULL,
  mime_type VARCHAR(100),
  sample_rate INTEGER,
  bit_rate INTEGER,
  channels INTEGER DEFAULT 1,
  encoding VARCHAR(50),
  upload_status VARCHAR(50) DEFAULT 'uploading',
  processing_status VARCHAR(50) DEFAULT 'pending',
  file_hash VARCHAR(64),
  encryption_key_id VARCHAR(100),
  quality_level VARCHAR(20),
  metadata JSONB DEFAULT '{}',
  error_message TEXT,
  retry_count INTEGER DEFAULT 0,
  is_public BOOLEAN DEFAULT FALSE,
  access_level VARCHAR(20) DEFAULT 'private',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.audio_files ENABLE ROW LEVEL SECURITY;
CREATE POLICY audio_files_select_policy ON public.audio_files FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY audio_files_insert_policy ON public.audio_files FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_audio_files_session_id ON public.audio_files(session_id);
CREATE INDEX IF NOT EXISTS idx_audio_files_user_id ON public.audio_files(user_id);
CREATE INDEX IF NOT EXISTS idx_audio_files_storage_path ON public.audio_files(storage_path);
CREATE INDEX IF NOT EXISTS idx_audio_files_upload_status ON public.audio_files(upload_status);
CREATE INDEX IF NOT EXISTS idx_audio_files_processing_status ON public.audio_files(processing_status);
CREATE INDEX IF NOT EXISTS idx_audio_files_file_hash ON public.audio_files(file_hash);
CREATE INDEX IF NOT EXISTS idx_audio_files_created_at ON public.audio_files(created_at DESC);

CREATE TABLE IF NOT EXISTS public.transcriptions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id UUID NOT NULL REFERENCES public.recording_sessions(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  segments JSONB DEFAULT '[]',
  language VARCHAR(10) DEFAULT 'zh-CN',
  confidence_score NUMERIC(3,2),
  processing_time_ms INTEGER,
  stt_model VARCHAR(100),
  stt_version VARCHAR(50),
  status VARCHAR(50) DEFAULT 'completed',
  quality_score NUMERIC(3,2),
  word_count INTEGER,
  error_message TEXT,
  retry_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.transcriptions ENABLE ROW LEVEL SECURITY;
CREATE POLICY transcriptions_policy ON public.transcriptions FOR SELECT USING (
  auth.uid() IN (
    SELECT user_id FROM public.recording_sessions WHERE id = transcriptions.session_id
  )
);
CREATE INDEX IF NOT EXISTS idx_transcriptions_session_id ON public.transcriptions(session_id);
CREATE INDEX IF NOT EXISTS idx_transcriptions_status ON public.transcriptions(status);
CREATE INDEX IF NOT EXISTS idx_transcriptions_language ON public.transcriptions(language);
CREATE INDEX IF NOT EXISTS idx_transcriptions_confidence_score ON public.transcriptions(confidence_score);

CREATE TABLE IF NOT EXISTS public.ai_summaries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id UUID NOT NULL REFERENCES public.recording_sessions(id) ON DELETE CASCADE,
  transcription_id UUID NOT NULL REFERENCES public.transcriptions(id) ON DELETE CASCADE,
  summary TEXT NOT NULL,
  key_points JSONB DEFAULT '[]',
  action_items JSONB DEFAULT '[]',
  participants JSONB DEFAULT '[]',
  ai_model VARCHAR(100) NOT NULL,
  ai_provider VARCHAR(50),
  model_version VARCHAR(50),
  processing_time_ms INTEGER,
  token_usage JSONB DEFAULT '{}',
  cost_cents INTEGER,
  status VARCHAR(50) DEFAULT 'completed',
  quality_rating INTEGER CHECK (quality_rating >= 1 AND quality_rating <= 5),
  template_id UUID,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.ai_summaries ENABLE ROW LEVEL SECURITY;
CREATE POLICY ai_summaries_policy ON public.ai_summaries FOR SELECT USING (
  auth.uid() IN (
    SELECT user_id FROM public.recording_sessions WHERE id = ai_summaries.session_id
  )
);
CREATE INDEX IF NOT EXISTS idx_ai_summaries_session_id ON public.ai_summaries(session_id);
CREATE INDEX IF NOT EXISTS idx_ai_summaries_transcription_id ON public.ai_summaries(transcription_id);
CREATE INDEX IF NOT EXISTS idx_ai_summaries_ai_model ON public.ai_summaries(ai_model);
CREATE INDEX IF NOT EXISTS idx_ai_summaries_status ON public.ai_summaries(status);

-- user_settings
CREATE TABLE IF NOT EXISTS public.user_settings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  default_audio_quality VARCHAR(20) DEFAULT 'high',
  auto_start_recording BOOLEAN DEFAULT FALSE,
  auto_pause_detection BOOLEAN DEFAULT TRUE,
  preferred_language VARCHAR(10) DEFAULT 'zh-CN',
  enable_speaker_identification BOOLEAN DEFAULT TRUE,
  enable_punctuation BOOLEAN DEFAULT TRUE,
  preferred_ai_model VARCHAR(100),
  auto_generate_summary BOOLEAN DEFAULT TRUE,
  auto_generate_title BOOLEAN DEFAULT TRUE,
  summary_style VARCHAR(50) DEFAULT 'concise',
  email_notifications BOOLEAN DEFAULT TRUE,
  summary_complete_notification BOOLEAN DEFAULT TRUE,
  auto_delete_recordings_days INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_settings_policy ON public.user_settings FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON public.user_settings(user_id);

CREATE TABLE IF NOT EXISTS public.shared_recordings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_id UUID NOT NULL REFERENCES public.recording_sessions(id) ON DELETE CASCADE,
  owner_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  share_token VARCHAR(100) UNIQUE NOT NULL,
  share_type VARCHAR(20) DEFAULT 'view',
  is_public BOOLEAN DEFAULT FALSE,
  requires_password BOOLEAN DEFAULT FALSE,
  password_hash TEXT,
  allowed_emails TEXT[],
  max_views INTEGER,
  current_views INTEGER DEFAULT 0,
  expires_at TIMESTAMPTZ,
  include_transcript BOOLEAN DEFAULT TRUE,
  include_summary BOOLEAN DEFAULT TRUE,
  include_audio BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.shared_recordings ENABLE ROW LEVEL SECURITY;
CREATE POLICY shared_recordings_policy ON public.shared_recordings FOR ALL USING (auth.uid() = owner_id);
CREATE INDEX IF NOT EXISTS idx_shared_recordings_session_id ON public.shared_recordings(session_id);
CREATE INDEX IF NOT EXISTS idx_shared_recordings_share_token ON public.shared_recordings(share_token);
CREATE INDEX IF NOT EXISTS idx_shared_recordings_owner_id ON public.shared_recordings(owner_id);

-- Policies on recording_sessions that reference shared_recordings must be created after the table exists
CREATE POLICY public_shared_recordings_policy ON public.recording_sessions FOR SELECT USING (
  id IN (
    SELECT session_id FROM public.shared_recordings 
    WHERE is_public = TRUE AND (expires_at IS NULL OR expires_at > NOW())
  )
);
CREATE POLICY shared_token_access_policy ON public.recording_sessions FOR SELECT USING (
  id IN (
    SELECT session_id FROM public.shared_recordings 
    WHERE share_token = current_setting('app.current_share_token', true) AND (expires_at IS NULL OR expires_at > NOW())
  )
);

CREATE TABLE IF NOT EXISTS public.access_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
  session_id UUID REFERENCES public.recording_sessions(id) ON DELETE CASCADE,
  action VARCHAR(100) NOT NULL,
  ip_address INET,
  user_agent TEXT,
  referer TEXT,
  country VARCHAR(5),
  city VARCHAR(100),
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_access_logs_user_id ON public.access_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_access_logs_session_id ON public.access_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_access_logs_action ON public.access_logs(action);
CREATE INDEX IF NOT EXISTS idx_access_logs_created_at ON public.access_logs(created_at DESC);

CREATE TABLE IF NOT EXISTS public.system_stats (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  stat_date DATE NOT NULL,
  total_users INTEGER DEFAULT 0,
  active_users INTEGER DEFAULT 0,
  new_users INTEGER DEFAULT 0,
  total_recordings INTEGER DEFAULT 0,
  new_recordings INTEGER DEFAULT 0,
  total_duration_minutes INTEGER DEFAULT 0,
  total_transcriptions INTEGER DEFAULT 0,
  avg_transcription_time_ms INTEGER DEFAULT 0,
  avg_confidence_score NUMERIC(3,2),
  total_summaries INTEGER DEFAULT 0,
  avg_summary_time_ms INTEGER DEFAULT 0,
  total_ai_cost_cents INTEGER DEFAULT 0,
  total_storage_bytes BIGINT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_system_stats_stat_date ON public.system_stats(stat_date DESC);

-- Functions
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

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
END; $$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION public.get_user_recording_stats(user_uuid UUID)
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
  ) INTO result
  FROM public.recording_sessions rs
  LEFT JOIN public.transcriptions t ON rs.id = t.session_id
  LEFT JOIN public.ai_summaries ais ON rs.id = ais.session_id
  WHERE rs.user_id = user_uuid;
  RETURN result;
END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.cleanup_expired_shares()
RETURNS INTEGER AS $$
DECLARE deleted_count INTEGER; BEGIN
  DELETE FROM public.shared_recordings WHERE expires_at < NOW() AND expires_at IS NOT NULL;
  GET DIAGNOSTICS deleted_count = ROW_COUNT; RETURN deleted_count; END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.cleanup_failed_audio_files(days_old INTEGER DEFAULT 7)
RETURNS INTEGER AS $$
DECLARE deleted_count INTEGER; BEGIN
  DELETE FROM public.audio_files 
  WHERE (upload_status = 'failed' OR processing_status = 'failed')
  AND created_at < NOW() - INTERVAL '1 day' * days_old;
  GET DIAGNOSTICS deleted_count = ROW_COUNT; RETURN deleted_count; END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.get_user_storage_stats(user_uuid UUID)
RETURNS JSON AS $$
DECLARE result JSON; BEGIN
  SELECT json_build_object(
    'total_files', COUNT(af.id),
    'total_size_bytes', COALESCE(SUM(af.file_size_bytes), 0),
    'total_duration_seconds', COALESCE(SUM(af.duration_seconds), 0),
    'avg_file_size_mb', ROUND(AVG(af.file_size_bytes) / 1024.0 / 1024.0, 2),
    'formats', json_agg(DISTINCT af.format),
    'upload_pending', COUNT(af.id) FILTER (WHERE af.upload_status = 'uploading'),
    'processing_pending', COUNT(af.id) FILTER (WHERE af.processing_status = 'processing')
  ) INTO result
  FROM public.audio_files af WHERE af.user_id = user_uuid; RETURN result; END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.update_session_duration(session_uuid UUID)
RETURNS BOOLEAN AS $$
DECLARE total_duration NUMERIC(10,3); BEGIN
  SELECT COALESCE(SUM(duration_seconds), 0) INTO total_duration
  FROM public.audio_files WHERE session_id = session_uuid AND upload_status = 'completed';
  UPDATE public.recording_sessions SET duration_seconds = total_duration, updated_at = NOW() WHERE id = session_uuid;
  RETURN TRUE; END; $$ LANGUAGE plpgsql;

-- Triggers
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_recording_sessions_updated_at BEFORE UPDATE ON public.recording_sessions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_audio_files_updated_at BEFORE UPDATE ON public.audio_files FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_transcriptions_updated_at BEFORE UPDATE ON public.transcriptions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_ai_summaries_updated_at BEFORE UPDATE ON public.ai_summaries FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
-- will be created after user_settings table creation (below)
CREATE TRIGGER update_shared_recordings_updated_at BEFORE UPDATE ON public.shared_recordings FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Views
CREATE OR REPLACE VIEW public.recording_sessions_detailed AS
SELECT 
  rs.*, af.id AS audio_file_id, af.original_filename, af.storage_path, af.public_url,
  af.file_size_bytes, af.format AS audio_format, af.duration_seconds AS audio_duration_seconds,
  af.quality_level, af.upload_status, af.processing_status,
  t.content AS transcript_content, t.word_count, t.confidence_score,
  ais.summary, ais.ai_model, ais.quality_rating,
  u.username, u.full_name
FROM public.recording_sessions rs
LEFT JOIN public.audio_files af ON rs.id = af.session_id
LEFT JOIN public.transcriptions t ON rs.id = t.session_id
LEFT JOIN public.ai_summaries ais ON rs.id = ais.session_id
LEFT JOIN public.users u ON rs.user_id = u.id;

CREATE OR REPLACE VIEW public.user_statistics AS
SELECT 
  u.id, u.username, u.full_name,
  COUNT(rs.id) AS total_recordings,
  SUM(rs.duration_seconds) AS total_duration_seconds,
  AVG(t.confidence_score) AS avg_confidence_score,
  COUNT(ais.id) AS total_summaries,
  u.created_at AS user_created_at,
  MAX(rs.created_at) AS last_recording_at
FROM public.users u
LEFT JOIN public.recording_sessions rs ON u.id = rs.user_id
LEFT JOIN public.transcriptions t ON rs.id = t.session_id
LEFT JOIN public.ai_summaries ais ON rs.id = ais.session_id
GROUP BY u.id, u.username, u.full_name, u.created_at;

-- Summary templates and related
CREATE TABLE IF NOT EXISTS public.summary_templates (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  description TEXT,
  template_content TEXT NOT NULL,
  category TEXT DEFAULT '会议',
  tags JSONB DEFAULT '[]',
  is_default BOOLEAN DEFAULT FALSE,
  is_active BOOLEAN DEFAULT TRUE,
  is_system_template BOOLEAN DEFAULT FALSE,
  usage_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.summary_templates ENABLE ROW LEVEL SECURITY;
CREATE POLICY summary_templates_select_system ON public.summary_templates FOR SELECT USING (is_system_template = TRUE);
CREATE POLICY summary_templates_user_all ON public.summary_templates FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_summary_templates_user_id ON public.summary_templates(user_id);
CREATE INDEX IF NOT EXISTS idx_summary_templates_is_system ON public.summary_templates(is_system_template);
CREATE INDEX IF NOT EXISTS idx_summary_templates_is_active ON public.summary_templates(is_active);
CREATE INDEX IF NOT EXISTS idx_summary_templates_is_default ON public.summary_templates(is_default);
CREATE INDEX IF NOT EXISTS idx_summary_templates_created_at ON public.summary_templates(created_at DESC);

-- RPC to increment usage
CREATE OR REPLACE FUNCTION public.increment_template_usage(template_id UUID)
RETURNS INTEGER LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE new_count INTEGER; BEGIN
  UPDATE public.summary_templates
  SET usage_count = COALESCE(usage_count, 0) + 1,
      updated_at = NOW()
  WHERE id = template_id
  RETURNING usage_count INTO new_count;
  RETURN COALESCE(new_count, 0);
END; $$;

-- recording_sessions.template_id FK
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'recording_sessions' AND column_name = 'template_id'
  ) THEN
    ALTER TABLE public.recording_sessions ADD COLUMN template_id UUID;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_schema = 'public' AND table_name = 'recording_sessions' AND constraint_name = 'recording_sessions_template_id_fkey'
  ) THEN
    ALTER TABLE public.recording_sessions
      ADD CONSTRAINT recording_sessions_template_id_fkey
      FOREIGN KEY (template_id) REFERENCES public.summary_templates(id) ON DELETE SET NULL;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_recording_sessions_template_id ON public.recording_sessions(template_id);

-- ai_summaries.template_id FK
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'ai_summaries' AND column_name = 'template_id'
  ) THEN
    ALTER TABLE public.ai_summaries ADD COLUMN template_id UUID;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_schema = 'public' AND table_name = 'ai_summaries' AND constraint_name = 'ai_summaries_template_id_fkey'
  ) THEN
    ALTER TABLE public.ai_summaries
      ADD CONSTRAINT ai_summaries_template_id_fkey
      FOREIGN KEY (template_id) REFERENCES public.summary_templates(id) ON DELETE SET NULL;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_ai_summaries_template_id ON public.ai_summaries(template_id);

-- updated_at triggers for summary_templates and user_profiles
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_summary_templates_updated_at') THEN
    CREATE TRIGGER update_summary_templates_updated_at BEFORE UPDATE ON public.summary_templates FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
  END IF;
END $$;

-- user_profiles
CREATE TABLE IF NOT EXISTS public.user_profiles (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL UNIQUE REFERENCES public.users(id) ON DELETE CASCADE,
  subscription_plan TEXT DEFAULT 'free',
  subscription_status TEXT DEFAULT 'active',
  quotas JSONB DEFAULT '{"transcription_minutes":{"used":0,"limit":1000},"ai_summary_count":{"used":0,"limit":100}}',
  preferences JSONB DEFAULT '{"default_language":"zh-CN","auto_summary":true}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_profiles_user_all ON public.user_profiles FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_user_profiles_updated_at') THEN
    CREATE TRIGGER update_user_profiles_updated_at BEFORE UPDATE ON public.user_profiles FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
  END IF;
END $$;

-- Grants (minimal needed)
GRANT USAGE ON SCHEMA public TO authenticated, anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon;

-- Seed system templates (id auto)
INSERT INTO public.summary_templates (user_id, name, description, template_content, category, tags, is_default, is_active, is_system_template)
SELECT NULL, '通用会议纪要', '适用于多数团队例会/项目会议的标准纪要模板', '# 会议总结\n\n## 基本信息\n- 主题：<自动概括>\n- 参会人员：<提取参与者>\n- 时间：<提取时间>\n\n## 主要议题\n- <要点1>\n- <要点2>\n\n## 重要决议\n- <决策1>\n\n## 行动项\n- [ ] 负责人：<姓名> | 事项：<内容> | 截止：<日期>\n\n## 待解决问题\n- <问题1>', '会议', '["系统","会议","通用"]'::jsonb, FALSE, TRUE, TRUE
WHERE NOT EXISTS (SELECT 1 FROM public.summary_templates WHERE is_system_template = TRUE AND name = '通用会议纪要');

INSERT INTO public.summary_templates (user_id, name, description, template_content, category, tags, is_default, is_active, is_system_template)
SELECT NULL, '访谈要点提炼', '用于采访/客户访谈后的结构化要点提炼', '# 访谈总结\n\n## 背景与目标\n<简述访谈背景、目标>\n\n## 受访者信息\n- 姓名/角色：<信息>\n\n## 关键发现\n- <发现1>\n- <发现2>\n\n## 痛点与诉求\n- <痛点1>\n\n## 后续跟进\n- <动作1>', '访谈', '["系统","访谈"]'::jsonb, FALSE, TRUE, TRUE
WHERE NOT EXISTS (SELECT 1 FROM public.summary_templates WHERE is_system_template = TRUE AND name = '访谈要点提炼');

INSERT INTO public.summary_templates (user_id, name, description, template_content, category, tags, is_default, is_active, is_system_template)
SELECT NULL, '技术评审结论', '代码/架构/方案评审后的结论与行动项', '# 技术评审总结\n\n## 评审范围\n<模块/方案>\n\n## 结论\n- <结论1>\n\n## 风险与假设\n- 风险：<风险1>\n- 假设：<假设1>\n\n## 改进建议\n- <建议1>\n\n## 行动项\n- [ ] 负责人：<姓名> | 事项：<内容> | 截止：<日期>', '技术', '["系统","技术","评审"]'::jsonb, FALSE, TRUE, TRUE
WHERE NOT EXISTS (SELECT 1 FROM public.summary_templates WHERE is_system_template = TRUE AND name = '技术评审结论');

-- auth.users -> public.users trigger
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'on_auth_user_created') THEN
    CREATE TRIGGER on_auth_user_created
      AFTER INSERT ON auth.users
      FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
  END IF;
END $$;

-- Backfill users from auth.users
INSERT INTO public.users (id, email, username, full_name)
SELECT u.id, u.email,
  COALESCE(u.raw_user_meta_data->>'username', split_part(u.email, '@', 1)) AS username,
  COALESCE(u.raw_user_meta_data->>'full_name', u.raw_user_meta_data->>'username', split_part(u.email, '@', 1)) AS full_name
FROM auth.users u
LEFT JOIN public.users pu ON pu.id = u.id
WHERE pu.id IS NULL;

-- ================================================================
-- Storage: 创建音频存储桶与访问策略
-- ================================================================

-- 创建存储桶（若已存在则跳过）
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM storage.buckets WHERE id = 'audio-recordings'
  ) THEN
    INSERT INTO storage.buckets (id, name, public)
    VALUES ('audio-recordings', 'audio-recordings', true);
  END IF;
END $$;

-- 允许任何人读取该桶内对象（用于公开访问URL）
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE schemaname = 'storage' 
      AND tablename = 'objects' 
      AND policyname = 'audio_recordings_public_read'
  ) THEN
    CREATE POLICY audio_recordings_public_read
      ON storage.objects FOR SELECT
      USING (bucket_id = 'audio-recordings');
  END IF;
END $$;

-- 允许认证用户上传到该桶
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE schemaname = 'storage' 
      AND tablename = 'objects' 
      AND policyname = 'audio_recordings_authenticated_upload'
  ) THEN
    CREATE POLICY audio_recordings_authenticated_upload
      ON storage.objects FOR INSERT
      WITH CHECK (
        bucket_id = 'audio-recordings' 
        AND auth.role() = 'authenticated'
      );
  END IF;
END $$;

-- 允许认证用户更新/删除自己上传的对象（可选但更安全）
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE schemaname = 'storage' 
      AND tablename = 'objects' 
      AND policyname = 'audio_recordings_authenticated_update_own'
  ) THEN
    CREATE POLICY audio_recordings_authenticated_update_own
      ON storage.objects FOR UPDATE
      USING (bucket_id = 'audio-recordings' AND owner = auth.uid())
      WITH CHECK (bucket_id = 'audio-recordings' AND owner = auth.uid());
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE schemaname = 'storage' 
      AND tablename = 'objects' 
      AND policyname = 'audio_recordings_authenticated_delete_own'
  ) THEN
    CREATE POLICY audio_recordings_authenticated_delete_own
      ON storage.objects FOR DELETE
      USING (bucket_id = 'audio-recordings' AND owner = auth.uid());
  END IF;
END $$;

-- ================================================================
-- Realtime publication: ensure target tables are added to publication
-- ================================================================

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    BEGIN
      EXECUTE 'ALTER PUBLICATION supabase_realtime ADD TABLE public.recording_sessions';
    EXCEPTION WHEN duplicate_object THEN
      -- already added, ignore
      NULL;
    END;
    BEGIN
      EXECUTE 'ALTER PUBLICATION supabase_realtime ADD TABLE public.transcriptions';
    EXCEPTION WHEN duplicate_object THEN
      NULL;
    END;
    BEGIN
      EXECUTE 'ALTER PUBLICATION supabase_realtime ADD TABLE public.ai_summaries';
    EXCEPTION WHEN duplicate_object THEN
      NULL;
    END;
  END IF;
END $$;

COMMIT;
