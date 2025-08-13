import numpy as np
from typing import Protocol, Tuple
import tempfile
import wave
import os
import logging
import torch

from .config import settings

logger = logging.getLogger(__name__)

from funasr import AutoModel


class STTModel(Protocol):
    def stt(self, audio: Tuple[int, np.ndarray]) -> str: ...


class LocalFunASR:
    """本地 ASR 模型适配器，实现 STTModel 协议"""
    
    def __init__(self):
        """
        初始化本地 STT 模型
        """
        self.model = None
        
        # 从配置获取参数
        self.model_dir = settings.stt.model_dir
        self.output_dir = settings.stt.output_dir
        self.delete_audio_file = settings.stt.delete_audio_file
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        
        logger.info(f"使用模型目录: {self.model_dir}")
        logger.info(f"使用输出目录: {self.output_dir}")
        logger.info(f"删除音频文件: {self.delete_audio_file}")
        
        if torch.cuda.is_available():
            device = "cuda:0"
            logger.info("检测到CUDA设备，将使用GPU加速")
        else:
            device = "cpu"
            logger.info("未检测到CUDA设备，将使用CPU")
        
        self.model = AutoModel(
            model=self.model_dir,
            vad_kwargs={"max_single_segment_time": 30000},
            hub="ms",  # 使用 ModelScope hub 自动下载模型
            device=device,  # 动态设置设备
            disable_update=True,  # 禁用自动更新检查
            # disable_log=True,  # 禁用详细日志
        )
    
    def stt(self, audio: Tuple[int, np.ndarray]) -> str:
        """
        语音转文本接口
        
        Args:
            audio: (sample_rate, audio_array) 元组
            
        Returns:
            转录的文本字符串
        """
        sample_rate, audio_array = audio
        
        # 如果模型未加载，返回模拟结果
        if self.model is None:
            return f"[模拟转录] 检测到 {len(audio_array)} 个音频样本，采样率: {sample_rate}Hz"
        
        try:
            # 将 numpy 数组转换为合适的格式
            if audio_array.dtype == np.float32:
                # 如果是 float32，转换为 int16
                audio_array = (audio_array * 32767).astype(np.int16)
            elif audio_array.dtype != np.int16:
                audio_array = audio_array.astype(np.int16)
            
            # 根据配置决定是否使用临时文件还是保存到输出目录
            if self.delete_audio_file:
                # 使用临时文件
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                    tmp_path = tmp_file.name
            else:
                # 保存到输出目录
                import time
                timestamp = int(time.time() * 1000)
                tmp_path = os.path.join(self.output_dir, f"audio_{timestamp}.wav")
            
            # 保存音频文件
            with wave.open(tmp_path, 'wb') as wav_file:
                wav_file.setnchannels(1)  # 单声道
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_array.tobytes())
            
            # 使用 FunASR 进行转录
            result = self.model.generate(
                input=tmp_path,
                cache={},
                language="auto",
                use_itn=True,
                batch_size_s=60,
            )
            
            # 处理转录结果
            text = result[0]["text"] if result and len(result) > 0 else ""
            
            # 根据配置决定是否删除音频文件
            if self.delete_audio_file:
                try:
                    os.unlink(tmp_path)
                except:
                    pass
            else:
                logger.info(f"音频文件已保存至: {tmp_path}")
                
            return text if text else ""
            
        except Exception as e:
            logger.error(f"语音转录错误: {e}")
            return f"转录失败: {str(e)}" 