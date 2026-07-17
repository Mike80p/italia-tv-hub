from __future__ import annotations

import concurrent.futures
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Iterable

from src.models.channel import Channel


@dataclass(slots=True)
class HealthResult:
    name: str
    stream_url: str
    source_id: str
    status: str
    http_status: int | None
    response_ms: int | None
    content_type: str
    final_url: str
    error: str

    # Campi Quality Engine.
    # I valori predefiniti mantengono compatibile il vecchio
    # costruttore di HealthResult.
    health_score: int = 0
    classification_reason: str = ""
    bytes_read: int = 0
    redirected: bool = False
    error_type: str = ""

    # Diagnostica Playback Verification Engine.
    playback_verified: bool = False
    hls_kind: str = ""
    manifest_url: str = ""
    variant_url: str = ""
    segment_url: str = ""
    segment_http_status: int | None = None
    segment_content_type: str = ""
    segment_bytes_read: int = 0
    drm_detected: bool = False
    codecs: str = ""
    resolution: str = ""
    bandwidth: int = 0
    country_check: str = ""
    validation_steps: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HealthStats:
    input_channels: int
    checked: int
    online: int
    reachable: int
    offline: int
    redirects: int
    errors: int
    average_score: float
    average_response_ms: float
    min_score: int
    max_score: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HealthBatchResult:
    results: tuple[HealthResult, ...]
    stats: HealthStats

    def to_dict(self) -> dict[str, object]:
        return {
            "stats": self.stats.to_dict(),
            "results": [
                result.to_dict()
                for result in self.results
            ],
        }


@dataclass(frozen=True, slots=True)
class _FetchResult:
    requested_url: str
    final_url: str
    http_status: int | None
    content_type: str
    data: bytes

    @property
    def redirected(self) -> bool:
        return self.final_url != self.requested_url


@dataclass(frozen=True, slots=True)
class _HLSVariant:
    url: str
    codecs: str = ""
    resolution: str = ""
    bandwidth: int = 0


@dataclass(frozen=True, slots=True)
class _PlaybackVerification:
    status: str
    reason: str
    base_score: int
    error: str = ""
    error_type: str = ""
    hls_kind: str = ""
    manifest_url: str = ""
    variant_url: str = ""
    segment_url: str = ""
    segment_http_status: int | None = None
    segment_content_type: str = ""
    segment_bytes_read: int = 0
    bytes_read: int = 0
    drm_detected: bool = False
    codecs: str = ""
    resolution: str = ""
    bandwidth: int = 0
    playback_verified: bool = False
    validation_steps: tuple[str, ...] = ()


class StreamHealthChecker:
    """
    Verifica disponibilità e riproducibilità dei flussi.

    `deep_hls_check=False` conserva il comportamento storico:
    una firma #EXTM3U è sufficiente per classificare il flusso online.

    `deep_hls_check=True` esegue invece:

    1. download del manifest iniziale;
    2. controllo DRM;
    3. scelta di una variante compatibile dal master HLS;
    4. download della media playlist;
    5. download reale di un segmento video/audio;
    6. controllo del payload del segmento.

    Solo il secondo flusso è adatto al filtro automatico della
    playlist pubblicata per Samsung Tizen.
    """

    MEDIA_CONTENT_TYPES = (
        "mpegurl",
        "video/",
        "audio/",
        "octet-stream",
        "mp2t",
    )

    MANIFEST_CONTENT_TYPES = (
        "application/vnd.apple.mpegurl",
        "application/x-mpegurl",
        "application/mpegurl",
        "audio/mpegurl",
        "audio/x-mpegurl",
    )

    SEGMENT_CONTENT_TYPES = (
        "video/",
        "audio/",
        "application/octet-stream",
        "binary/octet-stream",
        "video/mp2t",
        "application/mp2t",
    )

    UNSUPPORTED_TIZEN_CODECS = (
        "av01",
        "dvh1",
        "dvhe",
        "theora",
    )

    COUNTRY_ATTRIBUTE_KEYS = (
        "tvg-country",
        "country",
        "country-code",
        "country_code",
        "region",
    )

    URL_COUNTRY_KEYS = (
        "country",
        "countrycode",
        "country_code",
        "region",
        "market",
    )

    TOKEN_EXPIRY_KEYS = (
        "exp",
        "expires",
        "expiry",
        "token_exp",
        "tokenexp",
        "expiration",
    )

    def __init__(
        self,
        timeout_seconds: int = 10,
        max_workers: int = 12,
        user_agent: str = "Italia-TV-Hub/0.9",
        read_bytes: int = 2048,
        *,
        deep_hls_check: bool = False,
        manifest_read_bytes: int = 262_144,
        segment_read_bytes: int = 8_192,
        max_variants: int = 2,
        expected_country: str = "",
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds deve essere "
                "maggiore di zero"
            )

        if max_workers <= 0:
            raise ValueError(
                "max_workers deve essere "
                "maggiore di zero"
            )

        if read_bytes <= 0:
            raise ValueError(
                "read_bytes deve essere "
                "maggiore di zero"
            )

        if manifest_read_bytes <= 0:
            raise ValueError(
                "manifest_read_bytes deve essere "
                "maggiore di zero"
            )

        if segment_read_bytes <= 0:
            raise ValueError(
                "segment_read_bytes deve essere "
                "maggiore di zero"
            )

        if max_variants <= 0:
            raise ValueError(
                "max_variants deve essere "
                "maggiore di zero"
            )

        self.timeout_seconds = timeout_seconds
        self.max_workers = max_workers
        self.user_agent = user_agent
        self.read_bytes = read_bytes
        self.deep_hls_check = bool(
            deep_hls_check
        )
        self.manifest_read_bytes = (
            manifest_read_bytes
        )
        self.segment_read_bytes = (
            segment_read_bytes
        )
        self.max_variants = max_variants
        self.expected_country = (
            str(expected_country)
            .strip()
            .upper()
        )

    def check_many(
        self,
        channels: Iterable[Channel],
    ) -> list[HealthResult]:
        """
        Interfaccia compatibile con il checker precedente.

        Restituisce la sola lista dei risultati, mantenendo
        l'ordine dei canali ricevuti.
        """

        detailed = self.check_many_detailed(
            channels
        )

        return list(detailed.results)

    def check_many_detailed(
        self,
        channels: Iterable[Channel],
    ) -> HealthBatchResult:
        """
        Controlla più canali in parallelo e produce anche
        statistiche aggregate del batch.
        """

        channel_list = list(channels)

        if not channel_list:
            return HealthBatchResult(
                results=(),
                stats=self._empty_stats(),
            )

        ordered_results: list[
            HealthResult | None
        ] = [
            None
            for _ in channel_list
        ]

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            futures = {
                executor.submit(
                    self.check,
                    channel,
                ): index
                for index, channel
                in enumerate(channel_list)
            }

            for future in (
                concurrent.futures.as_completed(
                    futures
                )
            ):
                index = futures[future]

                try:
                    ordered_results[index] = (
                        future.result()
                    )
                except Exception as exc:
                    channel = channel_list[
                        index
                    ]

                    ordered_results[index] = (
                        self._error_result(
                            channel=channel,
                            started=(
                                time.perf_counter()
                            ),
                            http_status=None,
                            error=(
                                f"{type(exc).__name__}: "
                                f"{exc}"
                            ),
                            error_type=(
                                type(exc).__name__
                            ),
                            classification_reason=(
                                "worker_unexpected_error"
                            ),
                        )
                    )

        results = tuple(
            result
            for result in ordered_results
            if result is not None
        )

        return HealthBatchResult(
            results=results,
            stats=self._build_stats(
                input_channels=len(
                    channel_list
                ),
                results=results,
            ),
        )

    def check(
        self,
        channel: Channel,
    ) -> HealthResult:
        started = time.perf_counter()

        country_check = (
            self._country_check(
                channel
            )
        )

        if country_check == "mismatch":
            return self._error_result(
                channel=channel,
                started=started,
                http_status=None,
                error=(
                    "Canale dichiarato per un "
                    "mercato diverso da "
                    f"{self.expected_country}"
                ),
                error_type=(
                    "CountryMismatch"
                ),
                classification_reason=(
                    "country_mismatch"
                ),
                country_check=(
                    country_check
                ),
            )

        request_url, extra_headers = (
            self._split_url_headers(
                channel.stream_url
            )
        )

        if (
            self.deep_hls_check
            and self._has_expired_token(
                request_url
            )
        ):
            return self._error_result(
                channel=channel,
                started=started,
                http_status=None,
                error=(
                    "Il token dello stream "
                    "risulta scaduto"
                ),
                error_type="ExpiredToken",
                classification_reason=(
                    "token_expired"
                ),
                final_url=request_url,
                country_check=country_check,
            )

        read_limit = (
            self.manifest_read_bytes
            if self.deep_hls_check
            else self.read_bytes
        )

        try:
            initial = self._fetch(
                request_url,
                read_limit=read_limit,
                extra_headers=(
                    extra_headers
                ),
            )

            response_ms = self._elapsed_ms(
                started
            )

            (
                preliminary_status,
                preliminary_reason,
                preliminary_score,
            ) = self._assess_response(
                http_status=(
                    initial.http_status
                ),
                content_type=(
                    initial.content_type
                ),
                data=initial.data,
            )

            is_hls = self._is_hls_payload(
                initial.content_type,
                initial.data,
            )

            if (
                not self.deep_hls_check
                or not is_hls
            ):
                if (
                    self.deep_hls_check
                    and not is_hls
                ):
                    (
                        preliminary_status,
                        preliminary_reason,
                        preliminary_score,
                    ) = (
                        self
                        ._assess_deep_direct_payload(
                            http_status=(
                                initial.http_status
                            ),
                            content_type=(
                                initial.content_type
                            ),
                            data=initial.data,
                        )
                    )

                redirected = (
                    initial.final_url
                    != request_url
                )

                health_score = (
                    self._calculate_score(
                        status=(
                            preliminary_status
                        ),
                        base_score=(
                            preliminary_score
                        ),
                        response_ms=(
                            response_ms
                        ),
                        redirected=redirected,
                    )
                )

                verified_direct = (
                    self.deep_hls_check
                    and preliminary_status
                    == "online"
                )

                return HealthResult(
                    name=channel.name,
                    stream_url=(
                        channel.stream_url
                    ),
                    source_id=(
                        channel.source_id
                    ),
                    status=(
                        preliminary_status
                    ),
                    http_status=(
                        initial.http_status
                    ),
                    response_ms=response_ms,
                    content_type=(
                        initial.content_type
                    ),
                    final_url=(
                        initial.final_url
                    ),
                    error="",
                    health_score=(
                        health_score
                    ),
                    classification_reason=(
                        preliminary_reason
                    ),
                    bytes_read=len(
                        initial.data
                    ),
                    redirected=redirected,
                    error_type="",
                    playback_verified=(
                        verified_direct
                    ),
                    manifest_url=(
                        initial.final_url
                    ),
                    country_check=(
                        country_check
                    ),
                    validation_steps=(
                        (
                            "initial_payload",
                            "direct_media_verified",
                        )
                        if verified_direct
                        else (
                            "initial_payload",
                        )
                    ),
                )

            verification = (
                self._verify_hls(
                    initial=initial,
                    extra_headers=(
                        extra_headers
                    ),
                )
            )

            response_ms = self._elapsed_ms(
                started
            )

            redirected = (
                initial.final_url
                != request_url
            )

            health_score = (
                self._calculate_score(
                    status=(
                        verification.status
                    ),
                    base_score=(
                        verification.base_score
                    ),
                    response_ms=response_ms,
                    redirected=redirected,
                )
            )

            return HealthResult(
                name=channel.name,
                stream_url=(
                    channel.stream_url
                ),
                source_id=(
                    channel.source_id
                ),
                status=verification.status,
                http_status=(
                    initial.http_status
                ),
                response_ms=response_ms,
                content_type=(
                    initial.content_type
                ),
                final_url=(
                    initial.final_url
                ),
                error=verification.error,
                health_score=health_score,
                classification_reason=(
                    verification.reason
                ),
                bytes_read=(
                    len(initial.data)
                    + verification.bytes_read
                ),
                redirected=redirected,
                error_type=(
                    verification.error_type
                ),
                playback_verified=(
                    verification
                    .playback_verified
                ),
                hls_kind=(
                    verification.hls_kind
                ),
                manifest_url=(
                    verification.manifest_url
                    or initial.final_url
                ),
                variant_url=(
                    verification.variant_url
                ),
                segment_url=(
                    verification.segment_url
                ),
                segment_http_status=(
                    verification
                    .segment_http_status
                ),
                segment_content_type=(
                    verification
                    .segment_content_type
                ),
                segment_bytes_read=(
                    verification
                    .segment_bytes_read
                ),
                drm_detected=(
                    verification.drm_detected
                ),
                codecs=verification.codecs,
                resolution=(
                    verification.resolution
                ),
                bandwidth=(
                    verification.bandwidth
                ),
                country_check=(
                    country_check
                ),
                validation_steps=(
                    verification
                    .validation_steps
                ),
            )

        except urllib.error.HTTPError as exc:
            return self._error_result(
                channel=channel,
                started=started,
                http_status=exc.code,
                error=(
                    "HTTPError "
                    f"{exc.code}: {exc.reason}"
                ),
                error_type="HTTPError",
                classification_reason=(
                    "http_error"
                ),
                final_url=(
                    exc.geturl()
                    if hasattr(
                        exc,
                        "geturl",
                    )
                    else request_url
                ),
                country_check=country_check,
            )

        except urllib.error.URLError as exc:
            return self._error_result(
                channel=channel,
                started=started,
                http_status=None,
                error=(
                    f"URLError: {exc.reason}"
                ),
                error_type="URLError",
                classification_reason=(
                    "network_error"
                ),
                country_check=country_check,
            )

        except (
            TimeoutError,
            socket.timeout,
        ):
            return self._error_result(
                channel=channel,
                started=started,
                http_status=None,
                error="Timeout",
                error_type="TimeoutError",
                classification_reason="timeout",
                country_check=country_check,
            )

        except Exception as exc:
            return self._error_result(
                channel=channel,
                started=started,
                http_status=None,
                error=(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
                error_type=type(exc).__name__,
                classification_reason=(
                    "unexpected_error"
                ),
                country_check=country_check,
            )

    def _verify_hls(
        self,
        *,
        initial: _FetchResult,
        extra_headers: dict[str, str],
    ) -> _PlaybackVerification:
        text = self._decode_manifest(
            initial.data
        )

        steps = [
            "manifest_downloaded",
        ]

        if self._detect_drm(
            text
        ):
            return _PlaybackVerification(
                status="offline",
                reason="hls_drm_detected",
                base_score=0,
                error=(
                    "Manifest HLS protetto da "
                    "DRM non riproducibile dal "
                    "player M3U generico"
                ),
                error_type="DRMDetected",
                hls_kind=(
                    self._hls_kind(
                        text
                    )
                ),
                manifest_url=(
                    initial.final_url
                ),
                bytes_read=0,
                drm_detected=True,
                validation_steps=tuple(
                    steps
                    + [
                        "drm_rejected",
                    ]
                ),
            )

        variants = self._parse_variants(
            text,
            initial.final_url,
        )

        if variants:
            steps.append(
                "master_playlist"
            )

            supported = [
                variant
                for variant in variants
                if self._codecs_supported(
                    variant.codecs
                )
            ]

            if not supported:
                first = variants[0]

                return _PlaybackVerification(
                    status="offline",
                    reason=(
                        "hls_unsupported_codec"
                    ),
                    base_score=0,
                    error=(
                        "Nessuna variante HLS "
                        "usa codec compatibili"
                    ),
                    error_type=(
                        "UnsupportedCodec"
                    ),
                    hls_kind="master",
                    manifest_url=(
                        initial.final_url
                    ),
                    codecs=first.codecs,
                    resolution=(
                        first.resolution
                    ),
                    bandwidth=(
                        first.bandwidth
                    ),
                    validation_steps=tuple(
                        steps
                        + [
                            "variants_rejected",
                        ]
                    ),
                )

            candidates = sorted(
                supported,
                key=self._variant_rank,
                reverse=True,
            )[
                :self.max_variants
            ]

            last_failure: (
                _PlaybackVerification | None
            ) = None

            for variant in candidates:
                try:
                    variant_response = (
                        self._fetch(
                            variant.url,
                            read_limit=(
                                self
                                .manifest_read_bytes
                            ),
                            extra_headers=(
                                extra_headers
                            ),
                        )
                    )
                except urllib.error.HTTPError as exc:
                    last_failure = (
                        _PlaybackVerification(
                            status="offline",
                            reason=(
                                "hls_variant_http_error"
                            ),
                            base_score=0,
                            error=(
                                "Variante HLS HTTP "
                                f"{exc.code}: "
                                f"{exc.reason}"
                            ),
                            error_type=(
                                "HTTPError"
                            ),
                            hls_kind="master",
                            manifest_url=(
                                initial.final_url
                            ),
                            variant_url=(
                                variant.url
                            ),
                            codecs=(
                                variant.codecs
                            ),
                            resolution=(
                                variant.resolution
                            ),
                            bandwidth=(
                                variant.bandwidth
                            ),
                            validation_steps=tuple(
                                steps
                                + [
                                    "variant_failed",
                                ]
                            ),
                        )
                    )
                    continue

                except (
                    urllib.error.URLError,
                    TimeoutError,
                    socket.timeout,
                ) as exc:
                    last_failure = (
                        _PlaybackVerification(
                            status="offline",
                            reason=(
                                "hls_variant_network_error"
                            ),
                            base_score=0,
                            error=str(exc),
                            error_type=(
                                type(exc).__name__
                            ),
                            hls_kind="master",
                            manifest_url=(
                                initial.final_url
                            ),
                            variant_url=(
                                variant.url
                            ),
                            codecs=(
                                variant.codecs
                            ),
                            resolution=(
                                variant.resolution
                            ),
                            bandwidth=(
                                variant.bandwidth
                            ),
                            validation_steps=tuple(
                                steps
                                + [
                                    "variant_failed",
                                ]
                            ),
                        )
                    )
                    continue

                if not self._is_hls_payload(
                    variant_response
                    .content_type,
                    variant_response.data,
                ):
                    last_failure = (
                        _PlaybackVerification(
                            status="offline",
                            reason=(
                                "hls_variant_invalid_payload"
                            ),
                            base_score=0,
                            error=(
                                "La variante non "
                                "restituisce un "
                                "manifest HLS"
                            ),
                            error_type=(
                                "InvalidManifest"
                            ),
                            hls_kind="master",
                            manifest_url=(
                                initial.final_url
                            ),
                            variant_url=(
                                variant_response
                                .final_url
                            ),
                            bytes_read=len(
                                variant_response.data
                            ),
                            codecs=(
                                variant.codecs
                            ),
                            resolution=(
                                variant.resolution
                            ),
                            bandwidth=(
                                variant.bandwidth
                            ),
                            validation_steps=tuple(
                                steps
                                + [
                                    "variant_invalid",
                                ]
                            ),
                        )
                    )
                    continue

                verified = (
                    self._verify_media_playlist(
                        manifest_response=(
                            variant_response
                        ),
                        extra_headers=(
                            extra_headers
                        ),
                        hls_kind="master",
                        root_manifest_url=(
                            initial.final_url
                        ),
                        variant=variant,
                        previous_steps=(
                            steps
                            + [
                                "variant_downloaded",
                            ]
                        ),
                    )
                )

                if verified.playback_verified:
                    return verified

                last_failure = verified

            return (
                last_failure
                or _PlaybackVerification(
                    status="offline",
                    reason=(
                        "hls_all_variants_failed"
                    ),
                    base_score=0,
                    error=(
                        "Nessuna variante HLS "
                        "riproducibile"
                    ),
                    error_type=(
                        "PlaybackVerificationError"
                    ),
                    hls_kind="master",
                    manifest_url=(
                        initial.final_url
                    ),
                    validation_steps=tuple(
                        steps
                        + [
                            "all_variants_failed",
                        ]
                    ),
                )
            )

        return self._verify_media_playlist(
            manifest_response=initial,
            extra_headers=extra_headers,
            hls_kind="media",
            root_manifest_url=(
                initial.final_url
            ),
            variant=None,
            previous_steps=steps,
        )

    def _verify_media_playlist(
        self,
        *,
        manifest_response: _FetchResult,
        extra_headers: dict[str, str],
        hls_kind: str,
        root_manifest_url: str,
        variant: _HLSVariant | None,
        previous_steps: list[str],
    ) -> _PlaybackVerification:
        text = self._decode_manifest(
            manifest_response.data
        )

        steps = list(
            previous_steps
        )

        steps.append(
            "media_playlist"
        )

        if self._detect_drm(
            text
        ):
            return _PlaybackVerification(
                status="offline",
                reason="hls_drm_detected",
                base_score=0,
                error=(
                    "Media playlist protetta "
                    "da DRM"
                ),
                error_type="DRMDetected",
                hls_kind=hls_kind,
                manifest_url=(
                    root_manifest_url
                ),
                variant_url=(
                    manifest_response.final_url
                    if hls_kind == "master"
                    else ""
                ),
                bytes_read=len(
                    manifest_response.data
                ),
                drm_detected=True,
                codecs=(
                    variant.codecs
                    if variant
                    else ""
                ),
                resolution=(
                    variant.resolution
                    if variant
                    else ""
                ),
                bandwidth=(
                    variant.bandwidth
                    if variant
                    else 0
                ),
                validation_steps=tuple(
                    steps
                    + [
                        "drm_rejected",
                    ]
                ),
            )

        segment_url = (
            self._first_segment_url(
                text,
                manifest_response.final_url,
            )
        )

        if not segment_url:
            return _PlaybackVerification(
                status="offline",
                reason=(
                    "hls_no_media_segment"
                ),
                base_score=0,
                error=(
                    "Il manifest non contiene "
                    "segmenti multimediali"
                ),
                error_type=(
                    "MissingMediaSegment"
                ),
                hls_kind=hls_kind,
                manifest_url=(
                    root_manifest_url
                ),
                variant_url=(
                    manifest_response.final_url
                    if hls_kind == "master"
                    else ""
                ),
                bytes_read=len(
                    manifest_response.data
                ),
                codecs=(
                    variant.codecs
                    if variant
                    else ""
                ),
                resolution=(
                    variant.resolution
                    if variant
                    else ""
                ),
                bandwidth=(
                    variant.bandwidth
                    if variant
                    else 0
                ),
                validation_steps=tuple(
                    steps
                    + [
                        "segment_missing",
                    ]
                ),
            )

        if self._has_expired_token(
            segment_url
        ):
            return _PlaybackVerification(
                status="offline",
                reason=(
                    "hls_segment_token_expired"
                ),
                base_score=0,
                error=(
                    "Il token del segmento "
                    "risulta scaduto"
                ),
                error_type="ExpiredToken",
                hls_kind=hls_kind,
                manifest_url=(
                    root_manifest_url
                ),
                variant_url=(
                    manifest_response.final_url
                    if hls_kind == "master"
                    else ""
                ),
                segment_url=segment_url,
                bytes_read=len(
                    manifest_response.data
                ),
                codecs=(
                    variant.codecs
                    if variant
                    else ""
                ),
                resolution=(
                    variant.resolution
                    if variant
                    else ""
                ),
                bandwidth=(
                    variant.bandwidth
                    if variant
                    else 0
                ),
                validation_steps=tuple(
                    steps
                    + [
                        "segment_token_expired",
                    ]
                ),
            )

        try:
            segment = self._fetch(
                segment_url,
                read_limit=(
                    self.segment_read_bytes
                ),
                extra_headers=(
                    extra_headers
                ),
                accept=(
                    "video/*,audio/*,"
                    "application/octet-stream,"
                    "*/*"
                ),
            )

        except urllib.error.HTTPError as exc:
            return _PlaybackVerification(
                status="offline",
                reason=(
                    "hls_segment_http_error"
                ),
                base_score=0,
                error=(
                    "Segmento HLS HTTP "
                    f"{exc.code}: {exc.reason}"
                ),
                error_type="HTTPError",
                hls_kind=hls_kind,
                manifest_url=(
                    root_manifest_url
                ),
                variant_url=(
                    manifest_response.final_url
                    if hls_kind == "master"
                    else ""
                ),
                segment_url=segment_url,
                segment_http_status=(
                    exc.code
                ),
                bytes_read=len(
                    manifest_response.data
                ),
                codecs=(
                    variant.codecs
                    if variant
                    else ""
                ),
                resolution=(
                    variant.resolution
                    if variant
                    else ""
                ),
                bandwidth=(
                    variant.bandwidth
                    if variant
                    else 0
                ),
                validation_steps=tuple(
                    steps
                    + [
                        "segment_http_error",
                    ]
                ),
            )

        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
        ) as exc:
            return _PlaybackVerification(
                status="offline",
                reason=(
                    "hls_segment_network_error"
                ),
                base_score=0,
                error=str(exc),
                error_type=(
                    type(exc).__name__
                ),
                hls_kind=hls_kind,
                manifest_url=(
                    root_manifest_url
                ),
                variant_url=(
                    manifest_response.final_url
                    if hls_kind == "master"
                    else ""
                ),
                segment_url=segment_url,
                bytes_read=len(
                    manifest_response.data
                ),
                codecs=(
                    variant.codecs
                    if variant
                    else ""
                ),
                resolution=(
                    variant.resolution
                    if variant
                    else ""
                ),
                bandwidth=(
                    variant.bandwidth
                    if variant
                    else 0
                ),
                validation_steps=tuple(
                    steps
                    + [
                        "segment_network_error",
                    ]
                ),
            )

        segment_valid = (
            self._is_media_segment(
                url=segment.final_url,
                content_type=(
                    segment.content_type
                ),
                data=segment.data,
            )
        )

        if not segment_valid:
            return _PlaybackVerification(
                status="offline",
                reason=(
                    "hls_invalid_media_segment"
                ),
                base_score=0,
                error=(
                    "Il segmento restituito "
                    "non contiene dati "
                    "multimediali validi"
                ),
                error_type=(
                    "InvalidMediaSegment"
                ),
                hls_kind=hls_kind,
                manifest_url=(
                    root_manifest_url
                ),
                variant_url=(
                    manifest_response.final_url
                    if hls_kind == "master"
                    else ""
                ),
                segment_url=(
                    segment.final_url
                ),
                segment_http_status=(
                    segment.http_status
                ),
                segment_content_type=(
                    segment.content_type
                ),
                segment_bytes_read=len(
                    segment.data
                ),
                bytes_read=(
                    len(
                        manifest_response.data
                    )
                    + len(segment.data)
                ),
                codecs=(
                    variant.codecs
                    if variant
                    else ""
                ),
                resolution=(
                    variant.resolution
                    if variant
                    else ""
                ),
                bandwidth=(
                    variant.bandwidth
                    if variant
                    else 0
                ),
                validation_steps=tuple(
                    steps
                    + [
                        "segment_invalid",
                    ]
                ),
            )

        return _PlaybackVerification(
            status="online",
            reason=(
                "hls_segment_verified"
            ),
            base_score=100,
            hls_kind=hls_kind,
            manifest_url=(
                root_manifest_url
            ),
            variant_url=(
                manifest_response.final_url
                if hls_kind == "master"
                else ""
            ),
            segment_url=(
                segment.final_url
            ),
            segment_http_status=(
                segment.http_status
            ),
            segment_content_type=(
                segment.content_type
            ),
            segment_bytes_read=len(
                segment.data
            ),
            bytes_read=(
                len(manifest_response.data)
                + len(segment.data)
            ),
            codecs=(
                variant.codecs
                if variant
                else ""
            ),
            resolution=(
                variant.resolution
                if variant
                else ""
            ),
            bandwidth=(
                variant.bandwidth
                if variant
                else 0
            ),
            playback_verified=True,
            validation_steps=tuple(
                steps
                + [
                    "segment_downloaded",
                    "playback_verified",
                ]
            ),
        )

    def _fetch(
        self,
        url: str,
        *,
        read_limit: int,
        extra_headers: (
            dict[str, str] | None
        ) = None,
        accept: str | None = None,
    ) -> _FetchResult:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": (
                accept
                or (
                    "application/vnd.apple.mpegurl,"
                    "application/x-mpegURL,"
                    "video/*,"
                    "audio/*,"
                    "application/octet-stream,"
                    "*/*"
                )
            ),
            "Range": (
                f"bytes=0-{read_limit - 1}"
            ),
            "Cache-Control": "no-cache",
        }

        for key, value in (
            extra_headers
            or {}
        ).items():
            if key.casefold() == (
                "user-agent"
            ):
                headers["User-Agent"] = value
            else:
                headers[key] = value

        request = urllib.request.Request(
            url,
            headers=headers,
            method="GET",
        )

        with urllib.request.urlopen(
            request,
            timeout=self.timeout_seconds,
        ) as response:
            data = response.read(
                read_limit
            )

            return _FetchResult(
                requested_url=url,
                final_url=(
                    response.geturl()
                    or url
                ),
                http_status=(
                    response.getcode()
                ),
                content_type=(
                    response.headers.get(
                        "Content-Type",
                        "",
                    )
                    or ""
                ),
                data=data,
            )

    @classmethod
    def _parse_variants(
        cls,
        text: str,
        base_url: str,
    ) -> list[_HLSVariant]:
        lines = [
            line.strip()
            for line in text.replace(
                "\r",
                "",
            ).split(
                "\n"
            )
        ]

        variants: list[
            _HLSVariant
        ] = []

        for index, line in enumerate(
            lines
        ):
            if not line.upper().startswith(
                "#EXT-X-STREAM-INF:"
            ):
                continue

            attributes = (
                cls._parse_attribute_list(
                    line.split(
                        ":",
                        1,
                    )[1]
                )
            )

            uri = ""

            for following in lines[
                index + 1:
            ]:
                if not following:
                    continue

                if following.startswith(
                    "#"
                ):
                    continue

                uri = following
                break

            if not uri:
                continue

            bandwidth = cls._safe_int(
                attributes.get(
                    "AVERAGE-BANDWIDTH",
                    attributes.get(
                        "BANDWIDTH",
                        "0",
                    ),
                )
            )

            variants.append(
                _HLSVariant(
                    url=urllib.parse.urljoin(
                        base_url,
                        uri,
                    ),
                    codecs=attributes.get(
                        "CODECS",
                        "",
                    ),
                    resolution=attributes.get(
                        "RESOLUTION",
                        "",
                    ),
                    bandwidth=bandwidth,
                )
            )

        return variants

    @classmethod
    def _first_segment_url(
        cls,
        text: str,
        base_url: str,
    ) -> str:
        lines = [
            line.strip()
            for line in text.replace(
                "\r",
                "",
            ).split(
                "\n"
            )
        ]

        has_media_markers = any(
            line.upper().startswith(
                (
                    "#EXTINF:",
                    "#EXT-X-TARGETDURATION:",
                    "#EXT-X-MEDIA-SEQUENCE:",
                    "#EXT-X-PART:",
                )
            )
            for line in lines
        )

        if not has_media_markers:
            return ""

        for line in lines:
            if (
                not line
                or line.startswith("#")
            ):
                continue

            return urllib.parse.urljoin(
                base_url,
                line,
            )

        # Low-Latency HLS può usare soltanto EXT-X-PART nel momento
        # preciso in cui viene letto il manifest.
        for line in lines:
            if not line.upper().startswith(
                "#EXT-X-PART:"
            ):
                continue

            attributes = (
                cls._parse_attribute_list(
                    line.split(
                        ":",
                        1,
                    )[1]
                )
            )

            uri = attributes.get(
                "URI",
                "",
            )

            if uri:
                return urllib.parse.urljoin(
                    base_url,
                    uri,
                )

        return ""

    @classmethod
    def _detect_drm(
        cls,
        text: str,
    ) -> bool:
        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line.upper().startswith(
                (
                    "#EXT-X-KEY:",
                    "#EXT-X-SESSION-KEY:",
                )
            ):
                continue

            attributes = (
                cls._parse_attribute_list(
                    line.split(
                        ":",
                        1,
                    )[1]
                )
            )

            method = attributes.get(
                "METHOD",
                "",
            ).upper()

            keyformat = attributes.get(
                "KEYFORMAT",
                "identity",
            ).casefold()

            if method in {
                "",
                "NONE",
                "AES-128",
            } and keyformat in {
                "",
                "identity",
            }:
                continue

            return True

        return False

    @staticmethod
    def _parse_attribute_list(
        value: str,
    ) -> dict[str, str]:
        result: dict[
            str,
            str,
        ] = {}

        pattern = re.compile(
            r'([A-Za-z0-9-]+)='
            r'("(?:[^"\\]|\\.)*"|[^,]*)'
        )

        for match in pattern.finditer(
            value
        ):
            key = (
                match.group(1)
                .strip()
                .upper()
            )

            raw = (
                match.group(2)
                .strip()
            )

            if (
                len(raw) >= 2
                and raw[0] == '"'
                and raw[-1] == '"'
            ):
                raw = raw[
                    1:-1
                ]

            result[key] = raw

        return result

    @classmethod
    def _is_media_segment(
        cls,
        *,
        url: str,
        content_type: str,
        data: bytes,
    ) -> bool:
        if not data:
            return False

        lowered_type = (
            content_type.casefold()
        )

        stripped = data.lstrip()

        if stripped.startswith(
            (
                b"<html",
                b"<!doctype html",
                b"<?xml",
                b"{",
                b"[",
            )
        ):
            return False

        if b"#EXTM3U" in data.upper():
            return False

        # MPEG-TS: il byte sync compare ogni 188 byte.
        if data[:1] == b"\x47":
            return True

        if (
            len(data) > 188
            and data[188:189]
            == b"\x47"
        ):
            return True

        # ISO BMFF / fragmented MP4.
        if (
            len(data) >= 12
            and data[4:8]
            in {
                b"ftyp",
                b"moof",
                b"styp",
                b"sidx",
                b"mdat",
            }
        ):
            return True

        # AAC ADTS.
        if (
            len(data) >= 2
            and data[0] == 0xFF
            and (
                data[1] & 0xF6
            )
            in {
                0xF0,
                0xF2,
                0xF4,
                0xF6,
            }
        ):
            return True

        if data.startswith(
            (
                b"ID3",
                b"OggS",
                b"\x1aE\xdf\xa3",
            )
        ):
            return True

        if any(
            media_type in lowered_type
            for media_type in (
                cls.SEGMENT_CONTENT_TYPES
            )
        ):
            return True

        path = urllib.parse.urlsplit(
            url
        ).path.casefold()

        expected_extensions = (
            ".ts",
            ".m2ts",
            ".m4s",
            ".mp4",
            ".aac",
            ".mp3",
            ".ac3",
            ".ec3",
            ".webm",
        )

        if (
            path.endswith(
                expected_extensions
            )
            and len(data) >= 64
        ):
            return True

        return False

    @classmethod
    def _codecs_supported(
        cls,
        codecs: str,
    ) -> bool:
        lowered = codecs.casefold()

        return not any(
            marker in lowered
            for marker in (
                cls
                .UNSUPPORTED_TIZEN_CODECS
            )
        )

    @classmethod
    def _variant_rank(
        cls,
        variant: _HLSVariant,
    ) -> tuple[int, int, int]:
        width = 0
        height = 0

        match = re.fullmatch(
            r"(\d+)[xX](\d+)",
            variant.resolution.strip(),
        )

        if match:
            width = cls._safe_int(
                match.group(1)
            )
            height = cls._safe_int(
                match.group(2)
            )

        compatible_resolution = int(
            (
                not width
                or not height
                or (
                    width <= 1920
                    and height <= 1080
                )
            )
        )

        preferred_codec = int(
            (
                not variant.codecs
                or "avc1" in (
                    variant.codecs
                    .casefold()
                )
                or "hvc1" in (
                    variant.codecs
                    .casefold()
                )
                or "hev1" in (
                    variant.codecs
                    .casefold()
                )
            )
        )

        # Preferisce la variante migliore entro 1080p, evitando di
        # selezionare subito bitrate estremi.
        safe_bandwidth = min(
            variant.bandwidth,
            8_000_000,
        )

        return (
            compatible_resolution,
            preferred_codec,
            safe_bandwidth,
        )

    def _country_check(
        self,
        channel: Channel,
    ) -> str:
        if not self.expected_country:
            return "not_configured"

        expected = (
            self.expected_country
        )

        values: list[str] = []

        attributes = getattr(
            channel,
            "attributes",
            {},
        )

        if isinstance(
            attributes,
            dict,
        ):
            for key, value in (
                attributes.items()
            ):
                normalized_key = (
                    str(key)
                    .strip()
                    .casefold()
                )

                if normalized_key in (
                    self.COUNTRY_ATTRIBUTE_KEYS
                ):
                    values.append(
                        str(value)
                    )

        parsed = urllib.parse.urlsplit(
            self._split_url_headers(
                channel.stream_url
            )[0]
        )

        query = urllib.parse.parse_qs(
            parsed.query
        )

        for key, query_values in (
            query.items()
        ):
            if (
                key.casefold()
                not in self.URL_COUNTRY_KEYS
            ):
                continue

            values.extend(
                query_values
            )

        if not values:
            return "unknown"

        tokens: set[str] = set()

        for value in values:
            tokens.update(
                token.upper()
                for token in re.findall(
                    r"[A-Za-z]{2,15}",
                    value,
                )
            )

        aliases = {
            "IT": {
                "IT",
                "ITA",
                "ITALIA",
                "ITALY",
                "EU",
                "EUROPE",
            },
        }

        accepted = aliases.get(
            expected,
            {
                expected,
            },
        )

        if tokens & accepted:
            return "match"

        if tokens:
            return "mismatch"

        return "unknown"

    @classmethod
    def _has_expired_token(
        cls,
        url: str,
    ) -> bool:
        parsed = urllib.parse.urlsplit(
            url
        )

        query = urllib.parse.parse_qs(
            parsed.query
        )

        now = int(
            time.time()
        )

        for key, values in query.items():
            normalized_key = (
                key.casefold()
            )

            if normalized_key in (
                cls.TOKEN_EXPIRY_KEYS
            ):
                for value in values:
                    timestamp = (
                        cls._extract_timestamp(
                            value
                        )
                    )

                    if (
                        timestamp is not None
                        and timestamp
                        < now - 60
                    ):
                        return True

            # Alcuni CDN usano hdnts=exp=...~acl=...~hmac=...
            if normalized_key in {
                "hdnts",
                "hdnea",
                "token",
            }:
                for value in values:
                    match = re.search(
                        r"(?:^|[~|])exp=(\d{9,13})",
                        value,
                        flags=re.IGNORECASE,
                    )

                    if not match:
                        continue

                    timestamp = (
                        cls._extract_timestamp(
                            match.group(1)
                        )
                    )

                    if (
                        timestamp is not None
                        and timestamp
                        < now - 60
                    ):
                        return True

        return False

    @staticmethod
    def _extract_timestamp(
        value: str,
    ) -> int | None:
        match = re.search(
            r"\d{9,13}",
            str(value),
        )

        if not match:
            return None

        try:
            timestamp = int(
                match.group(0)
            )
        except ValueError:
            return None

        if timestamp > 10_000_000_000:
            timestamp //= 1000

        # Intervallo prudente 2000-2100: evita di scambiare ID
        # numerici casuali per una scadenza.
        if not (
            946_684_800
            <= timestamp
            <= 4_102_444_800
        ):
            return None

        return timestamp

    @staticmethod
    def _split_url_headers(
        stream_url: str,
    ) -> tuple[
        str,
        dict[str, str],
    ]:
        value = str(
            stream_url
        ).strip()

        if "|" not in value:
            return value, {}

        url, raw_headers = (
            value.split(
                "|",
                1,
            )
        )

        parsed = urllib.parse.parse_qsl(
            raw_headers,
            keep_blank_values=False,
        )

        headers: dict[
            str,
            str,
        ] = {}

        header_names = {
            "user-agent": "User-Agent",
            "useragent": "User-Agent",
            "referer": "Referer",
            "referrer": "Referer",
            "origin": "Origin",
            "cookie": "Cookie",
        }

        for key, item in parsed:
            normalized = (
                key.strip()
                .casefold()
            )

            canonical = header_names.get(
                normalized
            )

            if canonical and item:
                headers[
                    canonical
                ] = item

        return url.strip(), headers

    @classmethod
    def _assess_deep_direct_payload(
        cls,
        *,
        http_status: int | None,
        content_type: str,
        data: bytes,
    ) -> tuple[str, str, int]:
        if (
            http_status is None
            or not 200 <= http_status < 400
        ):
            return (
                "offline",
                "invalid_http_status",
                0,
            )

        if not data:
            return (
                "offline",
                "empty_payload",
                0,
            )

        lowered_type = (
            content_type.casefold()
        )

        if any(
            item in lowered_type
            for item in (
                cls.SEGMENT_CONTENT_TYPES
            )
        ) and cls._is_media_segment(
            url="",
            content_type=content_type,
            data=data,
        ):
            return (
                "online",
                "direct_media_verified",
                92,
            )

        return (
            "offline",
            "non_media_payload",
            0,
        )

    @classmethod
    def _is_hls_payload(
        cls,
        content_type: str,
        data: bytes,
    ) -> bool:
        text = data.decode(
            "utf-8",
            errors="ignore",
        )

        if "#EXTM3U" in text.upper():
            return True

        lowered_type = (
            content_type.casefold()
        )

        return any(
            item in lowered_type
            for item in (
                cls.MANIFEST_CONTENT_TYPES
            )
        )

    @staticmethod
    def _decode_manifest(
        data: bytes,
    ) -> str:
        return data.decode(
            "utf-8-sig",
            errors="replace",
        )

    @staticmethod
    def _hls_kind(
        text: str,
    ) -> str:
        if "#EXT-X-STREAM-INF:" in (
            text.upper()
        ):
            return "master"

        return "media"

    @classmethod
    def _assess_response(
        cls,
        http_status: int | None,
        content_type: str,
        data: bytes,
    ) -> tuple[str, str, int]:
        if (
            http_status is None
            or not 200 <= http_status < 400
        ):
            return (
                "offline",
                "invalid_http_status",
                0,
            )

        lowered_type = (
            content_type.casefold()
        )

        text = data.decode(
            "utf-8",
            errors="ignore",
        )

        if "#EXTM3U" in text.upper():
            return (
                "online",
                "hls_signature",
                100,
            )

        if any(
            value in lowered_type
            for value in (
                cls.MEDIA_CONTENT_TYPES
            )
        ):
            return (
                "online",
                "media_content_type",
                90,
            )

        if data:
            return (
                "reachable",
                "payload_reachable",
                50,
            )

        return (
            "offline",
            "empty_payload",
            0,
        )

    @classmethod
    def _classify_response(
        cls,
        http_status: int,
        content_type: str,
        data: bytes,
    ) -> str:
        """
        Metodo mantenuto per compatibilità con il vecchio
        Health Engine e con i relativi test.
        """

        status, _, _ = cls._assess_response(
            http_status=http_status,
            content_type=content_type,
            data=data,
        )

        return status

    @staticmethod
    def _calculate_score(
        status: str,
        base_score: int,
        response_ms: int | None,
        redirected: bool,
    ) -> int:
        if (
            status == "offline"
            or base_score <= 0
        ):
            return 0

        latency_penalty = 0

        if response_ms is not None:
            if response_ms > 5000:
                latency_penalty = 25
            elif response_ms > 2500:
                latency_penalty = 18
            elif response_ms > 1500:
                latency_penalty = 12
            elif response_ms > 750:
                latency_penalty = 7
            elif response_ms > 250:
                latency_penalty = 3

        redirect_penalty = (
            2
            if redirected
            else 0
        )

        score = (
            base_score
            - latency_penalty
            - redirect_penalty
        )

        return max(
            1,
            min(
                100,
                score,
            ),
        )

    @staticmethod
    def _error_result(
        channel: Channel,
        started: float,
        http_status: int | None,
        error: str,
        error_type: str = "",
        classification_reason: str = (
            "request_error"
        ),
        final_url: str | None = None,
        country_check: str = "",
    ) -> HealthResult:
        response_ms = (
            StreamHealthChecker._elapsed_ms(
                started
            )
        )

        resolved_final_url = (
            final_url
            or channel.stream_url
        )

        return HealthResult(
            name=channel.name,
            stream_url=channel.stream_url,
            source_id=channel.source_id,
            status="offline",
            http_status=http_status,
            response_ms=response_ms,
            content_type="",
            final_url=resolved_final_url,
            error=error,
            health_score=0,
            classification_reason=(
                classification_reason
            ),
            bytes_read=0,
            redirected=(
                resolved_final_url
                != channel.stream_url
            ),
            error_type=error_type,
            country_check=country_check,
            validation_steps=(
                (
                    classification_reason,
                )
                if classification_reason
                else ()
            ),
        )

    @staticmethod
    def _build_stats(
        input_channels: int,
        results: tuple[
            HealthResult,
            ...,
        ],
    ) -> HealthStats:
        if not results:
            return HealthStats(
                input_channels=(
                    input_channels
                ),
                checked=0,
                online=0,
                reachable=0,
                offline=0,
                redirects=0,
                errors=0,
                average_score=0.0,
                average_response_ms=0.0,
                min_score=0,
                max_score=0,
            )

        scores = [
            result.health_score
            for result in results
        ]

        response_times = [
            result.response_ms
            for result in results
            if result.response_ms is not None
        ]

        average_response_ms = (
            sum(response_times)
            / len(response_times)
            if response_times
            else 0.0
        )

        return HealthStats(
            input_channels=input_channels,
            checked=len(results),
            online=sum(
                1
                for result in results
                if result.status == "online"
            ),
            reachable=sum(
                1
                for result in results
                if result.status
                == "reachable"
            ),
            offline=sum(
                1
                for result in results
                if result.status == "offline"
            ),
            redirects=sum(
                1
                for result in results
                if result.redirected
            ),
            errors=sum(
                1
                for result in results
                if bool(result.error)
                or bool(result.error_type)
            ),
            average_score=(
                sum(scores)
                / len(scores)
            ),
            average_response_ms=(
                average_response_ms
            ),
            min_score=min(scores),
            max_score=max(scores),
        )

    @staticmethod
    def _empty_stats() -> HealthStats:
        return HealthStats(
            input_channels=0,
            checked=0,
            online=0,
            reachable=0,
            offline=0,
            redirects=0,
            errors=0,
            average_score=0.0,
            average_response_ms=0.0,
            min_score=0,
            max_score=0,
        )

    @staticmethod
    def _safe_int(
        value: object,
    ) -> int:
        try:
            return int(
                str(value).strip()
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0

    @staticmethod
    def _elapsed_ms(
        started: float,
    ) -> int:
        return int(
            (
                time.perf_counter()
                - started
            )
            * 1000
        )
