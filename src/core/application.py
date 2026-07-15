from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.catalog.loader import load_sources
from src.catalog.source_registry import SourceRegistry
from src.core.settings import Settings
from src.downloader.client import (
    DownloadError,
    DownloadResult,
    PlaylistDownloader,
)
from src.exporter.m3u import M3UExporter
from src.health.checker import (
    HealthResult,
    StreamHealthChecker,
)
from src.merger.merger import ChannelMerger
from src.models.channel import Channel
from src.models.source import Source
from src.parser.m3u import M3UParser, ParseResult
from src.registry.channel_registry import ChannelRegistry


class Application:
    VERSION = "0.8.0"
    PARSER_ISSUES_REPORT_LIMIT = 100
    MERGER_DECISIONS_REPORT_LIMIT = 100

    def __init__(
        self,
        root: Path,
    ) -> None:
        self.root = root

        self.settings = Settings.load(
            root / "config/settings.json"
        )

        self.downloader = PlaylistDownloader(
            root,
            self.settings.request_timeout_seconds,
            self.settings.retry_count,
            self.settings.user_agent,
        )

        self.parser = M3UParser()
        self.merger = ChannelMerger()

        self.source_registry = SourceRegistry()
        self.registry = ChannelRegistry()

        self.exporter = M3UExporter()

        self.health_checker = StreamHealthChecker(
            timeout_seconds=(
                self.settings.health_timeout_seconds
            ),
            max_workers=(
                self.settings.health_max_workers
            ),
            user_agent=self.settings.user_agent,
        )

    def run(self) -> int:
        """
        Esegue la pipeline completa di Italia TV Hub.

        Flusso:

        1. caricamento e registrazione sorgenti;
        2. download con diagnostica;
        3. parsing normalizzato con diagnostica;
        4. registrazione e deduplicazione canali;
        5. merge;
        6. health check opzionale;
        7. esportazione;
        8. report JSON.
        """

        if not hasattr(
            self,
            "source_registry",
        ):
            self.source_registry = SourceRegistry()

        if not hasattr(
            self,
            "registry",
        ):
            self.registry = ChannelRegistry()

        self.source_registry.clear()
        self.registry.clear()

        clear_download_history = getattr(
            self.downloader,
            "clear_history",
            None,
        )

        if callable(clear_download_history):
            clear_download_history()

        source_results: list[
            dict[str, object]
        ] = []

        channels_parsed = 0
        registry_duplicates_removed = 0

        raw_sources = load_sources(
            self.root / "config/sources"
        )

        source_batch = (
            self.source_registry.add_many(
                raw_sources,
                replace_existing=False,
                strict=False,
            )
        )

        source_stats = (
            self.source_registry.stats()
        )

        sources = (
            self.source_registry.snapshot()
        )

        source_priorities = {
            source.id: self._as_int(
                getattr(
                    source,
                    "priority",
                    0,
                )
            )
            for source in sources
        }

        for source in sources:
            if not source.enabled:
                source_results.append(
                    {
                        "id": source.id,
                        "name": source.name,
                        "status": "disabled",
                        "channels": 0,
                        "registered": 0,
                        "duplicates_skipped": 0,
                    }
                )
                continue

            try:
                (
                    content,
                    download_diagnostics,
                ) = self._download_source(
                    source
                )

                (
                    parsed_channels,
                    parser_diagnostics,
                ) = self._parse_source(
                    content,
                    source.id,
                )

                channels_parsed += len(
                    parsed_channels
                )

                channel_batch = (
                    self.registry.add_many(
                        parsed_channels,
                        replace=False,
                    )
                )

                registry_duplicates_removed += (
                    channel_batch.skipped
                )

                source_result: dict[
                    str,
                    object,
                ] = {
                    "id": source.id,
                    "name": source.name,
                    "status": "ok",
                    "channels": len(
                        parsed_channels
                    ),
                    "registered": (
                        channel_batch.inserted
                    ),
                    "duplicates_skipped": (
                        channel_batch.skipped
                    ),
                }

                source_result.update(
                    download_diagnostics
                )

                source_result.update(
                    parser_diagnostics
                )

                source_results.append(
                    source_result
                )

            except DownloadError as exc:
                source_result = {
                    "id": source.id,
                    "name": source.name,
                    "status": "error",
                    "channels": 0,
                    "registered": 0,
                    "duplicates_skipped": 0,
                    "error": str(exc),
                }

                source_result.update(
                    self._error_download_diagnostics(
                        source,
                        exc,
                    )
                )

                source_results.append(
                    source_result
                )

        registry_channels = list(
            self.registry.snapshot()
        )

        channels_before_merge = len(
            registry_channels
        )

        (
            merged_channels,
            merger_diagnostics,
        ) = self._merge_channels(
            registry_channels,
            source_priorities,
        )

        merger_duplicates_removed = (
            channels_before_merge
            - len(merged_channels)
        )

        self.registry.clear()

        post_merge_result = (
            self.registry.add_many(
                merged_channels,
                replace=False,
            )
        )

        post_merge_duplicates_removed = (
            post_merge_result.skipped
        )

        channels_after_merge = len(
            self.registry
        )

        duplicates_removed = (
            channels_parsed
            - channels_after_merge
        )

        health_results: list[
            HealthResult
        ] = []

        if self.settings.health_enabled:
            channels_to_check = list(
                self.registry.snapshot()
            )

            health_results = (
                self.health_checker.check_many(
                    channels_to_check
                )
            )

            self._write_health_report(
                health_results
            )

            if (
                self.settings
                .publish_only_online
            ):
                publishable_urls = {
                    result.stream_url
                    for result in health_results
                    if result.status
                    in {
                        "online",
                        "reachable",
                    }
                }

                for channel in (
                    self.registry.snapshot()
                ):
                    if (
                        channel.stream_url
                        not in publishable_urls
                    ):
                        self.registry.remove_by_url(
                            channel.stream_url
                        )

        else:
            self._write_health_report([])

        output_channels = list(
            self.registry.snapshot()
        )

        output_path = (
            self.root
            / self.settings.output_file
        )

        self.exporter.write(
            output_path,
            output_channels,
        )

        channel_registry_stats = (
            self.registry.stats()
        )

        download_summary = (
            self._build_download_summary(
                source_results
            )
        )

        parser_summary = (
            self._build_parser_summary(
                source_results
            )
        )

        report = {
            "project": "Italia TV Hub",
            "version": self.VERSION,
            "generated_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),

            # Source Management Engine
            "sources_total": (
                source_stats.total
            ),
            "sources_enabled": (
                source_stats.enabled
            ),
            "sources_disabled": (
                source_stats.disabled
            ),
            "sources_remote": (
                source_stats.remote
            ),
            "sources_local": (
                source_stats.local
            ),
            "sources_ok": sum(
                1
                for result in source_results
                if result["status"] == "ok"
            ),
            "sources_error": sum(
                1
                for result in source_results
                if result["status"] == "error"
            ),
            "source_duplicates_skipped": (
                source_batch.skipped
            ),
            "source_invalid": (
                source_batch.invalid
            ),
            "source_registry_errors": [
                {
                    "source_id": (
                        error.source_id
                    ),
                    "error": error.message,
                }
                for error in source_batch.errors
            ],

            # Download Reliability Engine
            "downloads_attempted": (
                download_summary["attempted"]
            ),
            "downloads_successful": (
                download_summary["successful"]
            ),
            "downloads_failed": (
                download_summary["failed"]
            ),
            "download_attempts_total": (
                download_summary[
                    "attempts_total"
                ]
            ),
            "download_retries_total": (
                download_summary[
                    "retries_total"
                ]
            ),
            "download_bytes_total": (
                download_summary["bytes_total"]
            ),
            "download_time_ms_total": (
                download_summary[
                    "time_ms_total"
                ]
            ),

            # Parser Normalization Engine
            "parser_sources_processed": (
                parser_summary[
                    "sources_processed"
                ]
            ),
            "parser_extinf_records": (
                parser_summary[
                    "extinf_records"
                ]
            ),
            "parser_channels_created": (
                parser_summary[
                    "channels_created"
                ]
            ),
            "parser_skipped_records": (
                parser_summary[
                    "skipped_records"
                ]
            ),
            "parser_issue_count": (
                parser_summary[
                    "issue_count"
                ]
            ),
            "parser_issues_reported": (
                parser_summary[
                    "issues_reported"
                ]
            ),
            "parser_issues_truncated": (
                parser_summary[
                    "issues_truncated"
                ]
            ),

            # Channel Registry Engine
            "channels_parsed": (
                channels_parsed
            ),
            "channels_before_merge": (
                channels_before_merge
            ),
            "registry_duplicates_removed": (
                registry_duplicates_removed
            ),
            "merger_duplicates_removed": (
                merger_duplicates_removed
            ),
            "merger_decision_count": (
                merger_diagnostics[
                    "decision_count"
                ]
            ),
            "merger_decisions_reported": (
                merger_diagnostics[
                    "decisions_reported"
                ]
            ),
            "merger_decisions_truncated": (
                merger_diagnostics[
                    "decisions_truncated"
                ]
            ),
            "post_merge_duplicates_removed": (
                post_merge_duplicates_removed
            ),
            "duplicates_removed": (
                duplicates_removed
            ),

            # Health Engine
            "health_enabled": (
                self.settings.health_enabled
            ),
            "health_checked": len(
                health_results
            ),
            "health_online": sum(
                1
                for result in health_results
                if result.status == "online"
            ),
            "health_reachable": sum(
                1
                for result in health_results
                if result.status
                == "reachable"
            ),
            "health_offline": sum(
                1
                for result in health_results
                if result.status == "offline"
            ),
            "publish_only_online": (
                self.settings
                .publish_only_online
            ),

            "channels": len(
                output_channels
            ),

            "source_registry": {
                "total": (
                    source_stats.total
                ),
                "enabled": (
                    source_stats.enabled
                ),
                "disabled": (
                    source_stats.disabled
                ),
                "remote": (
                    source_stats.remote
                ),
                "local": (
                    source_stats.local
                ),
            },

            "download_summary": (
                download_summary
            ),

            "parser_summary": (
                parser_summary
            ),

            "merger": (
                merger_diagnostics
            ),

            "registry": {
                "channels": (
                    channel_registry_stats
                    .channels
                ),
                "sources": (
                    channel_registry_stats
                    .sources
                ),
                "groups": (
                    channel_registry_stats
                    .groups
                ),
                "tvg_ids": (
                    channel_registry_stats
                    .tvg_ids
                ),
            },

            "output_file": str(
                output_path.relative_to(
                    self.root
                )
            ),

            "sources": source_results,
        }

        report_path = (
            self.root
            / self.settings.report_file
        )

        report_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        report_path.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        return 0

    def _download_source(
        self,
        source: Source,
    ) -> tuple[
        str,
        dict[str, object],
    ]:
        fetch_detailed = getattr(
            self.downloader,
            "fetch_detailed",
            None,
        )

        if callable(fetch_detailed):
            result = fetch_detailed(
                source
            )

            if not isinstance(
                result,
                DownloadResult,
            ):
                raise TypeError(
                    "fetch_detailed() deve restituire "
                    "DownloadResult"
                )

            return (
                result.content,
                self._success_download_diagnostics(
                    result
                ),
            )

        content = self.downloader.fetch(
            source
        )

        return content, {}

    def _parse_source(
        self,
        content: str,
        source_id: str,
    ) -> tuple[
        list[Channel],
        dict[str, object],
    ]:
        """
        Usa parse_detailed() quando disponibile.

        I parser semplificati dei vecchi test possono continuare
        a esporre soltanto parse().
        """

        parse_detailed = getattr(
            self.parser,
            "parse_detailed",
            None,
        )

        if callable(parse_detailed):
            result = parse_detailed(
                content,
                source_id,
            )

            if not isinstance(
                result,
                ParseResult,
            ):
                raise TypeError(
                    "parse_detailed() deve restituire "
                    "ParseResult"
                )

            return (
                list(result.channels),
                self._parser_diagnostics(
                    result
                ),
            )

        channels = self.parser.parse(
            content,
            source_id,
        )

        return list(channels), {}

    def _parser_diagnostics(
        self,
        result: ParseResult,
    ) -> dict[str, object]:
        issues = list(result.issues)

        reported_issues = issues[
            :self.PARSER_ISSUES_REPORT_LIMIT
        ]

        truncated = max(
            0,
            len(issues)
            - len(reported_issues),
        )

        return {
            "parser_stats": (
                result.stats.to_dict()
            ),
            "parser_issue_count": len(
                issues
            ),
            "parser_issues_reported": len(
                reported_issues
            ),
            "parser_issues_truncated": (
                truncated
            ),
            "parser_issues": [
                issue.to_dict()
                for issue in reported_issues
            ],
        }

    @staticmethod
    def _success_download_diagnostics(
        result: DownloadResult,
    ) -> dict[str, object]:
        return {
            "attempt_count": (
                result.attempt_count
            ),
            "download_ms": (
                result.total_elapsed_ms
            ),
            "bytes_downloaded": (
                result.bytes_downloaded
            ),
            "http_status": (
                result.http_status
            ),
            "final_url": result.final_url,
            "content_type": (
                result.content_type
            ),
            "encoding": result.encoding,
            "is_remote": result.is_remote,
            "retryable": False,
            "download_attempts": [
                attempt.to_dict()
                for attempt in result.attempts
            ],
        }

    @staticmethod
    def _error_download_diagnostics(
        source: Source,
        error: DownloadError,
    ) -> dict[str, object]:
        attempts = tuple(
            error.attempts
        )

        return {
            "attempt_count": (
                error.attempt_count
            ),
            "download_ms": sum(
                attempt.elapsed_ms
                for attempt in attempts
            ),
            "bytes_downloaded": 0,
            "http_status": (
                error.status_code
            ),
            "final_url": (
                error.url
                or source.url
            ),
            "content_type": "",
            "encoding": "",
            "is_remote": (
                source.is_remote()
            ),
            "retryable": (
                error.retryable
            ),
            "download_attempts": [
                attempt.to_dict()
                for attempt in attempts
            ],
        }

    @staticmethod
    def _build_download_summary(
        source_results: list[
            dict[str, object]
        ],
    ) -> dict[str, int]:
        downloadable = [
            result
            for result in source_results
            if result.get("status")
            in {
                "ok",
                "error",
            }
        ]

        attempts_total = sum(
            Application._as_int(
                result.get(
                    "attempt_count",
                    1,
                )
            )
            for result in downloadable
        )

        retries_total = sum(
            max(
                0,
                Application._as_int(
                    result.get(
                        "attempt_count",
                        1,
                    )
                )
                - 1,
            )
            for result in downloadable
        )

        return {
            "attempted": len(
                downloadable
            ),
            "successful": sum(
                1
                for result in downloadable
                if result.get("status")
                == "ok"
            ),
            "failed": sum(
                1
                for result in downloadable
                if result.get("status")
                == "error"
            ),
            "attempts_total": (
                attempts_total
            ),
            "retries_total": (
                retries_total
            ),
            "bytes_total": sum(
                Application._as_int(
                    result.get(
                        "bytes_downloaded",
                        0,
                    )
                )
                for result in downloadable
            ),
            "time_ms_total": sum(
                Application._as_int(
                    result.get(
                        "download_ms",
                        0,
                    )
                )
                for result in downloadable
            ),
        }

    @staticmethod
    def _build_parser_summary(
        source_results: list[
            dict[str, object]
        ],
    ) -> dict[str, int]:
        summary = {
            "sources_processed": 0,
            "lines_total": 0,
            "non_empty_lines": 0,
            "extinf_records": 0,
            "channels_created": 0,
            "skipped_records": 0,
            "malformed_extinf": 0,
            "missing_name": 0,
            "missing_url": 0,
            "invalid_channel": 0,
            "orphan_lines": 0,
            "abandoned_records": 0,
            "directives_collected": 0,
            "issue_count": 0,
            "issues_reported": 0,
            "issues_truncated": 0,
        }

        stats_fields = (
            "lines_total",
            "non_empty_lines",
            "extinf_records",
            "channels_created",
            "skipped_records",
            "malformed_extinf",
            "missing_name",
            "missing_url",
            "invalid_channel",
            "orphan_lines",
            "abandoned_records",
            "directives_collected",
        )

        for source_result in source_results:
            parser_stats = source_result.get(
                "parser_stats"
            )

            if not isinstance(
                parser_stats,
                dict,
            ):
                continue

            summary[
                "sources_processed"
            ] += 1

            for field in stats_fields:
                summary[field] += (
                    Application._as_int(
                        parser_stats.get(
                            field,
                            0,
                        )
                    )
                )

            summary["issue_count"] += (
                Application._as_int(
                    source_result.get(
                        "parser_issue_count",
                        0,
                    )
                )
            )

            summary[
                "issues_reported"
            ] += Application._as_int(
                source_result.get(
                    "parser_issues_reported",
                    0,
                )
            )

            summary[
                "issues_truncated"
            ] += Application._as_int(
                source_result.get(
                    "parser_issues_truncated",
                    0,
                )
            )

        return summary

    def _merge_channels(
        self,
        channels: list[Channel],
        source_priorities: dict[str, int],
    ) -> tuple[
        list[Channel],
        dict[str, object],
    ]:
        """
        Esegue il Merger Quality Engine con diagnostica.

        Usa merge_detailed() quando disponibile e conserva il
        fallback su merge() per i componenti semplificati usati
        dai test precedenti.
        """

        merge_detailed = getattr(
            self.merger,
            "merge_detailed",
            None,
        )

        if not callable(merge_detailed):
            merged_channels = list(
                self.merger.merge(
                    channels
                )
            )

            return (
                merged_channels,
                self._fallback_merger_diagnostics(
                    channels,
                    merged_channels,
                    source_priorities,
                ),
            )

        merge_kwargs: dict[
            str,
            object,
        ] = {}

        try:
            parameters = inspect.signature(
                merge_detailed
            ).parameters
        except (
            TypeError,
            ValueError,
        ):
            parameters = {}

        accepts_keyword_arguments = any(
            parameter.kind
            is inspect.Parameter.VAR_KEYWORD
            for parameter
            in parameters.values()
        )

        if (
            not parameters
            or "source_priorities"
            in parameters
            or accepts_keyword_arguments
        ):
            merge_kwargs[
                "source_priorities"
            ] = source_priorities

        merge_result = merge_detailed(
            channels,
            **merge_kwargs,
        )

        merged_value = getattr(
            merge_result,
            "channels",
            None,
        )

        if merged_value is None:
            merged_value = getattr(
                merge_result,
                "merged_channels",
                None,
            )

        if merged_value is None:
            raise TypeError(
                "merge_detailed() deve restituire "
                "un risultato con channels"
            )

        merged_channels = list(
            merged_value
        )

        if any(
            not isinstance(
                channel,
                Channel,
            )
            for channel in merged_channels
        ):
            raise TypeError(
                "Il risultato del merger contiene "
                "elementi non Channel"
            )

        stats = self._json_safe(
            getattr(
                merge_result,
                "stats",
                {},
            )
        )

        raw_decisions = getattr(
            merge_result,
            "decisions",
            (),
        )

        decisions = list(
            raw_decisions
        )

        reported_decisions = decisions[
            :self.MERGER_DECISIONS_REPORT_LIMIT
        ]

        decisions_truncated = max(
            0,
            len(decisions)
            - len(reported_decisions),
        )

        return (
            merged_channels,
            {
                "mode": "detailed",
                "source_priorities": dict(
                    sorted(
                        source_priorities.items()
                    )
                ),
                "stats": stats,
                "decision_count": len(
                    decisions
                ),
                "decisions_reported": len(
                    reported_decisions
                ),
                "decisions_truncated": (
                    decisions_truncated
                ),
                "decisions": [
                    self._json_safe(
                        decision
                    )
                    for decision
                    in reported_decisions
                ],
            },
        )

    def _fallback_merger_diagnostics(
        self,
        input_channels: list[Channel],
        output_channels: list[Channel],
        source_priorities: dict[str, int],
    ) -> dict[str, object]:
        duplicates_removed = max(
            0,
            len(input_channels)
            - len(output_channels),
        )

        return {
            "mode": "legacy",
            "source_priorities": dict(
                sorted(
                    source_priorities.items()
                )
            ),
            "stats": {
                "input_channels": len(
                    input_channels
                ),
                "output_channels": len(
                    output_channels
                ),
                "duplicates_removed": (
                    duplicates_removed
                ),
            },
            "decision_count": 0,
            "decisions_reported": 0,
            "decisions_truncated": 0,
            "decisions": [],
        }

    @classmethod
    def _json_safe(
        cls,
        value: Any,
    ) -> Any:
        """
        Converte dataclass, oggetti diagnostici e Channel in
        strutture serializzabili in JSON.
        """

        if value is None or isinstance(
            value,
            (
                bool,
                int,
                float,
                str,
            ),
        ):
            return value

        if isinstance(
            value,
            Path,
        ):
            return str(value)

        if isinstance(
            value,
            Channel,
        ):
            return {
                "name": value.name,
                "stream_url": (
                    value.stream_url
                ),
                "group": value.group,
                "tvg_id": value.tvg_id,
                "tvg_name": value.tvg_name,
                "tvg_logo": value.tvg_logo,
                "source_id": (
                    value.source_id
                ),
            }

        if isinstance(
            value,
            dict,
        ):
            return {
                str(key): cls._json_safe(
                    item
                )
                for key, item
                in value.items()
            }

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
                frozenset,
            ),
        ):
            return [
                cls._json_safe(
                    item
                )
                for item in value
            ]

        to_dict = getattr(
            value,
            "to_dict",
            None,
        )

        if callable(to_dict):
            return cls._json_safe(
                to_dict()
            )

        attributes = getattr(
            value,
            "__dict__",
            None,
        )

        if isinstance(
            attributes,
            dict,
        ):
            return cls._json_safe(
                {
                    key: item
                    for key, item
                    in attributes.items()
                    if not key.startswith("_")
                }
            )

        slots = getattr(
            value,
            "__slots__",
            (),
        )

        if isinstance(
            slots,
            str,
        ):
            slots = (
                slots,
            )

        if slots:
            slot_values = {
                slot: getattr(
                    value,
                    slot,
                )
                for slot in slots
                if hasattr(
                    value,
                    slot,
                )
            }

            return cls._json_safe(
                slot_values
            )

        return str(value)

    @staticmethod
    def _as_int(
        value: Any,
    ) -> int:
        if isinstance(value, bool):
            return int(value)

        if isinstance(value, int):
            return value

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ):
            return 0

    def _write_health_report(
        self,
        results: list[HealthResult],
    ) -> None:
        health_path = (
            self.root
            / self.settings.health_file
        )

        health_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "project": "Italia TV Hub",
            "version": self.VERSION,
            "generated_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
            "enabled": (
                self.settings.health_enabled
            ),
            "checked": len(results),
            "online": sum(
                1
                for result in results
                if result.status == "online"
            ),
            "reachable": sum(
                1
                for result in results
                if result.status
                == "reachable"
            ),
            "offline": sum(
                1
                for result in results
                if result.status == "offline"
            ),
            "channels": [
                result.to_dict()
                for result in results
            ],
        }

        health_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )