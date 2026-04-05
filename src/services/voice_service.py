import os
from openai import OpenAI
from src.config import settings
from src.services.agent_log_service import agent_trace
import logging

logger = logging.getLogger(__name__)

class VoiceService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPEN_AI_API_KEY)
        self.voice_dir = "logs/voice_notes"
        os.makedirs(self.voice_dir, exist_ok=True)

    @agent_trace("VoiceService.generate_summary")
    async def generate_summary(self, text: str, filename: str) -> str:
        """
        Uses OpenAI TTS-1 to generate a voice summary of a trade thesis.
        """
        try:
            file_path = os.path.join(self.voice_dir, f"{filename}.mp3")
            
            response = self.client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text
            )
            
            response.stream_to_file(file_path)
            logger.info(f"VoiceService: Generated summary saved to {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"VoiceService: TTS failed: {e}")
            return ""

voice_service = VoiceService()
