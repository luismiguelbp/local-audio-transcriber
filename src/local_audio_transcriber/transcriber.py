"""
Audio Transcription Module

Handles audio file processing, chunking for long files, and OpenAI Whisper API integration.
"""

import os
import tempfile
import logging
from pathlib import Path
from typing import Callable, Optional

from openai import OpenAI
from pydub import AudioSegment
from pydub.silence import detect_silence


# Constants
MAX_FILE_SIZE_MB = 25
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
CHUNK_DURATION_MS = 10 * 60 * 1000  # 10 minutes in milliseconds
OVERLAP_MS = 1000  # 1 second overlap between chunks
MIN_SILENCE_LEN = 500  # Minimum silence length in ms
SILENCE_THRESH = -40  # Silence threshold in dB

# Formats the OpenAI Whisper API accepts directly as upload payload.
# Inputs outside this set (e.g. .mkv) must have their audio extracted to a
# Whisper-compatible container before upload.
WHISPER_NATIVE_FORMATS = {'.mp3', '.wav', '.m4a', '.mp4', '.webm', '.ogg', '.flac'}
logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Custom exception for transcription errors."""
    pass


class AudioTranscriber:
    """
    Handles audio transcription using OpenAI's Whisper API.
    Automatically chunks long audio files to stay within API limits.
    """
    
    SUPPORTED_FORMATS = {'.mp3', '.wav', '.m4a', '.mp4', '.mkv', '.webm', '.ogg', '.flac'}
    
    def __init__(self, api_key: str):
        """
        Initialize the transcriber with an OpenAI API key.
        
        Args:
            api_key: OpenAI API key for Whisper access
        """
        self.client = OpenAI(api_key=api_key)
    
    def is_supported_format(self, file_path: str) -> bool:
        """Check if the file format is supported."""
        return Path(file_path).suffix.lower() in self.SUPPORTED_FORMATS
    
    def get_file_info(self, file_path: str) -> dict:
        """
        Get information about an audio file.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Dictionary with file info (size, duration, needs_chunking)
        """
        file_size = os.path.getsize(file_path)
        audio = AudioSegment.from_file(file_path)
        duration_seconds = len(audio) / 1000
        
        return {
            'size_bytes': file_size,
            'size_mb': file_size / (1024 * 1024),
            'duration_seconds': duration_seconds,
            'duration_formatted': self._format_duration(duration_seconds),
            'needs_chunking': file_size > MAX_FILE_SIZE_BYTES
        }
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"
    
    def _find_best_split_point(self, audio: AudioSegment, target_ms: int, 
                                search_range_ms: int = 5000) -> int:
        """
        Find the best split point near the target position, preferring silence.
        
        Args:
            audio: Audio segment to analyze
            target_ms: Target split position in milliseconds
            search_range_ms: Range to search for silence around target
            
        Returns:
            Best split position in milliseconds
        """
        start = max(0, target_ms - search_range_ms)
        end = min(len(audio), target_ms + search_range_ms)
        
        # Extract the search region
        search_region = audio[start:end]
        
        # Detect silence in the search region
        silences = detect_silence(
            search_region, 
            min_silence_len=MIN_SILENCE_LEN, 
            silence_thresh=SILENCE_THRESH
        )
        
        if silences:
            # Find the silence closest to the target
            target_in_region = target_ms - start
            best_silence = min(silences, key=lambda s: abs((s[0] + s[1]) / 2 - target_in_region))
            # Return the middle of the silence, adjusted to absolute position
            return start + (best_silence[0] + best_silence[1]) // 2
        
        # No silence found, use the target position
        return target_ms
    
    def _chunk_audio(self, file_path: str, 
                     progress_callback: Optional[Callable[[str, float], None]] = None) -> list[str]:
        """
        Split a long audio file into smaller chunks.
        
        Args:
            file_path: Path to the audio file
            progress_callback: Optional callback for progress updates (message, progress)
            
        Returns:
            List of paths to temporary chunk files
        """
        if progress_callback:
            progress_callback("Loading audio file...", 0.0)
        
        audio = AudioSegment.from_file(file_path)
        total_duration = len(audio)
        
        # Calculate number of chunks needed
        num_chunks = (total_duration // CHUNK_DURATION_MS) + 1
        chunk_paths = []
        
        if progress_callback:
            progress_callback(f"Splitting into {num_chunks} chunks...", 0.05)
        
        position = 0
        chunk_index = 0
        
        while position < total_duration:
            # Calculate end position for this chunk
            end_position = min(position + CHUNK_DURATION_MS, total_duration)
            
            # If not the last chunk, find a good split point
            if end_position < total_duration:
                end_position = self._find_best_split_point(audio, end_position)
            
            # Extract chunk
            chunk = audio[position:end_position]
            
            # Save chunk to temporary file
            temp_file = tempfile.NamedTemporaryFile(
                suffix='.mp3', 
                delete=False,
                prefix=f'chunk_{chunk_index:03d}_'
            )
            chunk.export(temp_file.name, format='mp3', bitrate='128k')
            chunk_paths.append(temp_file.name)
            
            # Update position (with small overlap for context)
            position = end_position - OVERLAP_MS if end_position < total_duration else total_duration
            chunk_index += 1
            
            if progress_callback:
                split_progress = 0.05 + (0.15 * (position / total_duration))
                progress_callback(f"Created chunk {chunk_index}/{num_chunks}", split_progress)
        
        return chunk_paths
    
    def _transcribe_single_file(self, file_path: str) -> str:
        """
        Transcribe a single audio file using the Whisper API.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Transcription text
        """
        with open(file_path, 'rb') as audio_file:
            response = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        return response
    
    def _extract_audio_to_temp_mp3(self, file_path: str) -> str:
        """
        Decode any container readable by FFmpeg and write the audio track to a
        temporary .mp3 file. Used for inputs Whisper does not accept directly
        (e.g. .mkv).

        Returns:
            Path to the temporary .mp3 file. Caller is responsible for deletion.
        """
        audio = AudioSegment.from_file(file_path)
        temp_file = tempfile.NamedTemporaryFile(
            suffix='.mp3',
            delete=False,
            prefix='extracted_audio_'
        )
        temp_file.close()
        audio.export(temp_file.name, format='mp3', bitrate='128k')
        return temp_file.name

    def _cleanup_chunks(self, chunk_paths: list[str]):
        """Remove temporary chunk files."""
        for path in chunk_paths:
            try:
                os.unlink(path)
            except OSError:
                pass  # Ignore cleanup errors
    
    def transcribe(self, file_path: str, 
                   progress_callback: Optional[Callable[[str, float], None]] = None) -> str:
        """
        Transcribe an audio file, automatically handling long files.
        
        Args:
            file_path: Path to the audio file
            progress_callback: Optional callback for progress updates (message, progress 0.0-1.0)
            
        Returns:
            Full transcription text
            
        Raises:
            TranscriptionError: If transcription fails
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file format is not supported
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")
        
        if not self.is_supported_format(file_path):
            raise ValueError(f"Unsupported file format: {Path(file_path).suffix}")

        extracted_audio_path: Optional[str] = None
        try:
            logger.info("Starting transcription for %s", file_path)
            # Whisper does not accept every container we support as input
            # (e.g. .mkv). For those, extract the audio track to a temp .mp3
            # up front and operate on that file for the rest of the pipeline.
            if Path(file_path).suffix.lower() not in WHISPER_NATIVE_FORMATS:
                if progress_callback:
                    progress_callback("Extracting audio track...", 0.0)
                extracted_audio_path = self._extract_audio_to_temp_mp3(file_path)
                working_path = extracted_audio_path
                logger.info("Extracted non-native format to temporary mp3 for %s", file_path)
            else:
                working_path = file_path

            file_info = self.get_file_info(working_path)
            
            if progress_callback:
                progress_callback(f"File duration: {file_info['duration_formatted']}", 0.0)
            
            if not file_info['needs_chunking']:
                # Small file - transcribe directly
                if progress_callback:
                    progress_callback("Transcribing...", 0.2)
                
                result = self._transcribe_single_file(working_path)
                logger.info("Completed direct transcription for %s", file_path)
                
                if progress_callback:
                    progress_callback("Complete!", 1.0)
                
                return result
            
            # Large file - chunk and transcribe
            chunk_paths = self._chunk_audio(working_path, progress_callback)
            logger.info("Transcribing %s chunk(s) for %s", len(chunk_paths), file_path)
            
            try:
                transcriptions = []
                num_chunks = len(chunk_paths)
                
                for i, chunk_path in enumerate(chunk_paths):
                    if progress_callback:
                        base_progress = 0.2 + (0.75 * (i / num_chunks))
                        progress_callback(f"Transcribing chunk {i + 1}/{num_chunks}...", base_progress)
                    
                    chunk_text = self._transcribe_single_file(chunk_path)
                    transcriptions.append(chunk_text.strip())
                
                # Merge transcriptions
                if progress_callback:
                    progress_callback("Merging transcriptions...", 0.95)
                
                full_text = self._merge_transcriptions(transcriptions)
                
                if progress_callback:
                    progress_callback("Complete!", 1.0)
                
                return full_text
                
            finally:
                self._cleanup_chunks(chunk_paths)
                
        except Exception as e:
            logger.exception("Transcription failed for %s", file_path)
            raise TranscriptionError(f"Transcription failed: {str(e)}") from e
        finally:
            if extracted_audio_path:
                try:
                    os.unlink(extracted_audio_path)
                except OSError:
                    pass  # Ignore cleanup errors
    
    def _merge_transcriptions(self, transcriptions: list[str]) -> str:
        """
        Merge multiple transcription chunks into a single text.
        Handles overlapping content from chunk boundaries.
        
        Args:
            transcriptions: List of transcription texts
            
        Returns:
            Merged transcription text
        """
        if not transcriptions:
            return ""
        
        if len(transcriptions) == 1:
            return transcriptions[0]
        
        # Simple merge with double newline between chunks
        # The overlap in audio helps ensure we don't lose content
        merged = []
        
        for i, text in enumerate(transcriptions):
            text = text.strip()
            if not text:
                continue
                
            if i == 0:
                merged.append(text)
            else:
                # Check if there's overlap with previous chunk
                # (first few words might be repeated)
                prev_words = merged[-1].split()[-10:] if merged else []
                curr_words = text.split()[:10]
                
                # Find overlap
                overlap_start = 0
                for j in range(min(len(prev_words), len(curr_words))):
                    if prev_words[-(j+1):] == curr_words[:j+1]:
                        overlap_start = j + 1
                
                # Remove overlap from current text
                if overlap_start > 0:
                    words = text.split()
                    text = ' '.join(words[overlap_start:])
                
                if text:
                    merged.append(text)
        
        return '\n\n'.join(merged)


def save_transcription(text: str, output_path: str) -> str:
    """
    Save transcription text to a file.
    
    Args:
        text: Transcription text
        output_path: Path for the output file
        
    Returns:
        Actual path where the file was saved
    """
    output_path = Path(output_path)
    
    # Ensure .txt extension
    if output_path.suffix.lower() != '.txt':
        output_path = output_path.with_suffix('.txt')
    
    # Create directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write the file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(text)
    
    return str(output_path)
