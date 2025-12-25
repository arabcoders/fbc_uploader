import os
import re
import typing

from yt_dlp.extractor.common import InfoExtractor  # type: ignore
from yt_dlp.utils import int_or_none, str_or_none, traverse_obj  # type: ignore


class FBCIE(InfoExtractor):
    _APIKEY = None
    _NETRC_MACHINE = "fbc_uploader"
    _VALID_URL = r"https?:\/\/.+\/api\/tokens\/(?P<id>fbc_[A-Za-z0-9_-]{22})\/?"
    _VALID_FBC = r"https?:\/\/.+\/api\/tokens\/(?P<id>fbc_[A-Za-z0-9_-]{22})\/uploads/?(?P<fid>\d+)?/?$"
    _POSSIBLE_METADATA_FIELDS: typing.ClassVar = {
        "title": "title",
        "description": "description",
        "release_date": ("broadcast_date", {"format_date"}),
        "release_year": ("broadcast_date", {"format_year"}),
    }

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

        fid: str | None = None
        _mat: re.Match[str] | None = re.search(self._VALID_FBC, url)
        if _mat and _mat.group("fid") is not None:
            fid = _mat.group("fid")

        json_dict = self._download_json(
            url,
            video_id=video_id,
            headers=headers,
            note="Downloading token info",
            fatal=True,
            errnote=err_note,
        )

        if fid:
            return self._format_item(json_dict, f"{video_id}-{json_dict.get('id')}", "video", headers=headers)

        _count: int = len(json_dict)
        playlist: list[dict] = [
            self._format_item(
                video_data,
                f"{video_id}-{video_data.get('id')}",
                "url" if _count > 1 else "video",
                headers=headers,
            )
            for video_data in json_dict
        ]

        if len(playlist) < 1:
            self.report_warning("Token contains no uploaded files.")
            return None

        if len(playlist) == 1:
            return playlist[0]

        return {"_type": "playlist", "id": video_id, "entries": playlist}

    def extract_metadata(self, meta_data: dict, fields: list[str]) -> dict:
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

    def _format_item(self, video_data: dict, video_id: str, _type: str, headers: dict | None = None) -> dict:
        dct = {
            "id": video_id,
            "_type": _type,
            "ext": video_data.get("ext"),
            "mimetype": video_data.get("mimetype"),
            "url": video_data.get("download_url") if _type == "video" else video_data.get("info_url"),
            "title": video_data.get("meta_data", {}).get("title") or video_data.get("filename", f"file_{video_data['id']}"),
            "filename": video_data.get("filename"),
            "filesize": int_or_none(video_data.get("size_bytes")),
            "upload_date": str_or_none(self._parse_date(video_data.get("created_at"))),
            **self.extract_metadata(video_data.get("meta_data", {}), self._POSSIBLE_METADATA_FIELDS),
        }

        if headers:
            dct["http_headers"] = headers

        return dct
