export type SubtitleTrack = {
  source_format: 'vtt' | 'srt' | 'ass';
  delivery_format: 'vtt' | 'ass';
  renderer: 'native' | 'assjs';
  url: string;
};

export type SubtitleManifestResponse = {
  subtitles: SubtitleTrack[];
};
