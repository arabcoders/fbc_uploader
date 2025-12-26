import os
import re
import typing

from yt_dlp.extractor.common import InfoExtractor  # type: ignore
from yt_dlp.utils import int_or_none, str_or_none, traverse_obj  # type: ignore


class FBCIE(InfoExtractor):
    _APIKEY = None
    _NETRC_MACHINE = "fbc_uploader"
    _VALID_URL = r"https?:\/\/.+\/api\/tokens\/(?P<id>fbc_[A-Za-z0-9_-]{22})\/?"
    _VALID_FBC: re.Pattern[str] = re.compile(r"https?:\/\/.+\/api\/tokens\/(?P<id>fbc_[A-Za-z0-9_-]{22})\/uploads/?(?P<fid>\d+)?/?$")
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
        mat = cls._match_valid_url(url)
        if not mat:
            return None

        if mat.group("fid"):
            return f"{mat.group('id')}-{mat.group('fid')}"

        return mat.group("id")

    def _perform_login(self, _, password):
        FBCIE._APIKEY = password

    def _real_extract(self, url):
        video_id: str = self._match_id(url)
        headers: dict[str, str] = {}

        if apikey := (FBCIE._APIKEY or os.environ.get("FBC_API_KEY")):
            headers["Authorization"] = f"Bearer {apikey!s}"

        err_note = "Failed to download token info"
        if not apikey:
            err_note += ", you may need to provide a valid API key --password or via FBC_API_KEY environment variable."

        items_info = self._download_json(
            url,
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
                video_id,
                "video" if is_single or len(items_info) < 2 else "url",
                headers=headers,
                is_single=is_single,
            )
            for video_data in items_info
            if "completed" == video_data.get("status")
        ]

        if len(playlist) < 1:
            self.report_warning("Token contains no uploaded files.")
            return None

        if len(playlist) == 1 or self.get_param("noplaylist"):
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
            _dt = dt.fromisoformat(date_str)
        except Exception:
            return None

        return dateformat.format(year=_dt.year, month=_dt.month, day=_dt.day)

    def _format_item(self, video_data: dict, video_id: str, _type: str, headers: dict | None = None, is_single: bool = False) -> dict:
        dct = {
            "id": f"{video_id}-{video_data.get('id')}" if not is_single else video_id,
            "_type": _type,
            "ext": video_data.get("ext"),
            "mimetype": video_data.get("mimetype"),
            "url": video_data.get("info_url"),
            "webpage_url": video_data.get("info_url"),
            "formats": [
                {
                    "url": video_data.get("download_url"),
                    "ext": video_data.get("ext"),
                    "filesize": int_or_none(video_data.get("size_bytes")),
                }
            ],
            "title": video_data.get("meta_data", {}).get("title") or video_data.get("filename", f"file_{video_data['id']}"),
            "filename": video_data.get("filename"),
            "filesize": int_or_none(video_data.get("size_bytes")),
            "upload_date": str_or_none(self._parse_date(video_data.get("created_at"))),
            **self._extract_metadata(video_data.get("meta_data", {}), self._POSSIBLE_METADATA_FIELDS),
        }

        if headers:
            dct["http_headers"] = headers

        return dct
