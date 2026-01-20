import os
import re
import typing
from urllib.parse import ParseResult, urlparse, urlunparse

from yt_dlp.extractor.common import InfoExtractor  # type: ignore
from yt_dlp.utils import int_or_none, str_or_none, traverse_obj  # type: ignore


class FBCIE(InfoExtractor):
    _APIKEY: str | None = None
    _NETRC_MACHINE: str = "fbc_uploader"
    _VALID_URL: str = r"https?:\/\/.+\/(?:api\/tokens|f)\/(?P<id>fbc_[A-Za-z0-9_-]{22})\/?"
    _VALID_FBC: re.Pattern[str] = re.compile(
        r"https?:\/\/.+?\/(?:api\/tokens|f)\/(?P<id>fbc_[A-Za-z0-9_-]{22})(?:\/uploads)?/?(?P<fid>[A-Za-z0-9_-]+)?/?$"
    )
    _POSSIBLE_METADATA_FIELDS: typing.ClassVar = {
        "title": "title",
        "description": "description",
        "release_date": ("broadcast_date", {"format_date"}),
        "release_year": ("broadcast_date", {"format_year"}),
    }

    @classmethod
    def _match_valid_url(cls, url) -> re.Match[str] | None:
        return cls._VALID_FBC.match(url)

    @classmethod
    def _match_id(cls, url) -> None | str:
        mat: re.Match[str] | None = cls._match_valid_url(url)
        if not mat:
            return None

        if mat.group("fid"):
            return mat.group("fid")

        return mat.group("id")

    def _perform_login(self, _, password):
        FBCIE._APIKEY: str = password

    def _convert_to_api_url(self, url: str) -> str:
        """Convert share URL format to API URL format."""
        mat: re.Match[str] | None = self._match_valid_url(url)
        if not mat:
            return url

        parsed: ParseResult = urlparse(url)
        token_id: str | None = mat.group("id")
        file_id: str | None = mat.group("fid")

        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                f"/api/tokens/{token_id}/uploads/{file_id}" if file_id else f"/api/tokens/{token_id}/uploads",
                "",
                "",
                "",
            )
        )

    def _real_extract(self, url):
        video_id: str = self._match_id(url)
        headers: dict[str, str] = {}

        parsed: ParseResult = urlparse(url)
        path_prefix = re.sub(r"/(api/tokens|f)/.*$", "", parsed.path)
        base_url: str = f"{parsed.scheme}://{parsed.netloc}{path_prefix}"

        if apikey := (FBCIE._APIKEY or os.environ.get("FBC_API_KEY")):
            headers["Authorization"] = f"Bearer {apikey!s}"

        err_note = "Failed to download token info."
        if not apikey:
            err_note += "You may need to provide a valid API key via --password or FBC_API_KEY environment variable."

        items_info = self._download_json(
            self._convert_to_api_url(url),
            video_id=video_id,
            headers=headers,
            note="Downloading token info",
            fatal=True,
            errnote=err_note,
        )

        if is_single := isinstance(items_info, dict):
            items_info = [items_info]

        playlist: list[dict] = [
            self._format_item(
                video_data,
                "video" if is_single or len(items_info) < 2 else "url",
                headers=headers,
                base_url=base_url,
            )
            for video_data in items_info
            if "completed" == video_data.get("status")
        ]

        if len(playlist) < 1:
            self.report_warning("Token contains no uploaded files.")
            return None

        if is_single or self.get_param("noplaylist"):
            if self.get_param("noplaylist") and len(playlist) > 1:
                self.to_screen(f"Downloading 1 video out of '{len(playlist)}' because of --no-playlist option")
                playlist[0]["_type"] = "video"

            return playlist.pop(0)

        return {"_type": "playlist", "id": video_id, "entries": playlist}

    def _extract_metadata(self, meta_data: dict, fields: list[str]) -> dict:
        extracted = {}
        for key, field in fields.items():
            if isinstance(field, str):
                value = str_or_none(traverse_obj(meta_data, field))
                if value:
                    extracted[key] = value

            if isinstance(field, tuple) and 2 == len(field):
                meta_key, methods = field
                date_str = str_or_none(traverse_obj(meta_data, meta_key))
                for method in methods:
                    if method not in ["format_date", "format_year"]:
                        continue

                    if val := self._format_date(
                        date_str,
                        dateformat="{year:04}{month:02}{day:02}" if method == "format_date" else "{year:04}",
                    ):
                        extracted[key] = int_or_none(val) if method == "format_year" else str_or_none(val)

        return extracted

    def _format_date(self, date_str: str | None, dateformat: str = "{year:04}{month:02}{day:02}") -> str | None:
        """Date is YYYY-MM-DD."""
        if not date_str:
            return None

        try:
            parts = date_str.split("-")
            if len(parts) != 3:
                return None
            year, month, day = map(int, parts)
        except Exception:
            return None

        return dateformat.format(year=year, month=month, day=day)

    def _parse_date(self, date_str: str | None, dateformat: str = "{year:04}{month:02}{day:02}") -> str | None:
        """Parse ISO DATE."""
        if not date_str:
            return None

        from datetime import datetime as dt

        try:
            _dt: dt = dt.fromisoformat(date_str)
        except Exception:
            return None

        return dateformat.format(year=_dt.year, month=_dt.month, day=_dt.day)

    def _expand_format(self, format_dict: dict, ffprobe_data: dict) -> dict:
        """Enrich format dictionary with data from ffprobe output."""
        if not ffprobe_data:
            return format_dict

        format_info = ffprobe_data.get("format", {})

        if format_name := str_or_none(format_info.get("format_name")):
            format_dict["container"] = format_name.split(",")[0]  # Take first format if multiple

        if not format_dict.get("filesize") and (size := format_info.get("size")):
            format_dict["filesize"] = int_or_none(size)

        if bit_rate := format_info.get("bit_rate"):
            format_dict["tbr"] = int_or_none(bit_rate) / 1000 if isinstance(bit_rate, (int, str)) else None

        if duration := format_info.get("duration"):
            format_dict["duration"] = float(duration) if isinstance(duration, (int, float, str)) else None

        streams = ffprobe_data.get("streams", [])

        video_stream = None
        audio_stream = None

        for stream in streams:
            codec_type = stream.get("codec_type")
            if codec_type == "video" and not video_stream:
                video_stream = stream
            elif codec_type == "audio" and not audio_stream:
                audio_stream = stream

        if video_stream:
            if codec_name := str_or_none(video_stream.get("codec_name")):
                format_dict["vcodec"] = codec_name

            if width := int_or_none(video_stream.get("width")):
                format_dict["width"] = width
            if height := int_or_none(video_stream.get("height")):
                format_dict["height"] = height

            if fps_str := str_or_none(video_stream.get("r_frame_rate")):
                try:
                    # Parse fps like "30/1" or "24000/1001"
                    if "/" in fps_str:
                        num, denom = fps_str.split("/")
                        format_dict["fps"] = int(num) / int(denom)
                    else:
                        format_dict["fps"] = float(fps_str)
                except (ValueError, ZeroDivisionError):
                    pass

            if bit_rate := video_stream.get("bit_rate"):
                format_dict["vbr"] = int_or_none(bit_rate) / 1000 if isinstance(bit_rate, (int, str)) else None

            if dar := str_or_none(video_stream.get("display_aspect_ratio")):
                format_dict["aspect_ratio"] = dar

        if audio_stream:
            if codec_name := str_or_none(audio_stream.get("codec_name")):
                format_dict["acodec"] = codec_name

            if sample_rate := int_or_none(audio_stream.get("sample_rate")):
                format_dict["asr"] = sample_rate

            if channels := int_or_none(audio_stream.get("channels")):
                format_dict["audio_channels"] = channels

            if bit_rate := audio_stream.get("bit_rate"):
                format_dict["abr"] = int_or_none(bit_rate) / 1000 if isinstance(bit_rate, (int, str)) else None

        if not video_stream:
            format_dict["vcodec"] = "none"

        if not audio_stream:
            format_dict["acodec"] = "none"

        return format_dict

    def _format_item(self, video_data: dict, _type: str, headers: dict | None = None, base_url: str | None = None) -> dict:
        download_url = video_data.get("download_url")
        if download_url and base_url and not download_url.startswith(("http://", "https://")):
            download_url = f"{base_url}{download_url}"

        base_format = {
            "url": download_url,
            "ext": video_data.get("ext"),
            "filesize": int_or_none(video_data.get("size_bytes")),
        }

        meta_data = video_data.get("meta_data", {})
        if ffprobe_data := meta_data.get("ffprobe"):
            base_format = self._expand_format(base_format, ffprobe_data)

        info_url = video_data.get("info_url")
        if info_url and base_url and not info_url.startswith(("http://", "https://")):
            info_url = f"{base_url}{info_url}"

        dct = {
            "id": video_data.get("public_id", video_data.get("id")),
            "_type": _type,
            "ext": video_data.get("ext"),
            "mimetype": video_data.get("mimetype"),
            "url": info_url,
            "webpage_url": info_url,
            "formats": [base_format],
            "title": meta_data.get("title") or video_data.get("filename", f"file_{video_data['id']}"),
            "filename": video_data.get("filename"),
            "filesize": int_or_none(video_data.get("size_bytes")),
            "upload_date": str_or_none(self._parse_date(video_data.get("created_at"))),
            **self._extract_metadata(meta_data, self._POSSIBLE_METADATA_FIELDS),
        }

        if base_format.get("duration") and not dct.get("duration"):
            dct["duration"] = base_format["duration"]

        if headers:
            dct["http_headers"] = headers

        return dct
