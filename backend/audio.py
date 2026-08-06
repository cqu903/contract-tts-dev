"""Audio artifacts shared by engines, storage, and HTTP responses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AudioFormat(Enum):
    """Canonical audio encodings supported by the service."""

    WAV = ("wav", "audio/wav", ".wav")
    MP3 = ("mp3", "audio/mpeg", ".mp3")

    def __init__(self, format_id: str, media_type: str, file_extension: str):
        self.format_id = format_id
        self.media_type = media_type
        self.file_extension = file_extension

    @classmethod
    def from_metadata(
        cls,
        format_id: object,
        media_type: object,
        file_extension: object,
    ) -> AudioFormat | None:
        """Resolve manifest metadata only when all canonical fields agree."""
        for audio_format in cls:
            if (
                format_id == audio_format.format_id
                and media_type == audio_format.media_type
                and file_extension == audio_format.file_extension
            ):
                return audio_format
        return None


@dataclass(frozen=True)
class AudioArtifact:
    """A complete, playable segment plus its canonical encoding metadata."""

    data: bytes
    audio_format: AudioFormat

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes) or not self.data:
            raise ValueError("audio artifact data must be non-empty bytes")
        if not isinstance(self.audio_format, AudioFormat):
            raise ValueError("audio artifact format must be canonical")

    @property
    def media_type(self) -> str:
        return self.audio_format.media_type

    @property
    def file_extension(self) -> str:
        return self.audio_format.file_extension
