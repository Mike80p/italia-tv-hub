from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.catalog.loader import load_sources
from src.catalog.source_registry import (
    SourceBatchResult,
    SourceRegistry,
)
from src.core.settings import Settings
from src.downloader.client import (
    DownloadError,
    DownloadResult,
    PlaylistDownloader,
)
from src.discovery.client import (
    DiscoveryBatchResult,
    DiscoveryError,
    DiscoveryStats,
    SourceDiscoveryClient,
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

        self.discovery_client = (
            SourceDiscoveryClient(
                user_agent=(
                    self.settings.user_agent
                ),
                timeout_seconds=(
                    self.settings
                    .request_timeout_seconds
                ),
            )
        )

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

        1. caricamento delle sorgenti configurate;
        2. discovery controllata delle sorgenti italiane;
        3. registrazione e deduplicazione delle sorgenti;
        4. download con diagnostica;
        5. parsing normalizzato con diagnostica;
        6. conservazione dei candidati alternativi;
        7. health check di tutti gli URL candidati;
        8. merge guidato dagli Health Score;
        9. filtro dei canali non disponibili;
        10. esportazione e report JSON.

        Se il merger installato non espone group_candidates(),
        viene mantenuto il precedente flusso compatibile:
        merge prima del controllo Health.
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

        parsed_candidates: list[
            Channel
        ] = []

        channels_parsed = 0
        registry_duplicates_removed = 0

        configured_sources = load_sources(
            self.root / "config/sources"
        )

        configured_source_batch = (
            self.source_registry.add_many(
                configured_sources,
                replace_existing=False,
                strict=False,
            )
        )

        discovery_result = (
            self._discover_sources()
        )

        discovery_source_batch = (
            self.source_registry.add_many(
                discovery_result.sources,
                replace_existing=False,
                strict=False,
            )
        )

        self._write_discovery_report(
            discovery_result,
            discovery_source_batch,
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

                # La lista separata conserva anche i flussi che il
                # ChannelRegistry può considerare duplicati. Questi
                # candidati sono necessari per il recupero automatico.
                parsed_candidates.extend(
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

        registered_channels = list(
            self.registry.snapshot()
        )

        supports_candidate_groups = callable(
            getattr(
                self.merger,
                "group_candidates",
                None,
            )
        )

        # Con il nuovo merger usiamo tutti i canali parsati.
        # Con merger legacy manteniamo l'input già registrato.
        merge_input = (
            list(parsed_candidates)
            if supports_candidate_groups
            else registered_channels
        )

        channels_before_merge = len(
            merge_input
        )

        (
            initial_grouping,
            candidate_group_diagnostics,
        ) = self._group_candidate_streams(
            merge_input,
            source_priorities,
        )

        health_results: list[
            HealthResult
        ] = []

        health_scores: dict[
            str,
            float,
        ] = {}

        health_result_by_url: dict[
            str,
            HealthResult,
        ] = {}

        recovery_diagnostics = (
            self._empty_recovery_diagnostics(
                mode=(
                    "candidate_health_recovery"
                    if (
                        self.settings.health_enabled
                        and initial_grouping
                        is not None
                    )
                    else (
                        "legacy_post_merge_health"
                        if self.settings.health_enabled
                        else "disabled"
                    )
                ),
                candidate_group_diagnostics=(
                    candidate_group_diagnostics
                ),
            )
        )

        if (
            self.settings.health_enabled
            and initial_grouping is not None
        ):
            all_candidate_channels = list(
                getattr(
                    initial_grouping,
                    "channels",
                    merge_input,
                )
            )

            channels_to_check = (
                self._unique_channels_by_url(
                    all_candidate_channels
                )
            )

            health_results = list(
                self.health_checker.check_many(
                    channels_to_check
                )
            )

            health_scores = (
                self._build_health_score_map(
                    health_results
                )
            )

            health_result_by_url = {
                self._url_key(
                    result.stream_url
                ): result
                for result in health_results
            }

            (
                merged_channels,
                merger_diagnostics,
            ) = self._merge_channels(
                merge_input,
                source_priorities,
                health_scores=health_scores,
            )

            (
                final_grouping,
                _,
            ) = self._group_candidate_streams(
                merge_input,
                source_priorities,
                health_scores=health_scores,
            )

            recovery_diagnostics = (
                self._build_recovery_diagnostics(
                    initial_grouping=(
                        initial_grouping
                    ),
                    final_grouping=(
                        final_grouping
                    ),
                    health_result_by_url=(
                        health_result_by_url
                    ),
                    candidate_streams_checked=(
                        len(channels_to_check)
                    ),
                    candidate_group_diagnostics=(
                        candidate_group_diagnostics
                    ),
                )
            )

        else:
            (
                merged_channels,
                merger_diagnostics,
            ) = self._merge_channels(
                merge_input,
                source_priorities,
            )

            if self.settings.health_enabled:
                channels_to_check = (
                    self._unique_channels_by_url(
                        merged_channels
                    )
                )

                health_results = list(
                    self.health_checker.check_many(
                        channels_to_check
                    )
                )

                health_scores = (
                    self._build_health_score_map(
                        health_results
                    )
                )

                health_result_by_url = {
                    self._url_key(
                        result.stream_url
                    ): result
                    for result in health_results
                }

                recovery_diagnostics[
                    "candidate_streams_checked"
                ] = len(
                    channels_to_check
                )

        merger_duplicates_removed = max(
            0,
            channels_before_merge
            - len(merged_channels),
        )

        selected_channels = list(
            merged_channels
        )

        if (
            self.settings.health_enabled
            and self.settings
            .publish_only_online
        ):
            selected_channels = (
                self._filter_publishable_channels(
                    selected_channels,
                    health_result_by_url,
                )
            )

        channels_filtered_unavailable = max(
            0,
            len(merged_channels)
            - len(selected_channels),
        )

        self.registry.clear()

        post_merge_result = (
            self.registry.add_many(
                selected_channels,
                replace=False,
            )
        )

        post_merge_duplicates_removed = (
            post_merge_result.skipped
        )

        channels_after_merge = len(
            self.registry
        )

        duplicates_removed = max(
            0,
            channels_parsed
            - channels_after_merge,
        )

        self._write_health_report(
            health_results,
            recovery_diagnostics=(
                recovery_diagnostics
            ),
        )

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
            "configured_sources_loaded": len(
                configured_sources
            ),
            "configured_sources_inserted": (
                configured_source_batch.inserted
            ),
            "discovery_sources_found": len(
                discovery_result.sources
            ),
            "discovery_sources_inserted": (
                discovery_source_batch.inserted
            ),
            "source_duplicates_skipped": (
                configured_source_batch.skipped
                + discovery_source_batch.skipped
            ),
            "source_invalid": (
                configured_source_batch.invalid
                + discovery_source_batch.invalid
            ),
            "source_registry_errors": [
                {
                    "origin": origin,
                    "source_id": (
                        error.source_id
                    ),
                    "error": error.message,
                }
                for origin, batch
                in (
                    (
                        "configured",
                        configured_source_batch,
                    ),
                    (
                        "discovery",
                        discovery_source_batch,
                    ),
                )
                for error in batch.errors
            ],

            # Source Discovery Engine
            "discovery_enabled": (
                getattr(
                    self,
                    "discovery_client",
                    None,
                )
                is not None
            ),
            "discovery_curated_sources": (
                discovery_result.stats
                .curated_sources
            ),
            "discovery_github_queries": (
                discovery_result.stats
                .github_queries
            ),
            "discovery_github_items": (
                discovery_result.stats
                .github_items
            ),
            "discovery_accepted_sources": (
                discovery_result.stats
                .accepted_sources
            ),
            "discovery_duplicates_skipped": (
                discovery_result.stats
                .duplicates_skipped
            ),
            "discovery_rejected_items": (
                discovery_result.stats
                .rejected_items
            ),
            "discovery_error_count": len(
                discovery_result.errors
            ),
            "discovery_github_token_used": (
                discovery_result.stats
                .github_token_used
            ),
            "discovery_errors": [
                error.to_dict()
                for error in (
                    discovery_result.errors
                )
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

            # Channel Registry / Merger Engine
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
            "channels_filtered_unavailable": (
                channels_filtered_unavailable
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

            # Alternative Stream Recovery Engine
            "alternative_recovery_enabled": (
                recovery_diagnostics[
                    "enabled"
                ]
            ),
            "candidate_groups": (
                recovery_diagnostics[
                    "candidate_groups"
                ]
            ),
            "duplicate_candidate_groups": (
                recovery_diagnostics[
                    "duplicate_candidate_groups"
                ]
            ),
            "alternative_candidates": (
                recovery_diagnostics[
                    "alternative_candidates"
                ]
            ),
            "candidate_streams_checked": (
                recovery_diagnostics[
                    "candidate_streams_checked"
                ]
            ),
            "selected_primary": (
                recovery_diagnostics[
                    "selected_primary"
                ]
            ),
            "recovered_from_alternative": (
                recovery_diagnostics[
                    "recovered_from_alternative"
                ]
            ),
            "upgraded_to_better_alternative": (
                recovery_diagnostics[
                    "upgraded_to_better_alternative"
                ]
            ),
            "all_candidates_failed": (
                recovery_diagnostics[
                    "all_candidates_failed"
                ]
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
                "discovery": self._as_int(
                    getattr(
                        source_stats,
                        "discovery",
                        0,
                    )
                ),
                "static": self._as_int(
                    getattr(
                        source_stats,
                        "static",
                        0,
                    )
                ),
                "trusted": self._as_int(
                    getattr(
                        source_stats,
                        "trusted",
                        0,
                    )
                ),
                "kinds": dict(
                    getattr(
                        source_stats,
                        "kinds",
                        (),
                    )
                ),
            },

            "discovery": {
                "stats": (
                    discovery_result.stats
                    .to_dict()
                ),
                "registration": {
                    "inserted": (
                        discovery_source_batch
                        .inserted
                    ),
                    "replaced": (
                        discovery_source_batch
                        .replaced
                    ),
                    "skipped": (
                        discovery_source_batch
                        .skipped
                    ),
                    "invalid": (
                        discovery_source_batch
                        .invalid
                    ),
                },
                "errors": [
                    error.to_dict()
                    for error in (
                        discovery_result.errors
                    )
                ],
                "output_file": (
                    "output/"
                    "discovered-sources.json"
                ),
            },

            "download_summary": (
                download_summary
            ),

            "parser_summary": (
                parser_summary
            ),

            "candidate_groups_summary": (
                candidate_group_diagnostics
            ),

            "alternative_recovery": (
                recovery_diagnostics
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

    def _discover_sources(
        self,
    ) -> DiscoveryBatchResult:
        """
        Esegue la discovery senza rendere fragile la pipeline.

        Le istanze create normalmente da __init__ possiedono il
        SourceDiscoveryClient e possono usare GITHUB_TOKEN. Le vecchie
        fixture di test che costruiscono Application con __new__ non
        eseguono richieste di rete e ricevono un risultato vuoto.
        """

        client = getattr(
            self,
            "discovery_client",
            None,
        )

        if client is None:
            return self._empty_discovery_result()

        discover = getattr(
            client,
            "discover_italian_sources",
            None,
        )

        if not callable(discover):
            return self._empty_discovery_result(
                error=(
                    "SourceDiscoveryClient non espone "
                    "discover_italian_sources()"
                )
            )

        try:
            result = discover()

        except Exception as exc:
            return self._empty_discovery_result(
                error=(
                    "Discovery non disponibile: "
                    f"{exc}"
                )
            )

        if not isinstance(
            result,
            DiscoveryBatchResult,
        ):
            return self._empty_discovery_result(
                error=(
                    "Il Discovery Client ha restituito "
                    "un risultato non valido"
                )
            )

        return result

    @staticmethod
    def _empty_discovery_result(
        *,
        error: str = "",
    ) -> DiscoveryBatchResult:
        errors = (
            (
                DiscoveryError(
                    provider="application",
                    query="",
                    message=error,
                ),
            )
            if error
            else ()
        )

        return DiscoveryBatchResult(
            sources=(),
            errors=errors,
            stats=DiscoveryStats(
                curated_sources=0,
                github_queries=0,
                github_items=0,
                accepted_sources=0,
                duplicates_skipped=0,
                rejected_items=0,
                errors=len(errors),
                github_token_used=False,
            ),
        )

    def _write_discovery_report(
        self,
        result: DiscoveryBatchResult,
        registration: SourceBatchResult,
    ) -> None:
        path = (
            self.root
            / "output"
            / "discovered-sources.json"
        )

        path.parent.mkdir(
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
            "stats": (
                result.stats.to_dict()
            ),
            "registration": {
                "inserted": (
                    registration.inserted
                ),
                "replaced": (
                    registration.replaced
                ),
                "skipped": (
                    registration.skipped
                ),
                "invalid": (
                    registration.invalid
                ),
                "errors": [
                    {
                        "source_id": (
                            error.source_id
                        ),
                        "error": error.message,
                    }
                    for error in (
                        registration.errors
                    )
                ],
            },
            "errors": [
                error.to_dict()
                for error in result.errors
            ],
            "sources": [
                source.to_dict()
                for source in result.sources
            ],
        }

        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

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
        *,
        health_scores: (
            dict[str, float] | None
        ) = None,
    ) -> tuple[
        list[Channel],
        dict[str, object],
    ]:
        """
        Esegue il Merger Quality Engine con diagnostica.

        Quando il merger supporta `health_scores`, il ranking finale
        viene eseguito dopo il controllo di tutti i candidati.
        I componenti legacy continuano a funzionare senza modifiche.
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

            diagnostics = (
                self._fallback_merger_diagnostics(
                    channels,
                    merged_channels,
                    source_priorities,
                )
            )

            diagnostics[
                "health_ranking"
            ] = False

            return (
                merged_channels,
                diagnostics,
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

        if (
            health_scores is not None
            and (
                not parameters
                or "health_scores"
                in parameters
                or accepts_keyword_arguments
            )
        ):
            merge_kwargs[
                "health_scores"
            ] = health_scores

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
                "health_ranking": (
                    health_scores is not None
                ),
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

    def _group_candidate_streams(
        self,
        channels: list[Channel],
        source_priorities: dict[str, int],
        *,
        health_scores: (
            dict[str, float] | None
        ) = None,
    ) -> tuple[
        object | None,
        dict[str, object],
    ]:
        """
        Costruisce i gruppi di flussi alternativi quando il merger
        espone la nuova API `group_candidates()`.

        Non effettua deduplicazione definitiva.
        """

        group_candidates = getattr(
            self.merger,
            "group_candidates",
            None,
        )

        if not callable(
            group_candidates
        ):
            return (
                None,
                {
                    "mode": "legacy",
                    "supported": False,
                    "stats": {
                        "input_channels": len(
                            channels
                        ),
                        "groups": 0,
                        "singleton_groups": 0,
                        "duplicate_groups": 0,
                        "alternative_candidates": 0,
                    },
                },
            )

        group_kwargs: dict[
            str,
            object,
        ] = {}

        try:
            parameters = inspect.signature(
                group_candidates
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
            group_kwargs[
                "source_priorities"
            ] = source_priorities

        if (
            health_scores is not None
            and (
                not parameters
                or "health_scores"
                in parameters
                or accepts_keyword_arguments
            )
        ):
            group_kwargs[
                "health_scores"
            ] = health_scores

        result = group_candidates(
            channels,
            **group_kwargs,
        )

        groups = getattr(
            result,
            "groups",
            None,
        )

        if groups is None:
            raise TypeError(
                "group_candidates() deve "
                "restituire un risultato con groups"
            )

        all_channels = getattr(
            result,
            "channels",
            None,
        )

        if all_channels is None:
            raise TypeError(
                "group_candidates() deve "
                "restituire un risultato con channels"
            )

        if any(
            not isinstance(
                channel,
                Channel,
            )
            for channel in all_channels
        ):
            raise TypeError(
                "I gruppi candidati contengono "
                "elementi non Channel"
            )

        return (
            result,
            {
                "mode": "candidate_groups",
                "supported": True,
                "health_ranking": (
                    health_scores is not None
                ),
                "stats": self._json_safe(
                    getattr(
                        result,
                        "stats",
                        {},
                    )
                ),
            },
        )

    @staticmethod
    def _url_key(
        stream_url: str,
    ) -> str:
        return str(
            stream_url
        ).strip()

    @classmethod
    def _unique_channels_by_url(
        cls,
        channels: list[Channel],
    ) -> list[Channel]:
        """
        Evita richieste HTTP ripetute verso lo stesso URL.

        Il risultato Health viene comunque riutilizzato da tutti i
        candidati del gruppo che condividono quel collegamento.
        """

        unique: list[
            Channel
        ] = []

        seen: set[
            str
        ] = set()

        for channel in channels:
            key = cls._url_key(
                channel.stream_url
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            unique.append(
                channel
            )

        return unique

    @staticmethod
    def _is_publishable_status(
        status: str,
    ) -> bool:
        return status in {
            "online",
            "reachable",
        }

    @classmethod
    def _build_health_score_map(
        cls,
        results: list[
            HealthResult
        ],
    ) -> dict[str, float]:
        """
        I risultati non pubblicabili ricevono punteggio zero.

        Per checker legacy che dichiarano un canale online ma non
        valorizzano health_score, viene usato un minimo di 1.
        """

        scores: dict[
            str,
            float,
        ] = {}

        for result in results:
            if not cls._is_publishable_status(
                result.status
            ):
                score = 0.0
            else:
                try:
                    score = float(
                        result.health_score
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    score = 0.0

                if score <= 0:
                    score = 1.0

            scores[
                cls._url_key(
                    result.stream_url
                )
            ] = score

        return scores

    @classmethod
    def _filter_publishable_channels(
        cls,
        channels: list[Channel],
        health_result_by_url: dict[
            str,
            HealthResult,
        ],
    ) -> list[Channel]:
        return [
            channel
            for channel in channels
            if (
                (
                    result := (
                        health_result_by_url.get(
                            cls._url_key(
                                channel.stream_url
                            )
                        )
                    )
                )
                is not None
                and cls._is_publishable_status(
                    result.status
                )
            )
        ]

    def _empty_recovery_diagnostics(
        self,
        *,
        mode: str,
        candidate_group_diagnostics: (
            dict[str, object]
        ),
    ) -> dict[str, object]:
        raw_stats = (
            candidate_group_diagnostics.get(
                "stats",
                {},
            )
        )

        stats = (
            raw_stats
            if isinstance(
                raw_stats,
                dict,
            )
            else {}
        )

        return {
            "enabled": False,
            "mode": mode,
            "candidate_groups": (
                self._as_int(
                    stats.get(
                        "groups",
                        0,
                    )
                )
            ),
            "duplicate_candidate_groups": (
                self._as_int(
                    stats.get(
                        "duplicate_groups",
                        0,
                    )
                )
            ),
            "alternative_candidates": (
                self._as_int(
                    stats.get(
                        "alternative_candidates",
                        0,
                    )
                )
            ),
            "candidate_streams_checked": 0,
            "selected_primary": 0,
            "recovered_from_alternative": 0,
            "upgraded_to_better_alternative": 0,
            "all_candidates_failed": 0,
            "decisions_reported": 0,
            "decisions_truncated": 0,
            "decisions": [],
        }

    def _build_recovery_diagnostics(
        self,
        *,
        initial_grouping: object,
        final_grouping: object | None,
        health_result_by_url: dict[
            str,
            HealthResult,
        ],
        candidate_streams_checked: int,
        candidate_group_diagnostics: (
            dict[str, object]
        ),
    ) -> dict[str, object]:
        """
        Confronta il candidato preferito prima e dopo il controllo.

        `recovered_from_alternative` conta solo i casi in cui il
        candidato iniziale non era disponibile e un'alternativa sì.
        """

        diagnostics = (
            self._empty_recovery_diagnostics(
                mode=(
                    "candidate_health_recovery"
                ),
                candidate_group_diagnostics=(
                    candidate_group_diagnostics
                ),
            )
        )

        diagnostics["enabled"] = True
        diagnostics[
            "candidate_streams_checked"
        ] = candidate_streams_checked

        initial_groups = {
            str(
                getattr(
                    group,
                    "group_id",
                    index,
                )
            ): group
            for index, group in enumerate(
                getattr(
                    initial_grouping,
                    "groups",
                    (),
                )
            )
        }

        final_groups = {
            str(
                getattr(
                    group,
                    "group_id",
                    index,
                )
            ): group
            for index, group in enumerate(
                getattr(
                    final_grouping,
                    "groups",
                    (),
                )
            )
        } if final_grouping is not None else {}

        decisions: list[
            dict[str, object]
        ] = []

        selected_primary = 0
        recovered = 0
        upgraded = 0
        all_failed = 0

        for group_id, initial_group in (
            initial_groups.items()
        ):
            final_group = final_groups.get(
                group_id,
                initial_group,
            )

            initial_channel = getattr(
                initial_group,
                "preferred_channel",
                None,
            )

            selected_channel = getattr(
                final_group,
                "preferred_channel",
                None,
            )

            if (
                not isinstance(
                    initial_channel,
                    Channel,
                )
                or not isinstance(
                    selected_channel,
                    Channel,
                )
            ):
                continue

            group_channels = tuple(
                getattr(
                    initial_group,
                    "channels",
                    (),
                )
            )

            publishable_channels = [
                channel
                for channel in group_channels
                if (
                    isinstance(
                        channel,
                        Channel,
                    )
                    and self._health_is_publishable(
                        health_result_by_url.get(
                            self._url_key(
                                channel.stream_url
                            )
                        )
                    )
                )
            ]

            initial_result = (
                health_result_by_url.get(
                    self._url_key(
                        initial_channel.stream_url
                    )
                )
            )

            selected_result = (
                health_result_by_url.get(
                    self._url_key(
                        selected_channel.stream_url
                    )
                )
            )

            initial_available = (
                self._health_is_publishable(
                    initial_result
                )
            )

            selected_available = (
                self._health_is_publishable(
                    selected_result
                )
            )

            changed = (
                self._url_key(
                    selected_channel.stream_url
                )
                != self._url_key(
                    initial_channel.stream_url
                )
            )

            outcome = (
                "selected_primary"
            )

            if not publishable_channels:
                all_failed += 1
                outcome = (
                    "all_candidates_failed"
                )

            elif (
                changed
                and not initial_available
                and selected_available
            ):
                recovered += 1
                outcome = (
                    "recovered_from_alternative"
                )

            elif (
                changed
                and selected_available
            ):
                upgraded += 1
                outcome = (
                    "upgraded_to_better_alternative"
                )

            elif selected_available:
                selected_primary += 1

            else:
                # Caso difensivo: esiste almeno un candidato
                # pubblicabile ma il merger non lo ha selezionato.
                all_failed += 1
                outcome = (
                    "selection_not_publishable"
                )

            if (
                changed
                or outcome
                != "selected_primary"
            ):
                decisions.append(
                    {
                        "group_id": group_id,
                        "name": (
                            selected_channel.name
                        ),
                        "outcome": outcome,
                        "initial_url": (
                            initial_channel
                            .stream_url
                        ),
                        "initial_status": (
                            initial_result.status
                            if initial_result
                            is not None
                            else "not_checked"
                        ),
                        "selected_url": (
                            selected_channel
                            .stream_url
                        ),
                        "selected_status": (
                            selected_result.status
                            if selected_result
                            is not None
                            else "not_checked"
                        ),
                        "candidate_count": len(
                            group_channels
                        ),
                        "publishable_candidates": (
                            len(
                                publishable_channels
                            )
                        ),
                    }
                )

        reported = decisions[
            :self.MERGER_DECISIONS_REPORT_LIMIT
        ]

        diagnostics.update(
            {
                "selected_primary": (
                    selected_primary
                ),
                "recovered_from_alternative": (
                    recovered
                ),
                "upgraded_to_better_alternative": (
                    upgraded
                ),
                "all_candidates_failed": (
                    all_failed
                ),
                "decisions_reported": len(
                    reported
                ),
                "decisions_truncated": max(
                    0,
                    len(decisions)
                    - len(reported),
                ),
                "decisions": reported,
            }
        )

        return diagnostics

    @classmethod
    def _health_is_publishable(
        cls,
        result: (
            HealthResult | None
        ),
    ) -> bool:
        return (
            result is not None
            and cls._is_publishable_status(
                result.status
            )
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
        *,
        recovery_diagnostics: (
            dict[str, object] | None
        ) = None,
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
            "alternative_recovery": (
                recovery_diagnostics
                or {}
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
