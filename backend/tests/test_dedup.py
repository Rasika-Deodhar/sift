from app.pipeline.dedup import PhashCache, hash_distance, sig_distance


def test_hash_distance():
    assert hash_distance("00", "00") == 0
    assert hash_distance("00", "ff") == 1
    assert hash_distance("0f", "00") == 0.5
    assert hash_distance("00", "000") == 1.0
    assert hash_distance("zz", "00") == 1.0


def test_near_match_hits_and_far_misses():
    c: PhashCache[str] = PhashCache(max_distance=0.05)
    base = "0" * 64  # 256 bits
    c.put(base, "item1", "card1")
    near = "1" + "0" * 63  # 1 bit different
    far = "f" * 16 + "0" * 48
    assert c.lookup(near) == ("item1", "card1")
    assert c.lookup(far) is None
    assert (c.hits, c.misses) == (1, 1)


def test_closest_match_wins_and_lru_evicts():
    c: PhashCache[int] = PhashCache(max_distance=0.1, capacity=2)
    c.put("0000", "a", 1)
    c.put("0001", "b", 2)
    assert c.lookup("0001") == ("b", 2)
    c.put("ffff", "c", 3)  # evicts least recently used ("0000")
    assert len(c) == 2
    assert c.lookup("0000") == ("b", 2)  # only the near one is left


def test_color_signature_must_match_when_present():
    c: PhashCache[str] = PhashCache(max_distance=0.05, max_sig_distance=3)
    c.put("0" * 64, "green", "card", sig="1f6f5c" * 4)
    assert c.lookup("0" * 64, sig="8a3b12" * 4) is None  # same layout, different colors
    assert c.lookup("0" * 64, sig="206e5c" * 4) == ("green", "card")
    assert c.lookup("0" * 64) == ("green", "card")  # no signature: hash only
    assert sig_distance("00ff", "00fe") == 0.5
    assert sig_distance("00", "0000") == 255.0
