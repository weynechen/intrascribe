"""
音频格式转换服务
使用ffmpeg进行音频格式转换，确保后续处理的音频格式统一
"""
import logging
import os
import tempfile
import subprocess
from typing import Tuple, Optional, Dict, Any
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class AudioInfo:
    """音频信息类"""
    def __init__(self, sample_rate: int, channels: int, bit_depth: int, duration: float, format: str):
        self.sample_rate = sample_rate
        self.channels = channels  
        self.bit_depth = bit_depth
        self.duration = duration
        self.format = format
    
    def needs_conversion(self, target_sample_rate: int = 16000, target_channels: int = 1, target_bit_depth: int = 16) -> bool:
        """Check if audio needs conversion to target specs"""
        return (self.sample_rate != target_sample_rate or 
                self.channels != target_channels or 
                self.bit_depth != target_bit_depth)
    
    def __str__(self) -> str:
        return f"AudioInfo(sr={self.sample_rate}Hz, ch={self.channels}, bit={self.bit_depth}, dur={self.duration:.2f}s, fmt={self.format})"


class AudioConverter:
    """音频格式转换器"""
    
    # Target audio specifications for speech recognition
    TARGET_SAMPLE_RATE = 16000  # 16kHz
    TARGET_CHANNELS = 1         # Mono
    TARGET_BIT_DEPTH = 16       # 16-bit
    
    def __init__(self):
        self.ffmpeg_path = self._find_ffmpeg()
        if not self.ffmpeg_path:
            logger.error("❌ 未找到ffmpeg！音频处理功能将不可用")
            logger.error("💡 安装指导:")
            for line in self.get_installation_guide().strip().split('\n'):
                if line.strip():
                    logger.error(f"   {line.strip()}")
        else:
            logger.info(f"✅ ffmpeg已准备就绪: {self.ffmpeg_path}")
    
    def _find_ffmpeg(self) -> Optional[str]:
        """查找ffmpeg可执行文件路径"""
        try:
            # Try to find ffmpeg in PATH
            result = subprocess.run(['which', 'ffmpeg'], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            if result.returncode == 0:
                ffmpeg_path = result.stdout.strip()
                logger.info(f"🔧 找到ffmpeg: {ffmpeg_path}")
                return ffmpeg_path
        except Exception as e:
            logger.warning(f"⚠️ 查找ffmpeg失败: {e}")
        
        # Try common installation paths
        common_paths = [
            '/usr/bin/ffmpeg',
            '/usr/local/bin/ffmpeg',
            '/opt/homebrew/bin/ffmpeg',  # macOS homebrew
            'ffmpeg'  # system PATH
        ]
        
        for path in common_paths:
            try:
                result = subprocess.run([path, '-version'], 
                                      capture_output=True, 
                                      timeout=5)
                if result.returncode == 0:
                    logger.info(f"🔧 找到ffmpeg: {path}")
                    return path
            except Exception:
                continue
        
        return None
    
    def is_available(self) -> bool:
        """检查ffmpeg是否可用"""
        return self.ffmpeg_path is not None
    
    def get_installation_guide(self) -> str:
        """获取ffmpeg安装指导"""
        return """
        请安装ffmpeg以获得最佳音频处理性能：
        
        Ubuntu/Debian: sudo apt-get install ffmpeg
        CentOS/RHEL: sudo yum install ffmpeg
        macOS: brew install ffmpeg
        Windows: 从 https://ffmpeg.org/download.html 下载
        
        Docker: 确保容器镜像包含ffmpeg
        """
    
    async def get_audio_info(self, input_file_path: str) -> AudioInfo:
        """
        获取音频文件的详细信息
        
        Args:
            input_file_path: 输入音频文件路径
            
        Returns:
            AudioInfo: 音频信息对象
        """
        try:
            if not self.ffmpeg_path:
                raise Exception("ffmpeg不可用，无法获取音频信息")
            
            return await self._get_audio_info_ffmpeg(input_file_path)
        except Exception as e:
            logger.error(f"❌ 获取音频信息失败: {e}")
            raise
    
    async def _get_audio_info_ffmpeg(self, input_file_path: str) -> AudioInfo:
        """使用ffprobe获取音频信息"""
        try:
            # Use ffprobe to get detailed audio information (ffmpeg suite)
            ffprobe_path = self.ffmpeg_path.replace('ffmpeg', 'ffprobe')
            
            cmd = [
                ffprobe_path,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                '-select_streams', 'a:0',  # Select first audio stream
                input_file_path
            ]
            
            logger.debug(f"🔧 执行ffprobe命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                error_msg = f"ffprobe获取音频信息失败: {result.stderr}"
                logger.error(f"❌ {error_msg}")
                raise Exception(error_msg)
            
            # Parse JSON output
            info = json.loads(result.stdout)
            streams = info.get('streams', [])
            
            if not streams:
                raise Exception("未找到音频流")
            
            audio_stream = streams[0]
            
            # Extract audio parameters
            sample_rate = int(audio_stream.get('sample_rate', 0))
            channels = int(audio_stream.get('channels', 0))
            duration = float(audio_stream.get('duration', 0))
            
            # Get bit depth from sample format
            sample_fmt = audio_stream.get('sample_fmt', '')
            bit_depth = self._parse_bit_depth_from_sample_fmt(sample_fmt)
            
            # Get format from codec
            codec_name = audio_stream.get('codec_name', 'unknown')
            
            audio_info = AudioInfo(
                sample_rate=sample_rate,
                channels=channels,
                bit_depth=bit_depth,
                duration=duration,
                format=codec_name
            )
            
            logger.info(f"📊 音频信息: {audio_info}")
            return audio_info
            
        except subprocess.TimeoutExpired:
            logger.error("❌ ffprobe获取音频信息超时")
            raise Exception("获取音频信息超时")
        except Exception as e:
            logger.error(f"❌ ffprobe获取音频信息失败: {e}")
            raise
    

    
    def _parse_bit_depth_from_sample_fmt(self, sample_fmt: str) -> int:
        """从ffmpeg的sample_fmt解析位深"""
        # Common sample formats and their bit depths
        fmt_mapping = {
            'u8': 8, 'u8p': 8,
            's16': 16, 's16p': 16,
            's32': 32, 's32p': 32,
            'flt': 32, 'fltp': 32,  # float32
            'dbl': 64, 'dblp': 64   # float64
        }
        return fmt_mapping.get(sample_fmt, 16)  # Default to 16-bit
    
    async def convert_mp3_to_wav(self, input_file_path: str, output_file_path: Optional[str] = None) -> str:
        """
        将MP3文件转换为WAV格式
        
        Args:
            input_file_path: 输入MP3文件路径
            output_file_path: 输出WAV文件路径，如果为None则自动生成
            
        Returns:
            str: 转换后的WAV文件路径
        """
        try:
            # 生成输出文件路径
            if output_file_path is None:
                input_path = Path(input_file_path)
                output_file_path = str(input_path.parent / f"{input_path.stem}_converted.wav")
            
            logger.info(f"🔄 开始转换音频格式: {input_file_path} -> {output_file_path}")
            
            if not self.ffmpeg_path:
                raise Exception("ffmpeg不可用，无法进行音频转换")
            
            # 使用ffmpeg进行转换
            return await self._ffmpeg_convert(input_file_path, output_file_path)
                
        except Exception as e:
            logger.error(f"❌ 音频格式转换失败: {e}")
            raise
    
    async def convert_to_target_specs(self, input_file_path: str, output_file_path: Optional[str] = None) -> str:
        """
        将音频转换为目标规格（16kHz, 单声道, 16bit）
        
        Args:
            input_file_path: 输入音频文件路径
            output_file_path: 输出音频文件路径，如果为None则自动生成
            
        Returns:
            str: 转换后的音频文件路径
        """
        try:
            # 生成输出文件路径
            if output_file_path is None:
                input_path = Path(input_file_path)
                output_file_path = str(input_path.parent / f"{input_path.stem}_normalized.wav")
            
            logger.info(f"🔄 转换音频为目标规格: {input_file_path} -> {output_file_path}")
            
            if not self.ffmpeg_path:
                raise Exception("ffmpeg不可用，无法进行音频规格转换")
            
            # 使用ffmpeg进行规格转换
            return await self._ffmpeg_convert_to_specs(input_file_path, output_file_path)
                
        except Exception as e:
            logger.error(f"❌ 转换音频规格失败: {e}")
            raise
    
    async def _ffmpeg_convert_to_specs(self, input_path: str, output_path: str) -> str:
        """使用ffmpeg转换音频为目标规格"""
        try:
            cmd = [
                self.ffmpeg_path,
                '-i', input_path,                          # Input file
                '-acodec', 'pcm_s16le',                    # 16-bit PCM encoding
                '-ar', str(self.TARGET_SAMPLE_RATE),       # 16kHz sample rate
                '-ac', str(self.TARGET_CHANNELS),          # Mono (1 channel)
                '-af', 'volume=1.0',                       # Normalize volume
                '-y',                                      # Overwrite output file
                output_path
            ]
            
            logger.debug(f"🔧 执行ffmpeg转换命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode != 0:
                error_msg = f"ffmpeg转换失败: {result.stderr}"
                logger.error(f"❌ {error_msg}")
                raise Exception(error_msg)
            
            # 验证输出文件
            if not os.path.exists(output_path):
                raise Exception("转换完成但输出文件不存在")
            
            output_size = os.path.getsize(output_path)
            if output_size == 0:
                raise Exception("转换后的文件为空")
            
            logger.info(f"✅ ffmpeg规格转换成功: {output_path} (大小: {output_size} bytes)")
            return output_path
            
        except subprocess.TimeoutExpired:
            logger.error("❌ ffmpeg转换超时")
            raise Exception("音频转换超时")
        except Exception as e:
            logger.error(f"❌ ffmpeg规格转换失败: {e}")
            raise
    


    async def _ffmpeg_convert(self, input_path: str, output_path: str) -> str:
        """使用ffmpeg进行音频转换"""
        try:
            # ffmpeg命令参数 - 优化语音识别
            cmd = [
                self.ffmpeg_path,
                '-i', input_path,                          # 输入文件
                '-acodec', 'pcm_s16le',                    # 使用PCM 16位编码
                '-ar', str(self.TARGET_SAMPLE_RATE),       # 采样率16kHz (适合语音识别)
                '-ac', str(self.TARGET_CHANNELS),          # 单声道
                '-af', 'volume=1.0',                       # 标准化音量
                '-y',                                      # 覆盖输出文件
                output_path
            ]
            
            logger.debug(f"🔧 执行ffmpeg命令: {' '.join(cmd)}")
            
            # 执行转换
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode != 0:
                error_msg = f"ffmpeg转换失败: {result.stderr}"
                logger.error(f"❌ {error_msg}")
                raise Exception(error_msg)
            
            # 验证输出文件是否生成
            if not os.path.exists(output_path):
                raise Exception("转换完成但输出文件不存在")
            
            # 检查文件大小
            output_size = os.path.getsize(output_path)
            if output_size == 0:
                raise Exception("转换后的文件为空")
            
            logger.info(f"✅ ffmpeg转换成功: {output_path} (大小: {output_size} bytes)")
            return output_path
            
        except subprocess.TimeoutExpired:
            logger.error("❌ ffmpeg转换超时")
            raise Exception("音频转换超时")
        except Exception as e:
            logger.error(f"❌ ffmpeg转换失败: {e}")
            raise
    

    
    async def process_audio_if_needed(self, input_file_path: str, file_format: str) -> Tuple[str, bool]:
        """
        检查音频参数并根据需要进行转换
        
        Args:
            input_file_path: 输入文件路径
            file_format: 文件格式 ('mp3', 'wav', etc.)
            
        Returns:
            Tuple[str, bool]: (处理后的文件路径, 是否进行了转换)
        """
        try:
            # 获取音频信息
            audio_info = await self.get_audio_info(input_file_path)
            
            # 检查是否需要转换
            needs_conversion = audio_info.needs_conversion(
                self.TARGET_SAMPLE_RATE, 
                self.TARGET_CHANNELS, 
                self.TARGET_BIT_DEPTH
            )
            
            if needs_conversion:
                logger.info(f"🔄 音频需要转换: {audio_info}")
                logger.info(f"🎯 目标规格: {self.TARGET_SAMPLE_RATE}Hz, {self.TARGET_CHANNELS}ch, {self.TARGET_BIT_DEPTH}bit")
                
                # 生成输出文件路径
                input_path = Path(input_file_path)
                output_file_path = str(input_path.parent / f"{input_path.stem}_normalized.wav")
                
                # 执行转换
                converted_path = await self.convert_to_target_specs(input_file_path, output_file_path)
                
                logger.info(f"✅ 音频转换完成: {converted_path}")
                return converted_path, True
            else:
                logger.info(f"✅ 音频已符合要求，无需转换: {audio_info}")
                return input_file_path, False
                
        except Exception as e:
            logger.error(f"❌ 处理音频失败: {e}")
            raise

    async def convert_to_wav_if_needed(self, input_file_path: str, file_format: str) -> Tuple[str, bool]:
        """
        如果需要，将音频文件转换为WAV格式并确保符合目标规格
        
        Args:
            input_file_path: 输入文件路径
            file_format: 文件格式 ('mp3', 'wav', etc.)
            
        Returns:
            Tuple[str, bool]: (处理后的文件路径, 是否进行了转换)
        """
        return await self.process_audio_if_needed(input_file_path, file_format)
    
    def cleanup_converted_file(self, file_path: str, was_converted: bool):
        """清理转换生成的临时文件"""
        if was_converted and file_path:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    logger.debug(f"🗑️ 清理转换文件: {file_path}")
            except Exception as e:
                logger.warning(f"⚠️ 清理转换文件失败: {e}")


# 全局实例
audio_converter = AudioConverter() 