"""
AudioProcessor class for audio format conversion and metadata embedding.
Handles MP3 conversion, metadata calculation, and artwork embedding using FFmpeg and Mutagen.
"""

import subprocess
import os
import logging
import shutil
from datetime import datetime, date
from typing import Optional, Dict, Any
from pathlib import Path

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TRCK, TDRC, APIC
from PIL import Image

from ..config import config


class AudioProcessor:
    """
    Audio processing class for format conversion and metadata embedding.
    Handles MP3 conversion using FFmpeg and metadata embedding using Mutagen.
    """
    
    def __init__(self):
        """Initialize AudioProcessor."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def process_audio_file(
        self,
        input_path: str,
        output_path: str,
        metadata: Dict[str, Any],
        artwork_path: Optional[str] = None,
        recording_date: Optional[datetime] = None
    ) -> bool:
        """
        Process audio file: convert to MP3 and embed metadata.
        
        Args:
            input_path: Path to input audio file
            output_path: Path for output MP3 file
            metadata: Dictionary containing metadata (artist, album, album_artist)
            artwork_path: Optional path to artwork image file
            recording_date: Date of recording (defaults to current date)
        
        Returns:
            True if processing successful, False otherwise
        """
        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Convert to MP3 if needed
            if not self._convert_to_mp3(input_path, output_path):
                return False
            
            # Calculate and embed metadata
            if not self._embed_metadata(output_path, metadata, artwork_path, recording_date):
                return False
            
            self.logger.info(f"Successfully processed audio file: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing audio file: {e}")
            return False
    
    def _convert_to_mp3(self, input_path: str, output_path: str) -> bool:
        """
        Convert audio file to MP3 format using FFmpeg.
        
        Args:
            input_path: Path to input audio file
            output_path: Path for output MP3 file
        
        Returns:
            True if conversion successful, False otherwise
        """
        try:
            # Check if input file exists
            if not os.path.exists(input_path):
                self.logger.error(f"Input file does not exist: {input_path}")
                return False
            
            # If input is already MP3 and same as output, just copy
            if input_path.lower().endswith('.mp3') and input_path == output_path:
                self.logger.info("Input is already MP3 at target location, no conversion needed")
                return True
            
            # If input is already MP3 but different location, copy it
            if input_path.lower().endswith('.mp3'):
                shutil.copy2(input_path, output_path)
                self.logger.info(f"Copied MP3 file from {input_path} to {output_path}")
                return True
            
            # Build FFmpeg command for conversion
            cmd = [
                config.FFMPEG_PATH,
                '-y',  # Overwrite output file
                '-i', input_path,
                '-codec:a', 'libmp3lame',  # Use LAME MP3 encoder
                '-b:a', '192k',  # 192 kbps bitrate
                '-ar', '44100',  # 44.1 kHz sample rate
                '-ac', '2',  # Stereo
                '-f', 'mp3',  # MP3 format
                output_path
            ]
            
            self.logger.info(f"Converting audio with FFmpeg: {' '.join(cmd)}")
            
            # Run FFmpeg conversion
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                self.logger.info(f"Successfully converted {input_path} to MP3")
                return True
            else:
                self.logger.error(f"FFmpeg conversion failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error("FFmpeg conversion timed out")
            return False
        except Exception as e:
            self.logger.error(f"Error during MP3 conversion: {e}")
            return False
    
    def _embed_metadata(
        self,
        mp3_path: str,
        metadata: Dict[str, Any],
        artwork_path: Optional[str] = None,
        recording_date: Optional[datetime] = None
    ) -> bool:
        """
        Embed metadata into MP3 file using Mutagen.
        
        Args:
            mp3_path: Path to MP3 file
            metadata: Dictionary containing metadata
            artwork_path: Optional path to artwork image
            recording_date: Date of recording
        
        Returns:
            True if metadata embedding successful, False otherwise
        """
        try:
            # Load MP3 file
            audio_file = MP3(mp3_path, ID3=ID3)
            
            # Add ID3 tag if it doesn't exist
            if audio_file.tags is None:
                audio_file.add_tags()
            
            # Calculate recording date
            if recording_date is None:
                recording_date = datetime.now()
            
            # Generate title in "YYYY-MM-DD Show" format
            title = self._generate_title(recording_date, metadata.get('name', 'Show'))
            
            # Calculate track number (days since January 1, 2020)
            track_number = self._calculate_track_number(recording_date)
            
            # Set metadata tags
            audio_file.tags.add(TIT2(encoding=3, text=title))  # Title
            audio_file.tags.add(TPE1(encoding=3, text=metadata.get('artist', '')))  # Artist
            audio_file.tags.add(TALB(encoding=3, text=metadata.get('album', '')))  # Album
            audio_file.tags.add(TPE2(encoding=3, text=metadata.get('album_artist', '')))  # Album Artist
            audio_file.tags.add(TRCK(encoding=3, text=str(track_number)))  # Track Number
            audio_file.tags.add(TDRC(encoding=3, text=str(recording_date.year)))  # Recording Date
            
            # Embed artwork if provided
            if artwork_path and os.path.exists(artwork_path):
                if not self._embed_artwork(audio_file, artwork_path):
                    self.logger.warning(f"Failed to embed artwork from {artwork_path}")
            
            # Save the file
            audio_file.save()
            
            self.logger.info(f"Successfully embedded metadata in {mp3_path}")
            self.logger.debug(f"Metadata: Title='{title}', Artist='{metadata.get('artist')}', "
                            f"Album='{metadata.get('album')}', Track={track_number}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error embedding metadata: {e}")
            return False
    
    def _generate_title(self, recording_date: datetime, show_name: str = "Show") -> str:
        """
        Generate title in "YYYY-MM-DD Show" format.
        
        Args:
            recording_date: Date of recording
            show_name: Name of the show (defaults to "Show")
        
        Returns:
            Generated title string
        """
        date_str = recording_date.strftime("%Y-%m-%d")
        return f"{date_str} {show_name}"
    
    def _calculate_track_number(self, recording_date: datetime) -> int:
        """
        Calculate track number as days since January 1, 2020.
        
        Args:
            recording_date: Date of recording
        
        Returns:
            Track number (days since Jan 1, 2020)
        """
        base_date = date(2020, 1, 1)
        recording_date_only = recording_date.date()
        
        delta = recording_date_only - base_date
        return max(1, delta.days + 1)  # Ensure track number is at least 1
    
    def _embed_artwork(self, audio_file: MP3, artwork_path: str) -> bool:
        """
        Embed artwork into MP3 file.
        
        Args:
            audio_file: MP3 file object from Mutagen
            artwork_path: Path to artwork image file
        
        Returns:
            True if artwork embedding successful, False otherwise
        """
        try:
            # Validate and process artwork image
            processed_artwork = self._process_artwork_image(artwork_path)
            if not processed_artwork:
                return False
            
            # Determine MIME type
            artwork_ext = Path(artwork_path).suffix.lower()
            if artwork_ext in ['.jpg', '.jpeg']:
                mime_type = 'image/jpeg'
            elif artwork_ext == '.png':
                mime_type = 'image/png'
            else:
                self.logger.error(f"Unsupported artwork format: {artwork_ext}")
                return False
            
            # Read artwork data
            with open(processed_artwork, 'rb') as artwork_file:
                artwork_data = artwork_file.read()
            
            # Add artwork to MP3
            audio_file.tags.add(
                APIC(
                    encoding=3,  # UTF-8
                    mime=mime_type,
                    type=3,  # Cover (front)
                    desc='Cover',
                    data=artwork_data
                )
            )
            
            # Clean up temporary processed file if it was created
            if processed_artwork != artwork_path:
                os.remove(processed_artwork)
            
            self.logger.info(f"Successfully embedded artwork from {artwork_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error embedding artwork: {e}")
            return False
    
    def _process_artwork_image(self, artwork_path: str) -> Optional[str]:
        """
        Process artwork image to ensure it meets requirements.
        
        Args:
            artwork_path: Path to original artwork image
        
        Returns:
            Path to processed image, or None if processing failed
        """
        try:
            # Open and validate image
            with Image.open(artwork_path) as img:
                # Convert to RGB if necessary
                if img.mode not in ['RGB', 'RGBA']:
                    img = img.convert('RGB')
                
                # Check file size
                file_size_mb = os.path.getsize(artwork_path) / (1024 * 1024)
                if file_size_mb > config.MAX_ARTWORK_SIZE_MB:
                    self.logger.warning(f"Artwork file too large ({file_size_mb:.1f}MB), "
                                      f"max allowed: {config.MAX_ARTWORK_SIZE_MB}MB")
                    
                    # Resize image to reduce file size
                    max_dimension = 800
                    if img.width > max_dimension or img.height > max_dimension:
                        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                        
                        # Save resized image to temporary file
                        temp_path = artwork_path + '.processed.jpg'
                        img.save(temp_path, 'JPEG', quality=85, optimize=True)
                        
                        self.logger.info(f"Resized artwork to {img.width}x{img.height}")
                        return temp_path
                
                # Image is acceptable as-is
                return artwork_path
                
        except Exception as e:
            self.logger.error(f"Error processing artwork image: {e}")
            return None
    
    def get_audio_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Get information about an audio file.
        
        Args:
            file_path: Path to audio file
        
        Returns:
            Dictionary with audio file information, or None if error
        """
        try:
            if not os.path.exists(file_path):
                return None
            
            # Use FFprobe to get audio information
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                file_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                import json
                probe_data = json.loads(result.stdout)
                
                # Extract relevant information
                format_info = probe_data.get('format', {})
                streams = probe_data.get('streams', [])
                
                audio_stream = None
                for stream in streams:
                    if stream.get('codec_type') == 'audio':
                        audio_stream = stream
                        break
                
                info = {
                    'file_path': file_path,
                    'file_size_bytes': int(format_info.get('size', 0)),
                    'duration_seconds': float(format_info.get('duration', 0)),
                    'format_name': format_info.get('format_name', ''),
                    'bit_rate': int(format_info.get('bit_rate', 0)),
                }
                
                if audio_stream:
                    info.update({
                        'codec_name': audio_stream.get('codec_name', ''),
                        'sample_rate': int(audio_stream.get('sample_rate', 0)),
                        'channels': int(audio_stream.get('channels', 0)),
                        'channel_layout': audio_stream.get('channel_layout', ''),
                    })
                
                return info
            else:
                self.logger.error(f"FFprobe failed: {result.stderr}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting audio info: {e}")
            return None
    
    def validate_mp3_file(self, file_path: str) -> bool:
        """
        Validate that a file is a proper MP3 with metadata.
        
        Args:
            file_path: Path to MP3 file
        
        Returns:
            True if file is valid MP3 with metadata, False otherwise
        """
        try:
            if not os.path.exists(file_path):
                return False
            
            # Load MP3 file
            audio_file = MP3(file_path, ID3=ID3)
            
            # Check if file has ID3 tags
            if audio_file.tags is None:
                self.logger.warning(f"MP3 file has no ID3 tags: {file_path}")
                return False
            
            # Check for required tags
            required_tags = ['TIT2', 'TPE1', 'TALB', 'TPE2', 'TRCK']
            missing_tags = []
            
            for tag in required_tags:
                if tag not in audio_file.tags:
                    missing_tags.append(tag)
            
            if missing_tags:
                self.logger.warning(f"MP3 file missing tags {missing_tags}: {file_path}")
                return False
            
            self.logger.info(f"MP3 file validation successful: {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating MP3 file: {e}")
            return False