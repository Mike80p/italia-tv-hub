from src.postprocess.m3u_deduper import dedupe_m3u_text


def test_quality_and_source_marker_duplicate():
    text = '''#EXTM3U
#EXTINF:-1 tvg-id="Rai1.it@SD",Rai 1 (720p)
https://a/1
#EXTINF:-1 tvg-id="Rai1.it",Rai 1 G
https://b/1
'''

    out, removed = dedupe_m3u_text(text)

    assert removed == 1
    assert out.count('#EXTINF:') == 1
    assert 'https://a/1' in out


def test_regional_channels_are_not_merged():
    text = '''#EXTM3U
#EXTINF:-1 tvg-id="Rai3TGRPuglia.it",Rai 3 TGR Puglia
https://a/p
#EXTINF:-1 tvg-id="Rai3TGRLazio.it",Rai 3 TGR Lazio
https://a/l
'''

    out, removed = dedupe_m3u_text(text)

    assert removed == 0
    assert out.count('#EXTINF:') == 2


def test_directives_follow_kept_entry():
    text = '''#EXTM3U
#EXTINF:-1 tvg-id="Rai2.it@HD",Rai 2 HD
#EXTVLCOPT:http-user-agent=x
https://a/2
#EXTINF:-1 tvg-id="Rai2.it",Rai 2 G
https://b/2
'''

    out, removed = dedupe_m3u_text(text)

    assert removed == 1
    assert '#EXTVLCOPT:http-user-agent=x' in out


def test_deduper_is_idempotent():
    text = '''#EXTM3U
#EXTINF:-1 tvg-id="Italia1.it@HD",Italia 1 HD
https://a/i
#EXTINF:-1 tvg-id="Italia1.it",Italia 1 G
https://b/i
'''

    once, _ = dedupe_m3u_text(text)
    twice, removed = dedupe_m3u_text(once)

    assert once == twice
    assert removed == 0
